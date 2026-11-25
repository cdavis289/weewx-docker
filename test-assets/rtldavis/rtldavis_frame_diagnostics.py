"""Optional, observation-only RF and sensor plausibility telemetry.

Never suppresses frames or changes WeeWX packets. The receiver already has
a 2.5-second burst guard; this class measures accepted-frame patterns only.
"""
from collections import Counter
import math


class FrameDiagnostics:
    def __init__(self, duplicate_window_seconds=0.5):
        self.duplicate_window_seconds = float(duplicate_window_seconds)
        self.last = {}
        self.counts = Counter()

    def inspect(self, payload, timestamp, readings):
        """Return labels for an accepted frame, without changing readings."""
        labels = []
        channel = (payload[0] & 7) + 1 if payload else None
        previous = self.last.get(channel)
        if previous is not None:
            old_payload, old_time = previous
            elapsed = timestamp - old_time
            if 0 <= elapsed <= self.duplicate_window_seconds:
                if old_payload == bytes(payload):
                    labels.append("duplicate_candidate")
                else:
                    labels.append("near_burst_candidate")
        self.last[channel] = (bytes(payload), timestamp)
        # Conservative physical bounds only, not weather-change thresholds.
        bounds = {
            "humidity": (0, 100), "humid_1": (0, 100),
            "humid_2": (0, 100), "wind_speed": (0, 90),
            "wind_gust": (0, 90), "uv": (0, 20),
            "temperature": (-90, 65), "temp_1": (-90, 65),
            "temp_2": (-90, 65),
        }
        for field, (low, high) in bounds.items():
            value = readings.get(field)
            if value is not None:
                try:
                    number = float(value)
                    if not math.isfinite(number) or not low <= number <= high:
                        labels.append("out_of_bounds:" + field)
                except (TypeError, ValueError):
                    labels.append("invalid_value:" + field)
        self.counts["accepted_frames"] += 1
        for label in labels:
            self.counts[label] += 1
        return labels
