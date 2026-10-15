"""Hash-checked file deletion with an exclusive Windows handle."""

import hashlib
import os
from pathlib import Path


def delete_exact(path, expected_sha256):
    from .maintenance import SafetyError

    path = Path(path)
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            before = os.fstat(fd)
            digest = hashlib.sha256()
            for chunk in iter(lambda: os.read(fd, 1024 * 1024), b""):
                digest.update(chunk)
            current = path.stat(follow_symlinks=False)
            if digest.hexdigest() != expected_sha256 or (
                before.st_dev,
                before.st_ino,
            ) != (current.st_dev, current.st_ino):
                raise SafetyError("File changed before exact deletion")
            path.unlink()
        finally:
            os.close(fd)
        return
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.GetFinalPathNameByHandleW.argtypes = [
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    kernel.GetFinalPathNameByHandleW.restype = wintypes.DWORD
    kernel.ReadFile.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
    ]
    kernel.ReadFile.restype = wintypes.BOOL
    kernel.SetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel.SetFileInformationByHandle.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    # GENERIC_READ|DELETE, no sharing, OPEN_EXISTING, open reparse point itself.
    # DELETE_ON_CLOSE is deliberately absent: a failed hash check must keep it.
    handle = kernel.CreateFileW(
        str(path.absolute()), 0x80010000, 0, None, 3, 0x08200080, None
    )
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        final = ctypes.create_unicode_buffer(32768)
        size = kernel.GetFinalPathNameByHandleW(handle, final, len(final), 0)
        if not size or size >= len(final):
            raise ctypes.WinError(ctypes.get_last_error())
        actual = final.value
        if actual.startswith("\\\\?\\UNC\\"):
            actual = "\\\\" + actual[8:]
        elif actual.startswith("\\\\?\\"):
            actual = actual[4:]
        if os.path.normcase(actual) != os.path.normcase(str(path.absolute())):
            raise SafetyError("Opened file resolves through an unapproved alias")
        buffer = ctypes.create_string_buffer(1024 * 1024)
        count = wintypes.DWORD()
        digest = hashlib.sha256()
        while True:
            if not kernel.ReadFile(
                handle, buffer, len(buffer), ctypes.byref(count), None
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            if not count.value:
                break
            digest.update(buffer.raw[: count.value])
        if digest.hexdigest() != expected_sha256:
            raise SafetyError("Exclusive-handle hash mismatch; file retained")

        class Disposition(ctypes.Structure):
            _fields_ = [("DeleteFile", ctypes.c_ubyte)]

        disposition = Disposition(1)
        if not kernel.SetFileInformationByHandle(
            handle, 4, ctypes.byref(disposition), ctypes.sizeof(disposition)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.CloseHandle(handle)
