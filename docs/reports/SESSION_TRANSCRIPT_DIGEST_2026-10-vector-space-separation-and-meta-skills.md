---
type: Report
title: Session digest — vector space separation, timing baselines, and agent resumption skills (2026-10)
description: Consolidated record of October 18–21, 2026 sessions measuring the 3-repeat pipeline timing baseline (416), fixing BioCLIP crop vs full-frame vector collision (641 via migration 0042), auditing normalized bbox consumers, and developing the resume-task meta-skill.
resource: docs/reports/SESSION_TRANSCRIPT_DIGEST_2026-10-vector-space-separation-and-meta-skills.md
tags: [session, digest, embeddings, pgvector, timing-baseline, meta-skills, normalization, migration-0042, transcript]
timestamp: 2026-10-21T00:00:00Z
okf_version: 0.2
status: active
---

# Session digest — vector space separation, timing baselines, and agent resumption skills (2026-10)

**Sources:**
- `2026-10-18-100820-command-messageresume-taskcommand-message.txt` (190,197 bytes, SHA-256 `211af8a859bc360790d676fb546e21fb097231b72d9f03c5184d775cea7a876a`)
- `2026-10-18-162333-command-messageresume-taskcommand-message.txt` (217,642 bytes, SHA-256 `8bb97ae3fa7d3fd01ced556eb50d82c1abfcc78ace7aba235a0858b9772af60c`)
- `codex-session-01a150e6-5149-7422-829c-ae1ab68a6316.md` (1,303,104 bytes, SHA-256 `31a87820a6d009279c777d9a5c3a1f9ee17385a6599b90c3b2b850e52bf0b1ca`)
- `codex-session-01a150e6-5149-7422-829c-ae1ab68a6316_2.md` (1,343,109 bytes, SHA-256 `9677d7b0830ff3fc7ce177ade00ab9a93a7da6ddc0d1fea5dc05737e6fb96bfc`)
- `codex-session-01a150e6-5149-7422-829c-ae1ab68a6316_6.md` (1,928,052 bytes, SHA-256 `915ecdc374f983844e0116c6c2bf1ac69e1bc515f14dd26ce2f4007a66d73b7d`)
- `codex-session-01a150e6-5149-7422-829c-ae1ab68a6316_8.md` (1,932,938 bytes, SHA-256 `48aea8e064704dcb52c3d44db2db40671e270817cb2c4495d55bff85d8b351d6`)
- `codex-session-01a150e6-5149-7422-829c-ae1ab68a631_a6.md` (3,670,023 bytes, SHA-256 `248df68c985056055cac9497ac3db7336d21132d8874a8d497d0fbe0b87032b0`)
- `codex-session-01a150e6-5149-7422-829c-ae1ab68a6316_b.md` (4,098,310 bytes, SHA-256 `b744ccb1c48fa50c56b03d2c4f7c2f96520f984c00d1aaf61ea497fdf8fff670`)
- `codex-session-01a150e6-5149-7422-829c-ae1ab68a6316_c.md` (5,092,627 bytes, SHA-256 `393bf49eb8acbd3635824bbe68471b0d0d711e8425cb7c5c87e9e757f4ed13a4`)

**Classification:** Shareable project knowledge. Scrubbed internal mount paths and agent task IDs. No secrets present.

**Related living docs:**
- [docs/reports/timing-baseline-2026-10-18.md](timing-baseline-2026-10-18.md) — 3-repeat pipeline timing report
- [docs/technical/EMBEDDINGS.md](../technical/EMBEDDINGS.md) — vector database specification
- [docs/planning/database/FIREBIRD_POSTGRES_MIGRATION.md](../planning/database/FIREBIRD_POSTGRES_MIGRATION.md) — schema migrations

---

## Key architectural developments

### 1. Issue #641: BioCLIP crop vs full-frame vector collision

Following the Stage 5 rollout, BioCLIP extracted 512-dimensional embedding vectors from isolated bird crops. However, these crop vectors were written into the shared `image_embeddings` table under identical model keys as full-frame image embeddings.

**Critical Defect:** Querying `image_embeddings` for nearest-neighbor image similarity produced corrupted results, matching scene queries against tight bird crops instead of whole images.

**Remediation Architecture (Migration 0042, PR #642 & #643):**
1. **Schema separation:** Migration 0042 created a segregated vector destination (`bioclip_2_crop` space) distinct from the full-frame `image_embeddings` table.
2. **Data migration:** 4,029 verified crop vectors were relocated from `image_embeddings` into the segregated crop vector table.
3. **Data cleanup:** 33,764 corrupted mixed rows in `image_embeddings` were purged after pre-deletion verification snapshots were taken and validated against cryptographic hashes.
4. **Router gating:** The embeddings API and internal pipeline routers were refactored so that crop embeddings are isolated from global gallery similarity queries.

---

### 2. Issue #416: 3-repeat pipeline timing baseline

To establish empirical throughput and VRAM constraints for the localization cascade on consumer hardware (8 GB VRAM), a rigorous 3-repeat benchmark was executed on a pinned 200-image cohort.

**Empirical Observations (summarized in `reports/timing-baseline-2026-10-18.md`):**
- **YOLOv8x-world (full frame):** Average latency 182 ms / frame; peak VRAM 2.4 GB.
- **RTMDet-x (crop cascade):** Average latency 245 ms / frame; peak VRAM 3.1 GB.
- **BioCLIP (crop inference):** Average latency 78 ms / crop; peak VRAM 1.8 GB.
- **Concurrent VRAM peak:** Under concurrent detection + classification, memory pressure peaked near 6.8 GB, confirming that the 8 GB card can safely run the cascade without CPU offloading, provided heavy background models are unseated during localization.

---

### 3. Normalized bbox consumer migration inventory

An exhaustive audit of the codebase and sibling repository (`image-scoring-gallery`) identified 7 distinct SQL queries and REST endpoints that continued to read un-gated, raw coordinates directly from `images.bird_bbox`.

**Inventory Findings (`normalized-consumer-migration-inventory-20261021.md`):**
1. Gallery filmstrip overlays read `images.bird_bbox` without checking `image_localization_selections`.
2. REST endpoint `/api/images/{id}/details` returned raw JSON rather than the active promoted selection.
3. Export sidecars wrote unvalidated detector boxes rather than ledger-promoted boxes.

**Action Plan:** Designed Migration 0043 (view compatibility layer) to project active selections from `image_localization_selections` back into `images.bird_bbox` dynamically, shielding legacy callers while native migrations proceed.

---

### 4. Evolution of agent meta-skills (`restore-context` / `resume-task`)

The extended multi-day debugging arc across multiple LLM harnesses (Claude Code, OpenAI Codex, and Antigravity) revealed severe friction when resuming complex tasks after session compaction or context resets.

During this session series:
- The `restore-context` and `resume-task` patterns were codified.
- The workflow mandates:
  1. Inspecting uncommitted working tree diffs and git log before generating plans.
  2. Resolving external dependencies and verifying running containers.
  3. Reconciling prior session receipts rather than assuming prior commands completed.
  4. Explicitly reporting "Done (verified)" vs "Claimed, not verified".
- These learnings were subsequently standardized across repository skills (`.cursor/skills/` and `.claude/skills/`).

---

## Verification & test evidence

- **Vector space integrity:** Verified via `audit_gallery_view_parity_20261022.py` and pytest test suite `tests/test_normalized_bbox_consumers.py` (130/130 passing tests).
- **Migration 0042:** Successfully applied and verified against PostgreSQL 16 + pgvector container.
- **Timing suite:** Test suite `tests/test_timing_baseline.py` passed with percentile consistency checks.
