# SPDX-License-Identifier: GPL-3.0-or-later
"""Keep periodic jobs observable without turning transient errors into dead workers.

No sleeps, thread creation, or dependency on Windows here: scheduler.py retains
the original intervals and threads. Failures are rate-limited in the log.
"""
import time


class TaskHealth:
    def __init__(self, retry_log_seconds=60, cpu_heartbeat_seconds=300, clock=None):
        self.retry_log_seconds = retry_log_seconds
        self.cpu_heartbeat_seconds = cpu_heartbeat_seconds
        self.clock = clock or time.monotonic
        self._state = {}

    def run(self, action, args, logger):
        name = getattr(action, "__name__", type(action).__name__)
        state = self._state.setdefault(name, {
            "failures": 0, "last_failure_log": None, "last_heartbeat": None,
        })
        try:
            action(*args)
        except Exception:
            state["failures"] += 1
            now = self.clock()
            if (state["last_failure_log"] is None or
                    now - state["last_failure_log"] >= self.retry_log_seconds):
                # The first traceback and periodic reminders survive frozen GUI
                # mode, where uncaught thread exceptions may miss log.log.
                logger.exception(
                    "Periodic task %s failed %d time(s); will retry next tick",
                    name, state["failures"])
                state["last_failure_log"] = now
            return False

        if state["failures"]:
            logger.info("Periodic task %s recovered after %d failure(s)",
                        name, state["failures"])
            state["failures"] = 0
            state["last_failure_log"] = None

        # A very sparse CPU scheduler heartbeat proves the worker is still
        # ticking. Its absence after resume is also useful diagnostic evidence.
        if name == "CPUPercentage":
            now = self.clock()
            if (state["last_heartbeat"] is None or
                    now - state["last_heartbeat"] >= self.cpu_heartbeat_seconds):
                logger.info("Periodic task CPUPercentage heartbeat: active")
                state["last_heartbeat"] = now
        return True
