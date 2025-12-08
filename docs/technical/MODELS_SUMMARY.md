# Model Summary

This project uses a hybrid ensemble of models to assess image quality from multiple perspectives.

## 1. Google MUSIQ (Multi-scale Image Quality Transformer)
*TensorFlow Implementation*

The backbone of the scoring system. Processing multi-scale inputs to capture global and local details.

| Variant | Dataset | Range | Role |
|---------|---------|-------|------|
| **KONIQ** | KonIQ-10k | 0-100 | **Reliability**. Large dataset of in-the-wild images. |
| **SPAQ** | SPAQ | 0-100 | **Discrimination**. Smartphone photography dataset. |
| **PAQ2PIQ**| PaQ-2-PiQ | 0-100 | **Detail**. Massive dataset, good for artifacts. |
| **AVA** | AVA | 1-10 | **Legacy Aesthetic**. Professional curation dataset. |

## 2. LIQE (Language-Image Quality Evaluator)
*PyTorch Implementation*

**Status: Active (15% Weight)**
A state-of-the-art model (2023) that uses CLIP (Contrastive Language-Image Pre-training) to understand the *content* of an image, not just its pixels.
- **Strengths**: Understands "semantic" quality (e.g., a "good photo of a dog" vs just "sharp pixels").
- **Range**: 0.0 - 1.0
- **Speed**: Moderate (runs as subprocess).

## 3. VILA (Vision-Language Aesthetics)
*TensorFlow Implementation*

**Status: DISABLED**
Originally integrated for semantic scoring, but removed due to persistent instability with TensorFlow Hub loading and dependencies. Replaced by LIQE.

## 4. Model Correlation
*Based on internal testing (v2.5.0)*

- **High Correlation**: KONIQ <-> SPAQ (They generally agree).
- **Moderate**: KONIQ <-> PAQ2PIQ.
- **Low Correlation**: Technical Models <-> Aesthetic Models (AVA/LIQE). This is expected; a blur can be artistic (Good Aesthetic) but technically poor (Low Sharpness). The weighted score balances this.
