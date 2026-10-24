# Dagu Playground

**One server. Two workers. No image builds.**

![Real Dagu executions showing successful workflows on two different workers and on the local server](/docs/images/executions.png)

[![CI](https://github.com/tbrandenburg/dagu-playground/actions/workflows/ci.yaml/badge.svg)](https://github.com/tbrandenburg/dagu-playground/actions/workflows/ci.yaml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](/LICENSE)
[![Dagu 2.22.2](https://img.shields.io/badge/Dagu-2.22.2-15803d)](https://github.com/dagucloud/dagu/releases/tag/v2.22.2)

A small, runnable lab for understanding distributed [Dagu](https://dagu.sh) workflows. Watch jobs land on different workers, manipulate files in isolated working directories, recover from a transient error, and compare worker execution with server-local execution.

No Dockerfile, external database, shared worker volume, Docker socket mount, or Dagu configuration file. The server and workers use the **same official, version-and-digest-pinned image**.

## Run it

You need Docker Engine with Compose v2 or newer, Make, and Python 3.10+. Linux and Docker Desktop are supported by the layout; automated acceptance runs on Linux.

```sh
git clone https://github.com/tbrandenburg/dagu-playground.git
cd dagu-playground
make up
make demo
```

Open **[localhost:8100](http://localhost:8100)**. No signup or credentials are required in this loopback-only lab.

`make demo` fills the four available worker slots, waits for eight successful runs, verifies their results, and writes evidence to `.artifacts/demo.json`. Run it again to create fresh, independent workspaces.

> **Local lab, not a production template.** Dashboard authentication is disabled and internal coordinator traffic is unencrypted. Keep the published address on `127.0.0.1`; don't expose this stack through a proxy or tunnel. Workflows execute commands inside the containers. The official image includes passwordless sudo, so container execution is not a security sandbox for hostile workflows.

## What you can learn

| Workflow                                            | Experiment                                      | What is checked                                                                                                   |
| --------------------------------------------------- | ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| [`hello-worker`](/dags/hello-worker.yaml)           | Fill available run slots and print the hostname | Every registered worker executes a run; hostname matches recorded worker ID                                       |
| [`file-pipeline`](/dags/file-pipeline.yaml)         | Write → transform → copy → move → verify        | Exact content, different input/output workdirs, source removed after move, file absent on peer workers and server |
| [`parallel-workdirs`](/dags/parallel-workdirs.yaml) | Two branches, two directories, one join         | Both branches overlap and produce `alpha` / `beta` without clobbering each other                                  |
| [`retry-recovery`](/dags/retry-recovery.yaml)       | Fail once, then recover                         | Exactly one retry and a successful recovery log                                                                   |
| [`local-server`](/dags/local-server.yaml)           | Use `worker_selector: local`                    | Server hostname, local worker ID, and server-only DAG mount                                                       |
| [`expected-failure`](/dags/expected-failure.yaml)   | Read a nonexistent file                         | Failed run and an unstarted dependent step; exercised by `make test`, not `make demo`                             |

**A DAG run stays on one worker.** Parallel steps within that run share its filesystem. Different runs can land on different workers; a later run must not assume a previous worker's files exist.

### Try an official recipe without maintaining a copy

```sh
make recipe
```

This downloads a reviewed, checksum-pinned version of Dagu's [HTTP-health recipe](https://dagu.sh/recipes/http-health-slack), prepares an on-demand health-only definition, and deploys it as a normal **recipe-health-check** workflow. Its upstream HTTP check and retry policy stay unchanged; Slack credentials and the schedule are omitted. The generated YAML is ignored by git, not vendored.

Each command invocation refreshes before running; a download, checksum, or validation failure stops execution. Dashboard starts use the last prepared definition. See [recipe deployment, update policy, and research findings](/docs/recipes.md).

## The shape of the lab

```text
Browser :8100 (loopback only)
           │
           ▼
   dagu: dashboard + scheduler + coordinator
     │    server history volume + read-only ./dags
     │
     └── internal gRPC :50055 ──┬── worker 1 · pool=playground · 2 slots
                               └── worker 2 · pool=playground · 2 slots
                                   independent, disposable filesystems
```

Workers connect outbound to `dagu:50055` and register automatically. Definitions and status/log traffic travel through the coordinator; workers do not mount this repository or the server volume. Only the dashboard port is published.

## Everyday commands

| Command                         | Effect                                                                 |
| ------------------------------- | ---------------------------------------------------------------------- |
| `make up` / `make spawn-up`     | Start one server and two workers; wait for registration                |
| `make demo`                     | Start the default topology and run the positive acceptance demo        |
| `make recipe`                   | Refresh, validate, deploy, and run the official HTTP-health recipe     |
| `make test-recipe`              | Check refresh, stale replacement, invalid deployment, and HTTP retries |
| `make down` / `make spawn-down` | Remove containers and network; retain server history                   |
| `make scale WORKERS=3`          | Change the running worker count, from 1 to 5                           |
| `make status`                   | Show containers and check registered workers                           |
| `make logs`                     | Follow server and worker logs                                          |
| `make validate`                 | Validate available definitions with the pinned Dagu binary             |
| `make test`                     | Tooling tests, demo, and intentional failure checks                    |
| `make test-scale`               | Execute jobs with 1 and 3 workers; restore the initial count           |
| `make test-lifecycle`           | Recreate containers; verify retained run records and logs              |
| `make lint`                     | Ruff and Prettier checks; requires `uv` and Node/npm                   |
| `make check`                    | Formatting, lint, and `make test`                                      |
| `make reset CONFIRM=reset`      | **Delete server history** and remove this stack                        |

Port 8100 is the default, not a reserved port. Startup rejects an occupied port rather than terminating another service:

```sh
make up PORT=8101
make demo PORT=8101
make down PORT=8101
```

Pass the same `PORT` to later commands, or place `PORT=8101` in your shell environment. Scaling down an active worker can interrupt its runs; wait for them to finish first. `make demo` restores the default two-worker topology; use `make demo WORKERS=3` to demo three workers instead.

### Explore in the dashboard

1. Open **System Status** to inspect workers and their `pool=playground` labels.
2. Open **Workflows**, choose a workflow, and start it.
3. Open **Executions**. The **Worker** column shows which worker ran each job.
4. Open a run and inspect its steps and stdout/stderr logs.

The image above is an unmodified browser capture of real completed runs, not a mockup. See [the evidence notes](/docs/verification.md) for reproduction and captured run IDs.

## Files, persistence, and cleanup

- **Server history and logs** live in the Compose-managed `dagu-data` volume. `make down` retains them.
- **Workflow definitions** are your local `dags/*.yaml`, mounted read-only into the server. Edit them in your editor, not the dashboard.
- **Worker files** live under `/tmp/dagu-playground/<run-id>/` inside the owning container. Each run gets its own path. `make down`, worker replacement, or scale-down removes those files.
- **No implicit transfer** exists between worker filesystems. For real handoffs, use Dagu artifacts or external object storage—not a shared playground mount.
- **Demo evidence** lives in ignored `.artifacts/`. It is a report, not Dagu's state store.

The server's Wiki path is moved into its data volume through an environment variable so Dagu can initialize while the DAG mount remains read-only.

## Repository map

```text
compose.yaml              Official image, server, scalable workers, one server volume
Makefile                  Human-facing command surface
dags/                     Six self-contained workflow examples
scripts/
  client.py               Bounded REST and Docker helpers
  manage.py               Validated startup, scaling, readiness
  demo.py                 Positive acceptance scenarios and evidence report
  recipe.py               Refresh and deploy one upstream-referenced recipe
  verify.py               Failure, scaling, and lifecycle scenarios
tests/                    Real loopback HTTP tests for the tooling
docs/
  architecture.md         Design decisions and trade-offs
  recipes.md              Official recipe deployment and reviewed updates
  verification.md         Reproduction and screenshot provenance
  images/                 Real dashboard screenshots
.github/                  Docker acceptance CI and dependency updates
AGENTS.md                 Contributor and coding-agent guardrails
LICENSE                   MIT license for this repository
```

## Quality gates

```sh
make check
make test-recipe
make test-scale
make test-lifecycle
```

GitHub Actions runs these checks against real Docker containers, validates the workflows with the shipped binary, and uploads run reports and Compose logs. End-to-end tests do not mock Dagu or Docker. Tooling tests use a real local HTTP server and cover error status preservation, malformed response shape, connection failures, timeouts, worker health filtering, and argument boundaries.

There is deliberately no application framework or Python dependency lockfile: the runtime helpers use the standard library. Development-only Ruff and Prettier versions are pinned in the Makefile. Image upgrades arrive through Dependabot; validate schema compatibility before merging them.

## Troubleshooting

**Port occupied?** Use `make up PORT=8101`. The repo never stops a process it did not start.

**Workers missing?** Run `make logs` and `make status`. Verify Docker is running and the coordinator is reachable on the internal Compose network. Worker registration, not container existence, determines readiness.

**Red run after `make test`?** The `expected-failure` workflow intentionally fails. Its dependent step must not execute. A red retry attempt inside `retry-recovery` is also intentional; that overall run must succeed.

**Files disappeared after stopping?** That is expected for disposable worker containers. Run `make demo` again. Historical run records and returned logs remain on the server volume.

**Low disk warning?** Dagu reports the underlying Docker data filesystem's usage. Repeated demos accumulate logs and live-worker workspaces. Review your own Docker storage before removing anything; `make reset CONFIRM=reset` deletes only this Compose project's stored server state.

## Further reading

- [Dagu workers](https://docs.dagu.sh/server-admin/distributed/workers/)
- [Shared-nothing deployment](https://docs.dagu.sh/server-admin/distributed/workers/shared-nothing)
- [Docker Compose deployment](https://docs.dagu.sh/server-admin/deployment/docker-compose)
- [Workflow reference](https://docs.dagu.sh/writing-workflows/yaml-specification)

## License

This repository's examples, tooling, and documentation are [MIT licensed](/LICENSE). Downloaded upstream recipes retain their [Apache-2.0 license](https://github.com/dagucloud/recipes/blob/main/LICENSE). Dagu itself is a separate upstream project licensed under [GPL-3.0](https://github.com/dagucloud/dagu/blob/v2.22.2/LICENSE.md); the MIT license here does not relicense the Dagu image or upstream software. This is an independent playground, not an official Dagu project.
