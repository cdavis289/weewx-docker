# weewx-docker 🌩🐳 #

[![GitHub Build Status](https://github.com/cdavis289/weewx-docker/workflows/Build/badge.svg)](https://github.com/cdavis289/weewx-docker/actions)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/cdavis289/weewx-docker/badge)](https://securityscorecards.dev/viewer/?uri=github.com/cdavis289/weewx-docker)
[![CII Best Practices](https://bestpractices.coreinfrastructure.org/projects/6003/badge)](https://bestpractices.coreinfrastructure.org/projects/6003)
[![CodeQL](https://github.com/cdavis289/weewx-docker/workflows/CodeQL/badge.svg)](https://github.com/cdavis289/weewx-docker/actions/workflows/codeql-analysis.yml)
[![WeeWX Version](https://img.shields.io/github/v/release/cdavis289/weewx-docker?color=brightgreen)](https://github.com/cdavis289/weewx-docker/releases)

[![GHCR](https://img.shields.io/badge/container-ghcr.io-blue)](https://github.com/cdavis289/weewx-docker/pkgs/container/weewx)
[![GitHub package](https://img.shields.io/badge/package-weewx-blue)](https://github.com/cdavis289/weewx-docker/pkgs/container/weewx)
[![Platforms](https://img.shields.io/badge/platforms-amd64%20%7C%20arm%2Fv6%20%7C%20arm%2Fv7%20%7C%20arm64%20%7C%20ppc64le%20%7C%20riscv64%20%7C%20s390x-blue)](https://github.com/cdavis289/weewx-docker/pkgs/container/weewx)

This docker container can be used to quickly get a
[WeeWX](http://weewx.com) instance up and running.

## Available images ##

This repository publishes two images to the [GitHub Container Registry](https://github.com/cdavis289/weewx-docker/pkgs):

| Image | Purpose |
| --- | --- |
| `ghcr.io/cdavis289/weewx:5.6.0` | Base WeeWX 5.6.0 image for conventional station drivers. |
| `ghcr.io/cdavis289/weewx-rtldavis:5.6.0` | WeeWX 5.6.0 with the maintained **Python RTL-Davis** receiver and the extensions listed below. |

The RTL-Davis image uses [cdavis289/weewx-rtldavis-py](https://github.com/cdavis289/weewx-rtldavis-py), pinned to the published [`v0.23.0-prod.1` driver release](https://github.com/cdavis289/weewx-rtldavis-py/releases/tag/v0.23.0-prod.1). It runs the receiver **inside WeeWX** using an RTL-SDR USB device; no separate Go receiver is needed.

The RTL-Davis image also includes MQTTSubscribe, the maintained WeeWX MQTT extension, and Belchertown New. At startup it installs or updates the vendored RTL-Davis and MQTT extension files in `/data/bin/user` and the Belchertown New skin in `/data/skins/new-belchertown`. It preserves an existing `charts.conf` but may replace other files at those paths. Back up the `/data` directory before changing image versions, and review [RTL-Davis production maintenance](docs/rtldavis-production.md) for build and validation commands.

For a reproducible deployment, use a versioned image tag such as `:5.6.0`; `:latest` follows the newest full release and can change.

## Running Python RTL-Davis ##

Use the RTL-Davis variant for Davis wireless stations received through an RTL-SDR dongle. This is a **separate example** from the base WeeWX image below:

```yaml
services:
  weewx:
    image: ghcr.io/cdavis289/weewx-rtldavis:5.6.0
    pull_policy: never
    restart: unless-stopped
    stop_grace_period: 90s
    devices:
      - /dev/bus/usb:/dev/bus/usb
    volumes:
      - ./data:/data
```

Pull the selected image explicitly before starting when using `pull_policy: never`:

```sh
docker pull ghcr.io/cdavis289/weewx-rtldavis:5.6.0
docker compose up -d --no-deps --pull never weewx
```

Provide appropriate USB device permissions for your host and container, and configure `[Rtldavis]` in `data/weewx.conf` with `driver = user.rtldavis`, the correct frequency plan and ISS channel, and optionally a stable dongle serial number via `device`. See the [Python driver configuration reference](https://github.com/cdavis289/weewx-rtldavis-py/blob/main/docs/configuration.md).

The additional MQTT and Belchertown services require configuration in `weewx.conf`; bundling their files does **not** configure a broker, credentials, report skin, or topics automatically.

## Running ##

The easiest way to start the container is to create a
`docker-compose.yml` similar to the following.  If you use a
serial port to connect to your weather station, make sure the
container has permissions to access the port.

Modify any paths or devices as needed:

```yaml
---
name: "weewx"

services:
  weewx:
    image: ghcr.io/cdavis289/weewx:5
    volumes:
      - type: bind
        source: ./data
        target: /data
    devices:
      - "/dev/ttyUSB0:/dev/ttyUSB0"
```

1. Create a directory on the host to store the configuration and database files:

    ```console
    mkdir data
    chown 1000:1000 data
    ```

1. If this is the first time running weewx, use the following command to start
   the container and generate a configuration file:

    ```console
    docker compose run --rm weewx
    ```

1. The configuration file will be created in the `data` directory.  You should
   edit this file to match the setup of your weather station.

1. When you are satisfied with configuration the container can be started in the
   background with:

    ```console
    docker compose up --detach
    ```

## Running as a different user ##

By default the container runs as the non-root `weewx` user (uid/gid
`1000`), which is why the `data` directory is assigned to `1000:1000` in
the steps above.

The container also supports running under an **arbitrary `uid:gid`**.

```yaml
services:
  weewx:
    image: ghcr.io/cdavis289/weewx:5
    user: "1234:1234"
    volumes:
      - type: bind
        source: ./data
        target: /data
```

The only requirement is that the volume mounted at `/data` be writable
by the `uid` the container runs as.  For a bind mount, make the host
directory writable by that user:

```console
mkdir data
chown 1234:1234 data
```

## Upgrading ##

1. Stop the running container:

    ```console
    docker compose down
    ```

1. Pull the selected image from GHCR (if your service uses \`pull_policy: never\`, pull it explicitly with \`docker pull\` before recreating the service):

    ```console
    docker compose pull
    ```

1. Update your configuration file (a backup will be created):

    ```console
    docker compose run --rm weewx station upgrade
    ```

1. Read through the new configuration and verify.
   It is helpful to `diff` the new config with the backup.  Check the
   [WeeWX Upgrade Guide](http://weewx.com/docs/upgrading.htm#Instructions_for_specific_versions)
   for instructions for specific versions.

1. Start the container up with the new image version:

    ```console
    docker compose up --detach
    ```

## Migrating ##

If you are migrating a WeeWX installation, you need to configure the logger to
write to the console. Add the following to your `weewx.conf` file to see the log
output in the container logs:

```ini
[Logging]
    [[root]]
        level = INFO
        handlers = console,
```

## Installing WeeWX Extensions ##

If arguments are passed to the container, they are forwarded on to the
[`weectl`](https://weewx.com/docs/5.6/utilities/weectl-about/) command.  This
can be used to install extensions:

```console
docker compose run --rm weewx \
  extension install --yes \
  https://github.com/matthewwall/weewx-windy/archive/master.zip
```

```console
docker compose run --rm weewx \
  extension install --yes \
  https://github.com/matthewwall/weewx-mqtt/archive/master.zip
```

## Installing Python Packages ##

To install and persist Python packages, use the `pip` command. The libraries
will be installed into the `data` volume, ensuring they persist between
container restarts.

```console
docker compose run --rm --entrypoint pip weewx \
  install git+https://github.com/felddy/weewx-home-assistant@v1.0.0
```

## Image tags ##

| Image:tag | Description |
| --- | --- |
| `ghcr.io/cdavis289/weewx:5.6.0` | WeeWX 5.6.0 base release. |
| `ghcr.io/cdavis289/weewx-rtldavis:5.6.0` | WeeWX 5.6.0 plus Python RTL-Davis v0.23.0-prod.1. |
| `ghcr.io/cdavis289/weewx:5` | Moving base-image major-version tag. |
| `ghcr.io/cdavis289/weewx-rtldavis:latest` | Moving RTL-Davis tag for the newest full release. |

The two image families have separate packages and support versioned release tags. Publishing a new release may move `latest`; a running container does not change until it is recreated from a new image.

See the
[base image](https://github.com/cdavis289/weewx-docker/pkgs/container/weewx) and
[RTL-Davis image](https://github.com/cdavis289/weewx-docker/pkgs/container/weewx-rtldavis)
packages for available tags.

## Volumes ##

| Mount point | Purpose                                                                                           |
| ----------- | ------------------------------------------------------------------------------------------------- |
| `/data`     | [WeeWX root](https://weewx.com/docs/5.6/usersguide/where/#location-of-weewx-components) directory |

## Building from source ##

Build the image locally using this git repository as the [build context](https://docs.docker.com/engine/reference/commandline/build/#git-repositories):

```console
docker build \
  --tag ghcr.io/cdavis289/weewx:5.6.0 \
  https://github.com/cdavis289/weewx-docker.git#develop
```

## Cross-platform builds ##

To create images that are compatible with other platforms you can use the
[`buildx`](https://docs.docker.com/buildx/working-with-buildx/) feature of
Docker:

1. Copy the project to your machine using the `Clone` button above
   or the command line:

    ```console
    git clone https://github.com/cdavis289/weewx-docker.git
    cd weewx-docker
    ```

1. Build the image using `buildx`:

    ```console
    docker buildx build \
      --platform linux/amd64 \
      --output type=docker \
      --tag ghcr.io/cdavis289/weewx:5.6.0 .
    ```

## Contributing ##

We welcome contributions!  Please see [`CONTRIBUTING.md`](CONTRIBUTING.md) for
details.

## License ##

This project is released as open source under the [MIT license](LICENSE).

All contributions to this project will be released under the same MIT license.
By submitting a pull request, you are agreeing to comply with this waiver of
copyright interest.
