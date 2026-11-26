#!/usr/bin/env bash
set -Eeuo pipefail

IMAGE="${1:?Usage: test-rtldavis-image.sh IMAGE}"

ROOT="$(pwd)"
TEST_ROOT="$(mktemp -d)"
TEST_DATA="${TEST_ROOT}/data"
mkdir -m 0755 "${TEST_DATA}"
CONTAINER=""

# Keep the host-owned logs separate from the container-owned data mount.

cleanup() {
  if [[ -n "${CONTAINER}" ]]; then
    docker rm -f "${CONTAINER}" > /dev/null 2>&1 || true
  fi

  docker run --rm \
    --user 0 \
    --entrypoint /bin/sh \
    -v "${TEST_DATA}:/cleanup" \
    "${IMAGE}" \
    -c 'find /cleanup -mindepth 1 -delete' || true

  rmdir "${TEST_DATA}" || true
  rm -f "${TEST_ROOT}/labels.json" "${TEST_ROOT}/startup.log" "${TEST_ROOT}/readonly.log"
  rmdir "${TEST_ROOT}" || true
}

trap cleanup EXIT

echo "=== SOURCE INTEGRITY ==="
python3 tools/validate-rtldavis.py \
  --dockerfile Dockerfile.rtldavis

echo "=== IMAGE PROVENANCE ==="
docker image inspect "${IMAGE}" \
  --format '{{json .Config.Labels}}' \
  > "${TEST_ROOT}/labels.json"

python3 - "${TEST_ROOT}/labels.json" << 'PYTHON'
import json
import sys
from pathlib import Path

labels = json.loads(Path(sys.argv[1]).read_text())
manifest = json.loads(
    Path("test-assets/rtldavis/source-manifest.json").read_text()
)

expected = {
    "repository": manifest["repository"],
    "revision": manifest["commit"],
    "version": "v" + manifest["driver_version"],
    "release": manifest["release"],
}

for key, value in expected.items():
    assert labels["io.github.rtldavis." + key] == value, key

print("Image provenance verified.")
PYTHON

echo "=== IMAGE MODULE CHECKSUMS ==="

docker run --rm \
  --entrypoint /opt/venv/bin/python \
  -v "${ROOT}/tools/validate-rtldavis.py:/tmp/validate.py:ro" \
  -v "${ROOT}/test-assets/rtldavis/source-manifest.json:/tmp/manifest.json:ro" \
  "${IMAGE}" \
  /tmp/validate.py \
  --manifest /tmp/manifest.json \
  --directory /opt/weewx-extensions/weewx-rtldavis

echo "=== NON-ROOT RUNTIME ==="
docker run --rm --entrypoint /bin/sh "${IMAGE}" -ec '
  test "$(id -u)" -eq 1000
  test "$(id -g)" -eq 1000
  test ! -w /opt/weewx-extensions/weewx-rtldavis/rtldavis.py
'

echo "=== STARTUP OVERLAY ==="

mkdir -p "${TEST_DATA}/skins/new-belchertown"

printf '%s\n' \
  '# CUSTOM TEST CHARTS FILE' \
  '[test_marker]' \
  '    value = preserve_me' \
  > "${TEST_DATA}/skins/new-belchertown/charts.conf"

# Give the runtime user ownership of the test mount, not the host's real data.
docker run --rm --user 0 --entrypoint /bin/sh \
  -v "${TEST_DATA}:/data" "${IMAGE}" -ec 'chown -R 1000:1000 /data'

CONTAINER="$(docker create \
  --entrypoint /usr/local/bin/start-weewx-rtldavis-overlay \
  -v "${TEST_DATA}:/data" \
  "${IMAGE}")"

timeout 60s docker start -a "${CONTAINER}" \
  > "${TEST_ROOT}/startup.log" 2>&1 || true

docker rm -f "${CONTAINER}" > /dev/null
CONTAINER=""

grep -q "Installing/updating Belchertown New Python extension" \
  "${TEST_ROOT}/startup.log"

grep -q "preserve_me" \
  "${TEST_DATA}/skins/new-belchertown/charts.conf"

echo "=== READ-ONLY DATA REJECTION ==="
if docker run --rm -v "${TEST_DATA}:/data:ro" "${IMAGE}" \
  > "${TEST_ROOT}/readonly.log" 2>&1; then
  echo "Expected read-only startup failure" >&2
  exit 1
fi
grep -q "must be writable by uid:gid" "${TEST_ROOT}/readonly.log"

echo "=== INSTALLED MODULES AND IMPORTS ==="

docker run --rm \
  --entrypoint /opt/venv/bin/python \
  -v "${TEST_DATA}:/data" \
  -v "${ROOT}/tools/validate-rtldavis.py:/tmp/validate.py:ro" \
  -v "${ROOT}/test-assets/rtldavis/source-manifest.json:/tmp/manifest.json:ro" \
  "${IMAGE}" \
  /tmp/validate.py \
  --manifest /tmp/manifest.json \
  --directory /data/bin/user \
  --imports

echo "=== RUNTIME DEPENDENCIES ==="

docker run --rm \
  --entrypoint /bin/sh \
  -v "${TEST_DATA}:/data" \
  "${IMAGE}" \
  -ec '
        command -v rtl_test
        command -v rtl_fm
        test ! -e /usr/local/bin/rtldavis
        test -f /data/bin/user/MQTTSubscribe.py
        test -f /data/bin/user/mqtt.py
        /opt/venv/bin/python -c "
import numpy
import ctypes.util
assert ctypes.util.find_library(\"rtlsdr\")
print(\"NumPy:\", numpy.__version__)
"
    '

echo "Complete RTL-Davis image smoke test passed."
