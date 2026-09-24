# Everypixel UGC correlation (phase 1)

Read-only research harness — **does not** write `image_model_scores` or change fusion.

**Spec:** [`docs/planning/integrations/EVERYPIXEL_CORRELATION_STUDY.md`](../../../docs/planning/integrations/EVERYPIXEL_CORRELATION_STUDY.md)  
**Artifacts:** [`image-scoring-skills/research/everypixel-correlation/`](https://github.com/synthet/image-scoring-skills/tree/main/research/everypixel-correlation)  
**Issue:** [#392](https://github.com/synthet/image-scoring-backend/issues/392)

| Script | Role |
|--------|------|
| `export_cohort.py` | PostgreSQL manifest (stratified by `score_general` quintile) |
| `fetch_ugc.py` | `/v1/quality_ugc` → `research/everypixel-correlation/everypixel_ugc.jsonl` (private [`image-scoring-skills`](https://github.com/synthet/image-scoring-skills) repo) |
| `join_and_analyze.py` | Spearman table + multivariate modeling pass → `correlation_summary.md`, `modeling_summary.md`, CSV/JSON artifacts |

Run in gpu-shell; see the planning doc for commands.
