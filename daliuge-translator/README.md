# DALiuGE translator

The translator converts EAGLE logical graph templates (LGTs) into physical graph
templates (PGTs), and can map those templates to a physical graph (PG). It also
provides the `dlg tm` REST service and command-line graph translation commands.

The user-facing documentation is maintained in the main DALiuGE repository:
<https://daliuge.readthedocs.io/en/latest/>.

## Install for development

The translator depends on the `daliuge-common` package. From checkouts of the
DALiuGE repositories, install the common package first and then this package in
editable mode:

```bash
cd daliuge-common
python -m pip install -e .
cd ../daliuge-translator
python -m pip install -e .
```

Install test dependencies when running the translator test suite:

```bash
python -m pip install -e '.[test]'
```

## Command-line pipeline

The commands read JSON from standard input and write JSON to standard output
unless an input or output option is supplied. A typical translation pipeline is:

```bash
dlg fill -L logical.graph -o filled.graph
dlg unroll -L filled.graph -o template.graph
dlg partition -P template.graph -o partitioned.graph
dlg map -P partitioned.graph -N localhost -o physical.graph
```

Use `dlg <command> --help` for command-specific options. The commands can also
be chained without temporary files:

```bash
dlg fill -L logical.graph | dlg unroll | dlg partition | dlg map -N localhost > physical.graph
```

`dlg unroll-and-partition` combines the unroll and partition stages. The
`--app` and `--zerorun` options are documented by the command help.

## Run the REST service

Start the service directly with:

```bash
dlg tm -d /path/to/logical-graphs -t /tmp -p 8084
```

The service listens on port `8084` by default. Its OpenAPI documentation is
available at `http://localhost:8084/docs` while it is running.

For Docker-based development, see [docker/README.md](docker/README.md). The
Docker scripts require a running Docker daemon and accept an explicit mode:

```bash
./build_translator.sh dev
./run_translator.sh dev
./stop_translator.sh
```
