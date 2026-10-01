"""Scene route: zero-shot scene classification ahead of localization (spec 05, #412).

Each image is classified on the orientation-correct localization rendition (not the stored CLIP
vectors, which are sideways for portrait RAWs, #418). The scene picks which per-class detectors
run; with no detector, no box or no usable crop, consumers fall back to the full frame.

Probabilities are a softmax over the label set at the model's logit scale; raw per-label cosines
are kept too, because calibrated per-label thresholds beat softmax selection when sibling labels
absorb mass (the #420 keyword finding).
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

PROMPT_SET_VERSION = "scene_v2"

#: Major classes follow the library's keyword frequencies (2026-10-01 survey, exclusive by subject
#: priority): bird 51%, other animal 8%, urban/architecture 7%, landscape 6%, insect 6%, people 4%,
#: vehicles 3%, plants/flowers 3%. Reptiles and amphibians have no keyword and sit in other_animal.
LABELS: dict[str, tuple[str, ...]] = {
    "wildlife_bird": (
        "a photo of a bird",
        "a wildlife photograph of a bird",
        "a bird perched on a branch",
        "a bird in flight",
        "a small bird in the distance",
    ),
    "other_animal": (
        "a photo of a wild mammal",
        "a wildlife photograph of a deer, fox, squirrel or rabbit",
        "a photo of a horse, dog or cat",
        "a photo of a lizard, snake, frog or turtle",
        "an animal grazing in a field",
    ),
    "wildlife_insect": (
        "a macro photo of an insect",
        "a close-up photo of a butterfly or dragonfly",
        "a macro photograph of a bee on a flower",
        "a macro photo of a spider",
    ),
    "people": (
        "a photo of a person",
        "a portrait photograph",
        "a group of people",
        "a street photo with people",
    ),
    "urban_architecture": (
        "a photo of a building",
        "an architecture photograph",
        "a photo of a city street",
        "a cityscape",
        "a photo of an interior room",
    ),
    "landscape": (
        "a landscape photograph",
        "a photo of mountains and sky",
        "a photo of a lake, river or sea",
        "a photo of a forest or field",
        "a sunset over the water",
        "an aerial photo of the land",
    ),
    "vehicles": (
        "a photo of a car",
        "a photo of an airplane",
        "a photo of a train or bus",
        "a photo of a boat",
    ),
    "plants_flowers": (
        "a close-up photo of a flower",
        "a photo of a plant",
        "a macro photo of leaves",
    ),
    "other": (
        "a photo of an object",
        "a photo of food",
        "an abstract photo",
        "a photo taken at night",
    ),
}

#: Scene label -> ``localization.detectors`` keys. Labels absent here have no detector yet:
#: their images keep the full frame.
ROUTES: dict[str, tuple[str, ...]] = {
    "wildlife_bird": ("bird",),
}

BACKENDS: dict[str, dict[str, str]] = {
    "hf_clip_b32": {"loader": "hf_clip", "model": "openai/clip-vit-base-patch32"},
    "openclip_b32_laion": {"loader": "open_clip", "model": "ViT-B-32", "pretrained": "laion2b_s34b_b79k"},
    "openclip_l14": {"loader": "open_clip", "model": "ViT-L-14", "pretrained": "laion2b_s32b_b82k"},
    "siglip2_base": {"loader": "hf_siglip", "model": "google/siglip2-base-patch16-224"},
}


def prompt_set_hash(backend: str, labels: dict[str, tuple[str, ...]] = LABELS) -> str:
    """Identity of a classification: prompt-set version, every prompt, and the model."""
    blob = json.dumps({"version": PROMPT_SET_VERSION, "backend": BACKENDS[backend], "labels": labels},
                      sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class SceneResult:
    probs: dict[str, float]
    cosines: dict[str, float]
    top_label: str
    top_prob: float
    version: str


def label_text_features(prompt_feats, counts: list[int]):
    """Mean of each label's L2-normalized prompt embeddings, re-normalized: ``(L, d)``."""
    import numpy as np

    feats = np.asarray(prompt_feats, dtype=np.float64)
    feats = feats / np.linalg.norm(feats, axis=1, keepdims=True)
    out, start = [], 0
    for n in counts:
        mean = feats[start:start + n].mean(axis=0)
        out.append(mean / np.linalg.norm(mean))
        start += n
    return np.stack(out)


def score(image_feat, label_feats, labels: list[str], logit_scale: float, version: str) -> SceneResult:
    """Cosine per label, softmax at ``logit_scale``, top label."""
    import numpy as np

    emb = np.asarray(image_feat, dtype=np.float64).reshape(-1)
    emb = emb / np.linalg.norm(emb)
    cos = np.asarray(label_feats, dtype=np.float64) @ emb
    logits = cos * logit_scale
    e = np.exp(logits - logits.max())
    probs = e / e.sum()
    top = int(np.argmax(probs))
    return SceneResult(
        probs={lab: round(float(p), 6) for lab, p in zip(labels, probs)},
        cosines={lab: round(float(c), 6) for lab, c in zip(labels, cos)},
        top_label=labels[top], top_prob=round(float(probs[top]), 6), version=version)


def detectors_to_run(result: SceneResult, thresholds: dict[str, float]) -> list[str]:
    """Detectors whose label probability reaches its calibrated run threshold (multi-label).

    A label without a threshold never triggers its detector, so routing stays opt-in per class.
    """
    keys: list[str] = []
    for label, detectors in ROUTES.items():
        threshold = thresholds.get(label)
        if threshold is not None and result.probs.get(label, 0.0) >= threshold:
            keys.extend(d for d in detectors if d not in keys)
    return keys


_UPSERT_SQL = """
    INSERT INTO image_scene_labels (image_id, scene_version, backend, top_label, top_prob,
                                    probs, cosines, rendition_hash, job_id)
    VALUES (?, ?, ?, ?, ?, ?::jsonb, ?::jsonb, ?, ?)
    ON CONFLICT (image_id, scene_version) DO UPDATE SET
        top_label = EXCLUDED.top_label, top_prob = EXCLUDED.top_prob, probs = EXCLUDED.probs,
        cosines = EXCLUDED.cosines, rendition_hash = EXCLUDED.rendition_hash,
        job_id = EXCLUDED.job_id, updated_at = CURRENT_TIMESTAMP
"""


def save_scene_label(image_id: int, result: SceneResult, *, backend: str,
                     rendition_hash: str | None = None, job_id: int | None = None) -> None:
    """Persist one resolved scene classification (AC-5); re-classifying the same version replaces it."""
    from modules import db

    db.get_connector().execute(_UPSERT_SQL, (
        int(image_id), result.version, backend, result.top_label, result.top_prob,
        json.dumps(result.probs, sort_keys=True), json.dumps(result.cosines, sort_keys=True),
        rendition_hash, job_id,
    ))


def get_scene_label(image_id: int, scene_version: str) -> dict | None:
    from modules import db

    return db.get_connector().query_one(
        "SELECT * FROM image_scene_labels WHERE image_id = ? AND scene_version = ?",
        (int(image_id), scene_version))


def _features(out, embeds_attr: str):
    """Tensor from ``get_*_features``; newer transformers return an output object (as in clip_accessibility)."""
    if hasattr(out, "cpu"):
        return out
    feats = getattr(out, embeds_attr, None)
    return feats if feats is not None else out.pooler_output


class SceneClassifier:
    """Zero-shot classifier with the image and text towers of one model (never mixed)."""

    def __init__(self, backend: str = "hf_clip_b32", device: str | None = None):
        if backend not in BACKENDS:
            raise ValueError(f"unknown scene_route backend: {backend}")
        self.backend = backend
        self.device = device
        self.labels = list(LABELS)
        self.version = f"{PROMPT_SET_VERSION}/{backend}/{prompt_set_hash(backend)}"
        self._model: Any = None
        self._encode_image: Any = None
        self._label_feats = None
        self._logit_scale = 1.0
        #: L2-normalized image embedding from the last ``classify`` call (benchmark linear probes).
        self.last_embedding = None

    def load(self) -> None:
        if self._model is not None:
            return
        import torch

        device = self.device or ("cuda" if torch.cuda.is_available() else "cpu")
        spec = BACKENDS[self.backend]
        prompts = [p for lab in self.labels for p in LABELS[lab]]
        counts = [len(LABELS[lab]) for lab in self.labels]
        logger.info("scene_route: loading %s (%s) on %s", self.backend, spec["model"], device)
        with torch.no_grad():
            if spec["loader"] == "hf_clip":
                from transformers import CLIPModel, CLIPProcessor

                model = CLIPModel.from_pretrained(spec["model"]).to(device).eval()
                processor = CLIPProcessor.from_pretrained(spec["model"])
                text = processor(text=prompts, return_tensors="pt", padding=True)
                text_feats = _features(model.get_text_features(**{k: v.to(device) for k, v in text.items()}),
                                       "text_embeds")

                def encode_image(img):
                    pixels = processor(images=img, return_tensors="pt")["pixel_values"].to(device)
                    return _features(model.get_image_features(pixel_values=pixels), "image_embeds")
            elif spec["loader"] == "hf_siglip":
                from transformers import AutoModel, AutoProcessor

                model = AutoModel.from_pretrained(spec["model"]).to(device).eval()
                processor = AutoProcessor.from_pretrained(spec["model"])
                # SigLIP was trained on max_length-padded text; shorter padding degrades it.
                text = processor(text=prompts, return_tensors="pt", padding="max_length", max_length=64)
                text_feats = _features(model.get_text_features(**{k: v.to(device) for k, v in text.items()}),
                                       "text_embeds")

                def encode_image(img):
                    pixels = processor(images=img, return_tensors="pt")["pixel_values"].to(device)
                    return _features(model.get_image_features(pixel_values=pixels), "image_embeds")
            else:
                import open_clip

                model, _, preprocess = open_clip.create_model_and_transforms(
                    spec["model"], pretrained=spec["pretrained"])
                model = model.to(device).eval()
                tokenizer = open_clip.get_tokenizer(spec["model"])
                text_feats = model.encode_text(tokenizer(prompts).to(device))

                def encode_image(img):
                    return model.encode_image(preprocess(img).unsqueeze(0).to(device))

        self._label_feats = label_text_features(text_feats.float().cpu().numpy(), counts)
        try:
            self._logit_scale = float(model.logit_scale.exp().item())
        except Exception:  # noqa: BLE001 — fall back to no rescale, as KeywordScorer does
            self._logit_scale = 1.0
        self._encode_image = encode_image
        self._model = model

    def classify(self, image) -> SceneResult:
        """Classify an RGB PIL image (the display-oriented localization rendition)."""
        import torch

        self.load()
        with torch.no_grad():
            feat = self._encode_image(image.convert("RGB")).float().cpu().numpy()
        self.last_embedding = feat.reshape(-1) / float((feat ** 2).sum() ** 0.5)
        return score(feat, self._label_feats, self.labels, self._logit_scale, self.version)
