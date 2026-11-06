# SPDX-License-Identifier: GPL-3.0-or-later
"""Limited post-resume scene repair after serial write failures.

The Windows resume handler queues the normal wake/orientation/static redraw.
If the serial writer reports failures after these commands were queued,
retry the whole scene when the physical port is open, the queue is drained,
and writes have stayed quiet. No device reset, COM selection or extra threads.
"""
import time


class ResumeRedrawWatch:
    def __init__(self, clock=None, quiet_seconds=2.0, window_seconds=90.0,
                 max_redraws=3):
        self.clock = clock or time.monotonic
        self.quiet_seconds = quiet_seconds
        self.window_seconds = window_seconds
        self.max_redraws = max_redraws
        self.active = False

    def arm(self, serial_write_failures):
        """Start observing immediately before queuing the initial resume redraw."""
        self.active = True
        self.started = self.clock()
        self.last_fault_time = None
        self.last_fault_count = serial_write_failures
        self.repair_pending = False
        self.repairs = 0

    def poll(self, serial_write_failures, ready, redraw, logger):
        """Run from the existing Windows message loop, without sleeping.

        ready means serial is open and queued output has drained. This cannot
        verify LCD firmware acknowledgement: log the repair as queued only.
        """
        if not self.active:
            return False
        now = self.clock()
        if serial_write_failures > self.last_fault_count:
            self.last_fault_count = serial_write_failures
            self.last_fault_time = now
            if not self.repair_pending:
                logger.warning(
                    "Resume serial writes failed; waiting for stable COM and "
                    "empty output queue before restoring orientation/background")
            self.repair_pending = True

        if now - self.started >= self.window_seconds:
            if self.repair_pending:
                logger.warning(
                    "Resume scene repair expired; no stable serial window "
                    "within %.0fs (attempts=%d)", self.window_seconds, self.repairs)
            self.active = False
            return False

        if not self.repair_pending:
            return False
        if self.repairs >= self.max_redraws:
            logger.warning(
                "Resume scene repair stopped after %d retries; check COM/USB log",
                self.repairs)
            self.active = False
            return False
        if not ready or now - self.last_fault_time < self.quiet_seconds:
            return False

        self.repairs += 1
        # Queue the full scene again, in the same order as normal resume:
        # ScreenOn, brightness, orientation, background, static text.
        try:
            redraw()
        except Exception:
            logger.exception(
                "Resume scene repair could not queue redraw (attempt %d)",
                self.repairs)
            self.last_fault_time = now
            return False

        self.repair_pending = False
        logger.info(
            "Resume scene repair queued after serial errors (attempt %d/%d)",
            self.repairs, self.max_redraws)
        return True
