---
type: Documentation Index
title: Embedding applications index
description: Embedding feature specs and current normalized-storage and next-task pointers.
resource: features/planned/embeddings/EMBEDDING_APPLICATIONS_INDEX.md
tags: [docs, planning, next-steps]
timestamp: 2026-10-13T00:58:42Z
okf_version: 0.2
---

# Embedding Applications - Detailed Specs

This index breaks out each proposed `image_embedding` use case into a separate implementation document. See the [source document](EMBEDDING_APPLICATIONS.md) for the overview and summary.

## Documents

- [NEXT_STEPS.md](NEXT_STEPS.md) — current shipped-versus-proposed gaps and implementation order
- [TODO.md](TODO.md) — retired task pointer to the canonical GitHub Project board
- [01 - Diversity-Aware Selection](EMBEDDING_APP_01_DIVERSITY_SELECTION.md)
- [02 - Near-Duplicate Detection](EMBEDDING_APP_02_NEAR_DUPLICATE_DETECTION.md)
- [03 - Tag Propagation](EMBEDDING_APP_03_TAG_PROPAGATION.md)
- [04 - Outlier Detection](EMBEDDING_APP_04_OUTLIER_DETECTION.md)
- [05 - 2D Embedding Map](EMBEDDING_APP_05_2D_EMBEDDING_MAP.md)
- [06 - Smart Stack Representative](EMBEDDING_APP_06_SMART_STACK_REPRESENTATIVE.md)
- [07 - More Like This UI](EMBEDDING_APP_07_MORE_LIKE_THIS_UI.md)
- [Two-level culling](two-level-culling.md) — persisted sub-stacks, visual→semantic split, best-M with N cap

## Scope and assumptions

- Spaces are registered, including the default MobileNet and additional CLIP/BioCLIP/BLIP spaces; use current [embedding documentation](../../../EMBEDDINGS.md).
- PostgreSQL stores normalized embeddings in `image_embeddings` and per-dimension fact tables. Revision 0024 removes the legacy `images.image_embedding`; the old Firebird BLOB description is historical.
- Retrieval uses the DB facade and `modules/projections_db.py`; route contracts live under `modules/api/routers/`.
- No model retraining is required for any of these items.
