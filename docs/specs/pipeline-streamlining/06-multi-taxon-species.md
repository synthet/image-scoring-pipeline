---
type: Feature Spec
title: "Spec 06: species beyond birds"
description: A two-level BioCLIP 2 zero-shot pass — taxon class, then species within it — extends species identification from birds to mammals, insects, reptiles and amphibians, benchmarked against human labels first.
resource: docs/specs/pipeline-streamlining/06-multi-taxon-species.md
tags: [specs, species, bioclip, taxonomy, wildlife]
timestamp: 2026-09-25T00:00:00Z
okf_version: 0.1
status: proposed
---

# Spec 06: species beyond birds

**Issue:** #413 · **Hub:** [INDEX.md](INDEX.md) · **Milestone:** M3 (benchmark), then later ·
**Depends on:** 03, 05, rollout stage 5

## Summary

`bird_species` runs BioCLIP 2 (`hf-hub:imageomics/bioclip-2`) zero-shot. It prompts "a photo of
{name}, a bird species" over the 382 North American common names in
`data/bird_species_list.txt`, but only for images tagged `birds`. The model itself covers the tree
of life; the bird-only scope comes from the list and the keyword gate.

This spec proposes a **two-level pass**:
1. Choose the taxon class (Aves, Mammalia, Insecta, Reptilia, Amphibia) from class-level prompts.
2. Choose the species from that class's regional list.

It runs on the subject crop (spec 03 regions) with a full-frame fallback, and it is scoped by the
scene route (spec 05) and detector regions instead of the `birds` keyword.

It is **benchmark-first**. The crop study's species numbers measure agreement, not accuracy, so
there is no human accuracy evidence for any class yet, including birds.

## Users / stakeholders

- **Photographer:** species keywords for mammals, insects and herps, not just birds.
- **Operator:** one species phase instead of a bird-only special case.
- **Gallery:** filters on `species:*` keywords; a new `taxon:*` facet is optional.

## Product scenario

A frame of a red fox is routed `wildlife_mammal` (spec 05) and localized by the cascade (spec 03).
BioCLIP picks Mammalia at the class level, then "Red Fox (Vulpes vulpes)" from the regional mammal
list. The image gains `species:Red Fox` and `taxon:mammalia` keywords, with the prediction's
confidence and provenance stored.

## Non-goals

- Fine-tuning BioCLIP.
- Plants, fungi and marine life (a possible later extension).
- Changing the `bird_species` phase code. A rename or a new `species` code is a cross-repo contract
  change and stays an open question.
- Overwriting existing bird species keywords without an explicit refresh.

## User stories

- As a photographer, I want mammals, insects and herps identified, so that I can search my library
  by species.
- As an operator, I want each species prediction's taxon, list version and input mode recorded, so
  that I can tell stale results apart.

## Acceptance criteria

- **AC-1** — The benchmark script shall report top-1 and top-5 species accuracy per taxon class
  against a human-labelled sample of ≥ 50 images per class.
- **AC-2** — The benchmark script shall report class-level (taxon) accuracy and a confusion matrix
  separately from species accuracy.
- **AC-3** — The benchmark script shall compare common-name prompts with taxonomic-name prompts,
  using the same images.
- **AC-4** — The benchmark script shall report accuracy for crop input and for full-frame input,
  split by subject-size tercile.
- **AC-5** — The system shall load one species list per enabled taxon from
  `data/species/<taxon>.txt`, each with a recorded list version.
- **AC-6** — Where `species.taxa` lists more than one taxon, the species runner shall choose the
  taxon from class-level prompts before choosing a species.
- **AC-7** — If the class-level top probability is below the configured class threshold, then the
  species runner shall record no species and store the class probabilities.
- **AC-8** — The species runner shall persist each prediction with taxon, species, confidence,
  list version, prompt style, input mode (`region` or `full_frame`) and region id.
- **AC-9** — When a prediction is persisted, the species runner shall project it to a
  `species:<common name>` keyword with `source = 'bioclip'`.
- **AC-10** — While `species.taxa` is `["aves"]`, the species runner shall produce the same
  predictions as today's `bird_species` for the same inputs.
- **AC-11** — The system shall not enable a taxon beyond Aves by default until its AC-1 top-1
  accuracy on crops is reported and approved by the operator.

## Assumptions and dependencies

- Rollout stage 5 moves BioCLIP onto regions first; this spec extends that consumer.
- Spec 05 provides the scene label. Spec 03 provides animal regions (`object_class = animal`) that
  the class-level step disambiguates.
- **Species lists:** regional checklists per taxon. Their source and licence must be recorded,
  because some checklist exports restrict redistribution.
- **Labels:** a human-labelled sample per class. Labels can come from the photographer's own
  identifications where they exist in XMP keywords.

## Open questions

1. Where do the lists come from? The current bird list's source isn't documented. The mammal,
   insect and herp lists need a documented, licence-compatible source.
2. Should the phase stay `bird_species` with a taxon dimension, or become `species`? The latter is
   a new `phase_code` and a cross-repo change.
3. Insects and herps have no detector yet (spec 03 non-goal). Is full-frame classification good
   enough, or does this wait for an open-vocabulary detector?
4. Should `taxon:*` keywords be added, or should the taxon live only in prediction rows?

## Implementation plan

**Goal:** first the benchmark (AC-1 to AC-4); then AC-5 to AC-11 behind `species.taxa`.

**Files:**
- New `scripts/research/species_taxa_benchmark.py`: AC-1 to AC-4.
- `data/species/`: per-taxon lists, with `data/bird_species_list.txt` moved or aliased.
- `modules/bird_species.py`: class-level step, per-taxon lists, prediction provenance.
- A migration: prediction rows, unless rollout stage 5's region-linked prediction table covers them.

**Approach:**
1. Collect the labelled sample.
2. Run the benchmark: prompt styles, crop vs full frame, per class.
3. Write a report in `docs/reports/`.
4. Add the class-level step with Aves-only parity (AC-10).
5. Enable other taxa one at a time after operator approval (AC-11).

**Tests to write first:**
- `tests/test_species_taxa_lists.py`: AC-5.
- `tests/test_species_two_level.py`: AC-6 to AC-9, with a stub model.
- `tests/test_species_aves_parity.py`: AC-10.

**Rollback:** set `species.taxa=["aves"]`. Predictions for other taxa stay as history, and their
keywords can be removed by `source`.
