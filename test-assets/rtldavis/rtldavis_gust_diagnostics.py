"""Opt-in, bounded evidence capture for suspicious Davis wind gusts.

This module does not modify, filter, or validate weather observations.
"""
from collections import deque
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import tempfile
import time
import uuid

from user.rtldavis_diagnostic_storage import prune_captures

LOG = logging.getLogger(__name__)


class GustDiagnostics:
    """Retain bounded decoded RF history and persist anomaly evidence."""

    def __init__(self, directory, absolute_mph=50.0, ratio=5.0,
                 ratio_minimum_mph=25.0, before_seconds=300,
                 after_seconds=60, max_files=100, clock=None,
                 max_frames=4096, max_events=128, max_pending=8,
                 max_capture_seconds=180,
                 retention_callback=None, retry_seconds=30):
        self.directory = Path(directory)
        self.absolute_mph = float(absolute_mph)
        self.ratio = float(ratio)
        self.ratio_minimum_mph = float(ratio_minimum_mph)
        self.before_seconds = max(0.0, float(before_seconds))
        self.after_seconds = max(0.0, float(after_seconds))
        self.max_files = max(1, int(max_files))
        self.max_frames = max(1, int(max_frames))
        self.max_events = max(1, int(max_events))
        self.max_pending = max(1, int(max_pending))
        self.max_capture_seconds = max(
            self.after_seconds, float(max_capture_seconds))
        self.clock = clock or time.time

        self.history = deque(maxlen=self.max_frames)
        self.pending = deque(maxlen=self.max_pending)
        self.active = None
        self.dropped_captures = 0
        self.write_failures = 0
        self.retention_callback = retention_callback
        self.retry_seconds = max(0.0, float(retry_seconds))
        self._retry_at = 0.0

    def _queue_active(self):
        if self.active is None:
            return

        if len(self.pending) == self.max_pending:
            self.dropped_captures += 1
            LOG.warning(
                "Gust diagnostic queue full; dropping oldest capture "
                "(total dropped=%d)", self.dropped_captures)

        self.pending.append(self.active)
        self.active = None

    def observe(self, payload, timestamp=None, **metadata):
        """Record decoded RF payloads; never retain raw IQ samples."""
        now = float(self.clock() if timestamp is None else timestamp)

        item = {
            "timestamp": now,
            "payload_hex": bytes(payload).hex(),
            "channel": (payload[0] & 7) + 1 if payload else None,
            "message_type": payload[0] >> 4 if payload else None,
        }
        item.update(metadata)

        self.history.append(item)

        cutoff = now - self.before_seconds
        while self.history and self.history[0]["timestamp"] < cutoff:
            self.history.popleft()

        self.tick(now)

        if self.active is not None and now <= self.active["until"]:
            frames = self.active["frames"]

            if len(frames) == self.max_frames:
                self.active["truncated_frames"] += 1

            frames.append(dict(item))

    def check(self, gust_mph, average_mph=None,
              timestamp=None, **metadata):
        """Trigger capture for an absolute or relative gust anomaly."""
        if gust_mph is None:
            return False

        gust = float(gust_mph)
        avg = None if average_mph is None else float(average_mph)

        absolute = gust >= self.absolute_mph
        relative = (
            avg is not None and avg > 0
            and gust >= self.ratio_minimum_mph
            and gust / avg >= self.ratio
        )

        if not (absolute or relative):
            return False

        now = float(self.clock() if timestamp is None else timestamp)
        self.tick(now)

        reasons = [
            reason for reason, enabled in (
                ("absolute", absolute),
                ("ratio", relative),
            ) if enabled
        ]

        event = {
            "timestamp": now,
            "gust_mph": gust,
            "average_mph": avg,
            "reasons": reasons,
            "metadata": metadata,
        }

        if self.active is not None:
            capture = self.active

            if len(capture["events"]) == self.max_events:
                capture["truncated_events"] += 1

            capture["events"].append(event)

            capture["until"] = min(
                capture["hard_until"],
                max(capture["until"], now + self.after_seconds),
            )

            capture["reasons"] = list(dict.fromkeys(
                capture["reasons"] + reasons))

            capture["gust_mph"] = max(
                capture["gust_mph"], gust)

            return True

        self.active = {
            "timestamp": now,
            "until": now + self.after_seconds,
            "hard_until": now + self.max_capture_seconds,
            "gust_mph": gust,
            "average_mph": avg,
            "reasons": reasons,
            "metadata": metadata,
            "truncated_frames": 0,
            "truncated_events": 0,
            "events": deque([event], maxlen=self.max_events),
            "frames": deque(
                (dict(item) for item in self.history
                 if now - self.before_seconds
                 <= item["timestamp"] <= now),
                maxlen=self.max_frames,
            ),
        }

        if self.after_seconds == 0:
            self._queue_active()
            self._persist_pending()

        return True

    def tick(self, timestamp=None):
        """Finalize elapsed captures and retry pending writes."""
        now = float(self.clock() if timestamp is None else timestamp)

        if self.active is not None and now > self.active["until"]:
            self._queue_active()

        self._persist_pending()

    def flush(self):
        """Persist completed and incomplete captures on shutdown."""
        if self.active is not None:
            now = float(self.clock())
            self.active["incomplete"] = now < self.active["until"]
            self.active["finalized_timestamp"] = now
        self._queue_active()
        self._persist_pending(force=True, max_captures=None)

    def _persist_pending(self, force=False, max_captures=1):
        if not force and time.monotonic() < self._retry_at:
            return

        written = 0
        while self.pending and (
                max_captures is None or written < max_captures):
            if not self._write(self.pending[0]):
                self._retry_at = (
                    time.monotonic() + self.retry_seconds)
                break

            self.pending.popleft()
            written += 1
            self._retry_at = 0.0

    def _write(self, capture):
        """Atomically persist one capture; retain it on write failure."""
        temp_name = None

        try:
            self.directory.mkdir(parents=True, exist_ok=True)

            stamp = datetime.fromtimestamp(
                capture["timestamp"], tz=timezone.utc
            ).strftime("%Y%m%dT%H%M%S%fZ")

            path = self.directory / (
                "gust-%s-%s.json" % (stamp, uuid.uuid4().hex)
            )

            document = dict(capture)
            document["frames"] = list(capture["frames"])
            document["events"] = list(capture["events"])

            fd, temp_name = tempfile.mkstemp(
                prefix=".gust-",
                suffix=".tmp",
                dir=str(self.directory),
            )

            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(
                    document, stream,
                    sort_keys=True, default=str,
                )
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())

            os.replace(temp_name, path)
            temp_name = None

        except (OSError, ValueError, TypeError):
            self.write_failures += 1

            if self.write_failures == 1 or self.write_failures % 100 == 0:
                LOG.exception(
                    "Unable to persist gust diagnostic capture "
                    "(failures=%d)", self.write_failures)

            return False

        finally:
            if temp_name is not None:
                try:
                    os.unlink(temp_name)
                except FileNotFoundError:
                    pass
                except OSError:
                    LOG.exception(
                        "Unable to remove temporary gust capture")

        # A retention failure must not cause a successfully saved
        # capture to be written again.
        try:
            if self.retention_callback is not None:
                self.retention_callback()
            else:
                prune_captures([
                    (self.directory, "gust", self.max_files),
                ])
        except OSError:
            LOG.exception("Unable to prune gust diagnostic captures")

        return True
