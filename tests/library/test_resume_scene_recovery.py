# SPDX-License-Identifier: GPL-3.0-or-later
"""A bad post-resume serial write must lead to a bounded full scene replay."""
import unittest
from unittest.mock import Mock, patch

import serial

from library.lcd.lcd_comm import LcdComm
from library.resume_recovery import ResumeRedrawWatch


class ResumeSceneRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.now = [10.0]
        self.log = Mock()
        self.redraw = Mock()
        self.watch = ResumeRedrawWatch(clock=lambda: self.now[0],
                                       quiet_seconds=2, window_seconds=40,
                                       max_redraws=3)
        self.watch.arm(0)

    def tick(self, failures=0, ready=True):
        return self.watch.poll(failures, ready, self.redraw, self.log)

    def test_clean_resume_does_not_redraw_twice(self):
        self.now[0] = 35
        self.assertFalse(self.tick())
        self.redraw.assert_not_called()

    def test_timeout_requires_quiet_and_drained_queue(self):
        self.now[0] = 11
        self.assertFalse(self.tick(17, False))
        self.now[0] = 12.9
        self.assertFalse(self.tick(17, True))
        self.now[0] = 13
        self.assertFalse(self.tick(17, False))
        self.assertTrue(self.tick(17, True))
        self.redraw.assert_called_once_with()
        self.assertFalse(self.tick(17, True))
        self.assertEqual(self.log.warning.call_count, 1)

    def test_more_timeouts_delay_replay(self):
        self.now[0] = 11
        self.tick(2)
        self.now[0] = 12.5
        self.tick(257)
        self.now[0] = 14
        self.assertFalse(self.tick(257))
        self.now[0] = 14.5
        self.assertTrue(self.tick(257))
        self.assertEqual(self.redraw.call_count, 1)

    def test_new_failures_after_replay_retry_but_cap(self):
        count = 0
        for i in range(3):
            self.now[0] += 1
            count += 1
            self.tick(count)
            self.now[0] += 2
            self.assertTrue(self.tick(count))
        self.assertEqual(self.redraw.call_count, 3)
        self.now[0] += 1
        self.assertFalse(self.tick(count + 1))
        self.assertFalse(self.watch.active)

    def test_repair_attempt_expires_if_usb_never_ready(self):
        self.now[0] = 11
        self.tick(1, False)
        self.now[0] = 51
        self.assertFalse(self.tick(1, False))
        self.assertFalse(self.watch.active)
        self.redraw.assert_not_called()
        self.log.warning.assert_any_call(
            "Resume scene repair expired; no stable serial window "
            "within %.0fs (attempts=%d)", 40, 0)

    def test_callback_exception_is_logged_and_retried(self):
        self.redraw.side_effect = [RuntimeError("render error"), None]
        self.now[0] = 11
        self.tick(1)
        self.now[0] = 13
        self.assertFalse(self.tick(1))
        self.log.exception.assert_called_once()
        self.now[0] = 15
        self.assertTrue(self.tick(1))
        self.assertEqual(self.redraw.call_count, 2)

    def test_rearm_after_second_resume(self):
        self.now[0] = 11
        self.tick(1)
        self.now[0] = 13
        self.tick(1)
        self.watch.arm(1)
        self.now[0] = 16
        self.assertFalse(self.tick(1))
        self.redraw.assert_called_once_with()


class WriteFaultDetectionTests(unittest.TestCase):
    @staticmethod
    def probe(write):
        class FakeDisplay:
            serial_write_failures = 0
            WriteLine = LcdComm.WriteLine
            serial_write = write
            closeSerial = Mock()
            openSerial = Mock()
        return FakeDisplay()

    def test_serial_timeout_is_counted_even_if_swallowed(self):
        probe = self.probe(Mock(side_effect=serial.SerialTimeoutException("slow")))
        with patch("library.lcd.lcd_comm.logger") as logger:
            probe.WriteLine(b"abcdef")
        self.assertEqual(probe.serial_write_failures, 1)
        logger.warning.assert_called_once()

    def test_serial_disconnect_is_counted_and_retry_is_preserved(self):
        writer = Mock(side_effect=[serial.SerialException("USB disappeared"), None])
        probe = self.probe(writer)
        with patch("library.lcd.lcd_comm.time.sleep"), \
             patch("library.lcd.lcd_comm.logger"):
            probe.WriteLine(b"abcdef")
        self.assertEqual(probe.serial_write_failures, 1)
        probe.closeSerial.assert_called_once()
        probe.openSerial.assert_called_once()
        self.assertEqual(writer.call_count, 2)


if __name__ == "__main__":
    unittest.main()
