# RTL-Davis production maintenance #

The Docker image uses the standalone Python driver maintained at
cdavis289/weewx-rtldavis-py.

## Source provenance ##

Dockerfile.rtldavis records the driver version, custom production
release, repository and exact source commit.

The source manifest records SHA-256 checksums for all eight driver
modules, before and after Docker-specific customizations.

## Automated updates ##

Only published stable vX.Y.Z-prod.N releases from the maintained
Python fork are eligible for automated updates.

The updater rejects downgrades, moved installed release tags,
unexpected module sets and inconsistent driver versions.

Upstream releases are monitored separately through a read-only
GitHub Actions workflow. Upstream releases are not directly vendored.

Automated updates create pull requests. They do not deploy containers.

## Local validation ##

Run from the Docker repository root:

```bash
python3 tools/test-rtldavis-updater.py
python3 tools/validate-rtldavis.py --dockerfile Dockerfile.rtldavis
```

Build a candidate:

```bash
docker build -f Dockerfile.rtldavis -t weewx-rtldavis:candidate .
```

Validate the candidate:

```bash
bash tools/test-rtldavis-image.sh weewx-rtldavis:candidate
```

The smoke test uses disposable containers and temporary data.
It does not access the production database or USB receiver.

## Non-root runtime migration ##

The RTL-Davis image defaults to the base image's `weewx` user
(uid/gid 1000). The host must grant that user write access to the
mounted data, diagnostics, database and report directories, and
read/write access to the RTL-SDR USB device. Check numeric ownership
with `stat` and `ls -ln` before changing permissions.

Use a host udev rule restricted to the actual dongle's vendor/product
IDs (and serial if needed), with a dedicated group and mode 0660.
Pass that group's numeric GID through Compose `group_add`. For USB
re-enumeration, bind /dev/bus/usb and allow USB character devices
(major 189) using `device_cgroup_rules: ["c 189:* rw"]` on a
rootful Linux Docker host. Host device permissions still apply.
Do not use privileged mode or world-writable USB permissions.

For an existing installation, back up the configuration, database and
diagnostic files before migrating ownership. Verify the actual host
paths and intended owner; do not recursively chown unrelated mounts.
The overlay no longer changes ownership on non-root startup.
An explicit Compose `user: "0:0"` remains a temporary compatibility
override, but forfeits non-root isolation.

CI verifies default UID/GID, extension integrity, writable temporary
volume startup, charts preservation and read-only volume rejection.
It cannot establish physical USB reception. Test a candidate on a
spare receiver or after the current production comparison ends, without
sharing the live database or USB dongle with another receiver.

## Deployment ##

Complete live receiver validation before publishing the first
production release or replacing the production receiver.

Retain the previous working image, configuration and database
backup for rollback.
