# Architecture and design decisions

## Plan: organize by what a newcomer wants to change

The repository is split into deployment (`compose.yaml`), user commands (`Makefile`), examples (`dags/`), acceptance tooling (`scripts/` and `tests/`), and explanation (`docs/`). There is no installable application or custom worker build. Each workflow demonstrates one concept; the demo brings those concepts together.

The optional official recipe follows the same deployment model: host-side tooling downloads a checksum-pinned upstream definition, validates a small health-only adaptation, and atomically writes an ignored DAG file into the existing mount. Dagu dispatches it as an ordinary workflow. No recipe body is vendored and no nested engine process is needed; see [recipes](/docs/recipes.md).

## Control plane and execution plane

The server runs `dagu start-all`: dashboard, scheduler, and coordinator. It owns the workflow definitions, persistent run history, logs, and Wiki. Its only public listener is mapped to `127.0.0.1:8100` by default.

Workers run `dagu worker`, discover the server through the Compose DNS name `dagu`, register over internal gRPC on port 50055, and poll for runs. Each advertises `pool=playground` and accepts two concurrent DAG runs. The coordinator transfers workflow definitions and receives status and logs; a worker does not need access to the server's filesystem.

There is no fairness promise for short runs. Filling the combined run capacity with held jobs makes distribution visible without relying on a few fast sequential submissions. The demo requires the observed worker IDs to equal the registered healthy-worker IDs.

## Filesystem boundaries

| Location                         | Owner                                | Survives `make down`? |
| -------------------------------- | ------------------------------------ | --------------------- |
| Repository `dags/`               | Host; read-only bind mount on server | Yes                   |
| `/var/lib/dagu` named volume     | Server only                          | Yes                   |
| `/tmp/dagu-playground/<run-id>/` | Worker container that ran the DAG    | No                    |
| `.artifacts/demo.json`           | Host-side demo tooling               | Yes; ignored by git   |

Within a DAG run, step-level `working_dir` selects directories on that same worker. `file-pipeline` creates `input/` and `output/`, transforms content in the input workdir, then verifies the moved result from the output workdir. `parallel-workdirs` uses `alpha/` and `beta/` for concurrent branches and joins their outputs locally.

Across runs, files are not implicitly portable. This is intentional: shared worker mounts would hide the distinction the playground is meant to teach. Production workflows needing a handoff should publish artifacts or use explicit external storage.

## Reproducibility over moving tags

The Compose anchor keeps the server and worker image identical. Both use upstream `2.22.2` plus its published multi-platform manifest digest. Updating the image means updating that one line, validating every definition with the new binary, and rerunning Docker acceptance checks.

This pinned release rejects root-level workflow `name` and hyphens in step IDs. Examples therefore use filenames as workflow names and underscore IDs. Online examples for older versions may differ.

## Small but deliberate safety measures

- Startup checks port availability and rejects invalid worker counts before changing the stack.
- Server health gates worker startup; API registration gates playground readiness.
- Read-only DAG mount prevents dashboard edits from modifying tracked examples.
- `DAGU_WIKI_DIR` points outside the read-only DAG mount because this release initializes Wiki storage on startup.
- The image contains Tini, so Compose does not add a redundant init process.
- No Docker socket, privileged container flag, or worker host bind mount is required.
- The official image includes passwordless sudo; trusted demo inputs are required.
- `make reset` requires an explicit confirmation variable; routine stop retains history.
- Workflow steps and tooling use error propagation, exact assertions, and bounded waits.

## Intentionally out of scope

TLS, multi-user authentication, remote exposure, autoscaling, high availability, coding-agent credentials, hostile-code isolation, and shared durable worker workspaces. These add operational concerns that would obscure a small distributed-execution lab.

For production deployment, start with upstream's [transport security](https://docs.dagu.sh/server-admin/distributed/transport-security) and [authentication](https://docs.dagu.sh/server-admin/authentication/) guidance rather than exposing this Compose file unchanged.
