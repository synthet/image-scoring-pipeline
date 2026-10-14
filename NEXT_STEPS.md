# Localization rollout — next steps

## Current handoff — 2026-10-12

PR [#594](https://github.com/synthet/image-scoring-pipeline/pull/594) merged the
implementation and gate reports into `master` at **`0e24a43`**. Local `master`
matches that merge. Thirty-eight targeted tests, scoped ruff, seven scoped OKF
documents and staged whitespace checks passed before delivery. The separate
agent-panel gate analysis is complete:

- Cascade AC-17/AC-18 pass: TIGHT 98/141 versus YOLO 97/140; independent recall
  65/78 versus 63/78, false positives 5/71. Twenty-three box judgments remain
  unresolved after confidence-filtered Jev adjudication.
- Rule/4 geometry passed earlier: 128/128 resolved usable boxes from 130 fresh
  frames. The small-species gate **fails**: precision lower bound 0.8123 < 0.85.
  The four-judge quorum stayed at three matching votes. Codex, Antigravity and
  Cursor completed 120/120; Claude was quota-limited. Blind descriptions covered
  all 31 splits, with zero detected leaks; Jev resolved 3, leaving 28 unresolved.
- The passing earlier 4,401-image species gate and 200/200 production-path parity
  check remain separate evidence. Neither overrides the small-species failure.
- No promotions, rollout flag changes or species/keyword refresh occurred.
  Read-only MCP confirmed job 6945 paused. PostgreSQL and GPU-shell are running;
  WebUI is stopped. Unrelated dirty release, list-research and setup files remain.

Read [the final gate report](docs/reports/localization-agent-panel-gates-2026-10-12.md).
All source replies and completed inference stay intact. Frozen analysis copies,
SHA-256 receipt, consensus, baseline/final gates, blind descriptions and Jev
responses live in ignored `.agent/scratch/rollout-20261012-resume/`.

**Next action:** retain the failed small-species gate. Geometry-only small-box
promotion needs an explicit consumer exclusion for small selections before they
can feed region species; that behavior is not implemented by this continuation.
Alternatively gather independent reviewed evidence under a new preregistered
evaluation. Do not lower the gate or repeat inference over completed artifacts.
The implementation is delivered; live enablement is a separate remaining task.
Passing large/medium species and shadow cascade changes still need a running-code
version check, fresh state/keyword-preservation checks and a verified DB backup
before production writes. Keep WebUI stopped and portrait job 6945 paused.

## Remaining tasks in order

1. **Small selections (#593):** decide and implement a tested exclusion from
   region species before any geometry-only promotion, or preregister new
   independently reviewed species evidence. Retain the failed 0.8123/0.85 gate.
2. **Large/medium species activation:** verify the deployed process uses the
   merged selection reader, the frozen 369-name list and strict `> 0.5` floor;
   back up PostgreSQL, snapshot keywords, and refresh only the approved cohort
   with preservation checks. #592 closed automatically when #594 merged; that
   issue closure does not establish live enablement or refresh completion.
3. **Cascade shadow activation (#408):** verify merged runner wiring and its
   0.60/no-retry operating point, back up before a flag write, and observe
   provenance-stamped `coco`/`subject_cascade` runs in the next authorized lane.
   A consumer-source promotion needs its own selection rule and gate.
4. **Operational follow-ups:** retain production retry-timing and mounted-source
   filesystem diagnosis. Resume portrait job 6945 only within the separate #418
   task; verify scores, captions and keyword/species restoration before closure.
5. **Later stages:** #415 human labels, #409 storage/fusion and #423 evidence
   precede Stage 6; Stage 8 still requires exercised selection/read rollback.
   Release 9.0.0 and the unrelated list/setup work remain separate.

For other tracks, use [scoring-input next steps](docs/planning/scoring-inputs/NEXT-STEPS.md),
[database next steps](docs/planning/database/NEXT_STEPS.md), and
[embedding next steps](docs/features/planned/embeddings/NEXT_STEPS.md).
The GitHub Project board remains the canonical queue. #593's Blocked update and
#592's Review update could not be made because neither issue was found on it;
reconcile operational follow-up tracking rather than treating closure as deployment.

## Historical October 10 handoff

The stopped-Docker state and code follow-ups below describe October 10; use the
current handoff above for continuation. Its frozen inference artifacts remain valid.

Updated 2026-10-10 after the frozen species comparison, timeout diagnosis and requested Docker shutdown.
Workspace: D:\Projects\image-scoring-backend. Branch: master; HEAD remains 2269ef1.

## Completed continuation

- The committed 369-species / 0.5 comparison has exactly 4,401 distinct expected final results, zero skips. Both partitions passed (2,201 and 2,200).
- Outcomes: same 2,961; changed 753; newly labelled 234; now abstains 403; both abstain 50. This is stored-label agreement evidence, not labelled accuracy or promotion approval.
- Final read-only preflight and merge verified unchanged source metadata, selected geometry/identities, stored baseline, classifier/canonical/decoder/cropper hashes, cached model revision and identical preprocessing.
- Mounted-source ExifTool extraction repeatedly hit its existing ten-second timeout. Byte-identical local staging reproduced two retained controls exactly and unblocked the remaining inference without changing canonical inference or original photos.
- Final merge verified preserved prior successes, 1,660 source/staged hash bindings, decode/crop provenance for all 4,401 results, and removal of owned temporary copies. Routes: 4,399 raw_preview, 2 direct.
- Selected-region keypoints were already complete: 4,370 detected, 31 no_keypoints. Stage 4 live lane observation remains historical evidence; registration boundary fix #585 / revision 0041 is merged and deployed. Production retry timing remains unobserved.

## Current operational state

- At the user's request, the PostgreSQL/GPU-shell containers were stopped and Docker Desktop shut down. WebUI stayed stopped. Do not restart processing until requested.
- Portrait job 6945 remains paused. No production job was submitted or resumed by this continuation.
- No keywords, scores, localization selections, phase status, rollout flags or original photos changed. Region reads and crop scoring were not promoted.
- Release 9.0.0 and unrelated research/hook changes remain uncommitted and preserved. No commit or push occurred.

## Retained evidence

Read [the aggregate report](docs/reports/localization-species-policy-validation-2026-10-10.md)
and [the rollout status](docs/architecture/pipeline/localization-rollout.md).
Private artifacts stay under ignored `.agent/scratch/`:

- `localization-policy-20261010-full.json/.md`: final full-cohort evidence.
- `localization-policy-20261010-part-0-recovered.json` and `localization-policy-20261010-part-1-staged-prefetch.json`: verified complete halves.
- `localization-policy-20261010-staging-probe.json`, `localization-policy-20261010-postflight.json` and `localization-policy-20261009-contract.md`: control, final-state and bounded-run provenance.
- Frozen `localization-policy-20261009-*` inputs, all intermediate checkpoints, excluded/accepted pilots and the historical 2,741-result partial audit remain intact.
- Earlier manifest, 360-species/0.1 results and strict-repair test evidence remain intact. Ten historical stored labels were missing before this snapshot; historical predictions do not isolate list effects.
- CPU-only ExifTool diagnosis: separate `exiftool-timeout-diagnosis-20261010T225631Z/` and `exiftool-timeout-diagnosis-20261010T225806Z/` artifacts. First probe reproduced three mounted timeouts and nine successful local extractions; second probe observed input reads waiting in 9p RPC and completed without timeouts. See the session work log's diagnosis/shutdown continuation.

Do not re-run the completed partitions or merge over these artifacts. The merge refuses existing
full-output paths. For a fresh read-only frozen-state check:

```text
docker exec -e PYTHONPATH=/app -e HF_HUB_OFFLINE=1 image-scoring-gpu-shell timeout 300 python /app/.agent/scratch/localization-policy-20261010-preflight.py --after
```

## Next work

1. Review full-cohort agreement and the separate labelled/second-folder gate before Stage 5 promotion. #422 strict-above-0.5, scene-routed non-birds and range-list follow-ups remain separate. No prediction equalled 0.5 in this cohort.
2. Production Stage 4 retry timing still needs a real failure or an explicit decision to accept isolated-test evidence. The manual shadow extraction failures do not supply production retry evidence.
3. Mounted-source/ExifTool diagnosis reproduced the ten-second timeout without a GPU model: the child waited in `p9_client_rpc` on the 9p source filesystem; identical local copies succeeded. A follow-up confirmed input-descriptor reads on this path but had no timeouts. Host-side cause remains unknown. Trace 9p/storage delays or evaluate a pixel-equivalent production mitigation separately. Decoder, timeout and completed comparison remain unchanged; preserve this baseline for later changes.
4. The separate portrait/release work remains in docs/reports/localization-rollout-next-steps-2026-10-09.md. Resume 6945 only within that task, verify scores/keywords/captions, restore species and close #418 afterward. Release 9.0.0 delivery remains unrequested here.
5. Stage 6 waits on #415 labels, #409 storage/fusion and #423 evidence; detector adoption/vision judging and Stage 8 retirement remain separate gates.

Keep `.agent/scratch/418/`, `422/`, `stage5-nef/` and existing database backups.
The earlier handoff is retained in commit 2269ef1 and local
`localization-policy-20261010-handoff-history.md`; its paused commands are historical.
Never modify `.git/config`, stage unrelated dirty files, publish private photo artifacts,
rewrite production keywords or flip rollout flags as part of this completed shadow comparison.
