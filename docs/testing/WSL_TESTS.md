## WSL-only tests

This repo uses pytest markers to indicate tests that should be run in **WSL/Linux** (instead of native Windows).

- **Marker**: `wsl`
- **Run command in WSL**: `python -m pytest -m wsl -ra`

### Why WSL?

Some tests depend on Linux tooling (e.g. `dcraw`, `exiftool`), Linux-only libraries, or a working TensorFlow/CUDA stack that is expected to be installed in WSL.

### Tests currently marked `wsl`

- **TensorFlow / GPU**
  - `tests/test_tf_gpu.py`
  - `tests/test_vila.py`
  - `tests/test_model_sources.py`
  - `tests/test_launch.py` (imports `webui`, which pulls TensorFlow in this repo)
  - `tests/test_verify_thumbnail.py`
  - `tests/test_verify_patching.py`

- **RAW extraction tooling + sample data**
  - `tests/test_raw_extraction.py` (requires `IMAGE_SCORING_TEST_RAW_FILE`)
  - `tests/test_resolution.py` (pyiqa/torch; optional sample thumbnail path)

- **Firebird WSL smoke/integration**
  - `tests/test_fb_wsl.py`
  - `tests/test_fb_wsl_integration.py`

### Environment variables used by WSL tests

- **`IMAGE_SCORING_TEST_RAW_FILE`**: Path to a RAW file in WSL (e.g. `/mnt/d/Photos/.../DSC_0001.NEF`)
- **`IMAGE_SCORING_TEST_THUMBNAIL`**: Path to a thumbnail image for LIQE test
- **`IMAGE_SCORING_RUN_NETWORK_TESTS`**: Enable network checks (TFHub/Kaggle)
- **`IMAGE_SCORING_RUN_KAGGLE_DOWNLOADS`**: Allow KaggleHub downloads (requires Kaggle auth)

### Scripts

- **Setup venv inside WSL**: `bash ./scripts/wsl/setup_wsl_test_env.sh`
- **Run WSL tests inside WSL**: `bash ./scripts/wsl/run_wsl_tests.sh`
- **Run from Windows (PowerShell)**:

```powershell
.\scripts\powershell\Run-WSLTests.ps1 -Setup
.\scripts\powershell\Run-WSLTests.ps1
```

## Related Documents

- [Docs index](../README.md)
- [WSL TensorFlow GPU setup](../setup/WSL2_TENSORFLOW_GPU_SETUP.md)
- [WSL wrapper verification](../setup/WSL_WRAPPER_VERIFICATION.md)
- [GPU setup guide](../setup/README_gpu.md)
- [Technical summary](../technical/TECHNICAL_SUMMARY.md)
- [Docker setup](../technical/DOCKER_SETUP.md)


