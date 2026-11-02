# SPDX-License-Identifier: GPL-3.0-or-later
"""Find a Turing rev.A serial port by its physical Windows USB connector.

This is opt-in via display.USB_LOCATION_PATH. Serial numbers/COM numbers may
change after hibernate on USB hubs. Never fall back to a different screen.
"""
import json
import os
import re
import subprocess

_TURING_ID = "VID_1A86&PID_5722"
_PORT = re.compile(r"\bCOM\d+\b", re.I)
_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$devices = @(Get-PnpDevice -PresentOnly -Class Ports |
  Where-Object { $_.InstanceId -like 'USB\VID_1A86&PID_5722\*' } |
  ForEach-Object {
    $loc = Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName 'DEVPKEY_Device_LocationPaths' -ErrorAction Stop
    [PSCustomObject]@{ FriendlyName = $_.FriendlyName; InstanceId = $_.InstanceId; LocationPaths = @($loc.Data) }
  })
ConvertTo-Json -InputObject $devices -Compress -Depth 5
"""


class UsbLocationError(RuntimeError):
    pass


def resolve_com_port(physical_path, *, scan=None):
    expected = str(physical_path or "").strip().upper()
    if (not expected.startswith(("PCIROOT(", "ACPI("))
            or "#USB(" not in expected):
        raise UsbLocationError("Invalid physical USB LocationPaths value")
    if scan is None:
        if os.name != "nt":
            raise UsbLocationError("Physical USB binding is available on Windows only")
        try:
            completed = subprocess.run(
                ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
                 "-ExecutionPolicy", "Bypass", "-Command", _SCRIPT],
                timeout=9, capture_output=True, text=True, errors="replace",
                encoding="utf-8",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise UsbLocationError("Windows PnP lookup failed: " + str(exc)) from exc
        if completed.returncode:
            raise UsbLocationError("Windows PnP lookup failed: " + completed.stderr.strip()[:250])
        try:
            devices = json.loads(completed.stdout)
        except ValueError as exc:
            raise UsbLocationError("Invalid Windows PnP response") from exc
    else:
        devices = scan()

    if isinstance(devices, dict):
        devices = [devices]
    if not isinstance(devices, list):
        raise UsbLocationError("Unexpected PnP device list")

    matches = set()
    for item in devices:
        if not isinstance(item, dict):
            continue
        if _TURING_ID not in str(item.get("InstanceId", "")).upper():
            continue
        match = _PORT.search(str(item.get("FriendlyName", "")))
        paths = item.get("LocationPaths") or []
        if isinstance(paths, str):
            paths = [paths]
        if match and expected in {str(p).upper() for p in paths}:
            matches.add(match.group(0).upper())
    if len(matches) != 1:
        reason = "not present" if not matches else "ambiguous"
        raise UsbLocationError(
            f"Bound Turing at {expected} is {reason}; refusing unrelated COM"
        )
    return next(iter(matches))
