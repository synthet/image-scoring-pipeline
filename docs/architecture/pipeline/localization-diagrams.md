---
type: Technical Reference
title: Localization Rollout Diagrams
description: Four views of the localization rollout that its other docs don't draw - the data model, how a detector box reaches consumers, the authority lifecycle, and the gates holding each stage.
resource: architecture/pipeline/localization-diagrams.md
tags: [pipeline, architecture, localization, bird-detection, rollout, diagrams]
timestamp: 2026-11-05T18:30:00Z
okf_version: 0.2
---

# Localization rollout diagrams

Epic #345, schema through migration 0048. Live figures are from read-only queries at 2026-11-05 03:10 UTC and will drift.

These are the views the rollout docs don't draw:

- [Data model](#data-model): how the tables relate.
- [From a detector box to what consumers read](#from-a-detector-box-to-what-consumers-read): how a box becomes the one everything else reads.
- [Authority lifecycle](#authority-lifecycle): how the runtime moves from shadow to active.
- [Stages and gates](#stages-and-the-gates-that-hold-them): which gates hold each stage.

Design and history: [localization-rollout.md](localization-rollout.md). Current plan: [localization-rollout-plan-2026-11-04.md](../../planning/localization-rollout-plan-2026-11-04.md).

## Data model

Every detector attempt is an immutable run. At most one run per image and detector is current, and the regions hang off the run. A **selection** is the separate decision that one region counts, and it is the only path that writes `images.bird_bbox` for promoted images. The authority tables record why a selection was proposed or made.

```mermaid
erDiagram
    images ||--o{ image_localization_runs : "attempts"
    image_localization_runs ||--o{ image_regions : "boxes"
    image_regions ||--o{ image_keypoint_runs : "eye passes"
    image_keypoint_runs ||--o{ image_region_keypoints : "points"
    images ||--o{ image_localization_selections : "decisions"
    image_localization_runs ||--o{ image_localization_selections : "chosen run"
    image_regions ||--o{ image_localization_selections : "chosen box"
    image_localization_selections ||--o| localization_selection_lineage : "made by policy"
    localization_authority_policies ||--o{ localization_selection_lineage : ""
    localization_authority_policies ||--o| localization_policy_approvals : "approval"
    localization_authority_policies ||--o{ localization_authority_evaluations : "R2 verdicts"
    image_localization_runs ||--o{ localization_authority_evaluations : "judged run"
    localization_authority_evaluations ||--o{ localization_authority_attempts : "proposals"
    images ||--o{ localization_species_work : "species queue"

    image_localization_runs {
        bigint id PK
        int image_id FK
        text detector_key "bird, coco, subject_cascade, bird_agreement"
        text detector_config_hash
        text rendition_hash
        text decode_route "0035"
        text status "detected, no_detection, retryable_error, terminal_error, disabled"
        bool is_current "one per image and detector"
        jsonb legacy_payload "imported bird_bbox"
    }
    image_regions {
        bigint id PK
        bigint localization_run_id FK
        text object_class
        float confidence
        int rank
        float x1_y1_x2_y2 "display-normalized, unpadded"
    }
    image_localization_selections {
        bigint id PK
        int image_id FK
        text selected_by "rule id and hash"
        jsonb previous_bird_bbox
        jsonb projected_bird_bbox
        timestamp revoked_at "active when null"
    }
    localization_authority_evaluations {
        text policy_hash FK
        text outcome "accept, reject, abstain, invalid"
        text reason
    }
    localization_policy_approvals {
        text policy_hash PK
        bool geometry_allowed
        bool species_allowed
        text approved_by
    }
```

- Unique indexes enforce one current run per `(image_id, detector_key)` and one active selection per `(image_id, detector_key)`. `bird_agreement` runs are written with `is_current` false (spec 08 AC-13), so they never take the current slot.
- 802 images have more than one current detected run. Each has a `subject_cascade` run plus either a `bird` run (787) or a `coco` run (15). The index allows that because the detector keys differ, and readers that don't filter on `detector_key` see two runs.
- The view `image_bird_bbox_compat` (0043) reads the active selection's projected box first, then the imported legacy payload, then `images.bird_bbox`. Nothing reads it by default while `read_normalized_first` is unset.
- Not drawn: `localization_authority_control` (one row holding the mode and scan cursor), reservations, journal, discovery evidence, recovery attempts, species outputs.

## From a detector box to what consumers read

Selections so far came from the manifest script, plus 19 from the 2026-10-23 box review. The authority runtime is built, but it only evaluates. Downstream, BioCLIP crops the selected region when there is one, and otherwise falls back to its own embedded YOLO.

**Key:** green is live, purple dashed is shadow, amber dashed is built but off.

```mermaid
flowchart LR
    meta["metadata phase"] --> loc["localization phase<br/>bird_detect_v1 @ 640<br/>new images only"]
    loc --> run["bird run, is_current<br/>+ regions"]
    loc -.-> casc["subject_cascade run<br/>RTMDet fallback"]
    run --> kp["eye keypoints"]
    run -.-> agree["bird_agreement backfill<br/>RTMDet on each crop<br/>is_current false"]
    agree -.-> report["per-shoot report only"]

    run --> manifest["promote_localization_selections.py<br/>rule/3 and rule/4 manifests"]
    run -.-> eval["authority evaluation<br/>R2: conf ≥ 0.70, ≤ 3 regions"]
    eval -.-> prop["proposal<br/>6,504 accepts, none applied"]
    prop -. "needs active mode,<br/>approval, freshness" .-> sel
    manifest --> sel["select_region<br/>active selection"]

    sel --> bbox["images.bird_bbox<br/>projected box"]
    sel --> sp{"species_input_for_image"}
    sp -- "selection, area ≥ 0.005" --> crop["BioCLIP on padded crop"]
    sp -- "no selection or small" --> yolo["embedded YOLO<br/>then full frame"]
    bbox --> gallery["gallery and API<br/>read bird_bbox"]
    bbox -.-> compat["image_bird_bbox_compat<br/>read_normalized_first unset"]

    classDef live fill:#dff1e6,stroke:#1c6b3f,color:#17222b
    classDef shadow fill:#ebe5f8,stroke:#5a3fa0,color:#17222b,stroke-dasharray:4 3
    classDef off fill:#f8ecd0,stroke:#80570a,color:#17222b,stroke-dasharray:4 3
    class meta,loc,run,kp,manifest,sel,bbox,sp,crop,yolo,gallery live
    class casc,agree,report,eval,prop shadow
    class compat off
```

- 4,665 selections are active: 4,372 from rule/3, 274 small ones from rule/4 (geometry only), and 19 from the box review. That is about 12% of the 38,479 bird-tagged images counted on 2026-10-25, or 9% of the 52,135 images with a current detected bird run.
- Small selections (area < 0.005) still go to the embedded detector for species, until #610 passes.
- The embedded YOLO path is what Stage 8 retires. It stays on (`embedded_detector` default true) until selections cover the bird-tagged images.
- Species work under the authority (`localization_species_work`) runs only in active mode, so today species still comes from the `bird_species` phase.

## Authority lifecycle

The operator commands in `scripts.maintenance.localization_authority` move the single control row through three modes. Today it is in **shadow**, with one registered R2 policy, 0 reservations and 0 approvals. Approval waits on the #694 gate, which needs three qualified judges and has one.

```mermaid
stateDiagram-v2
    direction LR
    [*] --> off
    off --> shadow: set-mode shadow
    state shadow {
        direction TB
        registered: policy registered (R2, v1 producer)
        reserved: reservations imported
        approved: policy approved
        fresh: selection freshness on
        registered --> reserved: import-reservations
        reserved --> approved: approve-policy with gate receipt
        approved --> fresh: set-freshness on
    }
    shadow --> active: activate with receipt
    active --> off: set-mode off
    shadow --> off: set-mode off
    active --> draining: revoke-policy
    draining --> active: cleanup-invalid until 0 pending
    note right of shadow
        Today: scan cursor 239,048 of 241,459
        (stopped while the WebUI is down),
        0 reservations, 0 approvals.
        Blocked at approve-policy by #694.
    end note
```

- Shadow writes evaluations, proposals and lineage only. Fingerprints of `bird_bbox` and the selections table matched the baseline on 2026-11-02.
- The scan bound is the highest run that isn't `bird_agreement`. Those shadow rows push `max(id)` higher (248,923) without adding work the rule can judge.
- Turning the mode off stops new applications, and published outputs stay. Revoking a policy removes only the outputs it owns, through the cleanup queue. Turning freshness off needs a separately reviewed reader rollback.
- Migration 0047 refuses a downgrade until a preservation migration is reviewed. Reverting code does not roll back data.

## Stages and the gates that hold them

The eight stages from the epic, colored by state as of 2026-11-05. Red nodes are blockers, and each arrow from a blocker points at what it holds.

**Key:** blue is done, green is live, purple is running in shadow, amber is waiting or research, red is a blocker.

```mermaid
flowchart TB
    s1["1 Control plane"] --> s2["2 Normalized persistence"] --> s3["3 Rendition and crops"] --> s4["4 Shadow localization<br/>live on new images"]
    s4 --> s5["5 BioCLIP on regions<br/>live since 2026-10-15"]
    s4 --> s7["7 Repair and backfill<br/>v1 rescan kept in shadow"]
    s4 --> s6["6 Crop and fusion<br/>moved to epic #645"]
    s5 --> cov["#694 coverage<br/>28,475 unselected runs"]
    s7 --> cov
    cov --> det["Retire BioCLIP's<br/>embedded detector"]
    det --> s8["8 Retire bird_bbox<br/>#638"]
    rel["Compatibility release<br/>observed with no regressions"] --> s8
    s780["#780 RTMDet agreement<br/>bar not met, stays in shadow"]

    b1["1 of 3 judges qualified"]:::block --> cov
    b2["Small-crop species<br/>0.8123 against 0.85, #610"]:::block --> s5
    b3["About 300 labelled bursts<br/>do not exist, #415"]:::block --> s6
    b5["WebUI stopped<br/>since 2026-11-03"]:::block -.-> cov

    classDef done fill:#e0ebf4,stroke:#2c5476,color:#17222b
    classDef live fill:#dff1e6,stroke:#1c6b3f,color:#17222b
    classDef shadow fill:#ebe5f8,stroke:#5a3fa0,color:#17222b
    classDef wait fill:#f8ecd0,stroke:#80570a,color:#17222b
    classDef block fill:#fae3e1,stroke:#a12b2b,color:#17222b
    class s1,s2,s3 done
    class s4,s5 live
    class s7,s780 shadow
    class s6,cov,det,s8,rel wait
```

- Even if #694 passes, R2 accepts 6,504 runs. That leaves the 21,032 v0 runs (out of producer scope) and the 4,146 bird-tagged no-detection images uncovered, so detector retirement may need another rule or a relocalization pass (#810).
- #780 is finished. The owner review missed the bar (12.0% of false-eye regions removed, 2.6% of birds lost), so agreement stays a shadow measurement. It never gated #694 or Stage 8.
- The WebUI stopped when the laptop went to sleep on 2026-11-03. That only pauses the shadow scan, which is about 2,400 runs from the end, and does not block approval.

## Sources

- **Schema:** `migrations/versions/0034`, `0035`, `0036`, `0038`, `0043`, `0045` to `0048`.
- **Code:** `modules/localization_selection.py` (`select_region`, `revoke_selection`), `modules/bird_species.py` (`species_input_for_image`, embedded detector check), `modules/localization.py` (`write_run(publish=…)`), `scripts/maintenance/promote_localization_selections.py`.
- **Docs:** [LOCALIZATION_AUTHORITY.md](../../technical/LOCALIZATION_AUTHORITY.md), [localization-rollout.md](localization-rollout.md), [spec 08](../../specs/pipeline-streamlining/08-bird-box-agreement.md).
- **Live counts:** read-only database queries of 2026-11-05 and #694 comments of 2026-11-02.
