---
type: Research Method
title: Verifying model weight provenance and running checkpoints without their framework
description: Reusable method for proving an ONNX model's weights are (or are not) a public checkpoint, spotting the checkpoint a fine-tuned model started from, and reimplementing an architecture from its state_dict so the upstream weights load strict and match to float32 rounding.
resource: docs/research/model-weight-provenance-method.md
tags: [research, method, provenance, licence, onnx, pytorch, detector]
timestamp: 2026-09-25T00:00:00Z
okf_version: 0.1
---

# Verifying model weight provenance

> **Why this exists.** Research reports sometimes measure a model we are not allowed to ship. That
> model may be a local research instrument, or an export of unknown origin. Before a result can drive a
> decision, we need to know **whether it transfers to weights we may use**. This page is the method.
> The first application is the
> [upstream weight identity report](../reports/upstream-weights-identity-2026-09-25.md).

## 1. Is this ONNX file a stock checkpoint?

Exporters rarely copy weights verbatim. Three transformations must be undone before comparing:

| Export transformation | How to undo it |
|---|---|
| **BatchNorm folded into the preceding conv** | For each upstream (conv, BN) pair, compute `k = γ / √(var + ε)`, `W' = W · k` (per output channel) and `b' = β − mean · k` (+ `b · k` when the conv has a bias). Compare `W'`/`b'`, not `W`. |
| **Transposed or reshaped matrices** | Linear layers may appear as `Wᵀ` (Gemm/MatMul). Scalars and vectors may be reshaped, e.g. `(256,)` stored as `(1, 1, 2, 128)`. Compare after flattening when the element count matches. |
| **Constants baked from buffers** | Anchor/prior grids and normalization constants appear as initializers. Recognize them and exclude them from the weight count. |

**Procedure:**
1. Download the candidate checkpoint **from its official source** and record the SHA-256 of the bytes.
   Don't trust the hash in the filename; it can differ (we have seen it).
2. Load every float initializer of the ONNX file and every float tensor of the checkpoint's
   `state_dict`.
3. Build a candidate set from the checkpoint: the raw tensors, their transposes, and the BN-folded weights
   and biases. **Use the ε from the model's config.** 1e-5 and 1e-3 both occur, and the wrong one shows
   up as small but systematic mismatches.
4. Match each ONNX tensor to the same-shape candidate with the smallest relative max difference,
   `max|a − b| / max|b|`.
5. **Verdict:**
   - *identical*: every trained tensor matches at ≤ 1e-6, each candidate is used at most once, and the
     parameter counts agree
   - *fine-tuned*: some tensors match (typically early layers) but others don't, or all are close but
     none within rounding
   - *unrelated*: the tensors don't match

A useful sanity check: an 80-class detector head that matches to rounding cannot have been fine-tuned
on anything.

## 2. Which checkpoint did a fine-tuned model start from?

Fine-tuning moves the weights but rarely far from where they started, especially in early layers. To
find the base, for each candidate base checkpoint:
- Compute, per matching layer, the Pearson correlation between the target's (BN-folded) conv weights and
  the candidate's.
- Look at the profile over depth. The true base shows correlations near 1.0 in the stem that decay
  slowly (medians above 0.9). A different pretraining of the same architecture, or random init, sits
  near 0 at every depth.
- Test **several** plausible bases: different pretraining recipes, library versions and random init.
  One candidate standing out against the others is the evidence.

This identifies the starting point. It says nothing about the training data or the licence of the
result: **a fine-tuned proprietary model is still proprietary**, whatever it started from.

## 3. Running an upstream checkpoint without its framework

Framework-bound checkpoints (e.g. OpenMMLab) often have no wheels for the CUDA/torch versions we run. The
alternative is to reimplement the architecture in plain PyTorch **from the paper and the state_dict**:
- **Mirror the parameter names and shapes exactly**, then load with `strict=True`. Every missing or
  unexpected key is an architecture error to fix, not to ignore.
- **Unpickle without the framework** by stubbing its metadata classes in a custom `Unpickler`.
  Checkpoints carry config objects alongside the tensors.
- **Match the post-processing, not just the network.** The pre-NMS top-k, IoU, score threshold,
  per-class cap and final keep all change the output list. Read them from the config, or from the
  constants in a reference export's graph.
- **Verify at the detection level.** Run both on the same letterboxed inputs and match detections by
  IoU. Report the match rate, box error in pixels and score error.

**Worked example (RTMDet-tiny COCO):**
- Reimplemented in the image-scoring-model repo under `training/teacher/`.
- 2,638 of 2,638 detections matched a reference export at IoU ≥ 0.99, with a median box error of
  3×10⁻⁴ px.
- The two bugs found on the way were BN ε (1e-3 → 1e-5) and the final keep (100 → 300).
- Our own ONNX export from it reproduces PyTorch to 0.13 px.

## 4. What may be used

| Source | Measure against it | Ship it | Use its outputs as training labels |
|---|---|---|---|
| Public checkpoint with a permissive licence, verified by hash | yes | yes, with a weights manifest | yes (teacher) |
| Verified-identical copy inside a third-party product | yes (results transfer) | **no**: ship the upstream download instead | via the upstream checkpoint only |
| Proprietary or fine-tuned model, or a repo with no licence | yes, local evaluation baseline only | no | **no** |

## Related

- [upstream weight identity report](../reports/upstream-weights-identity-2026-09-25.md)
- [ONNX conversion feasibility: parity lessons](../planning/models/ONNX_CONVERSION_FEASIBILITY.md)
- [subject-evidence model roles](../planning/models/subject-evidence-model-roles.md)
- image-scoring-model: [teacher pseudo-labels v0](https://github.com/synthet/image-scoring-model/blob/main/docs/reports/teacher-pseudo-labels-v0-2026-09-25.md) (open COCO detector used as a teacher for `bird_detect_v0`)
