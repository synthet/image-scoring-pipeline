# Model Input Specifications

This document describes the input format, score ranges, and constraints for the neural network models used in the Image Scoring project.

## Overview

| Model Family | Models | Framework | Input Type |
|-------------|--------|-----------|------------|
| MUSIQ | SPAQ, AVA, KonIQ, PaQ2PiQ | TensorFlow | JPEG bytes |
| LIQE | LIQE | PyTorch (PyIQA) | PIL Image tensor |

---

## 1. MUSIQ Models (SPAQ, AVA, KonIQ, PaQ2PiQ)

**Reference:** [MUSIQ: Multi-scale Image Quality Transformer (arxiv.org/abs/2108.05997)](https://arxiv.org/abs/2108.05997)

### Input Format

- **Type:** Raw JPEG bytes (TensorFlow Hub `image_bytes_tensor`)
- **Parameter name:** `image_bytes_tensor` (MUSIQ) or `image_bytes` (VILA)
- **Preprocessing:** None required. The model handles variable sizes and aspect ratios internally.

### Documentation

- MUSIQ is designed to process **native resolution images with varying sizes and aspect ratios**
- No fixed-shape constraint; avoids CNN-style resize/crop that degrades quality
- Multi-scale patch-based Transformer with hash-based 2D spatial embedding

### Model Score Ranges (Raw Output)

| Model | Raw Range | Source | Notes |
|-------|-----------|--------|-------|
| SPAQ | 0–100 | SPAQ dataset | |
| AVA | 1–10 | AVA dataset | |
| KonIQ | 0–100 | KONIQ-10k | |
| PaQ2PiQ | 0–100 | PAQ2PIQ | |

**Normalization:** `(score - min) / (max - min)` → 0–1 for weighted scoring.

### Source Variability

Different sources (TensorFlow Hub, Kaggle Hub, local .npz) may produce slightly different raw ranges. Normalization must be applied per-source. The project uses `model_ranges` in `run_all_musiq_models.py` for consistent 0–1 mapping.

---

## 2. LIQE Model

**Reference:** [LIQE: Blind Image Quality Assessment via Vision-Language Correspondence (CVPR 2023)](https://github.com/zwx8981/LIQE)

### Input Format

- **Type:** Tensor from PIL Image (via PyIQA)
- **PIL mode:** RGB
- **Resize rule:** If `max(img.size) > 518`, resize to 518px on longest edge (BICUBIC). High-resolution images left unscaled can produce incorrect "noise" scores (~1.0).

### Score Range

- **Raw range:** 1.0–5.0
- **Normalization:** `(score - 1) / 4` → 0–1

### Implementation

See `modules/liqe.py` for the current implementation, including the 518px downscale logic.

---

## 3. Database Storage

From `DB_SCHEMA.md`:

| Column | Stored Value | Note |
|--------|--------------|------|
| `score_general` | 0–1 | Normalized weighted score |
| `score_technical` | 0–1 | Normalized weighted score |
| `score_aesthetic` | 0–1 | Normalized weighted score |
| `score_spaq` | Normalized 0–1 | From `get_ind_score` → `normalized_score` |
| `score_ava` | Normalized 0–1 | Same |
| `score_koniq` | Normalized 0–1 | Same |
| `score_paq2piq` | Normalized 0–1 | Same |
| `score_liqe` | Normalized 0–1 | Same |

---

## 4. NEF Conversion to Model Input

For RAW files (NEF, etc.), the pipeline converts to JPEG before feeding to models. See [RAW_PROCESSING_GUIDE.md](RAW_PROCESSING_GUIDE.md) for conversion methods and [scripts/research_models.py](../../scripts/research_models.py) for the assessment of optimal input parameters.
