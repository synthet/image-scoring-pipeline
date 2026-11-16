"""Run another probe script inside the Windows App SDK bootstrap (#875).

Usage: python winml_wrap.py <script.py> [script args ...]
Example: python winml_wrap.py ort_probe.py <model.onnx> DmlExecutionProvider ref.npz
"""

import runpy
import sys

import winui3.microsoft.windows.applicationmodel.dynamicdependency.bootstrap as bootstrap


def main() -> None:
    with bootstrap.initialize():
        script = sys.argv[1]
        sys.argv = sys.argv[1:]
        runpy.run_path(script, run_name="__main__")


if __name__ == "__main__":
    main()
