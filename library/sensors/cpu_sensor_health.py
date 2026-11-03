# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure, testable CPU sensor selection for the LibreHardwareMonitor backend.

Never fabricate a temperature. Treat None, NaN, infinity, and nonsense ranges
as unavailable. Hybrid Intel CPUs can expose different core clock names.
"""
import math
from statistics import mean


def finite_metric(value, low, high):
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return number if math.isfinite(number) and low <= number <= high else None


def core_clock_mhz(sensors):
    """Average actual core clocks; ignore effective clocks and bus speeds."""
    values = []
    for sensor in sensors:
        name = str(sensor.Name).lower()
        if ("core" not in name or "effective" in name
                or "bus" in name or "uncore" in name or "ring" in name):
            continue
        value = finite_metric(sensor.Value, 100, 10000)
        if value is not None:
            values.append(value)
    return mean(values) if values else math.nan


def core_temperature_c(sensors):
    """Prefer average/max/package CPU sensors, not unrelated board readings."""
    selectors = (
        lambda n: n.startswith("core average"),
        lambda n: n.startswith("core max"),
        lambda n: n.startswith("cpu package") or n.startswith("package id"),
        lambda n: n in ("cpu", "cpu core", "tctl/tdie", "cpu tctl/tdie"),
        lambda n: n.startswith("core") or n.startswith("cpu core"),
    )
    for selector in selectors:
        for sensor in sensors:
            if not selector(str(sensor.Name).strip().lower()):
                continue
            value = finite_metric(sensor.Value, -20, 135)
            if value is not None:
                return value
    return math.nan


def cpu_sensor_inventory(cpu):
    if cpu is None:
        return "no CPU hardware"
    try:
        items = [f"{sensor.SensorType}:{sensor.Name}="
                 f"{'unavailable' if sensor.Value is None else sensor.Value}"
                 for sensor in list(cpu.Sensors)[:30]]
    except Exception as exc:
        return f"could not enumerate sensors ({type(exc).__name__})"
    return ", ".join(items) if items else "CPU has no exposed sensors"
