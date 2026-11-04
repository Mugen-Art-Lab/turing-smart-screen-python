# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression tests for CPU% normalization and self-healing periodic workers."""
import math
import unittest
from unittest.mock import Mock

from library.sensors.cpu_sensor_health import cpu_percentage_value
from library.task_health import TaskHealth


class PercentageGuardTests(unittest.TestCase):
    def test_valid_and_near_boundary(self):
        for v in (0, 15.8, 100, "52.5"):
            self.assertEqual(cpu_percentage_value(v), float(v))
        self.assertEqual(cpu_percentage_value(100.2), 100)
        self.assertEqual(cpu_percentage_value(-0.1), 0)

    def test_invalid_never_reaches_int_or_draw(self):
        for v in (None, math.nan, math.inf, -50, 200, "", "NaN", object()):
            self.assertIsNone(cpu_percentage_value(v))


class TaskHealthTests(unittest.TestCase):
    def setUp(self):
        self.t = [100.0]
        self.logger = Mock()
        self.guard = TaskHealth(clock=lambda: self.t[0])

    def test_exception_does_not_end_task_and_recovery_is_logged(self):
        side = [ValueError("CPU sensor momentarily unavailable"), None]
        def CPUPercentage():
            maybe = side.pop(0)
            if maybe:
                raise maybe
        self.assertFalse(self.guard.run(CPUPercentage, (), self.logger))
        self.assertEqual(self.logger.exception.call_count, 1)
        self.assertTrue(self.guard.run(CPUPercentage, (), self.logger))
        self.logger.info.assert_any_call(
            "Periodic task %s recovered after %d failure(s)", "CPUPercentage", 1)
        self.logger.info.assert_any_call("Periodic task CPUPercentage heartbeat: active")

    def test_repeated_errors_have_bounded_logs(self):
        def CPUPercentage():
            raise RuntimeError("bad reading")
        for n in range(300):
            self.t[0] = 100 + 0.1 * n
            self.assertFalse(self.guard.run(CPUPercentage, (), self.logger))
        self.assertEqual(self.logger.exception.call_count, 1)
        self.t[0] += 61
        self.guard.run(CPUPercentage, (), self.logger)
        self.assertEqual(self.logger.exception.call_count, 2)

    def test_cpu_heartbeat_is_sparse_and_independent(self):
        def CPUPercentage():
            return None
        def CPUTemperature():
            return None
        self.guard.run(CPUPercentage, (), self.logger)
        self.t[0] += 299
        self.guard.run(CPUPercentage, (), self.logger)
        self.guard.run(CPUTemperature, (), self.logger)
        self.assertEqual(self.logger.info.call_count, 1)
        self.t[0] += 1
        self.guard.run(CPUPercentage, (), self.logger)
        self.assertEqual(self.logger.info.call_count, 2)

    def test_different_tasks_not_confused(self):
        def CPUPercentage():
            raise IOError("broken")
        def CPUFrequency():
            return None
        self.assertFalse(self.guard.run(CPUPercentage, (), self.logger))
        self.assertTrue(self.guard.run(CPUFrequency, (), self.logger))
        self.assertEqual(self.logger.exception.call_count, 1)

    def test_keyboard_interrupt_not_swallowed(self):
        def CPUPercentage():
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.guard.run(CPUPercentage, (), self.logger)


if __name__ == "__main__":
    unittest.main()
