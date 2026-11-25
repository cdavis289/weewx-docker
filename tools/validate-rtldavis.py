#!/usr/bin/env python3
"""Validate standalone RTL-Davis source integrity."""

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

    assert manifest["repository"] == "cdavis289/weewx-rtldavis-py"
    assert re.fullmatch(r"[0-9a-f]{40}", manifest["commit"])
    assert set(manifest["modules"]) == MODULES

    actual = {p.name for p in root.glob("rtldavis*.py")}
    assert actual == MODULES, actual

    for name in sorted(MODULES):
        path = root / name
        content = path.read_bytes()
        hashes = manifest["modules"][name]

        assert re.fullmatch(
            r"[0-9a-f]{64}", hashes["source_sha256"]
        )
        assert hashlib.sha256(content).hexdigest() == (
            hashes["vendored_sha256"]
        ), name

        compile(content, name, "exec")
        print("Verified:", name)

    driver = (root / "rtldavis.py").read_text()
    tree = ast.parse(driver)

    versions = [
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(t, ast.Name)
            and t.id == "DRIVER_VERSION"
            for t in node.targets
        )
    ]

    assert versions == [manifest["driver_version"]]
    assert "return self._hardware_name" in driver

    if args.dockerfile:
        docker = Path(args.dockerfile).read_text()
        expected = {
            "RTL_DAVIS_REF": "v" + manifest["driver_version"],
            "RTL_DAVIS_RELEASE": manifest["release"],
            "RTL_DAVIS_REPOSITORY": manifest["repository"],
            "RTL_DAVIS_COMMIT": manifest["commit"],
        }

        for name, value in expected.items():
            matches = re.findall(
                rf"^ARG {name}=(.*)$", docker, re.MULTILINE
            )
            assert matches == [value], name

    if args.imports:
        assert root.name == "user", root
        sys.path.insert(0, str(root.parent))

        for name in sorted(MODULES):
            module = importlib.import_module(
                "user." + Path(name).stem
            )
            assert Path(module.__file__).resolve() == root / name
            print("Imported:", module.__name__)

    print("RTL-Davis integrity validation passed.")


if __name__ == "__main__":
    main()
