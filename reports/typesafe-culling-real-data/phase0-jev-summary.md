# Jev Phase-0 action Choice: real-data exploratory arm

Generated: `2026-09-22T01:31:32.399406+00:00`  
Model: `jev-1.13.0` (pinned)  
Probability status: **uncalibrated**

This is a read-only shadow experiment. Jev received structured scores, captions,
concepts, and retained-set similarity evidence. It did not receive image bytes,
file paths, or historical labels.

## Results

- Calls: 50 (50 successful, 0 failed)
- Historical labels: `{"pick": 26, "reject": 24}`
- Jev actions: `{"keep": 2, "reject": 48}`
- Direct historical-label agreement: 0.480
- Pick preservation (pick or keep rather than reject): 0.077
- Reject recall: 1.000
- Reject precision: 0.500
- Multiclass log loss: 5.365
- Multiclass Brier score: 0.865
- Mean Jev confidence: 0.556
- Mean evidence sufficiency: 0.399
- Invalid probability sums: 0

## Limits

- Historical pick/reject labels are behavior targets, not proof of safe deletion.
- No historical keep labels exist in this cohort.
- The deterministic prefix is exploratory, not a locked session-level test split.
- Pairwise visual differences were not supplied.
- Probabilities are uncalibrated.
