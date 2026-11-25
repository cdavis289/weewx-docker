#!/usr/bin/env python3
"""Validate standalone RTL-Davis source integrity."""

# Standard Python Libraries
import argparse
import ast
import hashlib
import importlib
import json
from pathlib import Path
import re
import sys

MODULES = {
    "rtldavis.py",
    "rtldavis_receiver.py",
    "rtldavis_dsp.py",
    "rtldavis_gust_diagnostics.py",
    "rtldavis_frame_diagnostics.py",
    "rtldavis_phase_c_diagnostics.py",
    "rtldavis_diagnostic_storage.py",
    "rtldavis_wind_validation.py",
}


def main():
    """Validate driver integrity and optional imports."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        default="test-assets/rtldavis/source-manifest.json",
    )
    parser.add_argument(
        "--directory",
        default="test-assets/rtldavis",
    )
    parser.add_argument("--dockerfile")
    parser.add_argument("--imports", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text())
    root = Path(args.directory).resolve()

    if not (manifest["repository"] == "cdavis289/weewx-rtldavis-py"):
        raise SystemExit(
            "Validation failed: manifest['repository'] == 'cdavis289/weewx-rtldavis-py'"
        )
    if not (re.fullmatch("[0-9a-f]{40}", manifest["commit"])):
        raise SystemExit(
            "Validation failed: re.fullmatch('[0-9a-f]{40}', manifest['commit'])"
        )
    if not (set(manifest["modules"]) == MODULES):
        raise SystemExit("Validation failed: set(manifest['modules']) == MODULES")

    actual = {p.name for p in root.glob("rtldavis*.py")}
    if not (actual == MODULES):
        raise SystemExit(actual)

    for name in sorted(MODULES):
        path = root / name
        content = path.read_bytes()
        hashes = manifest["modules"][name]

        if not (re.fullmatch("[0-9a-f]{64}", hashes["source_sha256"])):
            raise SystemExit(
                "Validation failed: re.fullmatch('[0-9a-f]{64}', hashes['source_sha256'])"
            )
        if not (hashlib.sha256(content).hexdigest() == hashes["vendored_sha256"]):
            raise SystemExit(name)

        compile(content, name, "exec")
        print("Verified:", name)

    driver = (root / "rtldavis.py").read_text()
    tree = ast.parse(driver)

    versions = [
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(t, ast.Name) and t.id == "DRIVER_VERSION" for t in node.targets
        )
    ]

    if not (versions == [manifest["driver_version"]]):
        raise SystemExit("Validation failed: versions == [manifest['driver_version']]")
    if not ("return self._hardware_name" in driver):
        raise SystemExit("Validation failed: 'return self._hardware_name' in driver")

    if args.dockerfile:
        docker = Path(args.dockerfile).read_text()
        expected = {
            "RTL_DAVIS_REF": "v" + manifest["driver_version"],
            "RTL_DAVIS_RELEASE": manifest["release"],
            "RTL_DAVIS_REPOSITORY": manifest["repository"],
            "RTL_DAVIS_COMMIT": manifest["commit"],
        }

        for name, value in expected.items():
            matches = re.findall(rf"^ARG {name}=(.*)$", docker, re.MULTILINE)
            if not (matches == [value]):
                raise SystemExit(name)

    if args.imports:
        if not (root.name == "user"):
            raise SystemExit(root)
        sys.path.insert(0, str(root.parent))

        for name in sorted(MODULES):
            module = importlib.import_module("user." + Path(name).stem)
            if not (Path(module.__file__).resolve() == root / name):
                raise SystemExit(
                    "Validation failed: Path(module.__file__).resolve() == root / name"
                )
            print("Imported:", module.__name__)

    print("RTL-Davis integrity validation passed.")


if __name__ == "__main__":
    main()
