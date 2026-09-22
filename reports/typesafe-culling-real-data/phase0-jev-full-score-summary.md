# Jev Phase-0 action Choice: real-data exploratory arm

Generated: `2026-09-22T02:32:28.114506+00:00`  
Model: `jev-1.13.0` (pinned)  
Probability status: **uncalibrated**

This is a read-only shadow experiment. Jev received structured scores, captions,
concepts, and retained-set similarity evidence. It did not receive image bytes,
file paths, or historical labels.

## Results

- Calls: 5893 (5893 successful, 0 failed)
- Historical labels: `{"pick": 3028, "reject": 2865}`
- Jev actions: `{"keep": 3055, "pick": 194, "reject": 2644}`
- Direct historical-label agreement: 0.256
- Pick preservation (pick or keep rather than reject): 0.609
- Reject recall: 0.509
- Reject precision: 0.552
- Pick recall: 0.017
- Pick precision: 0.268
- Multiclass log loss: 5.206
- Multiclass Brier score: 0.997
- Mean Jev confidence: 0.454
- Mean evidence sufficiency: 0.482
- Invalid probability sums: 0

## Limits

- Historical pick/reject labels are behavior targets, not proof of safe deletion.
- No historical keep labels exist in this cohort.
- Pairwise visual differences were not supplied.
- Probabilities are uncalibrated.
