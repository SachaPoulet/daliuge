# DALiuGE translator Docker image

This directory contains Docker images and helper scripts for the DALiuGE
translator. The deployment image is published as
`icrar/daliuge-translator:<tag>` and the development image uses the matching
`daliuge-common` and `daliuge-engine` development images.

## Building the image

Docker must be installed and running. From the `daliuge-translator` directory,
build one of the supported image variants:

```bash
./build_translator.sh dep       # release/deployment image
./build_translator.sh dev       # development image
./build_translator.sh slim      # build and slim the deployment image
```

The build uses the corresponding `icrar/daliuge-common` base image. The
development image also uses `icrar/daliuge-engine`.

## Starting the translator

Start a built image in the background with:

```bash
./run_translator.sh dep
```

For a development image, mount the local `dlg/translator` package so Python
changes are immediately visible in the container:

```bash
./run_translator.sh dev
```

The service is exposed on port `8084`. Locally, use
<http://localhost:8084/docs> for the FastAPI OpenAPI interface. Stop the
container with:

```bash
./stop_translator.sh
```

The `slim` mode runs the generated slim image. The `casa` mode is intended for
the CASA development environment and runs in the foreground.

## Calling the REST API

The translator exposes a REST API for graph translation. Once the service is
running, inspect the available endpoints and request schemas at
<http://localhost:8084/docs>. The command-line interface is usually simpler
for local pipelines; use `dlg --help` and `dlg tm --help` for the complete CLI
options.
