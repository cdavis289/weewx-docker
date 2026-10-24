#!/usr/bin/env pytest -vs
"""Tests for example container."""

# Standard Python Libraries
import os
import re
import time

# Third-Party Libraries
import pytest

READY_MESSAGE = "engine: Starting main packet loop"
VERSION_FILE = "src/version.txt"


def test_gen_config(gen_test_config_container):
    """Test that the test configuration generator completed successfully."""
    # Wait until the container has exited or timeout.

    for _ in range(10):
        gen_test_config_container.reload()
        if gen_test_config_container.status == "exited":
            break
        time.sleep(1)
    assert gen_test_config_container.status == "exited", "config generator did not exit"
    # The container must exit cleanly: a non-zero exit code means configuration
    # generation failed (e.g. weectl crashing), which would otherwise be masked
    # by only checking that the container reached the "exited" state.
    assert (
        gen_test_config_container.wait()["StatusCode"] == 0
    ), "The configuration generator did not exit cleanly"


@pytest.mark.parametrize(
    "container",
    [
        "main_container",
        "version_container",
    ],
)
def test_container_running(container, request):
    """Test that the container has started."""
    # Lazy fixture evaluation
    container = request.getfixturevalue(container)

    # Wait until the container is running or timeout.
    for _ in range(10):
        container.reload()
        if container.status != "created":
            break
        time.sleep(1)
    assert container.status in ("exited", "running")


def test_wait_for_version_container_exit(version_container):
    """Wait for version container to exit cleanly."""
    assert (
        version_container.wait()["StatusCode"] == 0
    ), "The version container did not exit cleanly"


def test_log_version(version_container, project_version):
    """Verify the container outputs the correct version to the logs."""
    version_container.wait()  # make sure container exited if running test isolated
    log_output = version_container.logs().decode("utf-8").strip()
    assert (
        log_output == project_version
    ), "Container version output to log does not match project version file"


def test_wait_for_ready(main_container):
    """Wait for container to be ready."""
    TIMEOUT = 30
    for _ in range(TIMEOUT):
        if READY_MESSAGE in main_container.logs().decode("utf-8"):
            break
        time.sleep(1)
    else:
        raise Exception(
            f"Container does not seem ready.  "
            f'Expected "{READY_MESSAGE}" in the log within {TIMEOUT} seconds.'
        )


def release_image_version(project_version, release_tag):
    """Validate an upstream version with an optional container revision."""
    pattern = rf"v{re.escape(project_version)}(?:-r[1-9][0-9]*)?"
    assert re.fullmatch(pattern, release_tag or ""), (
        f"Release tag {release_tag!r} must match v{project_version} "
        "or its -rN container revision"
    )
    return release_tag[1:]


@pytest.mark.parametrize(
    ("release_tag", "valid"),
    [
        ("v5.5.2", True),
        ("v5.5.2-r1", True),
        ("v5.5.2-r12", True),
        ("v5.5.3-r1", False),
        ("v5.5.2-rc1", False),
        ("v5.5.2-r0", False),
        ("v5.5.2-r1-extra", False),
    ],
)
def test_release_image_version_validation(release_tag, valid):
    """Container revisions must not change the upstream WeeWX version."""
    if valid:
        assert release_image_version("5.5.2", release_tag) == release_tag[1:]
    else:
        with pytest.raises(AssertionError):
            release_image_version("5.5.2", release_tag)


def current_release_tag():
    """Use the explicit tag, or the GitHub release ref when running in Actions."""
    return os.getenv("RELEASE_TAG") or (
        os.getenv("GITHUB_REF_NAME")
        if os.getenv("GITHUB_EVENT_NAME") == "release"
        else None
    )


@pytest.mark.skipif(
    not (
        os.environ.get("RELEASE_TAG")
        or (
            os.environ.get("GITHUB_EVENT_NAME") == "release"
            and os.environ.get("GITHUB_REF_NAME")
        )
    ),
    reason="not a release (no release tag available)",
)
def test_release_version(project_version):
    """Verify release version is the project version or a container revision."""
    release_image_version(project_version, current_release_tag())


@pytest.mark.skipif(
    os.environ.get("GITHUB_ACTIONS") != "true"
    or os.environ.get("GITHUB_EVENT_NAME") != "release",
    reason="only checked during GitHub Actions release builds",
)
def test_container_version_label_matches(version_container, project_version):
    """Verify the OCI label matches the full validated release image version."""
    expected_version = release_image_version(project_version, current_release_tag())
    assert (
        version_container.labels["org.opencontainers.image.version"] == expected_version
    ), "Container version label does not match release image version"
