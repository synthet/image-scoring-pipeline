---
type: Technical Reference
title: RAW diagnostics and decode comparison
description: Optional LibRaw failure probes and isolated CPU decoder comparisons.
resource: technical/RAW_DIAGNOSTICS.md
tags: [docs, raw, diagnostics, research]
timestamp: 2026-10-06T23:04:44Z
okf_version: 0.2
---
# RAW diagnostics and decode comparison

## Failure diagnostics

Set `RAW_DIAGNOSTICS=1` in the backend process environment to log a `RAW_DIAGNOSTIC`
JSON record on terminal RAW failures in scoring conversion, ML loading, thumbnail
generation and preview generation. Set `RAW_IDENTIFY_PATH` to a compatible LibRaw
`raw-identify` executable, or put `raw-identify` on PATH. This setting does not
select a decoder or alter failure status. It is disabled by default.

The probe retains camera model, decoder name, sensor/image/output/preview sizes,
crop inset, flip and camera white balance. It discards the full metadata dump,
capture timestamp, unique identifiers and camera/lens serial numbers. Two
metadata-only calls share a five-second timeout; a missing executable, timeout,
nonzero exit or unfamiliar output is reported without replacing the processing
failure. Recognition is always marked `decode_support: not_tested`: recognizing
a Nikon HE file does not establish sensor decoding support.

Inspect a file without running a pipeline or touching the database:

```bash
python scripts/raw_diagnostics.py image.NEF --tool /path/to/raw-identify
```

The CLI explicitly enables its probe, emits JSON, and exits nonzero if any probe
is unsuccessful. Unlike automatic failure logging, it does not require
`RAW_DIAGNOSTICS=1`. Tools receive paths as arguments, never shell commands.

Implementation: [raw_diagnostics.py](../../modules/raw_diagnostics.py).

## Decode comparison

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python \
  scripts/research/rendition/compare_raw_decoders.py image.NEF another.NEF \
  --dcraw /path/to/dcraw_emu --identify /path/to/raw-identify \
  --repeats 3 --timeout 60 --output reports/raw-decode/comparison.json
```

Run backend research in `image-scoring-gpu-shell`; for example pass the command
to `docker exec` with `-e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1`.
`DCRAW_EMU_PATH` and `RAW_IDENTIFY_PATH` are optional defaults for CLI tool paths.
`--routes` selects a subset of `embedded_preview`, `rawpy_half`, `dcraw_emu_half`,
`rawpy_full`, and `dcraw_emu_full`.

Every attempt uses a separate worker. On timeout, the worker and its descendants
are terminated. Rendered images live in a temporary directory and are removed;
only the JSON report persists. There are no DB calls, model inference, original
image writes or shared rendition-cache writes. Failed routes remain in the report;
exit zero means at least one decode succeeded, not that every route worked.

Sensor routes use camera WB, sRGB, 8-bit output, AHD and the default auto-bright/gamma
curve. Decoder rotation is disabled and source orientation is applied once.
Embedded previews retain camera rendering. Reported geometry is not harmonized:
an inset or aspect difference must not be hidden by calling pixels equivalent.
Whole-frame resized MAE/RMSE measures pixel differences, not quality or crop
registration. Matching sensor dimensions plus exact pixel hashes is stronger
evidence than a low resized error.

`decode_s` includes route setup and pixel materialization. `process_wall_s` also
includes worker startup, orientation metadata and temporary PNG output. Python
peak RSS (Linux current-address-space `VmHWM`) and maximum native-child RSS are reported separately before PNG output;
the Python figure includes comparison-only RGB/buffer copies and pixel fingerprinting.
They are not a sum of concurrent memory or a pure production-decoder memory benchmark.
Source hashing and repeated reads warm
the filesystem cache. This is a small CPU experiment, not a production
throughput benchmark or evidence to change scoring defaults.

## Compatible tools

The extracted BurstPick Windows tools require their adjacent `libraw.dll`.
Their `dcraw_emu` stdout flag is `-Z -`; it cannot replace `dcraw -e -c` for
embedded JPEG extraction. The bundled Linux binary requires GLIBC 2.38 and
external `libraw.so.23`; it cannot run on this repository's Ubuntu 22.04 base.
Build compatible upstream tools rather than copying vendor binaries into the repo.

For the recorded experiment, official [LibRaw 0.22.0](https://www.libraw.org/download)
source was built under `/tmp/vexlum-libraw-0.22` in the test container:

```bash
# Prerequisites in an Ubuntu 22.04 test container:
apt-get update
apt-get install -y --no-install-recommends build-essential pkg-config libjpeg-dev zlib1g-dev
curl --fail --location https://www.libraw.org/data/LibRaw-0.22.0.tar.gz -o source.tar.gz
tar -xzf source.tar.gz
cd LibRaw-0.22.0
./configure --disable-shared --disable-openmp
make -j2 bin/raw-identify bin/dcraw_emu
```

Source archive SHA256:
`1071e6e8011593c366ffdadc3d3513f57c90202d526e133174945ec1dd53f2a1`.
The build has JPEG/zlib support, no OpenMP, and no optional LCMS development package.
`rawpy` wheel features can differ despite the same LibRaw version; binary hashes
and `rawpy`/LibRaw versions are recorded in the experiment. These test-container
tools are temporary and are not installed in or enabled on the running WebUI.

Results: [2026-10-06 comparison](../reports/raw-decode-comparison-2026-10-06.md).
Upstream semantics: [LibRaw examples](https://www.libraw.org/node/35),
[rawpy](https://github.com/letmaik/rawpy).
