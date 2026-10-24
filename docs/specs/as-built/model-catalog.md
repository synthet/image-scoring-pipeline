---
type: Technical Reference
title: Model and algorithm catalog as built
description: Model identities, loaders, preprocessing, output semantics, gates, consumers and evaluation limits.
resource: specs/as-built/model-catalog.md
tags: [specification, as-built, models, embeddings]
timestamp: 2026-10-23T00:00:00Z
okf_version: 0.2
---

# Model and algorithm catalog as built

Baseline `321d3a15f5ebf5f2de62cc212eb087eccf548f2e`; model definitions are **recipes**, not proof of
loaded checkpoint bytes. Per-installation enabled/shadow flags, profiles, checkpoint hashes, library versions
and evaluation datasets must accompany an inference receipt. The review's catalog does not certify that a
registered model is enabled in a running process. [execution-and-scoring](execution-and-scoring.md) defines gates.

## Quality and localization models

| Identity / lifecycle | Loader and preprocessing | Output / direction | Consumers, fallback, provenance and evidence |
|---|---|---|---|
| MUSIQ SPAQ, AVA; factory-registered | [MusiqModelWrapper](../../../modules/engines/musiq_model.py) → shared [MultiModelMUSIQ](../../../scripts/python/run_all_musiq_models.py), TF Hub model recipe; upright-v1 square prepared JPEG, default512; internal MUSIQ multi-scale patches | SPAQ0..100; AVA1..10; larger better; linear normalized[0,1] | Host fusion + score rows; load/predict failure stays missing. TF implementation VERSION5.2.0; wrappers musiq-1. Actual TF Hub cache bytes not frozen by this campaign. Registry/wrapper unit tests establish contracts, not field ranking accuracy. |
| MUSIQ KONIQ/PAQ2PIQ, VILA; retired recipes | Backend historical loaders/ranges retained, factory refuses registration | KONIQ/PAQ2PIQ0..100, VILA0..1 | Historical rows and research context; weights availability does not reactivate them. |
| LIQE; factory-registered | [LiqeScorer](../../../modules/liqe.py), pyiqa `liqe`, PyTorch; RGB tensor[0,1], max dimension518 default, bicubic if larger; optional path fallback | **Native1..5**, normalized(score−1)/4, higher better | Production/shadow per config; persistent scorer, CPU fallback if CUDA absent; tensor failure tries path inference, which can change preprocessing. Old “subprocess, native0..1” descriptions are obsolete. |
| TOPIQ-NR; import-registered | [TopiqScorer](../../../modules/topiq.py), pyiqa `topiq_nr`; RGB tensor, max dimension1024 default | 0..1, higher better; topiq-nr-1 | Host fusion when enabled non-shadow and weighted; CPU/path fallback; optional resize override224..2048. |
| ARNIQA; import-registered, config controls shadow | [ArniqaScorer](../../../modules/arniqa.py), pyiqa metric `arniqa` default or `scoring.arniqa.metric`; RGB tensor, max1024 | 0..1 higher better; arniqa-1 or head-specific version | Config can promote to production; comments saying “always shadow” are historical. Default composites include technical/general weights, not aesthetic. Profile high_throughput disables inference. Historical model-selection report is dated evidence, not this campaign's validation. |
| Student v1, nine proxies; conditional registration | [StudentScorerService](../../../modules/student_scoring.py), validated bundle metadata and weights_sha256, manifest_id/protocol_id/preprocessing fingerprint; shared forward/cache | Eight quality/composite proxies plus uncertainty, each[0,1]; uncertainty is uncertainty, not “higher quality” | [PROXY_SPECS](../../../modules/engines/student_model.py) namespaces prevent teacher-name reuse. Bundle env/config required; failed validation leaves not-loaded. Shadow status remains config-controlled; no teacher substitution inferred from matching dimensions. |
| QPT V2; experimental, not registered | [qpt_v2](../../../modules/qpt_v2.py), local reconstructed architecture/checkpoint recipe | Wrapper normalization exists, but native calibration is not established | No normal production consumer until explicit registration/validation. A checkpoint file alone is insufficient. |
| Cursor/Claude judges; registered, normally disabled in template | Optional SDK wrappers; image/evidence prompt, rubric | Native rubric scalar per wrapper plus optional subscores | Paid external services; excluded from this campaign. Registration does not authorize calls. |
| YOLO bird/pose | [bird_detection](../../../modules/bird_detection.py), model-repo YOLO11n bird checkpoints / six-point pose; RGB upright rendition, imgsz640 | Confidence and pixel/normalized box coordinates; pose includes anatomical points | Localization/species provider boundaries. Exact loaded bytes depend on resolved path; fallback chain is in model repo. No weights promoted here. |
| RTMDet-tiny COCO fallback | [RTMDetProvider](../../../modules/detectors/rtmdet.py), ONNX manifest/hash gate, 640BGR letterbox | Sigmoid per-class scores and xyxy; application threshold.4 | Subject cascade only; provider_unavailable/weights_mismatch errors preserve missing evidence. Model repo manifest binds ONNX `366c677e5d3d3d45118d906a78a3b715a6cff266296740eb327790d48f8ea3cd`. |

## Embedding spaces and classification

[embedding_spaces](../../../modules/embedding_spaces.py) fixes code/dimension;
[embedding_extractors](../../../modules/embedding_extractors.py) defines optional culling recipes.
Persisting a catalog row does not make its extractor active. Vector dimensions alone cannot establish
interchangeability; crop/full-frame inputs, pooling, normalization and model revision belong to identity.

| Space / exact recipe | Dimensions and preprocessing | Consumers / runtime / fallback |
|---|---|---|
| mobilenet_v2_imagenet_gap |1280D, ImageNet MobileNetV2 global average pooling; TF/Keras input preprocessing | Default visual clustering, feature cache and pgvector; missing features cause documented clustering fallback rather than proof of duplication |
| clip_vit_b32_image; `openai/clip-vit-base-patch32` |512D, HF CLIP image processor/model, normalized projected image features | Keyword tagging/similarity; JIT culling ensure can produce it before tagging; CLIP quality is derived evidence, not a learned eye scorer |
| bioclip_2_image / bioclip_2_crop; `imageomics/bioclip-2` |768D, OpenCLIP ViT-L/14 processor, full frame vs padded bird crop are separate identities | Species text similarity and image embeddings; selected-region eligibility/fallback in [localization-and-consumers](localization-and-consumers.md). Confidence is prompt/list-relative, not calibrated universal species probability |
| blip_vit_b16_image |768D, BLIP base vision pooler output | Caption-aligned embeddings/keywords; no substitute for CLIP512 or BioCLIP768 despite same size |
| openclip_l14_laion2b_image |768D, OpenCLIP `ViT-L-14`, pretrained `laion2b_s32b_b82k`, bundled processor | Opt-in culling tower and two-level leaf substacks; torch CPU/CUDA, lazy loader |
| openai_clip_vit_l14_image |768D, OpenCLIP `ViT-L-14-quickgelu`, `openai` | Opt-in culling grouping; distinct from L14LAION weights |
| dinov2_reg_base_image |768D, **timm `vit_base_patch14_dinov2.lvd142m`**, library transform | Optional/HOLD culling space; name does not prove register-token architecture. Not the skills study's HF DINOv2 patch representation |
| siglip2_base_image |768D, HF `google/siglip2-base-patch16-224` | Opt-in culling/keyword evidence, library image processor |
| SSCD; skills-local `sscd_disc_mixup.torchscript.pt` | TorchScript SHA-256 `9f26bd4c848cc19b73d2ae92eea6e04886f61a7b764ceb7a13aeee62e6a6db56`; 320letterbox, ImageNet norm, L2 vectors | Skills dedupe research/provider, not this pipeline registry; cosine distance lower is nearer |
| DINOv2 skills HF `facebook/dinov2-base` |336letterbox, ImageNet norm, per-patch L2; local library stores fp16 tokens | Dedupe patch-mean cosine distance, no production pipeline replacement inferred |
| DINOv3 ViT-B/16 and ViT-L/16 | Skills research loader calls official local `dinov3.hub.backbones`, 336ImageNet letterbox, CLS/patch outputs; model-repo manifest records hashes | Experimental study recipes. Other manifest-listed DINOv3 architectures are **available weights only** unless a loader/consumer is independently identified. No DINOv3 space exists in pipeline SPACE_DIMS |

## Clustering, ranking and persistence

[ClusteringEngine](../../../modules/clustering.py) uses agglomerative visual clustering with time gating;
representative policy is score/centroid/balanced, with score fallback when features are unavailable.
[sub_clustering](../../../modules/sub_clustering.py) supplies within-stack grouping;
[two_level_culling](../../../modules/two_level_culling.py) policy2.0 defaults visual threshold.15, OpenCLIP
leaf threshold.06, picks3 per substack and stack cap20, diversity enabled/lambda.70. Uniform allocation
uses `M_eff=min(M,max(1,floor(N/c)))`, then leftover to larger substacks with stable quality tie-breaks.
This allocation formula's c>N boundary needs its existing tests; do not infer physical equivalence from a cluster.
[culling_embeddings](../../../modules/culling_embeddings.py) lazily ensures missing selected-space vectors;
it reports requested/missing/persisted/covered and warns below90% coverage.

`image_model_scores` stores per-model evidence; primary image composite fields are separate projections.
Embedding spaces route dimension-specific pgvector facts. Localization runs/regions and selected-production
bbox ownership are separate tables. DB facade→connector→Postgres is current; Firebird remains historical
compatibility code. Repair/reset and application/reversion are side effects behind their own boundaries.

## Coverage and unresolved evidence

This is a complete catalog of the named families requested in the review, plus the adjacent active model
recipes traced above. The hub module/symbol inventory lists additional source surfaces as explicit gaps;
it is not a claim that every source function was semantically reviewed. Actual checkpoint/runtime versions,
full per-model native preprocessing internals, field denominators, uncertainty and cross-GPU latency/memory
remain unresolved where no frozen inference receipt exists. No model contribution or redundancy claim is
promoted from historical correlations or synthetic data. Validate model contribution by grouped ablation
and selected-region/full-frame comparison under a new versioned policy before migration.
