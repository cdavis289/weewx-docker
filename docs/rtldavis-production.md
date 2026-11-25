# RTL-Davis production maintenance

The Docker image uses the standalone Python driver maintained at
cdavis289/weewx-rtldavis-py.

## Source provenance

Dockerfile.rtldavis records the driver version, custom production
release, repository and exact source commit.

The source manifest records SHA-256 checksums for all eight driver
modules, before and after Docker-specific customizations.

## Automated updates

Only published stable vX.Y.Z-prod.N releases from the maintained
Python fork are eligible for automated updates.

The updater rejects downgrades, moved installed release tags,
unexpected module sets and inconsistent driver versions.

Upstream releases are monitored separately through a read-only
GitHub Actions workflow. Upstream releases are not directly vendored.

Automated updates create pull requests. They do not deploy containers.

## Local validation

Run from the Docker repository root:

    python3 tools/test-rtldavis-updater.py
    python3 tools/validate-rtldavis.py --dockerfile Dockerfile.rtldavis

Build a candidate:

    docker build -f Dockerfile.rtldavis -t weewx-rtldavis:candidate .

Validate the candidate:

    bash tools/test-rtldavis-image.sh weewx-rtldavis:candidate

The smoke test uses disposable containers and temporary data.
It does not access the production database or USB receiver.

## Deployment

Complete live receiver validation before publishing the first
production release or replacing the production receiver.

Retain the previous working image, configuration and database
backup for rollback.
