"""Passive wind history for future ISS gust comparison.

This module does not modify weather observations or write archive data.
All speeds are expressed in mph.
"""

from collections import deque
from math import isfinite


class WindHistory:
    """Maintain bounded receiver wind history and ISS gust reports."""

    def __init__(self, window_seconds=600, iss_max_age_seconds=120):
        self.window_seconds = float(window_seconds)
        self.iss_max_age_seconds = float(iss_max_age_seconds)
        if self.window_seconds <= 0 or self.iss_max_age_seconds <= 0:
            raise ValueError("Window and maximum ISS age must be positive")
        self.samples = deque()
        self.latest_iss = None
        self.last_timestamp = None

    def reset(self):
        """Discard history, including the previous ISS reference."""
        self.samples.clear()
        self.latest_iss = None
        self.last_timestamp = None

    def _advance(self, timestamp):
        now = float(timestamp)
        if not isfinite(now):
            raise ValueError("Timestamp must be finite")

        # A clock moving backward invalidates the rolling history.
        if self.last_timestamp is not None and now < self.last_timestamp:
            self.reset()

        self.last_timestamp = now
        cutoff = now - self.window_seconds

        while self.samples and self.samples[0][0] < cutoff:
            self.samples.popleft()

        return now

    def observe_wind(self, speed_mph, timestamp):
        """Record a decoded wind sample without changing its value."""
        now = self._advance(timestamp)

        if speed_mph is None:
            return

        speed = float(speed_mph)
        if not isfinite(speed) or speed < 0:
            return

        self.samples.append((now, speed))

    def observe_iss(self, gust_mph, timestamp):
        """Record the latest independently reported ISS gust."""
        now = self._advance(timestamp)

        if gust_mph is None:
            return

        gust = float(gust_mph)
        if not isfinite(gust) or gust < 0:
            return

        self.latest_iss = (now, gust)

    def snapshot(self, timestamp):
        """Return diagnostic measurements without asserting validity."""
        now = self._advance(timestamp)

        five_minute = [
            speed for when, speed in self.samples
            if when >= now - 300
        ]
        ten_minute = [speed for _, speed in self.samples]

        iss_age = (
            None if self.latest_iss is None
            else now - self.latest_iss[0]
        )

        return {
            "timestamp": now,
            "rxWindGust5": max(five_minute) if five_minute else None,
            "rxWindGust10": max(ten_minute) if ten_minute else None,
            "rxSampleCount5": len(five_minute),
            "rxSampleCount10": len(ten_minute),
            "rxHistorySpanSeconds": (
                now - self.samples[0][0] if self.samples else 0
            ),
            "issWindGust10": (
                self.latest_iss[1] if self.latest_iss else None
            ),
            "issAgeSeconds": iss_age,
            "issFresh": (
                iss_age is not None
                and iss_age <= self.iss_max_age_seconds
            ),
        }
