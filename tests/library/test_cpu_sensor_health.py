# SPDX-License-Identifier: GPL-3.0-or-later
"""CPU metrics regression tests, no Windows/CLR dependencies."""
import math
import unittest
from types import SimpleNamespace
from library.sensors.cpu_sensor_health import finite_metric, core_clock_mhz, core_temperature_c


def s(name, value):
    return SimpleNamespace(Name=name, Value=value)


class CpuSensorHealthTests(unittest.TestCase):
    def test_clock_hybrid_core_names_and_bad_values(self):
        self.assertAlmostEqual(core_clock_mhz([
            s("CPU Core #1", 4990),
            s("P-Core 2 Clock", 4900),
            s("E-Core 1 Clock", 3600),
            s("CPU Core #2 Effective Clock", 1500),
            s("Bus Speed", 100),
            s("Core #3", math.nan),
        ]), (4990 + 4900 + 3600) / 3)

    def test_clock_missing_remains_unknown(self):
        self.assertTrue(math.isnan(core_clock_mhz([s("Bus Speed", 100), s("CPU Core #1", None)])))

    def test_temperature_prefers_supported_core_over_board(self):
        self.assertEqual(core_temperature_c([
            s("CPU Package", 61), s("Core Average", 53), s("Core Max", 74),
        ]), 53)
        self.assertEqual(core_temperature_c([s("CPU Package", 46)]), 46)
        self.assertEqual(core_temperature_c([s("CPU", 48)]), 48)
        self.assertTrue(math.isnan(core_temperature_c([s("Motherboard", 35)])))

    def test_bad_temperature_is_not_zero(self):
        self.assertTrue(math.isnan(core_temperature_c([
            s("Core Average", math.nan), s("CPU Package", None),
        ])))
        self.assertEqual(core_temperature_c([
            s("Core Average", math.nan), s("CPU Package", 59),
        ]), 59)

    def test_finite_rejects_impossible(self):
        for bad in (None, math.nan, math.inf, "broken", 0, 11000):
            self.assertIsNone(finite_metric(bad, 100, 10000))
        self.assertEqual(finite_metric("4200", 100, 10000), 4200)


if __name__ == "__main__":
    unittest.main()
