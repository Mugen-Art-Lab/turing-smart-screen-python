# SPDX-License-Identifier: GPL-3.0-or-later
"""Safe UI helpers for the optional Windows rev.A physical USB binding."""
from library.usb_location import UsbLocationError, normalize_location


def location_for_selected_com(com, devices):
    selected = str(com or "").strip().upper()
    if not selected.startswith("COM") or not selected[3:].isdigit():
        raise UsbLocationError("Select a specific current COM before binding")
    matching = [d for d in devices if d.com_port.upper() == selected]
    if len(matching) != 1:
        raise UsbLocationError("Selected COM does not identify exactly one present Turing display")
    paths = matching[0].locations
    candidates = [normalize_location(p) for p in paths if p.upper().startswith("PCIROOT(")]
    if not candidates:
        candidates = [normalize_location(p) for p in paths]
    if not candidates:
        raise UsbLocationError("Selected display has no physical USB location")
    # Choose one stable physical connector path, never VID/PID or instance id.
    return candidates[0]


def check_binding_disable(previous_path, enabled, saved_com, resolver):
    """Return (error, actual_port); never silently unbind onto the other screen."""
    if enabled or not str(previous_path or "").strip():
        return "", ""
    try:
        actual = str(resolver(previous_path)).upper()
    except Exception:
        return "unavailable", ""
    if str(saved_com or "").upper() != actual:
        return "mismatch", actual
    return "", ""
