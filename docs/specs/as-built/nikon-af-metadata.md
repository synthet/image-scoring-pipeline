---
type: Technical Reference
title: Nikon AF metadata as built
description: Numeric validity, camera-grid geometry and cache semantics for Nikon AF evidence.
resource: specs/as-built/nikon-af-metadata.md
tags: [specification, as-built, nikon, exif]
timestamp: 2026-10-24T23:58:23Z
okf_version: 0.2
---

# Nikon AF metadata extraction

Observed source: pipeline commit `d887d47a4541e9c5fcc1600d9535cc5b6315aa09` plus the scoped
validation correction in `modules/exif_extractor.py` (`322decec`), plus the ExifTool pin and
nullable focus result from #672 (`e9c4ae00`). Before/after hashes and failing/passing receipts
are in the hub's `docs/reports/focus-af-validation-2026-10-24/evidence/`. This is implemented behavior;
camera-to-preview calibration and quality-policy integration remain proposed work.

## Decoder version

AF decoding depends on the ExifTool release. Ubuntu 22.04's `libimage-exiftool-perl` (12.40) drops Nikon Z8
AFInfo2 `0400` geometry and `FocusResult`, so the [`Dockerfile`](../../../Dockerfile) installs a pinned,
checksum-verified ExifTool **13.52** and fails the build if `exiftool -ver` differs. Each successful AF
object records `exiftool_version` from `get_exiftool_version()` (cached per process; null if the tool
cannot be run). Rows extracted earlier carry no version and are not backfilled.

Fixture check (2026-10-24, repo `tests/fixtures/testing_samples/public`): with 12.40, 0 of 8 Z8 files yield
`af_metadata`; with 13.52, 5 of 8 do (AFInfo2 `0400`, `in_focus` from `FocusResult`). The other three report
`AFCoordinatesAvailable` 0 and correctly yield none. All 9 Z6ii files (`0301`) yield a box with `in_focus`
null under both versions.

## Entry point and output

[`extract_exif`](../../../modules/exif_extractor.py) invokes ExifTool with `-j -s -n -ee`, explicitly
requesting AFInfo2 version, coordinate availability, AF area/grid fields, mode, crop area, focus result
and distance alongside standard EXIF. It does not write the photograph. It returns standard column
values plus optional `af_metadata`, consumed by the existing nullable `image_exif.af_metadata` JSONB
column through `extract_and_upsert_exif` / `_merge_exif_for_upsert`.

The AF object retains its existing keys: version, mode/mode_code, in_focus, focus_distance_m,
area_x/area_y/area_w/area_h, af_image_w/af_image_h, crop_area, box and optional crop_box, plus
`exiftool_version` (see above).
No schema, scoring weight, selection gate or localization ownership changed.

## Numeric and availability contract

| Input | Implemented behavior |
|---|---|
| Explicit `AFCoordinatesAvailable` | Must be finite numeric 1; otherwise AF geometry is unavailable |
| Coordinate flag absent | Preserve legacy parsing when geometry is present; absence does not certify camera support |
| Six geometry fields | Finite numeric values; booleans, malformed values and numeric overflow are unavailable |
| Grid and area dimensions | Positive integral pixel counts; fractional dimensions cannot be truncated to zero |
| Normalized primary box | Reject non-finite computed values |
| Optional distance | Finite, nonnegative metres; invalid value becomes null while valid geometry survives |
| Numeric mode | Invalid/non-finite numeric mode becomes `Unknown`, mode_code null; existing descriptive strings are retained |
| CropArea | Exactly four finite integral values; malformed arrays or non-finite elements become null |

Numeric strings remain accepted where ExifTool or legacy artifacts use them. Required missing/invalid
geometry returns no AF object; it does not discard valid model, ISO, capture time or other EXIF.

## Coordinate formulas and limits

Let `(x,y)` be the reported AF center, `(w,h)` its size, and `(W,H)` the AF grid dimensions.
The primary `box` is **xywh in the camera AF grid**, rounded to five decimals:

`left=(x-w/2)/W; top=(y-h/2)/H; width=w/W; height=h/H; center_x=x/W; center_y=y/H`.

Raw reported pixel fields are integer-converted for compatibility with the existing object. This
parser does not apply EXIF orientation, select a subject, identify an anatomical eye, clamp the region
to a display frame, or establish which embedded preview corresponds to the AF grid.

The existing crop behavior is preserved: for parsed CropArea `(cx,cy,cw,ch)`, positive crop size and
`cw < .95*W OR ch < .95*H` produce `crop_box` using the same formulas after subtracting `(cx,cy)`
and dividing by `(cw,ch)`. This heuristic is not independent proof of crop-frame compatibility.
The observed Z8 records have AF grid 8256Ã—5504 and CropArea `12 8 8256 5504`; they produce no
additional crop_box. RAW-grid offsets and orientation must be calibrated before display alignment.

## Cache and failure behavior

When any AF version/availability/grid/area tag is present but geometry is unavailable, extraction
returns **`af_metadata: null`**. The existing merge updates that key explicitly, invalidating an older
cached rectangle while preserving unrelated existing EXIF columns. A partial update containing no AF
tags omits the key and retains prior AF data. Invalid optional crop/distance values are discarded locally.

Missing tool/file, command failure, timeout or malformed JSON retain the existing extraction-error
behavior and do not create an AF success result. This increment performs no library backfill or live DB
write. Existing cached rows change only when an explicitly invoked extraction/upsert processes them.

## Observed requirement gaps

- `in_focus` is true/false only when the body writes `FocusResult` (or `ContrastDetectAFInFocus`);
  when neither tag is present (for example Z6ii AFInfo2 `0301`) it is null, meaning unknown, not a miss.
  It is not a calibrated eye-quality label, and consumers that treat a falsy value as a miss still need an audit.
- Unqualified extraction still lacks a complete namespace/provenance contract. Standard and Nikon ISO
  values must not silently be treated as identical evidence in a future adapter.
- Version support, all eight EXIF orientations, source/rendition identity, geometric bounds and complete
  crop-transform conformance are not established by the finite-value tests.
- When `AFCoordinatesAvailable` is 0 the whole AF object is null, so a reported `FocusResult` is not kept
  either (seen on three Z8 fixtures with AF area mode 197).
- No optical focus accuracy, bird-eye localization, suppression safety or ranking benefit was measured.

## Acceptance and verification

| Example | Expected behavior | Test |
|---|---|---|
| NaN/Infinity, bool or oversized number in required AF geometry | AF unavailable; no parser exception | `test_invalid_af_geometry_is_unavailable` |
| Coordinate availability 0 or invalid | No AF rectangle | `test_unavailable_or_invalid_coordinate_flag_blocks_geometry` |
| Fractional dimension | AF unavailable | `test_af_dimensions_are_positive_pixel_counts` |
| Invalid optional distance/mode/crop | Other valid evidence retained and serializable in covered cases | Corresponding invalid optional-field tests |
| Invalid AF alongside ISO/model/time | Standard EXIF retained; explicit AF null clears old box on merge | `test_extract_preserves_standard_exif_with_invalid_af` |
| Unrelated partial EXIF update | Existing AF and other columns retained | `test_unrelated_partial_extraction_preserves_cached_af` |
| No FocusResult tag | `in_focus` null (unknown) | `test_missing_focus_result_is_unknown_not_a_miss` |
| Decoder version lookup | `exiftool -ver` cached once per process | `test_exiftool_version_is_cached` |

Tests live in [`test_exif_af_validation.py`](../../../tests/test_exif_af_validation.py), alongside
[`test_exif_extractor_af.py`](../../../tests/test_exif_extractor_af.py) and
[`test_exif_extractor_camera_lens_unit.py`](../../../tests/test_exif_extractor_camera_lens_unit.py).
The final focused run passed **95 tests**, with three sample-data tests explicitly deselected. Ruff passed.
After the #672 merge the same selection passes **97 tests**.

A frozen replay of the eleven previously extracted Z8 numeric records produced **11/11 identical AF
objects** between the baseline and corrected parsers, with strict JSON serialization. This used recorded
metadata, not fresh RAW extraction, image decoding, optical labels or overlay calibration. Source/photo
files were not modified and no GPU time was consumed.
