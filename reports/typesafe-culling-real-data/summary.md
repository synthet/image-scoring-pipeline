# Jev-ready culling evidence: real-data baseline

Generated: `2026-09-22T01:37:21.684110+00:00`  
Tracking: [#359](https://github.com/synthet/image-scoring-backend/issues/359)

This is a read-only baseline over historical image records. It evaluates whether the
evidence available to a future Jev experiment carries useful pick/reject signal.
No database row, rating, pick, cull decision, or image file was changed.

## Dataset

- 11,590 candidates across 2,304 mixed stacks
- 9,754 candidates have pick/reject labels
- 5,123 picks and 4,631 rejects
- 328 folder groups used for leakage-resistant validation
- 7,370 rows in metadata-hinted wildlife stacks

## Caption evidence

- Fully collapsed stacks: 1,070 (46.4%)
- Mean distinct-caption ratio: 41.8%
- Picks whose caption also appears on a reject in the same stack: 1,521 (29.7%)
- Missing captions: 4,347 (37.5%)

## Deterministic score baseline

| Cohort | Stacks | Picks | Score-only pick recall | Random expectation |
|---|---:|---:|---:|---:|
| All mixed | 2,304 | 5,123 | 0.7455 | 0.5324 |
| Fully captioned | 1,497 | 3,028 | 0.7005 | 0.5229 |

## Folder-grouped historical-pick prediction

| Variant | ROC-AUC | Average precision | Wildlife ROC-AUC | Wildlife AP |
|---|---:|---:|---:|---:|
| `scores` | 0.627 | 0.627 | 0.629 | 0.625 |
| `scores_plus_caption` | 0.627 | 0.628 | 0.629 | 0.627 |
| `scores_plus_mobilenet_v2_imagenet_gap` | 0.628 | 0.625 | 0.628 | 0.622 |
| `scores_plus_clip_vit_b32_image` | 0.627 | 0.627 | 0.629 | 0.625 |
| `scores_plus_bioclip_2_image` | 0.627 | 0.626 | 0.628 | 0.623 |
| `scores_plus_openclip_l14_laion2b_image` | 0.628 | 0.625 | 0.629 | 0.621 |
| `all_model_scores` | 0.658 | 0.637 | 0.654 | 0.631 |
| `composites_plus_all_model_scores` | 0.658 | 0.638 | 0.655 | 0.632 |
| `all_evidence` | 0.658 | 0.639 | 0.655 | 0.632 |

These scores measure agreement with historical picks. They do not establish that
historical rejects were safe to remove or that an embedding recognized the reason a
frame was distinctive.

## Jev arm

Status: **available**. Capability is available, but this baseline intentionally makes no paid calls.

## Interpretation rule

Promote a Jev experiment only after structured or paired visual evidence improves over
the score-only baseline on held-out folders. Then evaluate rules and Jev on the exact
same evidence so improved perception is not incorrectly credited to the decision model.
