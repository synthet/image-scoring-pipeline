---
type: Report
title: Upstream weight identity for the research detector, pose and mask models
description: Tensor-level check that the ONNX weights used in the 2026-09-24 research reports are identical to public upstream checkpoints (RTMDet-tiny COCO, RTMPose-m AP-10K, U²-Net-p), so their results transfer to upstream weights.
resource: docs/reports/upstream-weights-identity-2026-09-25.md
tags: [research, localization, detector, provenance, licence, onnx]
timestamp: 2026-09-25T00:00:00Z
okf_version: 0.1
---

# Upstream weight identity (2026-09-25)

> **Status:** research memo. It closes the evidence half of blocker **B6** in the
> [decision register](../specs/pipeline-streamlining/07-blockers-and-decisions.md) and supports #408
> (spec 03 AC-1) and #426.

## Question

Several 2026-09-24 reports used three ONNX models from a third-party product's local install. They
were run locally as a research instrument; none of those files enter this repo. The reports are:
- [subject detector comparison](subject-detector-comparison-2026-09-24.md)
- [bbox LLM panel](bbox-llm-judge-panel-2026-09-24.md)
- [subject-evidence probe](subject-evidence-probe-2026-09-24.md)

Are those weights the public upstream checkpoints, or fine-tuned variants? If they are identical,
every number in those reports holds for the upstream Apache-2.0 weights we are allowed to ship.

## Method

- Downloaded each upstream checkpoint from its official source and recorded its SHA-256.
- Read every float initializer of the ONNX file, and every float tensor of the checkpoint's
  `state_dict`.
- Folded each BatchNorm into its preceding convolution (the usual export fusion, with or without a
  conv bias), and allowed transposed 2-D matrices.
- Matched each ONNX tensor to the closest same-shape upstream candidate by relative max difference.

## Results

| Model | Upstream checkpoint (SHA-256 prefix) | ONNX weight tensors matched | Worst relative difference |
|---|---|---|---|
| RTMDet-tiny, COCO (detector) | OpenMMLab `rtmdet_tiny_8xb32-300e_coco_20220902_112414-78e30dcc.pth` (`78e30dcc`) | 167 / 167, plus 2 constant anchor-point grids (8,400 points) | 7.6 × 10⁻⁸ |
| RTMPose-m, AP-10K, 256×256 (mammal pose) | OpenMMLab `rtmpose-m_simcc-ap10k_pt-aic-coco_210e-256x256-7a041aa1_20230206.pth` (`896e3665`) | 132 / 132, all 13.6 M parameters (the GAU `gamma` is stored reshaped to (1, 1, 2, 128)) | ≤ 10⁻⁶ |
| U²-Net-p (subject mask) | official `u2netp.pth` from the U-2-Net README's Google Drive link (`e7567cde`) | 231 / 231, all 1.13 M parameters | ≤ 10⁻⁶ |

- **No fine-tuning.** Every trained tensor, including RTMDet's 80-class COCO heads, equals upstream
  to float32 rounding. No upstream tensor is used twice.
- **Export fingerprints.** The detector and pose files are standard OpenMMLab deployment exports
  (opset 11, `dets`/`labels` and SimCC `simcc_x`/`simcc_y` outputs). The mask model is a plain
  PyTorch export (opset 18).
- **Checksum note.** The RTMPose file's SHA-256 prefix (`896e3665`) differs from the hash in its
  published filename (`7a041aa1`), but its weights are the ones in the research file. Record the
  observed SHA-256 in the weights manifest, not the filename's.

## Consequences

- **B6 is now a packaging task only.** The detector-comparison and box-panel numbers apply unchanged
  to the upstream RTMDet-tiny weights. Spec 03 still needs our own export (AC-1) and a weights
  manifest (AC-2). Running the checkpoint directly in PyTorch also works, but needs `mmdet`.
- **#426 has verified sources:**
  - mammal pose: the RTMPose-m AP-10K checkpoint above
  - subject mask: `u2netp.pth` above

  Both are Apache-2.0.
- **Still no open equivalent for bird head/eye keypoints.** The research instrument's bird
  head/eye keypoint model is proprietary and was not compared. The bird path uses our own eye-pose model
  (image-scoring-model).
- **Nothing third-party enters the repo.** Only upstream checkpoints and our own exports may be
  used.
