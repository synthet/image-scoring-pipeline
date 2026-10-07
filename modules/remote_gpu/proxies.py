"""Remote stand-ins for the GPU model classes the runners already use.

Each proxy subclasses (or mirrors) the local model and overrides only the method
that touches the GPU, so the runner code around it stays identical in both
modes: the host still preprocesses, checks idempotency, persists and writes XMP.
Construction is the only branch point; see the ``new_*`` factories in each runner.
"""

from __future__ import annotations

import logging
import base64
import math
import os
from typing import Any

from modules.bird_detection import BirdDetector
from modules.bird_species import BioCLIPClassifier
from modules.engines.host import MultiModelHost
from modules.remote_gpu.client import GpuRunnerClient, ready_client
from modules.remote_gpu.contract import (
    ACCESSIBILITY,
    BIOCLIP,
    CAPTION,
    DETECT,
    EMBEDDING,
    KEYWORDS,
    SCENE,
    SCORING,
    SCORING_INPUTS_VERSION,
    RemoteGpuError,
    as_vector,
    encode_array,
    encode_png,
)
from modules.scene_route import PROMPT_SET_VERSION, SceneClassifier, score
from modules.scoring_inputs import validate_input
from modules.tagging import CaptionGenerator, KeywordScorer

logger = logging.getLogger(__name__)


def _validate_scoring_result(result: dict[str, Any]) -> None:
    """Reject corrupt output before it can be persisted as completed scoring."""
    models, summary = result.get("models"), result.get("summary")
    if not isinstance(models, dict) or not models or not isinstance(summary, dict):
        raise RemoteGpuError("GPU runner returned an invalid scoring result")
    total = summary.get("total_models")
    if type(total) is not int or total <= 0 or total != len(models):
        raise RemoteGpuError("GPU runner scoring result contains no models")
    for counter in ("successful_predictions", "failed_predictions"):
        value = summary.get(counter)
        if type(value) is not int or not 0 <= value <= total:
            raise RemoteGpuError(f"GPU runner scoring result has an invalid {counter}")
    successful = 0
    for name, payload in models.items():
        if not isinstance(payload, dict):
            raise RemoteGpuError(f"GPU runner scoring result has invalid model {name}")
        if payload.get("status") == "success":
            score_value = payload.get("normalized_score")
            if type(score_value) not in (int, float) or not math.isfinite(score_value):
                raise RemoteGpuError(f"GPU runner scoring result has invalid score for {name}")
            successful += 1
    if summary["successful_predictions"] != successful or summary["failed_predictions"] != total - successful:
        raise RemoteGpuError("GPU runner scoring result has inconsistent prediction counts")


def _read(path: str) -> tuple[bytes, str]:
    with open(path, "rb") as handle:
        return handle.read(), os.path.basename(path) or "input.bin"


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

class RemoteScoringHost(MultiModelHost):
    """``MultiModelHost`` whose model inference runs on the GPU runner.

    The CPU backend stays local for RAW conversion and ``preprocess_image``, and the
    registry stays local so ``ScoringWorker`` sees the same active models (and does
    not run LIQE or registry models itself). Only ``run_all_models`` goes remote.
    """

    runs_remotely = True

    def __init__(self, client: GpuRunnerClient, backend: Any, registry: Any) -> None:
        super().__init__(backend=backend, registry=registry)
        self._client = client

    def run_all_models(
        self,
        image_path: str,
        external_scores: dict[str, Any] | None = None,
        logger=print,
        write_metadata: bool = True,
        model_inputs: dict[str, dict] | None = None,
    ) -> dict[str, Any]:
        is_raw = self.is_raw_file(image_path)
        processing_path = self._resolve_processing_path(image_path, is_raw, logger,
                                                       prepared=model_inputs is not None)
        if processing_path is None:
            return self._raw_failure_result(image_path, is_raw=is_raw)

        data, filename = _read(processing_path)
        # Private host paths are transport metadata, never model scores.
        params = {"external_scores": {key: value for key, value in (external_scores or {}).items()
                                      if not key.startswith("_")}}
        if model_inputs is not None:
            for model in self.registry.all_active():
                if model.name not in params["external_scores"] and model.name not in model_inputs:
                    raise ValueError(f"Missing prepared input for {model.name}")
            params["scoring_inputs_version"] = SCORING_INPUTS_VERSION
            params["model_inputs"] = {}
            for name, spec in model_inputs.items():
                validate_input(spec)
                contents, _ = _read(spec["path"])
                params["model_inputs"][name] = {
                    "data": base64.b64encode(contents).decode("ascii"),
                    "metadata": spec["metadata"],
                }
        results = self._client.call(SCORING, params, data, filename=filename)
        _validate_scoring_result(results)
        if model_inputs is not None:
            for name, spec in model_inputs.items():
                if name in params["external_scores"]:
                    continue
                if (results["models"].get(name) or {}).get("input") != spec["metadata"]:
                    raise RemoteGpuError(f"GPU runner did not attest selected input for {name}")
        # The runner scored a temp copy; report the host's paths, as a local run would.
        identity = self._init_result(image_path, is_raw, processing_path, [])
        results.pop("raw_conversion", None)
        for key in ("image_path", "image_name", "raw_conversion"):
            if key in identity:
                results[key] = identity[key]
        logger(f"  Scored on GPU runner ({len(results.get('models') or {})} models)")

        avg = (results.get("summary") or {}).get("average_normalized_score")
        if write_metadata and avg is not None:
            normalized = {
                name: float(payload["normalized_score"])
                for name, payload in (results.get("models") or {}).items()
                if isinstance(payload, dict)
                and payload.get("status") == "success"
                and not payload.get("is_shadow")
                and payload.get("normalized_score") is not None
            }
            self._write_nef_metadata(results, normalized, image_path, avg)
        return results


def create_remote_scoring_host() -> RemoteScoringHost:
    """Scoring host for ``gpu_runner.phases.scoring = remote``. Raises RemoteGpuError when not ready."""
    from modules.engines.factory import ensure_production_registry
    from modules.engines.registry import ModelRegistry
    from scripts.python.run_all_musiq_models import MultiModelMUSIQ

    client = ready_client("scoring")
    backend = MultiModelMUSIQ(skip_gpu=True)
    # A private registry: the process-wide one keeps the GPU-backed wrappers a local run registers.
    registry = ensure_production_registry(backend, registry=ModelRegistry())
    return RemoteScoringHost(client, backend, registry)


# ---------------------------------------------------------------------------
# Keywords
# ---------------------------------------------------------------------------

class RemoteKeywordScorer(KeywordScorer):
    """``KeywordScorer`` (same ``model_name`` resolution) that predicts on the runner."""

    runs_remotely = True

    def __init__(self, client: GpuRunnerClient, model_name: str | None = None) -> None:
        super().__init__(model_name=model_name, device="cpu")
        self._client = client

    def load_model(self):
        """Models live on the runner; readiness was checked when the client was built."""

    def rank_accessibility(self, image_path, prompts, image_embedding=None):
        """Run both CLIP towers remotely, including the stored-embedding path."""
        data, filename = (None, "input.bin") if image_embedding is not None else _read(image_path)
        out = self._client.call(
            ACCESSIBILITY, {"prompts": list(prompts), "image_embedding": image_embedding},
            data, filename=filename,
        )
        embedding = as_vector(out.get("image_embedding"))
        ranked = [(str(prompt), float(value)) for prompt, value in out.get("ranked") or []]
        return embedding, ranked

    def predict(
        self,
        image_path: str,
        keywords: list[str] = None,
        threshold: float = 0.2,
        top_k: int = 5,
        return_scores: bool = False,
        image_embedding=None,
    ):
        self.last_image_embedding = None
        data, filename = _read(image_path)
        out = self._client.call(
            KEYWORDS,
            {
                "keywords": list(keywords) if keywords else None,
                "threshold": threshold,
                "top_k": top_k,
                "image_embedding": image_embedding,
            },
            data,
            filename=filename,
        )
        self.last_image_embedding = as_vector(out.get("last_image_embedding"))
        tags = list(out.get("keywords") or [])
        if return_scores:
            return tags, dict(out.get("confidence_map") or {}), dict(out.get("relevance_map") or {})
        return tags


class RemoteCaptionGenerator(CaptionGenerator):
    """``CaptionGenerator`` that captions on the runner."""

    runs_remotely = True

    def __init__(self, client: GpuRunnerClient) -> None:
        super().__init__(device="cpu")
        self._client = client

    def load_model(self):
        """Models live on the runner."""

    def generate(self, image_path: str, extract_embedding: bool = False) -> str:
        self.last_image_embedding = None
        data, filename = _read(image_path)
        out = self._client.call(CAPTION, {"extract_embedding": bool(extract_embedding)}, data, filename=filename)
        self.last_image_embedding = as_vector(out.get("last_image_embedding"))
        return str(out.get("caption") or "")


# ---------------------------------------------------------------------------
# Culling embeddings
# ---------------------------------------------------------------------------

class RemoteEmbeddingModel:
    """Stands in for the Keras MobileNetV2 in ``ClusteringEngine``: ``predict(batch, verbose=0)``."""

    runs_remotely = True

    def __init__(self, client: GpuRunnerClient) -> None:
        self._client = client

    def predict(self, batch, verbose: int = 0):
        import numpy as np

        out = self._client.call(EMBEDDING, {}, encode_array(np.asarray(batch, dtype=np.float32)), filename="batch.npy")
        return np.asarray(out.get("vectors") or [], dtype=np.float32)


# ---------------------------------------------------------------------------
# Bird detector (localization and the bird-box rescan)
# ---------------------------------------------------------------------------

class RemoteBirdDetector(BirdDetector):
    """``BirdDetector`` whose YOLO forward pass runs on the runner.

    Ranking, validation, best-box selection and cropping are inherited, so boxes
    are post-processed on the host exactly as in a local run.
    """

    runs_remotely = True

    def __init__(self, client: GpuRunnerClient, config: dict | None = None) -> None:
        super().__init__(config=config, device="cpu")
        self._client = client

    def load_model(self) -> None:
        """Weights live on the runner."""

    def remote_weights_sha256(self) -> str:
        """SHA-256 of the runner's weights, so ``detector_config_hash`` matches a local run."""
        info = self._client.detector_info()
        if info.get("load_error"):
            raise RemoteGpuError(str(info["load_error"]))
        digest = info.get("weights_sha256")
        if not digest:
            raise RemoteGpuError("GPU runner did not report detector weights")
        return str(digest)

    def _predict_raw_boxes(self, image) -> list[dict]:
        out = self._client.call(
            DETECT,
            {"conf": self.confidence, "imgsz": self.imgsz, "max_det": self.max_det},
            encode_png(image),
            filename="image.png",
            content_type="image/png",
        )
        return [
            {"xyxy": tuple(float(v) for v in box["xyxy"]), "conf": float(box["conf"])}
            for box in out.get("boxes") or []
        ]


class RemoteSceneClassifier(SceneClassifier):
    """``SceneClassifier`` whose image and text towers run on the runner.

    The runner returns the image embedding and label features; the host scores
    them with the same ``score`` a local run uses, after checking that both sides
    have the same prompt set.
    """

    runs_remotely = True

    def __init__(self, client: GpuRunnerClient, backend: str = "hf_clip_b32",
                 prompt_set: str = PROMPT_SET_VERSION) -> None:
        super().__init__(backend, device="cpu", prompt_set=prompt_set)
        self._client = client
        self._prompt_set = prompt_set

    def load(self) -> None:
        """Models live on the runner."""

    def classify(self, image):
        import numpy as np

        out = self._client.call(
            SCENE,
            {"backend": self.backend, "prompt_set": self._prompt_set},
            encode_png(image),
            filename="image.png",
            content_type="image/png",
        )
        if out.get("version") != self.version:
            raise RemoteGpuError(
                f"GPU runner scene version {out.get('version')!r} differs from this host's {self.version!r}"
            )
        feat = np.asarray(out["image_feat"], dtype=np.float32)
        self.last_embedding = feat.reshape(-1) / float((feat ** 2).sum() ** 0.5)
        return score(feat, out["label_feats"], self.labels, float(out["logit_scale"]), self.version)


# ---------------------------------------------------------------------------
# Bird species
# ---------------------------------------------------------------------------

class RemoteBioCLIPClassifier(BioCLIPClassifier):
    """``BioCLIPClassifier`` whose classify runs on the runner.

    The host decodes the image (``open_oriented_for_ml``, as ``classify`` does) and
    sends the upright pixels losslessly, so RAW files never cross the network and
    ``last_bbox`` is in the same display space as a local run.
    """

    runs_remotely = True

    def __init__(self, client: GpuRunnerClient) -> None:
        super().__init__(device="cpu")
        self._client = client

    def load_model(self):
        """Models live on the runner."""

    def _ensure_detector(self):
        if self._detector_state == "enabled":
            return self.detector
        if self._detector_state == "disabled":
            return None
        detector = RemoteBirdDetector(self._client)
        if not detector.enabled:
            logger.info("Bird detector disabled via config; classifying whole images.")
            self._detector_state = "disabled"
            return None
        self.detector = detector
        self._detector_state = "enabled"
        return detector

    def classify(
        self,
        image_path: str,
        candidate_species: list[str],
        threshold: float = 0.1,
        top_k: int = 1,
        region: tuple[float, float, float, float] | None = None,
        use_detector: bool = True,
    ) -> list[tuple[str, float]]:
        from modules.thumbnails import open_oriented_for_ml

        self.last_image_embedding = None
        self.last_bbox = None
        try:
            img = open_oriented_for_ml(image_path)
        except Exception as exc:  # noqa: BLE001 — same outcome as a local decode failure
            logger.error("BioCLIP classify error for %s: %s", image_path, exc)
            return []
        out = self._client.call(
            BIOCLIP,
            {
                "candidate_species": list(candidate_species),
                "threshold": threshold,
                "top_k": top_k,
                "region": list(region) if region is not None else None,
                "use_detector": bool(use_detector),
            },
            encode_png(img),
            filename="image.png",
            content_type="image/png",
        )
        self.last_bbox = out.get("last_bbox")
        self.last_image_embedding = as_vector(out.get("last_image_embedding"))
        return [(str(name), float(prob)) for name, prob in out.get("predictions") or []]
