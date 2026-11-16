"""Read-only Windows ML probe (#875): list catalog execution providers and ORT EP devices. Installs nothing.

Needs a python.org or uv CPython (not the Microsoft Store Python) with
``wasdk-Microsoft.Windows.AI.MachineLearning[all]``, ``wasdk-...DynamicDependency.Bootstrap`` and
``onnxruntime-windowsml`` matching the installed Windows App SDK runtime.
"""

import winui3.microsoft.windows.applicationmodel.dynamicdependency.bootstrap as bootstrap


def main() -> None:
    with bootstrap.initialize():
        import onnxruntime as ort
        import winui3.microsoft.windows.ai.machinelearning as winml

        print("ort", ort.__version__)
        catalog = winml.ExecutionProviderCatalog.get_default()
        for provider in catalog.find_all_providers():
            # ready_state: 0 READY, 1 NOT_READY, 2 NOT_PRESENT; certification: 1 CERTIFIED, 2 UNCERTIFIED
            print(f"catalog: {provider.name:34} ready_state={provider.ready_state!s:5} "
                  f"certification={getattr(provider, 'certification', '?')}")
        for dev in ort.get_ep_devices():
            hw = getattr(dev, "device", None)
            print("ort ep_device:", dev.ep_name, getattr(hw, "type", "?"), getattr(hw, "vendor", ""))


if __name__ == "__main__":
    main()
