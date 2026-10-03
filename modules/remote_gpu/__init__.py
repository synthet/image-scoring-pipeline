"""Remote GPU runner: offload a phase's model inference to a container on another machine.

The host sends the full input and receives the full output; database and XMP
writes stay on the host. See ``docs/guides/REMOTE_GPU_RUNNER.md``.
"""

from modules.remote_gpu.contract import RemoteGpuError

__all__ = ["RemoteGpuError"]
