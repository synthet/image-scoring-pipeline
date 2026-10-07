"""Model-method execution shared by the HTTP worker and embedded fallback."""

from __future__ import annotations

import logging
import base64
import os
import tempfile
import threading
from contextlib import contextmanager, ExitStack

from modules.remote_gpu.contract import (
    ACCESSIBILITY, BIOCLIP, CAPTION, DETECT, DETECTOR_INFO, EMBEDDING, KEYWORDS,
    SCENE, SCORING, SCORING_INPUTS_VERSION, RemoteGpuError, as_vector, decode_array, decode_png,
)
from modules.scoring_inputs import validate_input

logger = logging.getLogger(__name__)


@contextmanager
def _input_file(data: bytes, filename: str):
    suffix = os.path.splitext(filename or "")[1].lower()
    if not suffix[1:].isalnum() or len(suffix) > 9:
        suffix = ".bin"
    fd, path = tempfile.mkstemp(prefix="gpu-runner-", suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        yield path
    finally:
        try:
            os.remove(path)
        except OSError:
            logger.debug("gpu_runner: temp cleanup failed for %s", path, exc_info=True)


class InferenceRuntime:
    """Cache models and serialize execution; never persist DB or XMP results."""

    def __init__(self, provider=None):
        if provider is None:
            from modules.remote_gpu.server import ModelProvider

            provider = ModelProvider()
        self.provider = provider
        self._lock = threading.Lock()

    def execute(self, endpoint: str, params: dict, data: bytes | None = None, *, filename="input.bin"):
        from modules.remote_gpu.client import local_inference

        with self._lock, local_inference():
            if endpoint == DETECTOR_INFO:
                return self.provider.detector_info()
            if endpoint == ACCESSIBILITY and params.get("image_embedding") is not None:
                return self._accessibility(params)
            if data is None:
                raise RemoteGpuError(f"GPU runner {endpoint} requires input data")
            if endpoint == EMBEDDING:
                return {"vectors": self.provider.embedding_model().predict(decode_array(data), verbose=0)}
            if endpoint == DETECT:
                detector = self.provider.bird_detector()
                detector.confidence = float(params["conf"])
                detector.imgsz = int(params["imgsz"])
                detector.max_det = int(params["max_det"])
                return {"boxes": detector._predict_raw_boxes(decode_png(data))}
            if endpoint == SCENE:
                classifier = self.provider.scene_classifier(str(params["backend"]), str(params["prompt_set"]))
                classifier.classify(decode_png(data))
                return {"version": classifier.version, "image_feat": classifier.last_embedding,
                        "label_feats": classifier._label_feats, "logit_scale": classifier._logit_scale}
            with _input_file(data, filename) as path:
                if endpoint == SCORING:
                    with ExitStack() as stack:
                        options = {}
                        if params.get("model_inputs") is not None:
                            if params.get("scoring_inputs_version") != SCORING_INPUTS_VERSION:
                                raise RemoteGpuError("Unsupported scoring input bundle version")
                            bundle = params["model_inputs"]
                            if not isinstance(bundle, dict):
                                raise RemoteGpuError("Invalid scoring input bundle")
                            inputs = {}
                            # Decode and validate the whole bundle before loading models.
                            for name, wire in bundle.items():
                                contents = base64.b64decode(wire["data"], validate=True)
                                input_path = stack.enter_context(_input_file(contents, "prepared.jpg"))
                                spec = {"path": input_path, "metadata": wire["metadata"]}
                                validate_input(spec)
                                inputs[name] = spec
                            options["model_inputs"] = inputs
                        return self.provider.scoring_host().run_all_models(
                            path, external_scores=params.get("external_scores") or None,
                            logger=lambda msg: logger.debug("gpu_runner scoring: %s", msg),
                            write_metadata=False, **options,
                        )
                if endpoint == KEYWORDS:
                    scorer = self.provider.keyword_scorer()
                    tags, confidence, relevance = scorer.predict(
                        path, keywords=params.get("keywords"), threshold=float(params.get("threshold", 0.2)),
                        top_k=int(params.get("top_k", 5)), return_scores=True,
                        image_embedding=as_vector(params.get("image_embedding")),
                    )
                    return {"keywords": tags, "confidence_map": confidence, "relevance_map": relevance,
                            "last_image_embedding": scorer.last_image_embedding}
                if endpoint == CAPTION:
                    captioner = self.provider.captioner()
                    caption = captioner.generate(path, extract_embedding=bool(params.get("extract_embedding")))
                    return {"caption": caption, "last_image_embedding": captioner.last_image_embedding}
                if endpoint == ACCESSIBILITY:
                    return self._accessibility(params, path)
                if endpoint == BIOCLIP:
                    classifier = self.provider.bioclip()
                    region = params.get("region")
                    predictions = classifier.classify(
                        path, list(params.get("candidate_species") or []),
                        threshold=float(params.get("threshold", 0.1)), top_k=int(params.get("top_k", 1)),
                        region=tuple(region) if region is not None else None,
                        use_detector=bool(params.get("use_detector", True)),
                    )
                    return {"predictions": [[name, prob] for name, prob in predictions],
                            "last_bbox": classifier.last_bbox, "last_image_embedding": classifier.last_image_embedding}
            raise RemoteGpuError(f"Unknown GPU runner endpoint: {endpoint}")

    def _accessibility(self, params, path=None):
        from modules.clip_accessibility import _rank_prompts_from_image_path

        scorer = self.provider.keyword_scorer()
        prompts = params["prompts"]
        if params.get("image_embedding") is not None:
            scorer.load_model()
            _, cosines, embedding = scorer._score_prompts_from_embedding(params["image_embedding"], prompts)
            ranked = sorted(zip(prompts, cosines), key=lambda item: item[1], reverse=True)
        else:
            embedding, ranked = _rank_prompts_from_image_path(path, prompts, scorer=scorer)
        return {"image_embedding": embedding, "ranked": ranked}
