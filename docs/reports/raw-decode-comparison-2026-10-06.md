---
type: Report
title: RAW decode comparison 2026-10-06
description: Six Nikon fixture comparison of embedded previews, rawpy and LibRaw CLI decoding.
resource: reports/raw-decode-comparison-2026-10-06.md
tags: [docs, raw, research, benchmark]
timestamp: 2026-10-06T23:04:46Z
okf_version: 0.2
---
# RAW decode comparison 2026-10-06

The evidence favors **diagnostics now, with further study before adding a sensor
decoder fallback**. The probe identified all six files and exposed preview/sensor
geometry differences. Embedded previews succeeded in every attempt. `dcraw_emu`
provided no extra high-efficiency decode coverage; its speed relative to `rawpy`
varied by fixture. The Z8 lossless full-size decode was faster with the CLI helper
in the first run, but that advantage reversed in the follow-up. There is no
consistent speed advantage or production promotion gate in these measurements.

## Decode results

Median decode seconds over three attempts; each numeric entry succeeded 3/3.
There were **66 successful decodes, 24 format failures, and no timeouts**.
Both high-efficiency files failed all four sensor routes. `rawpy` returned
unsupported-format errors and `dcraw_emu` exited 2; their embedded previews worked.

| Fixture | Embedded preview | rawpy half | CLI half | rawpy full | CLI full |
|---|---:|---:|---:|---:|---:|
| D90 | 0.286 | 2.650 | 3.270 | 4.050 | 3.779 |
| D300 | 0.319 | 4.173 | 3.310 | 3.976 | 4.377 |
| Z6 II | 0.353 | 6.081 | 6.961 | 8.867 | 9.675 |
| Z8 lossless | 0.589 | 16.371 | 13.272 | 28.675 | 14.719 |
| Z8 HE high | 0.677 | failed | failed | failed | failed |
| Z8 HE low | 0.564 | failed | failed | failed | failed |

### Geometry and pixels

The two sensor implementations produced equal dimensions at each resolution.
They were not byte-identical. After resizing to a 512-pixel-wide comparison frame,
mean absolute error was under 0.008 on the 0–255 channel scale. This establishes
close resized-pixel agreement on these samples, not exact rendition equivalence.

| Fixture | Preview dimensions | Full sensor dimensions | Half sensor dimensions | Half/full rawpy–CLI MAE |
|---|---|---|---|---|
| D90 | 4288×2848 | 4310×2868 | 2155×1434 | 0.0079 / 0.0061 |
| D300 | 4288×2848 | 4320×2868 | 2160×1434 | 0.0024 / 0.0025 |
| Z6 II | 6048×4024 | 6064×4040 | 3032×2020 | 0.0057 / 0.0051 |
| Z8 lossless | 8256×5504 | 8280×5520 | 4140×2760 | 0.0027 / 0.0026 |

The probe reports Z6 II's inset at left/top 8/8 and Z8's at 12/8. These matter for
mapping detector/crop coordinates between previews and sensor renditions. The
resized preview-versus-full MAE was 23.01–32.60 across the four decodable fixtures,
which mixes camera rendering differences and unregistered crop offsets. It does
not show which rendition is better for model scoring.

### Memory measurement correction

The first run used Linux `getrusage().ru_maxrss` for Python workers. Those values
can retain pre-exec inherited parent memory, so the original Python memory fields
are explicitly marked invalid in `comparison.json` and must not be compared.
The CLI now uses `/proc/self/status` `VmHWM` for the current worker address space.
A separate single-attempt Z8 lossless validation is saved in
[memory-validation.json](../../reports/raw-decode/2026-10-06/memory-validation.json).
The original timing, dimensions and pixel results are retained. Native-child RSS
is a separate maximum over child processes, including metadata helpers; it is
not concurrent total pipeline memory.

Corrected Z8 lossless figures from one successful attempt per route:

| Route | Python worker peak MiB | Maximum child peak MiB | Decode seconds |
|---|---:|---:|---:|
| Embedded preview | 641.93 | 39.36 | 0.624 |
| rawpy half | 243.98 | 35.02 | 15.509 |
| CLI half | 187.04 | 178.12 | 15.584 |
| rawpy full | 646.05 | 35.02 | 17.504 |
| CLI full | 645.16 | 446.38 | 21.449 |

The Python figures include RGB/buffer copies and pixel fingerprinting in the
comparison harness, not just the decoder. They do not establish a production
memory advantage. The full-size timing reversal (rawpy 17.50 s versus CLI 21.45 s)
also argues for a controlled larger study before promoting a new route.

## Method and provenance

The [comparison CLI](../../scripts/research/rendition/compare_raw_decoders.py)
compares five routes on six public Nikon fixtures with three isolated attempts
per route (90 attempts). Sensor routes use matched camera WB, sRGB, 8-bit, AHD,
auto-bright and gamma settings. Decoder rotation is disabled and source EXIF
orientation is applied once. Embedded previews retain camera rendering.

Fixtures: D90 `RAW_NIKON_D90.NEF`, D300 `RAW_NIKON_D300.NEF`, Z6 II
`nikon_z6_ii_01.nef`, and Z8 lossless, high-efficiency-high and
high-efficiency-low files. Source image hashes and tool binary hashes are in
[comparison.json](../../reports/raw-decode/2026-10-06/comparison.json).

The test container runs Ubuntu 22.04/glibc 2.35, Python 3.11 and
`rawpy` 0.26.1 / LibRaw 0.22.0. Since the extracted Linux executable requires
GLIBC 2.38, this experiment uses compatible upstream LibRaw 0.22.0 helpers built
in the test container, not that extracted binary. No production image was rebuilt.
[build.json](../../reports/raw-decode/2026-10-06/build.json) records the release
archive checksum, configure flags and optional features. The CLI build lacks
OpenMP and LCMS; the `rawpy` wheel enables both. `OMP_NUM_THREADS=1` and
`OPENBLAS_NUM_THREADS=1` limit the experiment to single-threaded compute.

```powershell
docker exec -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 image-scoring-gpu-shell python scripts/research/rendition/compare_raw_decoders.py tests/fixtures/testing_samples/public/D90/RAW_NIKON_D90.NEF tests/fixtures/testing_samples/public/D300/RAW_NIKON_D300.NEF tests/fixtures/testing_samples/public/Z6II/nikon_z6_ii_01.nef tests/fixtures/testing_samples/public/Z8/Z8_14bit_lossless_compression.NEF tests/fixtures/testing_samples/public/Z8/Z8_high_efficiency_high.NEF tests/fixtures/testing_samples/public/Z8/Z8_high_efficiency_low.NEF --dcraw /tmp/vexlum-libraw-0.22/LibRaw-0.22.0/bin/dcraw_emu --identify /tmp/vexlum-libraw-0.22/LibRaw-0.22.0/bin/raw-identify --repeats 3 --timeout 60 --output reports/raw-decode/2026-10-06/comparison.json
```

## Interpretation limits

This is a small warmed-cache CPU sample. CPU affinity and other host workloads
were not controlled. Timings describe this run, not a guaranteed production
speedup. Decode time includes route setup; process wall time also includes Python
startup, orientation metadata and temporary PNG writing. Memory figures cover
individual workers and fingerprinting before PNG writing; Python and native-child
peaks are separate.

Pixel differences are measured after whole-frame resizing, without registering
crop insets. They are not image-quality labels or downstream scoring results.
Support must be established by actual decoding: `raw-identify` metadata success
alone is insufficient. Timeouts include worker output writing and should not be
classified as unsupported encoding.

## Implementation verification

148 targeted tests passed in `image-scoring-gpu-shell`, including failure-report
integration, shared probe timeout, real worker descendant cleanup, scoring/thumbnail
orientation, scoring preparation, RAW conversion retries and rendition contracts.
One existing TensorFlow Hub `pkg_resources` deprecation warning was emitted.
Ruff passed for the new code and thumbnail integration. The scoring converter's
21 existing Ruff findings are identical before/after the two diagnostic lines.
Documentation was checked with the repository OKF linter.

```powershell
docker exec image-scoring-gpu-shell python -m pytest tests/test_raw_diagnostics.py tests/test_raw_decode_comparison.py tests/test_raw_conversion_retry.py tests/test_thumbnail_orientation.py tests/test_scoring_orientation.py tests/test_scoring_preparation_failures.py tests/test_rendition.py -q
docker exec image-scoring-gpu-shell ruff check modules/thumbnails.py modules/raw_diagnostics.py scripts/raw_diagnostics.py scripts/research/rendition/compare_raw_decoders.py tests/test_raw_diagnostics.py tests/test_raw_decode_comparison.py
```

Usage and tool setup: [RAW diagnostics](../technical/RAW_DIAGNOSTICS.md).
