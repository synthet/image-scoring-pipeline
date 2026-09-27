---
type: Archive
title: "Raw source — Visual Domain Router and Specialist Image Analysis (design proposal, 2026-09-27)"
description: "Immutable user-provided design proposal for a multi-label visual domain router and bird / animal / macro specialist analysis. Ingested into docs/planning/visual-domain-router.md."
resource: docs/raw/2026-09-27-visual-domain-router-design.md
tags: [raw, design, routing, scene, localization, evidence, macro]
timestamp: 2026-09-27T00:00:00Z
okf_version: 0.1
---

# Visual Domain Router and Specialist Image Analysis

**Project:** Vexlum Scoring / Driftara Gallery  
**Primary repository:** `image-scoring-backend`  
**Consumer:** `image-scoring-gallery`  
**Status:** Design proposal  
**Purpose:** Introduce a preliminary visual-domain routing stage that selects specialist analysis workflows for birds, other animals, macro subjects, and future photographic domains.

---

## 1. Summary

The scoring pipeline should not treat every photograph as the same kind of image.

A global image-quality model can estimate generic properties such as aesthetics, blur, exposure, or technical quality, but wildlife and macro culling often depends on **where** quality occurs and **what the important subject anatomy is**.

Examples:

- A bird photograph may be globally soft while the eye and head are critically sharp.
- A technically sharp bird photograph may actually be misfocused because the background is sharper than the eye.
- A macro photograph can have extremely shallow depth of field by design; global sharpness is therefore a poor rejection signal.
- In a burst, several frames may have nearly identical generic quality scores while differing strongly in eye focus, wing position, pose, occlusion, or expression.

This design introduces a lightweight **Visual Domain Router** before expensive specialist analysis.

The router identifies applicable workflows rather than forcing every image into one mutually exclusive scene class.

```text
Image / RAW Preview
        |
        v
+----------------------------+
| P1 Visual Domain Router    |
+----------------------------+
        |
        +--> wildlife.bird
        |
        +--> wildlife.animal
        |
        +--> macro.arthropod
        |       +--> insect
        |       +--> spider
        |
        +--> macro.botanical
        |
        +--> landscape
        |
        +--> portrait
        |
        +--> generic
```

The selected specialist workflow produces normalized semantic evidence:

```text
domain
subjects
bounding boxes
segmentation masks
taxonomy/species
anatomical regions
eyes
pose
visibility
occlusion
regional sharpness
regional exposure
background separation
other domain-specific observations
```

Those observations remain separate from the final scoring and culling decision.

```text
Visual Analysis
      |
      v
Normalized Evidence
      |
      v
Domain Scoring
      |
      v
Cluster-relative Features
      |
      v
Statistical / Learned Meta-model
      |
      v
P(Pick), P(Keep), P(Reject)
```

This separation allows the scoring methodology to evolve without rerunning expensive visual inference.

---

## 2. Goals

### Primary goals

1. Detect the photographic domain before running specialist models.
2. Support multiple simultaneous workflows for one image.
3. Detect important subjects and anatomical regions.
4. Measure image quality locally rather than only globally.
5. Support fine-grained species/taxonomy classification.
6. Produce normalized evidence consumable by scoring and culling models.
7. Improve comparison of near-duplicate images inside stacks/clusters.
8. Preserve raw observations independently of scoring policy.
9. Allow new photographic domains to be added without redesigning the pipeline.
10. Provide explainable evidence for Pick / Keep / Reject decisions.

### Non-goals

The router itself should **not**:

- decide Pick / Keep / Reject;
- replace existing generic IQA models;
- perform full species classification;
- encode final weighting rules;
- assume exactly one subject;
- assume exactly one applicable workflow.

---

## 3. Canonical Sources and Cross-Repository Contract

Before implementing a formal pipeline or schema change, verify and update the backend canonical sources.

Backend authority:

- `docs/CANONICAL_SOURCES.md`
- `docs/technical/API_CONTRACT.md`
- `docs/reference/api/openapi.yaml`
- `docs/technical/PIPELINE_TERMINOLOGY.md`
- `docs/technical/DB_SCHEMA.md`
- `docs/technical/AGENT_COORDINATION.md`

Supporting documentation likely affected:

- `docs/ARCHITECTURE.md`
- `docs/DATABASE.md`
- `docs/IMAGE_PIPELINE.md`
- `docs/TESTING.md`
- `docs/DIAGNOSTICS.md`
- `docs/log.md`

The backend contract should be changed first.

`image-scoring-gallery` should consume the backend terminology and API/schema contract rather than defining parallel names.

---

## 4. Core Design Principle: Routing, Not Classification

The first stage should be called **Visual Domain Router** or **Workflow Router**, rather than simply "scene classifier."

A conventional classifier might produce:

```json
{
  "class": "bird",
  "confidence": 0.97
}
```

That is unnecessarily restrictive.

A better representation is multi-label:

```json
{
  "workflows": [
    {
      "type": "wildlife.bird",
      "confidence": 0.97,
      "priority": 1
    },
    {
      "type": "photography.action",
      "confidence": 0.84,
      "priority": 2
    }
  ]
}
```

Possible compositions include:

```text
Bird in flight
    wildlife
    wildlife.bird
    photography.action

Perched bird
    wildlife
    wildlife.bird
    photography.portrait_like

Dragonfly
    wildlife
    wildlife.insect
    macro
    macro.arthropod

Spider
    wildlife
    wildlife.spider
    macro
    macro.arthropod
```

A workflow can therefore inherit or combine evidence from multiple specialist analyzers.

---

## 5. Proposed Pipeline

The exact phase identifiers must be aligned with the canonical backend pipeline terminology before implementation.

Conceptually:

```text
P0  Metadata / Preview Preparation
        |
P1  Visual Domain Routing
        |
P2  Subject Detection / Segmentation
        |
P3  Domain Specialist Analysis
        |
P4  Anatomy / Semantic Region Detection
        |
P5  Regional Quality Measurement
        |
P6  Taxonomy / Species / Semantic Understanding
        |
P7  Generic + Domain Feature Aggregation
        |
P8  Stack / Cluster-relative Analysis
        |
P9  Pick / Keep / Reject Decision
```

These are **conceptual stages**, not proposed canonical phase codes.

Do not add these identifiers to code until they have been reconciled with:

`docs/technical/PIPELINE_TERMINOLOGY.md`

---

## 6. Conditional Execution

Not every image should run every model.

Example:

```text
Landscape
  router
    -> generic IQA
    -> landscape analysis

Bird
  router
    -> bird detector
    -> bird segmentation
    -> anatomy / eyes
    -> species classifier
    -> regional IQA
    -> bird-specific features

Macro spider
  router
    -> arthropod detector
    -> spider classifier
    -> spider anatomy
    -> focal-region analysis
    -> macro-specific features
```

This provides two benefits:

1. specialist inference is only performed where useful;
2. expensive models can be deferred until a cheaper model establishes sufficient probability.

---

## 7. Router Output

A preliminary representation might look like:

```json
{
  "domains": {
    "wildlife": 0.99,
    "bird": 0.96,
    "animal": 0.99,
    "macro": 0.18
  },
  "workflows": [
    {
      "type": "wildlife.bird",
      "confidence": 0.96
    }
  ],
  "subjects": [
    {
      "class": "bird",
      "bbox": [0.31, 0.19, 0.73, 0.84],
      "confidence": 0.98
    }
  ],
  "scene": {
    "subject_count": 1,
    "dominant_subject": 0,
    "background_complexity": 0.31
  }
}
```

This is illustrative only. The final API and persistence structures must follow the backend contract and schema conventions.

---

## 8. Common Semantic Evidence Model

All specialist workflows should emit a shared logical representation.

```text
ImageAnalysis
 |
 +-- scene
 |
 +-- workflows[]
 |
 +-- subjects[]
 |    |
 |    +-- taxonomy
 |    +-- bbox
 |    +-- mask
 |    +-- confidence
 |    |
 |    +-- parts[]
 |    |    |
 |    |    +-- type
 |    |    +-- bbox / mask / keypoints
 |    |    +-- visibility
 |    |    +-- sharpness
 |    |    +-- exposure
 |    |    +-- clipping
 |    |    +-- occlusion
 |    |    +-- confidence
 |    |
 |    +-- attributes
 |
 +-- global_quality
 |
 +-- workflow_features
```

The important abstraction is:

> Bird eyes, mammal eyes, insect eyes, spider eye regions, heads, wings, and other structures are semantic parts of a detected subject.

This avoids adding a dedicated database column for every possible anatomical measurement.

---

# 9. Bird Specialist Workflow

Bird photography should be one of the first specialist implementations because the culling criteria are well defined and strongly dependent on localized analysis.

## 9.1 Subject detection

Detect:

- individual birds;
- bounding boxes;
- optional segmentation masks;
- subject confidence;
- dominant subject;
- multiple subjects.

## 9.2 Taxonomy

The workflow may progressively determine:

```text
bird
  -> order
  -> family
  -> genus
  -> species
```

Fine-grained species classification should generally operate on a detected/cropped bird rather than the entire source image.

Example:

```text
bird detected: 0.997

Kingfisher family:      0.98
Belted Kingfisher:      0.93
Ringed Kingfisher:      0.04
Green Kingfisher:       0.01
```

Store alternatives and confidence rather than only the top label.

## 9.3 Bird anatomy

Candidate semantic regions:

- head;
- left eye;
- right eye;
- beak;
- body;
- wings;
- tail;
- feet/legs.

Depending on model capability, representation can use:

- bounding boxes;
- segmentation masks;
- landmarks/keypoints;
- combinations of the above.

## 9.4 Bird-specific technical evidence

Measure:

- eye sharpness;
- head sharpness;
- body/feather detail;
- wing sharpness;
- motion blur;
- local exposure;
- highlight clipping;
- shadow clipping;
- subject/background focus separation;
- occlusion;
- subject visibility.

Example:

```text
Global sharpness       0.71
Bird sharpness         0.83
Head sharpness         0.91
Eye sharpness          0.96
Background sharpness   0.35
```

This may represent a strong bird photograph despite mediocre global sharpness.

Conversely:

```text
Global sharpness       0.89
Bird sharpness         0.75
Eye sharpness          0.42
Background sharpness   0.96
```

is evidence consistent with focus landing away from the intended subject.

The scoring layer, not the detector, should decide how strongly this affects culling.

## 9.5 Bird-specific semantic/aesthetic evidence

Potential features:

- eye visibility;
- catchlight;
- head angle;
- gaze direction;
- pose;
- wing position;
- wing clipping;
- tail clipping;
- branch/vegetation occlusion;
- subject isolation;
- background interference;
- behavioral interest;
- flight/action state.

These should initially be observations, not hard-coded rejection rules.

---

# 10. General Animal Workflow

The animal workflow can share much of the bird infrastructure.

Possible anatomy:

```text
Animal
 |
 +-- head
 +-- left eye
 +-- right eye
 +-- nose / muzzle
 +-- body
 +-- limbs
 +-- tail
```

Potential evidence:

- eye visibility;
- eye sharpness;
- head sharpness;
- fur/detail quality;
- pose;
- gaze direction;
- body truncation;
- limb truncation;
- occlusion;
- subject/background separation.

Multiple animals must be first-class.

Example:

```text
animal[0]
    eye_sharpness = 0.94
    pose_quality = 0.87

animal[1]
    eye_sharpness = 0.31
    pose_quality = 0.79
```

The scoring layer can distinguish:

- one sharp primary subject with secondary animals;
- two intentionally important subjects;
- one accidentally out-of-focus member of a group.

---

# 11. Macro Workflow

Macro should be treated as a photographic domain with nested subject-specific analyzers.

Suggested hierarchy:

```text
macro
 |
 +-- arthropod
 |     |
 |     +-- insect
 |     +-- spider
 |     +-- other
 |
 +-- botanical
 |
 +-- fungi
 |
 +-- other
```

Macro analysis must not assume that low global sharpness means poor quality.

The key question is often:

> Is the intended anatomical or compositional focal plane sharp?

---

## 11.1 Insect Workflow

Potential semantic parts:

```text
Insect
 |
 +-- head
 +-- left compound eye
 +-- right compound eye
 +-- antennae
 +-- thorax
 +-- abdomen
 +-- wings
 +-- legs
```

Potential evidence:

- eye sharpness;
- head sharpness;
- compound-eye detail;
- antenna visibility;
- wing detail;
- subject-plane sharpness;
- depth-of-field coverage;
- background separation;
- occlusion;
- highlight clipping;
- diffraction/softness evidence.

---

## 11.2 Spider Workflow

Potential semantic regions:

```text
Spider
 |
 +-- cephalothorax
 +-- abdomen
 +-- eye region
 +-- visible individual eyes (optional)
 +-- legs
```

Potential evidence:

- eye-region sharpness;
- cephalothorax sharpness;
- body detail;
- leg visibility;
- leg truncation;
- focal-plane placement;
- depth-of-field coverage;
- subject/background separation.

Individual eye detection should be optional because visibility and scale vary dramatically between images and taxa.

---

## 11.3 Macro Quality Example

A good macro photograph might produce:

```text
Global sharpness       0.38
Subject sharpness      0.62
Eye sharpness          0.97
Background sharpness   0.04
```

A generic IQA pipeline might penalize this image.

A macro-aware pipeline can recognize that the critical subject region is exceptionally sharp while the background is intentionally defocused.

---

# 12. Generic and Specialist Models Must Coexist

Existing global models remain useful.

Conceptually:

```text
                     Generic IQA
                         |
          +--------------+--------------+
          |              |              |
          v              v              v
        Bird           Animal          Macro
          |              |              |
       eyes/head       eyes/head      focal plane
       feathers        fur/detail     eye/detail
       wings           pose           DOF
       pose             limbs          subject detail
       background       background     background
```

The final feature set can contain:

```text
generic quality scores
+
domain-specific measurements
+
semantic observations
+
cluster-relative measurements
```

The meta-model decides how those signals interact.

---

# 13. Keep Observation Separate From Judgment

This is a critical design rule.

Store:

```text
eye_sharpness = 0.91
background_sharpness = 0.42
eye_visibility = 0.98
wing_occlusion = 0.07
```

Do not prematurely convert them into:

```text
bird_quality = 87
```

and discard the underlying measurements.

The desired architecture is:

```text
specialist inference
        |
        v
raw semantic evidence
        |
        +--------------------------+
        |                          |
        v                          v
 current scoring model       future scoring model
        |                          |
        v                          v
 culling decision            different decision
```

This allows scoring methodology to change without rerunning expensive detection and anatomy models.

---

# 14. Stack / Cluster-Aware Analysis

This architecture becomes especially valuable during burst culling.

Suppose cluster `C17` contains 12 frames of the same bird.

Shared context:

```text
domain = wildlife.bird
species = Scissor-tailed Flycatcher
activity = flight
```

Per-frame observations:

| Frame | Eye | Head | Wings | Pose | Occlusion |
|---|---:|---:|---:|---:|---:|
| 1001 | .62 | .71 | .91 | .72 | .03 |
| 1002 | .81 | .84 | .94 | .77 | .02 |
| 1003 | .94 | .93 | .91 | .88 | .01 |
| 1004 | .91 | .92 | .98 | .96 | .00 |

The cluster analyzer can derive relative features:

```text
eye_rank
head_rank
wing_position_rank
pose_rank
occlusion_rank
generic_quality_rank
```

The decision system can then explain:

```text
Frame 1004

Eye sharpness:       #2 / 12
Head sharpness:      #2 / 12
Wing pose:           #1 / 12
Occlusion:           #1 / 12
Generic IQA:         #3 / 12
```

This is substantially more useful for wildlife culling than comparing only global IQA scores.

---

# 15. Shared Analysis Across a Cluster

Expensive semantic work should be reusable where appropriate.

For a burst:

```text
cluster
 |
 +-- shared domain hypothesis
 +-- shared species hypothesis
 +-- shared activity/context hypothesis
 |
 +-- frame 1 subject/anatomy/quality
 +-- frame 2 subject/anatomy/quality
 +-- frame 3 subject/anatomy/quality
 ...
```

However, shared inference must not erase real frame-level changes.

Examples requiring frame-level analysis:

- eye becomes hidden;
- wing position changes;
- head turns;
- subject moves outside the focal plane;
- vegetation crosses the subject;
- a second animal enters the frame.

Cluster-level reuse should therefore be an optimization and prior, not a substitute for frame analysis.

---

# 16. Model Provenance

Every stored observation should retain enough provenance to make experiments reproducible.

Conceptually:

```json
{
  "feature": "eye_sharpness",
  "value": 0.91,
  "confidence": 0.96,
  "model": "example-model",
  "model_version": "x.y",
  "workflow": "wildlife.bird",
  "analyzer_version": "1"
}
```

Exact persistence fields must be designed against the existing backend schema.

At minimum, preserve the ability to determine:

- which model produced the observation;
- model/checkpoint version;
- preprocessing version;
- workflow/analyzer version;
- confidence;
- source image/preview identity;
- inference timestamp or run identity where appropriate.

---

# 17. Confidence and Fallback Behavior

No specialist workflow should require perfect routing.

Suggested behavior:

```text
high confidence
    -> run specialist workflow

medium confidence
    -> run cheap confirmation detector
    -> specialist workflow if confirmed

low confidence
    -> generic pipeline
```

Multiple workflows can run when confidence warrants it.

Example:

```text
bird        0.91
macro       0.82
animal      0.98
```

The system should not be forced to choose exactly one.

---

# 18. Failure Isolation

A specialist model failure should not invalidate the entire image.

Example:

```text
router                 OK
bird detector          OK
eye detector           FAILED
species classifier     OK
generic IQA            OK
```

The result remains useful.

The scoring layer should receive missingness explicitly rather than fabricated defaults.

Bad:

```text
eye_sharpness = 0
```

Better:

```text
eye_sharpness = null
eye_sharpness_status = unavailable
```

The exact representation should follow existing backend result conventions.

---

# 19. Persistence Strategy

Before adding tables or columns, inspect:

- `docs/technical/DB_SCHEMA.md`
- current Alembic migrations;
- existing model-score persistence;
- embedding/result metadata conventions.

A flexible normalized or semi-structured evidence representation is preferable to creating columns such as:

```text
bird_left_eye_sharpness
bird_right_eye_sharpness
spider_eye_sharpness
insect_antenna_visibility
...
```

because the specialist taxonomy will grow.

Logical entities may include:

```text
analysis run
workflow result
subject
subject part
taxonomy hypothesis
measurement
model provenance
```

These are conceptual entities, **not proposed table names**.

---

# 20. API Design

Do not invent a new REST endpoint until the existing backend API contract has been reviewed.

If analysis evidence becomes externally visible, update in this order:

1. backend response/data model;
2. `docs/technical/API_CONTRACT.md`;
3. `docs/reference/api/openapi.yaml`;
4. backend implementation;
5. backend tests;
6. gallery API client/types;
7. gallery UI.

The gallery should not query specialist database structures directly from the renderer process.

Any DB/filesystem integration in Driftara Gallery must remain behind the Electron main-process / preload / IPC boundary.

---

# 21. Driftara Gallery Opportunities

Once the backend contract exposes the evidence, the gallery could optionally visualize:

- detected subject bounding boxes;
- eye/head regions;
- species hypotheses;
- confidence;
- eye sharpness;
- head sharpness;
- focus target;
- cluster-relative rank;
- reasons supporting Pick / Keep / Reject.

Example overlay:

```text
+--------------------------------------+
|                                      |
|       +----------------------+       |
|       | Bird                 |       |
|       |                      |       |
|       |   [eye] 0.96         |       |
|       |                      |       |
|       +----------------------+       |
|                                      |
+--------------------------------------+

Belted Kingfisher          93%
Eye sharpness              96%
Head sharpness             91%
Background sharpness       35%
```

This should be an optional diagnostic/explainability view, not necessarily the normal browsing interface.

---

# 22. Relationship to the Statistical / Meta-Model Layer

The specialist architecture should feed the broader scoring model.

Instead of only:

```text
score(
    MUSIQ,
    LIQE,
    Q-Align,
    ...
)
```

the system can eventually learn:

```text
score(
    generic_model_scores,
    visual_domain,
    subject_measurements,
    anatomical_measurements,
    semantic_features,
    cluster_relative_features,
    model_confidences
)
```

Outputs can include:

```text
P(Pick)
P(Keep)
P(Reject)
overall score
confidence
```

This allows empirical human-label data to determine the importance of individual observations.

For example, training data may show that:

- eye sharpness dominates for perched birds;
- wing position becomes more discriminative for bird-in-flight bursts;
- focal-plane placement dominates for macro;
- global aesthetic score is more useful for standalone images than for near-duplicate culling.

Those relationships should be learned and measured rather than assumed permanently in specialist code.

---

# 23. Human Labeling Integration

The proposed architecture aligns naturally with a human-labeling system.

Labels can exist at multiple levels:

```text
Image level
    pick / keep / reject
    overall quality

Pair level
    A better than B

Subject level
    correct subject
    species

Region level
    eye correctly detected
    head correctly detected
    intended focus region

Attribute level
    eye sharp
    eye soft
    occluded
    good pose
    bad wing position
```

This enables both:

1. training specialist models;
2. measuring whether specialist evidence actually predicts human culling decisions.

---

# 24. Evaluation Strategy

Evaluate each layer independently.

## Router

Metrics:

- multi-label precision;
- recall;
- F1;
- calibration;
- false-negative rate for specialist domains.

For routing, high recall may be more important than perfect precision because missing a bird workflow can discard valuable specialist evidence.

## Subject detection

Metrics:

- mAP;
- recall;
- IoU;
- multi-subject detection rate.

## Anatomy

Metrics depend on representation:

- keypoint accuracy;
- bbox IoU;
- segmentation IoU;
- eye detection recall.

## Species

Metrics:

- top-1 accuracy;
- top-k accuracy;
- hierarchical taxonomic accuracy;
- confidence calibration.

## Regional quality

Evaluate correlation against human labels for:

- eye sharpness;
- head sharpness;
- subject sharpness;
- focal-plane correctness;
- occlusion.

## Culling

The ultimate test is downstream.

Compare:

```text
Baseline:
generic IQA scores

vs.

Generic IQA
+ domain

vs.

Generic IQA
+ domain
+ subject measurements

vs.

Generic IQA
+ domain
+ anatomy measurements

vs.

all above
+ cluster-relative features
```

Measure whether specialist evidence improves human-label agreement.

---

# 25. Ablation Studies

Ablation is particularly important because specialist inference increases complexity.

Suggested experiments:

```text
A  existing model scores only

B  A + scene/domain

C  B + subject bbox/crop features

D  C + eye/head sharpness

E  D + pose/occlusion

F  E + species/taxonomy

G  F + cluster-relative ranking
```

Measure the incremental value of each stage.

If species classification does not improve culling, it can remain metadata-only.

If eye/head localization produces a large improvement, prioritize that path.

---

# 26. Performance Strategy

Use staged inference.

Example:

```text
Tier 0
    metadata
    preview generation

Tier 1 - cheap
    visual-domain router

Tier 2
    subject detector

Tier 3
    specialist anatomy detector

Tier 4
    expensive fine-grained classifier / VLM

Tier 5
    cluster aggregation
```

Possible optimizations:

- operate on generated previews where sufficient;
- crop subjects before fine-grained inference;
- batch inference;
- cache results by image/model/preprocessing version;
- reuse cluster-level hypotheses;
- skip irrelevant workflows;
- defer expensive semantic inference until required.

---

# 27. RAW / NEF Considerations

The system should normally analyze an appropriate rendered preview rather than repeatedly decoding full-resolution RAW data for every model.

However, preview selection can affect:

- sharpness;
- noise;
- exposure;
- fine feather/fur detail;
- eye detail.

Therefore model evaluation must explicitly document the input representation.

Any changes to NEF preview extraction, RAW handling, EXIF orientation, or export orientation require regression tests.

Do not assume that a model validated on JPEG previews will produce equivalent measurements from another RAW rendering path.

---

# 28. Proposed Initial MVP

Avoid implementing the entire taxonomy at once.

A high-value MVP would be:

```text
Visual Domain Router
       |
       +-- bird
       +-- animal
       +-- macro
       +-- generic

Bird:
    bird bbox
    head bbox
    eye bbox
    eye sharpness
    head sharpness
    bird sharpness
    background sharpness

Animal:
    animal bbox
    head bbox
    eye bbox
    eye/head sharpness

Macro:
    subject bbox
    focal-region estimation
    subject sharpness
    background sharpness
```

Do **not** make species recognition a blocker for the first version.

The most important hypothesis to validate first is:

> Does semantic localization of the important subject region improve quality scoring and culling over global IQA alone?

---

# 29. Recommended Implementation Sequence

## Phase A — research and baseline

1. Audit existing scoring result structures.
2. Audit current image/preview preprocessing.
3. Define a representative validation dataset.
4. Ensure human Pick / Keep / Reject labels are available.
5. Establish the current generic-IQA culling baseline.

## Phase B — domain routing

1. Define initial workflow taxonomy.
2. Evaluate candidate routing models.
3. Store routing confidence and provenance.
4. Measure false negatives.

## Phase C — bird proof of concept

1. Detect bird.
2. Detect head.
3. Detect eye/eye region.
4. Compute regional sharpness.
5. Compare subject vs background focus.
6. Persist evidence.
7. Run culling ablation study.

## Phase D — animal

Reuse the common subject/part abstraction.

## Phase E — macro

Implement focal-region-aware analysis, then add insect/spider specialization.

## Phase F — species

Add fine-grained taxonomy after subject localization is reliable.

## Phase G — cluster model

Generate within-cluster relative features and train/evaluate culling models.

---

# 30. Risks

## Router false negatives

A bird classified as generic would miss specialist analysis.

Mitigation:

- optimize router for recall;
- permit multiple workflows;
- use fallback object detection where appropriate.

## Detector confidence interpreted as quality

Detection confidence does not mean photographic quality.

Keep these signals distinct.

## Model-specific score scales

Different specialist models may produce incompatible ranges.

Persist raw outputs and provenance; normalize downstream.

## Missing anatomy

Eyes may be:

- hidden;
- extremely small;
- turned away;
- motion blurred;
- outside frame.

Missing detection must not automatically imply poor quality.

## Species overconfidence

Fine-grained classifiers can be confidently wrong.

Store alternatives and calibrated confidence.

## Compute explosion

Running every model on every image will not scale.

Use routing, staged execution, caching, cropping, and batching.

## Overfitting scoring rules

Handwritten rules such as:

```text
if eye_sharpness < 0.5:
    reject
```

should be avoided unless strongly validated.

Prefer learned/statistically evaluated relationships.

---

# 31. Testing

## Unit tests

Test:

- workflow selection;
- confidence thresholds;
- multi-label routing;
- missing specialist results;
- evidence normalization;
- model-version handling;
- cluster aggregation.

## Regression fixtures

Maintain representative images for:

- perched bird;
- bird in flight;
- multiple birds;
- mammal;
- multiple animals;
- insect macro;
- spider macro;
- intentionally shallow DOF;
- subject occlusion;
- eye not visible;
- background-focused failure;
- unknown/generic scene.

RAW/NEF regression fixtures are especially important for orientation and preview behavior.

## Backend checks

Use the existing fast local suite where appropriate:

```bash
python -m pytest -m "not gpu and not db and not ml and not firebird" --ignore=tests/test_probe.py
```

ML and DB integration tests should be added separately where required.

## Gallery checks

After contract/UI changes:

```bash
npx tsc --noEmit
npx tsc -p electron/tsconfig.json --noEmit
npm run lint
```

Also run:

```bash
npm run doctor
npm run dev
```

Known pre-existing TypeScript errors should be distinguished from regressions.

---

# 32. Diagnostics

Before diagnosing backend integration problems:

```bash
source ~/.venvs/tf/bin/activate
python scripts/doctor.py
python scripts/doctor.py --no-gpu
python scripts/doctor.py --json
```

The doctor workflow should continue checking configuration, DB connectivity, query ping, pgvector, and optional GPU/CUDA support.

For a support bundle:

```bash
source ~/.venvs/tf/bin/activate
python scripts/export_debug_bundle.py
```

Bundles are intended to be redacted and exclude `secrets.json`; review the generated archive before sharing.

For Driftara Gallery:

```bash
npm run doctor
npm run dev
```

Also verify backend discovery/configuration, including the relevant `webui.lock`, `config.json`, API URL, and port behavior.

---

# 33. Open Questions

1. Which model should perform the initial multi-label routing?
2. Can one general detector cover birds, mammals, insects, and spiders sufficiently well?
3. Should eye/head detection use detection, segmentation, pose/keypoints, or a combination?
4. How should regional sharpness be measured?
5. Should regional sharpness be model-based, classical, or an ensemble?
6. How much does species identity improve culling after anatomy is already known?
7. Should action/behavior be its own orthogonal workflow dimension?
8. Which observations should be persisted permanently versus cached?
9. How should masks and keypoints be stored efficiently?
10. How much cluster-level inference can safely be shared?
11. How should confidence calibration differ between routing, taxonomy, and quality measurements?
12. Which specialist features provide measurable incremental value over existing IQA scores?

---

# 34. Key Architectural Decision

The recommended architecture is:

```text
                 Image
                   |
                   v
        +----------------------+
        | Visual Domain Router |
        +----------------------+
                   |
       +-----------+------------+
       |           |            |
       v           v            v
     Bird        Animal        Macro
       |           |            |
       +-----------+------------+
                   |
                   v
        Semantic Observations
                   |
                   v
        Normalized Evidence
                   |
        +----------+----------+
        |                     |
        v                     v
  Standalone Scoring    Cluster Analysis
        |                     |
        +----------+----------+
                   |
                   v
         Learned Meta-model
                   |
                   v
        Pick / Keep / Reject
```

The central design principle is:

> **Specialist vision models should describe the image; the scoring layer should decide what those observations mean.**

This keeps detection, taxonomy, anatomy, technical measurements, scoring policy, and human-label learning separable.

It also provides a scalable path from today's generic image-quality scoring toward domain-aware photographic culling without replacing the existing scoring stack all at once.

---

# 35. Cross-Repository Change Checklist

When implementation begins:

### Backend

- define canonical workflow terminology;
- define result/evidence model;
- implement routing;
- implement specialist analyzers;
- persist provenance;
- expose contract where needed;
- add tests.

### Shared contract

Update first in the backend:

- `docs/technical/API_CONTRACT.md`
- `docs/reference/api/openapi.yaml`
- `docs/technical/PIPELINE_TERMINOLOGY.md`
- `docs/technical/DB_SCHEMA.md`

### Gallery

- update generated/manual API types as appropriate;
- display specialist evidence;
- optionally add diagnostic overlays;
- keep DB/filesystem access in Electron main process via IPC/preload boundaries.

### Documentation

Update:

- relevant canonical-source table;
- architecture/pipeline documentation;
- indexes;
- `docs/log.md`;
- gallery docs if UI or contract behavior changes.

---

## Conclusion

The preliminary scene-classifier idea is most useful when generalized into a **multi-label Visual Domain Router**.

The router should select sibling specialist workflows such as:

- bird;
- general animal;
- insect;
- spider;
- macro;
- future landscape/portrait/botanical workflows.

Each specialist workflow identifies subjects and meaningful anatomical regions and emits reusable semantic evidence such as eye sharpness, head sharpness, focal-plane placement, pose, occlusion, and taxonomy.

The final culling system then combines:

```text
generic IQA
+ specialist semantic evidence
+ confidence/provenance
+ cluster-relative evidence
+ human-label-trained statistical relationships
```

rather than attempting to encode photographic judgment directly inside individual vision models.
