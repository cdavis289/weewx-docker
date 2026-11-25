#!/usr/bin/env python3
"""Offline regression tests for the production release updater."""

# Standard Python Libraries
import json
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

updater = runpy.run_path("update-rtldavis")
release_key = updater["release_key"]
latest_release = updater["latest_release"]
main = updater["main"]
namespace = main.__globals__


def release(tag, draft=False, prerelease=False):
    """Construct mock GitHub release metadata."""
    return {
        "tag_name": tag,
        "draft": draft,
        "prerelease": prerelease,
    }


class UpdaterTests(unittest.TestCase):
    """Test production release selection and safeguards."""

    def test_valid_tags(self):
        """Accept supported production release tags."""
        self.assertEqual(
            release_key("v0.23.0-prod.1"),
            (0, 23, 0, 1),
        )
        self.assertEqual(
            release_key("v0.24.0-prod.10"),
            (0, 24, 0, 10),
        )

    def test_invalid_tags(self):
        """Reject unsupported release tags."""
        for tag in (
            "v0.23.0",
            "v0.23.0-prod.0",
            "v0.23.0-beta.1",
            "v0x23x0-prod.1",
            "v0.23.0-prod.1;echo",
        ):
            with self.subTest(tag=tag):
                with self.assertRaises(SystemExit):
                    release_key(tag)

    def test_numeric_release_order(self):
        """Compare release revisions numerically."""
        self.assertGreater(
            release_key("v0.23.0-prod.10"),
            release_key("v0.23.0-prod.2"),
        )

    def test_latest_approved_release(self):
        """Select the latest approved release."""
        releases = [
            release("v0.23.0"),
            release("v0.23.0-prod.2"),
            release("v0.23.0-prod.10"),
            release("v0.24.0-prod.1", draft=True),
            release("v0.25.0-prod.1", prerelease=True),
        ]

        with patch.dict(
            namespace,
            {"fetch_json": lambda url: releases},
        ):
            self.assertEqual(latest_release(), "v0.23.0-prod.10")

    def test_no_approved_releases(self):
        """Handle an empty approved release list."""
        with patch.dict(
            namespace,
            {"fetch_json": lambda url: [release("v0.23.0")]},
        ):
            self.assertIsNone(latest_release())

    def run_update(self, current, requested, commit=None):
        """Exercise the updater without network access."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "source-manifest.json"
            manifest.write_text(json.dumps(current))

            with (
                patch.dict(
                    namespace,
                    {
                        "DESTINATION": root,
                        "fetch_json": lambda url: release(requested),
                    },
                ),
                patch.object(sys, "argv", ["update-rtldavis", requested]),
                patch("subprocess.run"),
                patch(
                    "subprocess.check_output",
                    return_value=commit or "a" * 40,
                ),
            ):
                try:
                    main()
                finally:
                    self.assertEqual(
                        json.loads(manifest.read_text()),
                        current,
                    )

    def test_downgrade_rejected(self):
        """Reject older production releases."""
        with self.assertRaisesRegex(SystemExit, "downgrade"):
            self.run_update(
                {
                    "release": "v0.23.0-prod.2",
                    "driver_version": "0.23.0",
                    "commit": "a" * 40,
                },
                "v0.23.0-prod.1",
            )

    def test_unreleased_downgrade_rejected(self):
        """Protect the initial driver pin."""
        with self.assertRaisesRegex(SystemExit, "downgrade"):
            self.run_update(
                {
                    "release": "unreleased",
                    "driver_version": "0.23.0",
                    "commit": "a" * 40,
                },
                "v0.22.2-prod.1",
            )

    def test_moved_tag_rejected(self):
        """Reject changes to an installed tag."""
        with self.assertRaisesRegex(SystemExit, "tag has moved"):
            self.run_update(
                {
                    "release": "v0.23.0-prod.1",
                    "driver_version": "0.23.0",
                    "commit": "a" * 40,
                },
                "v0.23.0-prod.1",
                commit="b" * 40,
            )

    def test_same_release_is_noop(self):
        """Leave an installed release unchanged."""
        self.run_update(
            {
                "release": "v0.23.0-prod.1",
                "driver_version": "0.23.0",
                "commit": "a" * 40,
            },
            "v0.23.0-prod.1",
            commit="a" * 40,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
