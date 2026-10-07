# Model selection study — exploratory evidence

Frozen 2026-10-02T00:52:09.639766+00:00. 77,331 images; 11,174 multi-image stacks.

Only aggregate evidence and provenance are published. The frozen library snapshot,
review sample and owner labels remain local and are excluded from Git. Manifest hashes
identify those private inputs; regeneration requires access to the local study folder.

Human accuracy rankings and omission decisions are pending the new blind reviews.

## Coverage and within-stack discrimination

Spread and ties describe discrimination, not correctness. Scores have different scales.

| Signal | Images | Coverage | Complete stacks | Top ties |
|---|---:|---:|---:|---:|
| aesthetic | 77,331 | 100.00% | 11,174 | 0.2% |
| arniqa | 77,331 | 100.00% | 11,174 | 0.8% |
| ava | 77,331 | 100.00% | 11,174 | 3.9% |
| clip_quality_v0 | 77,294 | 99.95% | 11,174 | 0.0% |
| general | 77,331 | 100.00% | 11,174 | 0.2% |
| koniq | 38,035 | 49.18% | 6,686 | 3.7% |
| liqe | 77,331 | 100.00% | 11,174 | 1.0% |
| paq2piq | 38,035 | 49.18% | 6,686 | 6.0% |
| refcull_composite | 76,796 | 99.31% | 11,143 | 23.7% |
| refcull_composition | 76,796 | 99.31% | 11,143 | 31.1% |
| refcull_context | 76,796 | 99.31% | 11,143 | 39.5% |
| refcull_exposure | 76,796 | 99.31% | 11,143 | 24.7% |
| refcull_eye | 76,796 | 99.31% | 11,143 | 37.7% |
| refcull_focus | 76,796 | 99.31% | 11,143 | 39.3% |
| refcull_noise | 76,796 | 99.31% | 11,143 | 53.2% |
| spaq | 77,331 | 100.00% | 11,174 | 1.9% |
| technical | 77,331 | 100.00% | 11,174 | 0.1% |
| topiq | 77,331 | 100.00% | 11,174 | 0.9% |

## Strongest model correlations

Library statistics use pairwise-complete images. Within-stack values average defined correlations
over fully scored stacks. Winner agreement credits random choice among tied maxima.

| Pair | Library ρ | Within-stack ρ | Images |
|---|---:|---:|---:|
| liqe / topiq | 0.662 | 0.266 | 77,331 |
| clip_quality_v0 / liqe | 0.618 | 0.162 | 77,294 |
| koniq / paq2piq | 0.589 | 0.243 | 38,035 |
| arniqa / liqe | 0.587 | 0.124 | 77,331 |
| arniqa / topiq | 0.575 | 0.171 | 77,331 |
| koniq / spaq | 0.560 | 0.220 | 38,035 |
| paq2piq / topiq | 0.485 | 0.176 | 38,035 |
| arniqa / clip_quality_v0 | 0.464 | 0.064 | 77,294 |
| clip_quality_v0 / topiq | 0.460 | 0.128 | 77,294 |
| koniq / topiq | 0.447 | 0.161 | 38,035 |
| spaq / topiq | 0.435 | 0.149 | 77,331 |
| paq2piq / spaq | 0.434 | 0.217 | 38,035 |

## Review sample

- Original units: {'single': 600, 'burst': 126, 'stack': 174}
- Hidden consistency repeats: 90
- Split units: {'test': 166, 'train': 510, 'validation': 224}
- Independent session/overlap blocks: 247
- Labels start empty; existing automatic ratings and picks are excluded.
- Small subgroups and too few independent test blocks cannot support omission decisions.

## Runtime

Unavailable: normalized score table has no timing column
Use the benchmark command for measured model costs. Missing times are unknown, never zero.

## Interpretation

LIQE/TOPIQ and ARNIQA/LIQE are useful ablation candidates because they share some global
ranking signal, but their within-stack agreement is much lower. This is a hypothesis to test.
KonIQ/PaQ2PiQ require matched coverage comparisons. Reference-culling dimensions are related
outputs of one research pipeline; their joint inference costs are not additive independent models.
Low correlation may reflect complementary signal or noise. Human judgments decide which.
