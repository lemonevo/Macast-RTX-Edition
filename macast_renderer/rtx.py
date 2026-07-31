# Copyright (c) 2026 by Macast RTX Edition contributors.
#
# Lightweight Windows GPU capability detection for NVIDIA RTX Video.

import ctypes
import logging
import os
import re
import shutil
import subprocess
import sys
from ctypes import wintypes
from dataclasses import dataclass
from functools import lru_cache


logger = logging.getLogger("RTXVideo")


@dataclass(frozen=True)
class RTXVideoCapability:
    supported: bool
    detected: bool
    gpu_names: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()

    @property
    def primary_gpu(self):
        for name in self.gpu_names:
            if is_supported_rtx_gpu(name):
                return name
        return self.gpu_names[0] if self.gpu_names else ""

    @property
    def menu_status(self):
        if self.supported:
            return "Detected: {}".format(self.primary_gpu)
        if self.detected:
            return "No supported NVIDIA RTX GPU detected"
        return "GPU detection unavailable"

    @property
    def unavailable_notice(self):
        if self.detected:
            return (
                "No supported NVIDIA RTX GPU was detected. "
                "RTX VSR and HDR are disabled."
            )
        return (
            "GPU detection was unavailable. "
            "RTX VSR and HDR are disabled."
        )


def is_supported_rtx_gpu(name):
    """Return whether a display adapter name identifies an NVIDIA RTX GPU."""
    normalized = re.sub(r"\s+", " ", str(name)).strip().upper()
    return (
        "NVIDIA" in normalized
        and re.search(r"(^|[\s-])RTX([\s-]|$)", normalized) is not None
    )


def _unique_names(names):
    unique = []
    seen = set()
    for name in names:
        normalized = re.sub(r"\s+", " ", str(name)).strip()
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            unique.append(normalized)
    return unique


def _nvidia_smi_candidates():
    candidates = []
    resolved = shutil.which("nvidia-smi")
    if resolved:
        candidates.append(resolved)

    windows_dir = os.environ.get("WINDIR")
    if windows_dir:
        candidates.append(os.path.join(windows_dir, "System32", "nvidia-smi.exe"))

    program_files = os.environ.get("ProgramFiles")
    if program_files:
        candidates.append(
            os.path.join(
                program_files,
                "NVIDIA Corporation",
                "NVSMI",
                "nvidia-smi.exe",
            )
        )

    return [
        path for path in _unique_names(candidates)
        if os.path.isfile(path)
    ]


def _query_nvidia_smi():
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    for executable in _nvidia_smi_candidates():
        try:
            result = subprocess.run(
                [
                    executable,
                    "--query-gpu=name",
                    "--format=csv,noheader",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=4,
                check=False,
                creationflags=creation_flags,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0:
            names = _unique_names(result.stdout.splitlines())
            if names:
                return names
    return []


def _query_display_devices():
    if sys.platform != "win32":
        return []

    class DisplayDevice(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("DeviceName", wintypes.WCHAR * 32),
            ("DeviceString", wintypes.WCHAR * 128),
            ("StateFlags", wintypes.DWORD),
            ("DeviceID", wintypes.WCHAR * 128),
            ("DeviceKey", wintypes.WCHAR * 128),
        ]

    try:
        enum_display_devices = ctypes.windll.user32.EnumDisplayDevicesW
        enum_display_devices.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.POINTER(DisplayDevice),
            wintypes.DWORD,
        ]
        enum_display_devices.restype = wintypes.BOOL
    except (AttributeError, OSError):
        return []

    names = []
    index = 0
    while True:
        device = DisplayDevice()
        device.cb = ctypes.sizeof(DisplayDevice)
        if not enum_display_devices(None, index, ctypes.byref(device), 0):
            break
        names.append(device.DeviceString)
        index += 1
    return _unique_names(names)


def _query_registry_display_devices():
    if sys.platform != "win32":
        return []

    try:
        import winreg
    except ImportError:
        return []

    names = []
    registry_path = r"SYSTEM\CurrentControlSet\Control\Video"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, registry_path) as root:
            guid_index = 0
            while True:
                try:
                    guid_name = winreg.EnumKey(root, guid_index)
                except OSError:
                    break
                guid_index += 1
                try:
                    with winreg.OpenKey(root, guid_name) as guid_key:
                        adapter_index = 0
                        while True:
                            try:
                                adapter_name = winreg.EnumKey(
                                    guid_key,
                                    adapter_index,
                                )
                            except OSError:
                                break
                            adapter_index += 1
                            try:
                                with winreg.OpenKey(
                                    guid_key,
                                    adapter_name,
                                ) as adapter_key:
                                    value, _ = winreg.QueryValueEx(
                                        adapter_key,
                                        "DriverDesc",
                                    )
                                    names.append(value)
                            except OSError:
                                continue
                except OSError:
                    continue
    except OSError:
        return []
    return _unique_names(names)


@lru_cache(maxsize=1)
def detect_rtx_video_capability():
    if sys.platform != "win32":
        return RTXVideoCapability(
            supported=False,
            detected=True,
            sources=("platform",),
        )

    names = []
    sources = []
    for source, query in (
        ("nvidia-smi", _query_nvidia_smi),
        ("EnumDisplayDevices", _query_display_devices),
        ("registry", _query_registry_display_devices),
    ):
        try:
            result = query()
        except Exception as error:
            logger.warning("%s GPU detection failed: %s", source, error)
            continue
        if result:
            names.extend(result)
            sources.append(source)

    names = _unique_names(names)
    supported = any(is_supported_rtx_gpu(name) for name in names)
    capability = RTXVideoCapability(
        supported=supported,
        detected=bool(names),
        gpu_names=tuple(names),
        sources=tuple(sources),
    )
    logger.info(
        "RTX Video capability: supported=%s, detected=%s, GPUs=%s, sources=%s",
        capability.supported,
        capability.detected,
        ", ".join(capability.gpu_names) or "none",
        ", ".join(capability.sources) or "none",
    )
    return capability
