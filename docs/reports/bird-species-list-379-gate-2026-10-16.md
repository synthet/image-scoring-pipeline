---
type: Report
title: Bird species list 379 gate
description: Agent-panel gate that replaced the 369-name species list with a 379-name Austin-ordered list; three proposed additions were rejected.
resource: reports/bird-species-list-379-gate-2026-10-16.md
tags: [species, bioclip, validation]
timestamp: 2026-10-16T00:00:00Z
okf_version: 0.2
---

# Bird species list 379 gate

A working-tree edit proposed 382 names: the gated 369 plus 13 additions, reordered by an
Austin-area frequency proxy (`data/bird_species_austin_frequency_proxy_2026-10-09.csv`).

**Result: the gate passed. The bundled list becomes 379 names**, the 369 plus 10 additions:
- Not adopted: Boat-tailed Grackle, Eurasian Jackdaw and American Herring Gull.
- These are **agent-panel labels, not owner labels**.
- The Stage 5 refresh operator keeps the frozen 369-name list,
  `data/bird_species_list_369_stage5.txt`.

## Method

The decision rules (L1–L3) and an addendum were pre-registered before any label existed.

- **Population:** the 4,401 Stage 5 large/medium cohort.
- **Rescoring:** the stored region BioCLIP-2 image embeddings were rescored with
  softmax(100·cos) under each list, using a strict floor > 0.5. No images were decoded and nothing
  was written to production.
- **Parity:** rescoring the 369 list reproduced all 4,401 live outcomes (maximum top-1 error 0.0001).
- **Jev range screen (jev-1.13.0, text evidence only):**
  - Boat-tailed Grackle was judged implausible (0.88). It has zero local photo records, only audio
    detections, and the library is inland.
  - Eurasian Jackdaw was judged implausible (1.00). It has no local records and the library has
    no European photos.
  - Both were removed: a Jev result can only tighten the list.
- **Duplicate removed:** American Herring Gull is the North American form of Herring Gull in the
  AOS checklist, so it was removed as a duplicate. Jev agreed at 0.69, below the 0.7 threshold, so
  that answer was not relied on.
- **Frames judged:** under the 379-name list, 124 frames differ from the 369-name list:
  - 86 newly labelled;
  - 33 changed;
  - 5 newly abstaining.

  All 124 were judged.
- **Judges:**
  - A blind four-CLI vision panel (Claude, Codex, Antigravity, Cursor) answered 124/124 frames
    each. Each judge gave its own ID first, then chose A, B, NEITHER or UNSURE.
  - Consensus required three of the four judges to agree.
  - Seven frames split. They were given species-blind descriptions (0 leaks), then Jev chose a
    label. Only one answer reached the 0.7 confidence bar, so six frames stay unresolved and are
    excluded.

## Gate

| Resolved differing frames (118) | 369 list | 379 list |
|---|---:|---:|
| Right | 5 | **110** |
| Wrong | 29 | **4** |

**L1, right ≥ old right:** pass. Breakdown by frame class:

| Class | Resolved | 369 right / wrong | 379 right / wrong | Unresolved |
|---|---:|---:|---:|---:|
| Changed | 29 | 3 / 26 | 26 / 3 | 4 |
| Newly labelled | 84 | — | 83 / 1 | 2 |
| Newly abstaining | 4 | 2 / 2 | — | 1 |

**L2, more right and no more wrong:** pass.

**L3, each added species right on a strict majority of its wins:** pass for every winner.

| Species | Right | Wrong | Unresolved |
|---|---:|---:|---:|
| Ladder-backed Woodpecker | 55 | 3 | 0 |
| American Avocet | 18 | 0 | 0 |
| Crested Caracara | 15 | 0 | 2 |
| Couch's Kingbird | 12 | 1 | 3 |
| Greater Roadrunner | 4 | 0 | 0 |
| Black-necked Stilt | 3 | 0 | 0 |
| American Pipit | 2 | 0 | 0 |
| Monk Parakeet | 1 | 0 | 0 |

Muscovy Duck and Greylag Goose won no frames in this cohort.

The pass is robust: even if all six unresolved frames had gone against the 379-name list, every
gate would still pass.

## Scope and follow-up

The gate measures the selected-region cohort only:
- **Legacy path not measured.** Full-frame and detector-crop species inference on unselected
  images uses the same list, but these frames did not test it.
- **No relabelling yet.** Existing production labels still come from the 369-name list.
  Relabelling the 124 affected cohort images is a separate approved refresh. The frozen 369-name
  operator cannot do it as built.
- **Evidence location:** contract, rescoring, panel, consensus and Jev receipts are in the ignored
  `.agent/scratch/species-list-382/`.
