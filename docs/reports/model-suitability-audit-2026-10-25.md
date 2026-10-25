---
type: Report
title: Model suitability export audit
description: "External statistical audit of the 2026-10-25 model-suitability export: no independent culling labels, within-stack agreement collapse, composite-distorted partial correlation, LIQE high-end crowding, tie metric and evaluation-set defects; three defects confirmed in code (#685, #686, #687)."
resource: reports/model-suitability-audit-2026-10-25.md
tags: [score-analytics, suitability, models, culling, evaluation, report]
timestamp: 2026-10-25T00:00:00Z
okf_version: 0.2
---

# Model suitability export audit (2026-10-25)

An outside analysis of the score-analytics export `model-suitability-2026-10-25.json` (snapshot
`8f27a9e9758b18c6`, code hash `5c00406e`) and 16 dashboard PDFs, made with ChatGPT and supplied by
the owner. It works from aggregates only: no image IDs, pixels or per-stack rows. Its findings are
hypotheses about the library unless confirmed in code below.

## Confirmed in code

| Audit section | Code | Status | Issue |
|---|---|---|---|
| §10 Suitability map falls back to all data although the global test split is large | `modules/score_analytics/suitability_report.py:189-192`: one `use_test` flag, set from the **culling** test clusters, also selects the **global** evaluation set | Defect | #685 |
| §5 Partial correlation is distorted by derived composites | `modules/score_analytics/suitability.py:419`: `partial_correlation(cols)` covers all nine keys, composites included (the export's `correlation.keys`) | Defect | #686 |
| §8 `tie_fraction` is not a tie probability | `modules/score_analytics/suitability.py:187`: `1 - uniq.size / n` | Misleading name and metric | #687 |
| §12 RefCull and legacy KONIQ / PaQ-2-PiQ dimensions are not analysed | `modules/score_analytics/data.py:40-41` sets them apart (`LEGACY_MODELS`, `RESEARCH_PREFIXES`) | By design; analysing them is an enhancement | — |

The remaining sections (within-stack agreement, LIQE resolution, genre effects, the ridge
candidate, normalization provenance, proposed next export) are analysis and recommendations. They
are not filed as issues.

## Audit text

The report follows as supplied. Headings are demoted one level, links to the author's private
file library are reduced to file names, and the overview chart is omitted.

Analysis date: 2026-10-25. Sources: all 16 supplied dashboard PDFs and `model-suitability-2026-10-25.json`. JSON generated at 14:02:03 UTC, matrix at 14:00:04 UTC; snapshot `8f27a9e9758b18c6`, code hash `5c00406eacff70d0e8b32802d542bb01394b04fc`.

### Main result

The export supports a useful analysis of score geometry, redundancy, numerical resolution, genre associations, and evaluation defects. It does **not** establish which model chooses the better photograph: after the provenance filter, there are **zero culling pairs**, while global ratings are unverified.

The strongest new findings are:

1. The six actual models' mean pairwise Spearman correlation falls from **0.407 across the library to 0.140 within stacks**. Global agreement is a poor substitute for keeper agreement.
2. Including derived composites in partial correlation creates extreme conditional associations. Removing composites changes ARNIQA–TOPIQ from **−0.798 to approximately +0.330**, and AVA–SPAQ from **−0.890 to approximately +0.225**.
3. LIQE's highest-scoring 5% occupy less than **0.00595** score units. Any two scores in that range fall inside the dashboard's fixed **0.01** near-tie rule.
4. The suitability map falls back to all data even though global test estimates exist for about **3,970 groups**. AVA passes the all-data threshold but fails the stated lower-CI threshold on the test split.
5. Keyword associations are substantial: AVA is lower for street (d = −0.77) and architecture (−0.64), while CLIP Quality is higher for macro (+0.49). These are corpus associations, not proof of model bias or correctness.
6. Nine score dimensions exist in the dictionary but are absent from the nine-dimension analysis, including seven RefCull dimensions with nearly full coverage. There is more existing score data to analyze before adding models.

### 1. Scope and what can be inferred

| Quantity | Result |
|---|---:|
| Library images | 80,443 |
| Multi-image stacks | 11,358 |
| Images in stacks | 68,765 / 85.48% |
| Standalone images | 11,678 |
| Mean images per stack | 6.05 |
| Core score coverage | 79,875 / 99.29% |
| CLIP Quality coverage | 79,828 / 99.24% |
| Actual models evaluated | 6 |
| Derived composites evaluated | 3 |
| Verified manual culling images | 0 |
| Usable culling pairs after filtering | 0 |
| XMP-rated images | 65,649, provenance unverified |

This is an **aggregate export**, not an image-level dataset. It contains matrices, summaries, provenance counts, and precomputed evaluations. It does not contain image identifiers and their score rows, pixels, per-stack score lists, keyword memberships, camera strata, or run histories. Consequently, I cannot identify actual problem images, recompute stack winners, separate camera/version effects, fit a new validated ensemble, or measure false rejection rates from these files.

The calculations supplied with this report operate on the exported matrices. They are not new runs over 80,443 image records. Pooled matrices are pairwise-complete; calculations involving their inverse are approximate relative to a common complete-case fit because CLIP has 47 fewer observations. All six-model matrices used here are symmetric and positive definite. The reconstructed model R² values agree with the PDF regressions to their displayed precision.

### 2. The existing leaderboard mostly measures policy agreement

The older stacks dashboard reports General pick AUC **0.826**, top-1-is-pick **0.669**, and top-1-equals-best **0.940**. Its own text warns that agreement is circular if picks came from the composite policy. The newer suitability audit provides the decisive detail:

| Label source | Images/rows | What it establishes |
|---|---:|---|
| Manual culling | 0 images | No independent culling evidence |
| Unverified pick flags remaining after filtering | 0 images | No fallback culling evidence either |
| Auto-policy pick status | 70,632 images | Policy output, not independent truth |
| App-written XMP flags | 32,670 images | Excluded score-derived output |
| Auto suggestions | 51 rows | Excluded score-derived output |
| XMP stars | 65,649 images | Unverified global target |
| Derived images.rating | 79,869 images | Explicitly score-derived |

These groups overlap; their counts must not be summed. Of the auto-policy images, 32,712 are picks and 25,503 rejects. The pairwise model reports `pairs: 0`, and its holdout is skipped with `no pairs`.

**Interpretation:** the old AUC results can describe reproduction of the existing policy. They cannot demonstrate perceptual accuracy or justify a superior culling model. General's high agreement is expected when it helped generate the decisions; the exact origin of each `best_image_id` is not established by the export.

The 68.92% equality between XMP stars and score-derived ratings is a provenance warning, not an estimate that exactly 68.92% were copied. Conversely, the other 31.08% are not automatically independent. A cluster-disjoint holdout prevents one kind of leakage but does not repair score-derived targets.

### 3. Scene-level agreement collapses inside stacks

The six model-only pairs provide a clearer picture than correlations dominated by composites.

| Model pair | Pooled Spearman | Within-stack Spearman | Drop |
|---|---:|---:|---:|
| ARNIQA × LIQE | 0.585 | 0.163 | 0.421 |
| CLIP Quality × LIQE | 0.623 | 0.199 | 0.424 |
| ARNIQA × TOPIQ-NR | 0.569 | 0.189 | 0.380 |
| ARNIQA × CLIP Quality | 0.455 | 0.079 | 0.377 |
| LIQE × TOPIQ-NR | 0.666 | 0.318 | 0.348 |
| CLIP Quality × TOPIQ-NR | 0.461 | 0.131 | 0.330 |
| AVA × SPAQ | 0.347 | 0.096 | 0.251 |
| CLIP Quality × SPAQ | 0.350 | 0.067 | 0.283 |
| Mean of all 15 model pairs | **0.407** | **0.140** | **0.267** |

Even the strongest within-stack model-only pair, LIQE–TOPIQ, reaches only 0.318 Spearman. All 15 within-stack model pairs remain positive; this is attenuation, not a literal sign reversal. The exporter calls the analysis Simpson-type, but that does not establish Simpson's paradox or a causal explanation.

The exported within metric is described as correlation after removing each cluster's level. It should not be equated with the mean of separate per-stack Spearman correlations shown elsewhere in the UI. Pooled scores also include standalone images. A stricter follow-up would compare pooled and centered correlations on exactly the same stacked cohort and export both image-weighted and equal-stack estimators.

**Operational implication:** choosing an ensemble from pooled correlations alone risks choosing models that agree about scene content but disagree about which frame to keep. Low agreement can mean complementary cues, noise, or different preferences. It is not evidence that the most unusual model is correct.

### 4. Variance measures discrimination, not correctness

| Model | Within variance, image weighted | Within variance, cluster weighted | Median within-stack SD |
|---|---:|---:|---:|
| ARNIQA | 10.08% | 9.63% | 0.01591 |
| AVA | 8.49% | 6.32% | 0.01139 |
| CLIP Quality | 10.61% | 9.23% | 0.03498 |
| LIQE | 6.65% | 6.23% | 0.03107 |
| SPAQ | 8.23% | 7.54% | 0.02725 |
| TOPIQ-NR | 8.77% | 7.75% | 0.01428 |

Across these models, **89.4–93.3%** of score variance in the stacked cohort is between stacks. That fits near-duplicate grouping, but does not show whether the smaller within-stack variation tracks desirable changes.

Two instructive details:

- CLIP has the largest image-weighted within share, while ARNIQA has the largest cluster-weighted share. The ordering depends on the estimand.
- AVA's image-weighted share is **34.4% larger** than its equal-cluster share. This flags sensitivity to stack weighting; it does not identify which particular stack sizes or scenes cause it.

The stacks page describes higher within share as “more culling signal.” A more precise label is **within-stack score variation**. A noisy model can also have high variation. A model with low variation could still order tiny differences correctly.

### 5. Derived composites distort partial correlation

The export's partial-correlation matrix has nine dimensions: six source models plus General, Technical, and Aesthetic. Those composites are computed from source scores. Conditioning on these derived combinations can impose artificial tradeoffs between their ingredients.

| Pair | Exported partial r, including composites | Recomputed partial r, six models only |
|---|---:|---:|
| ARNIQA × TOPIQ-NR | −0.798 | +0.330 |
| AVA × SPAQ | −0.890 | +0.225 |
| CLIP Quality × LIQE | −0.044 | +0.388 |

The pooled Pearson matrix condition number is approximately **11,999.6** with composites and **15.94** for the six actual models. This is a concrete warning about interpreting the nine-variable inverse as a map of model relationships.

The six-model partial estimates were recomputed as `−P_ij / sqrt(P_ii P_jj)`, where `P` is the inverse of the model-only correlation matrix. Small common-cohort differences are possible because the pooled matrix is pairwise-complete.

**Fix:** default partial-correlation and redundancy analysis to actual model outputs only. Display composites separately as outputs to explain or audit. Keep composite-conditioned analysis only as an explicit diagnostic with its assumptions stated. This issue is separate from the OLS pages, whose actual coefficient tables already use only model predictors.

### 6. How much distinct information is present?

The exported six-model PCA uses 79,828 complete cases:

| Principal components retained | Cumulative variance explained |
|---|---:|
| 1 | 56.97% |
| 2 | 70.90% |
| 3 | 81.32% |
| 4 | 90.35% |
| 5 | 96.43% |

PC1 has the same sign across all six models. PC2 is dominated by AVA (absolute eigenvector coefficient approximately 0.844), PC3 by SPAQ (0.726), and PC4 by CLIP Quality (0.707). Component signs are arbitrary. These axes describe covariance, not independently verified quality dimensions.

Recomputing spectra from the exported matrices gives:

| Matrix, six models | First component | Participation ratio |
|---|---:|---:|
| Pooled Pearson | 56.97% | 2.72 |
| Within-stack Pearson | 36.98% | 4.55 |
| Pooled Spearman | 51.81% | 3.10 |
| Within-stack Spearman | 28.94% | 5.37 |

Participation ratio is `(sum eigenvalues)^2 / sum(eigenvalues^2)`. It is a descriptive effective-dimension measure, not the number of reliable quality signals. The within-stack scores are much less compressible into one consensus direction. They may contain both useful distinctions and independent noise.

The PDF regressions provide another view:

| Target model | CV R² predicted by the other five models | Unexplained variance, 1 − CV R² |
|---|---:|---:|
| AVA | 0.189 | 81.1% |
| SPAQ | 0.348 | 65.2% |
| CLIP Quality | 0.422 | 57.8% |
| ARNIQA | 0.519 | 48.1% |
| TOPIQ-NR | 0.647 | 35.3% |
| LIQE | 0.658 | 34.2% |

AVA is the most distinctive output under this linear reconstruction test. Dropping it because it does not significantly help predict TOPIQ confuses “predicting another model” with “contributing useful aesthetics.” Conversely, its uniqueness does not establish usefulness. No model-only Pearson pair reaches the dashboard's 0.8 redundancy threshold; its listed high correlations all involve composites.

### 7. LIQE has a high-end resolution problem for fixed thresholds

LIQE quantiles are:

| Percentile | Score |
|---|---:|
| 75 | 0.917000 |
| 90 | 0.983699 |
| 95 | 0.994055 |
| 99 | 0.999000 |
| 99.9 | 1.000000 |

The interval from the 95th percentile to the maximum is only **0.005945**. Therefore, whenever both compared images are at or above this percentile, their score difference is below 0.01. The old dashboard's near-tie rule necessarily counts those comparisons as ties. About **0.2304%**, or **184** scored images, are exactly at the upper bound; this should be distinguished from the much larger compressed upper tail.

The same epsilon represents very different scales:

| Model | 0.01 / global SD | 0.01 / median stack SD |
|---|---:|---:|
| ARNIQA | 0.158 | 0.629 |
| AVA | 0.189 | 0.878 |
| CLIP Quality | 0.079 | 0.286 |
| LIQE | 0.054 | 0.322 |
| SPAQ | 0.076 | 0.367 |
| TOPIQ-NR | 0.131 | 0.700 |

A shared 0–1 range does not make distances comparable. AVA's 0.01 threshold is nearly a full median within-stack SD, while CLIP's is under one third. Consequently, the reported near-tie rates are partly a scale comparison.

**Fix:** report exact ties, numerical precision, standardized differences, and perturbation stability separately. Rank/percentile transformations can make scale comparisons easier, but cannot recover information lost to clipping or quantization and may amplify tiny unstable differences. Do not use a transformed margin as certainty without repeatability evidence.

### 8. `tie_fraction` is not a pairwise tie probability

I verified algebraically for every exported profile that:

`tie_fraction = 1 − number_of_unique_values / number_of_observations`.

AVA has 461 unique scores and SPAQ 703 out of 79,875 observations, producing values of **99.42%** and **99.12%**. These measure how many observations remain after retaining one instance of each distinct value. They do **not** mean that 99% of randomly selected pairs or same-stack pairs tie.

The actual exact-pair tie probability requires value frequencies: `sum n_v(n_v−1) / [n(n−1)]`. Within-stack ties require those frequencies within each stack. Neither can be recovered from unique counts alone.

**Fix:** rename the profile field to `duplicate_value_fraction`; add explicitly defined exact-pair and epsilon-pair tie metrics. AVA/SPAQ's limited score levels are consistent with quantization, but this export does not reveal whether it happened in inference, normalization, rounding, or storage.

### 9. Genre associations are large enough to affect a global ranking

The keyword heatmap in PDF 14 is graphical; the following values were read visually at enlarged resolution, not extracted from the JSON. Values are displayed Cohen's d rounded to two decimals, comparing images with the keyword to the rest of the library.

| Keyword | Images | Notable associations |
|---|---:|---|
| Birds | 38,312 | LIQE +0.29; ARNIQA/AVA/TOPIQ +0.24; SPAQ −0.14; CLIP −0.09 |
| Wildlife | 52,046 | AVA +0.30; ARNIQA −0.11; General +0.01 |
| Macro | 7,668 | CLIP +0.49; ARNIQA +0.29; SPAQ −0.14; TOPIQ −0.06 |
| Insect | 6,175 | CLIP +0.27; SPAQ −0.46; TOPIQ −0.31; General −0.29 |
| Street | 5,119 | AVA −0.77; Technical +0.20; Aesthetic −0.25 |
| Architecture | 3,572 | AVA −0.64; TOPIQ +0.39; Technical +0.36; Aesthetic −0.14 |
| Cityscape | 4,274 | AVA −0.69; LIQE +0.26; Aesthetic −0.22 |
| Landscape | 7,978 | AVA −0.56; SPAQ +0.20 |
| Minimal | 10,152 | CLIP −0.66; SPAQ −0.57; General −0.54; AVA +0.07 |
| Abstract | 3,945 | General −0.64; Technical −0.61; LIQE −0.60 |
| Beach | 4,553 | AVA +0.45; CLIP −0.41; Aesthetic +0.18 |

The particularly useful tension is **macro/insects**: CLIP is elevated while SPAQ and TOPIQ are lower. This is a good cohort for investigating whether models respond differently to shallow depth of field, subject size, texture, or background treatment. Those mechanisms are hypotheses; the export contains no pixels or causal controls to choose among them.

For architecture and street, Technical rises while Aesthetic falls. The data suggest that a single global score can mix genre preference with technical evaluation. Keyword groups overlap and may correlate with camera, date, model version, and actual image quality. These effect sizes neither prove unfair bias nor justify equalizing every genre's score distribution.

**Next analysis:** keyword effects conditional on camera, date/version, stack, and available exposure/subject-size information; then within-keyword ranking and cross-keyword calibration as separate questions. Export the heatmap's numeric table with sample counts and cluster-bootstrap uncertainty.

### 10. Suitability selection appears to couple two unrelated sample-size checks

The map says `all labelled data (test split too small)`, but global test metrics exist for approximately **3,970 groups** and **13,487 images** (CLIP: 3,965 / 13,482). The declared minimum is 30 test clusters. Culling has no usable pairs, but global evaluation is not empty.

| Model | All-data weighted Spearman | Test weighted Spearman | Test lower 95% CI | Pass 0.3 threshold on test? |
|---|---:|---:|---:|---|
| LIQE | 0.579 | 0.554 | 0.533 | Yes, provisional |
| SPAQ | 0.452 | 0.440 | 0.416 | Yes, provisional |
| TOPIQ-NR | 0.432 | 0.416 | 0.391 | Yes, provisional |
| ARNIQA | 0.379 | 0.372 | 0.347 | Yes, provisional |
| CLIP Quality | 0.371 | 0.349 | 0.323 | Yes, provisional |
| AVA | 0.341 | 0.327 | **0.298** | **No** |

The all-data AVA lower bound is 0.328, so the fallback changes its displayed membership. The exact code cause is unconfirmed without source, but the selection/reporting inconsistency is observable.

**Fix:** choose evaluation sets independently for global and culling tasks. Render culling as **unknown / unmeasured**, not “unsuitable.” Label global membership **agreement with unverified XMP ratings**, even when the numeric threshold passes. Do not silently promote provisional roles into production selection.

The export uses only **200 bootstrap resamples**. AVA's threshold crossing is close enough that Monte Carlo variability in the interval endpoint matters. It is a useful demonstration of the selection inconsistency, not a firm biological or photographic boundary between good and bad models. Several exported p-values are numerically zero; interpret these as numerical underflow/display limits, not literal zero probability. Correlation inference should account for stack dependence; multiple-testing correction alone does not do that.

### 11. The exported learned global formula is not ready to deploy

The ridge candidate has standardized weights ARNIQA +0.0745, AVA +0.1851, CLIP +0.0434, LIQE +0.3699, SPAQ +0.2371, TOPIQ −0.0738; intercept 3.1337. Its reported CV Spearman is 0.6837, MAE 0.5098, against unverified stars.

Issues:

- The target may partially encode the current scoring policy. Fitting it can learn that policy again.
- The candidate exports `n=65,629`, the full complete labelled cohort, and does not export a distinct candidate holdout result. The number alone does not prove test leakage, but it is insufficient evidence of a train/dev-only fit.
- Its CV Spearman weighting is not stated. It must not be compared directly with burst-weighted single-model scores as though the metrics were identical.
- Training means/scales, selected ridge penalty, fold assignments, and foldwise preprocessing provenance are absent. The displayed equation alone is not a reproducible inference artifact.
- TOPIQ's negative coefficient is conditional on correlated predictors and this target. It does not mean better TOPIQ scores indicate worse photographs.

Keep this as a diagnostic candidate. Export the fit cohort, fold-local scaling, model artifact, and comparable holdout metrics before evaluating it for use.

### 12. Existing unused score dimensions are a substantial opportunity

The dictionary has 18 dimensions; analysis includes nine. Excluded from the analytical matrices are:

| Available dimension(s) | Rows each | Current limitation |
|---|---:|---|
| KONIQ, PaQ-2-PiQ | 38,033 | Historical partial coverage |
| RefCull composite | 79,860 | Not included in these evaluations |
| RefCull composition/context/exposure/eye/focus/noise | 79,860 | Not included in these evaluations |

RefCull coverage is approximately **99.28%** of the library. If these are separate observations already computed, their disagreement with the six current models could expose useful blind spots. Their names alone do not establish accuracy, and if they are LLM-produced or otherwise derived, that provenance must remain explicit.

Analyze them first as **candidate signals**, never as ground truth. Export native raw scores, missingness, scales, uncertainty if any, and within-stack ranks. For legacy models, compare on a matched intersection and stratify by time/camera; comparing their 38,033-image history with the full modern cohort would confound model and cohort effects.

### 13. Normalization, provenance, and snapshot consistency

There are several audit leads rather than demonstrated normalization failures:

- AVA, LIQE, and SPAQ each have 54,399 `legacy-backfill` rows, 22,972 `5.0.0` rows, and 2,504 `5.2.0` rows. Thus **68.1%** use the legacy-backfill version label. Compare distributions, quantization, and score mappings by these cohorts before fitting a shared calibration.
- Raw extrema span different apparent units: AVA 0.136–6.53, LIQE approximately 0.00047–5, SPAQ 0.096–80.18. These extrema do not alone prove mixed units, but the legacy provenance makes the mapping worth auditing. Every existing evaluated row has a normalized value; missing-normalized fallback is not currently evidenced as the cause.
- Some `first_scored` timestamps are in 2013 even though the version is legacy-backfill. Verify whether these mean capture/import time rather than actual model execution time. They cannot safely support temporal model-drift claims without clarification.
- The same **568 images** lack every core score; CLIP is missing on **47 additional images**. This follows from the exact co-missingness matrix and coverage counts. It points first toward a shared coverage cohort, not six independent failures, but the actual cause requires IDs and statuses.
- The dictionary's zero failures and zero not-loaded counts describe recorded score rows, not necessarily the entire library queue. They do not explain the 568 absent cases.
- Earlier PDFs use 79,862 core observations; the JSON and later correlation PDF use 79,875, a difference of 13. The dashboard showed active scoring. These are not a single perfectly frozen snapshot, although rounded correlations are stable.
- `git_sha` is null. Query/code hashes and deterministic options are helpful, but retain the actual implementation revision for reproducibility.
- One row per image/model means run-to-run stability is currently unmeasurable. Record append-only runs before interpreting tiny margins as robust.

### 14. Composite regressions explain implementation, not photographic validity

General, Technical, and Aesthetic have CV R² values **0.969, 0.959, 0.978** when predicted from component scores. Since the targets are derived from those components, these results mostly show recoverability of the implemented fusion.

General's standardized regression coefficients are largest for LIQE (0.517) and SPAQ (0.421). Aesthetic is dominated by SPAQ (0.682) and AVA (0.458). These are conditional regression coefficients, not fractions of causal contribution; correlated features prevent that interpretation.

The rendered composite residual plots visibly contain structure, consistent with a nonlinear transformation, clipping, mixed implementations, or other omitted behavior. The export describes percentile-rescaled fusion, but the files do not identify the exact cause of each residual pattern. The generic “no overfitting detected” note is too broad: the PDFs do not document group-disjoint folds, and equal train/CV R² alone does not establish deployment validity.

Similarly, “log or rank transform” should not be triggered solely because ARNIQA/TOPIQ are left-skewed. OLS does not require normally distributed predictors; an ordinary log often stretches the low-end tail. Choose transformations for the actual task and validate residuals/ranking behavior rather than making histograms look normal.

### 15. Work that can proceed without new human or LLM labels

The current absence of independent labels need not stop engineering. It limits which claims can be made.

#### A. Repair the measurements first

1. Freeze a snapshot; export stable image, stack, run, and provenance IDs.
2. Exclude composites from model partial-correlation and feature-redundancy defaults.
3. Separate global/culling holdout eligibility and render missing evidence explicitly.
4. Replace ambiguous tie metrics; preserve model-native precision.
5. Add the existing RefCull/legacy scores to descriptive analyses on matched cohorts.
6. Export keyword effects and per-stack diagnostics, not only charts.

#### B. Build objective technical tests with narrow claims

On a fixed, versioned cohort, generate controlled blur, downsampling, compression, noise, and highlight-clipping ladders. Measure monotonic response and ordering violations for the corresponding technical dimension. Mild changes can sometimes improve perceived images, so specify transformations/severity ranges where the intended technical loss is defensible. These tests validate response to known degradations; they do not provide ground truth for composition, pose, expression, or the best original frame.

Measure repeatability under nuisance changes such as harmless encoding/resizing choices, and record score variation and top-k winner stability. Eye/subject crops can be separate inputs for focus diagnostics if valid regions are available; crop scores are not automatically interchangeable with whole-frame scores. The present attachments cannot run these experiments because they contain no source images.

#### C. Use disagreement to manage selection uncertainty

For each stack, calculate actual-model ranks, top-k overlap, pairwise order disagreement, native-score margins, and stability across specified perturbations. Do not count General/Technical/Aesthetic as three additional votes. Use these measures to produce candidate sets and explicit abstention when the ordering is unstable; agreement is a consistency signal, not a calibrated probability of correctness.

A deterministic policy can retain a stable leader plus a different-frame candidate when the models disagree, or use a Pareto candidate set across clearly defined dimensions. These are proposed operational policies, not optimized weights established by this export. Choose the retention budget from the user's workflow and evaluate loss/stability before automatic rejection.

#### D. Minimum next export

One row per image/model/run should include:

`image_id, stack_id, session_id, model_id, model_version, raw_score, normalized_score, normalizer_version, inference_timestamp, input_hash, preprocessing_version`.

Joinable image metadata should include camera/lens, capture time, exposure/ISO, dimensions, keyword memberships with provenance, and optional verified subject/eye regions. Label events need `label_value, origin, actor_or_policy, timestamp, policy_version, score_snapshot_id`; never infer independent labels merely from storage in XMP. Preserve run history rather than overwriting it.

With these records, the next mining pass can identify concrete stacks, measure whether disagreement is concentrated in genre/camera/version cohorts, and audit wrong-unit or quantization hypotheses. Independent preference accuracy remains a separate question even after these engineering tests pass.

### Evidence index and reproducibility

| Source | Used for |
|---|---|
| `model-suitability-2026-10-25.json` | Primary aggregate data; provenance, profiles, correlations, PCA, variance, split, labels, candidate model, suitability |
| `Vexlum Scoring.pdf` | Distributions and descriptive statistics |
| `Vexlum Scoring 2.pdf` | Earlier correlation snapshot |
| `Vexlum Scoring 3.pdf` | General regression and fusion weights |
| `Vexlum Scoring 4.pdf` | Technical regression and fusion weights |
| `Vexlum Scoring 5.pdf` | Aesthetic regression and fusion weights |
| `Vexlum Scoring 6.pdf` | ARNIQA regression |
| `Vexlum Scoring 7.pdf` | AVA regression |
| `Vexlum Scoring 8.pdf` | CLIP regression |
| `Vexlum Scoring 9.pdf` | LIQE regression |
| `Vexlum Scoring 10.pdf` | SPAQ regression |
| `Vexlum Scoring 11.pdf` | TOPIQ regression |
| `Vexlum Scoring 12.pdf` | Old pick-agreement metrics, near-tie definition, stack comparisons |
| `Vexlum Scoring 13.pdf` | Suitability UI and provenance explanations |
| `Vexlum Scoring 14.pdf` | Visually transcribed rounded keyword effect sizes |
| `Vexlum Scoring 15.pdf` | Pooled/within metric explanations and missing subgroup results |
| `Vexlum Scoring 16.pdf` | Later correlation snapshot |

The original bundle also held the supplied JSON, `mine_vexlum.py`, `derived_metrics.json`, an overview plot and the keyword transcription. They are not committed. PDF-only values are attributed above. No source scores, labels, policies or files were changed.
