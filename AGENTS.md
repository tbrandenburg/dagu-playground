# Working on Dagu Playground

## Purpose

Keep a small, understandable lab for distributed Dagu execution. Prefer an inspectable YAML workflow and a short acceptance check over a framework or abstraction layer.

## Non-negotiable design

- One server and a scalable `worker` service; default worker count: two.
- Official prebuilt Dagu image only, pinned by version and manifest digest.
- No Dockerfile, external database, shared worker volumes, Docker socket mount, or custom Dagu config files.
- Dashboard binds to loopback, default port 8100. Coordinator port stays internal.
- Authentication and peer TLS are disabled only for this local playground. Do not advertise this as production-ready.
- Treat workflow execution as trusted code. The upstream container's sudo tooling is not a hostile-code sandbox.
- Worker files are disposable. Never assume a later DAG run lands on the same worker.
- Do not interrupt unrelated containers or host processes. Do not use global Docker prune commands.

## Map

- `compose.yaml`: deployment and environment-only Dagu configuration.
- `dags/*.yaml`: self-contained examples; filenames define workflow names.
- `scripts/client.py`: REST, polling, subprocess helpers, and API types.
- `scripts/manage.py`: CLI argument validation and startup readiness.
- `scripts/demo.py`: positive scenarios and `.artifacts/demo.json`.
- `scripts/verify.py`: negative, scaling, and persisted-history checks.
- `scripts/recipe.py`: checksum-verified refresh and normal deployment of an upstream recipe; generated YAML stays ignored.
- `tests/`: standard-library unittest tests using actual loopback HTTP.
- `docs/`: architecture and reproducible verification notes.

## Before changing anything

1. Read `README.md`, `compose.yaml`, and the relevant script or workflow.
2. Check `git status`; preserve unrelated work.
3. Inspect the pinned binary's schema with `docker compose exec -T dagu dagu schema dag`.
4. Validate definitions with `make validate`. Do not copy syntax from another Dagu version blindly.

Current image-specific rules: omit root `name`, use `type: graph`, and give steps underscore-style IDs. A run executes on one worker even when its steps are parallel. Shell snippets must be portable `sh` unless an interpreter is explicitly declared.

## Implementation conventions

- Keep Python standard-library-only and compatible with Python 3.10+.
- Use explicit exported types; avoid `Any`, ignored type errors, empty exception handlers, and swallowed subprocess failures.
- Bound HTTP requests, polls, subprocesses, and CI jobs with timeouts.
- Use a unique run ID in filesystem paths; avoid shared mutable scratch names.
- Prefer Dagu `file.*` actions for file operations; use shell for actual CLI pipelines.
- Keep files focused and roughly under 200 lines.
- Keep formatting reproducible with the Makefile's pinned Ruff and Prettier versions.
- Update README behavior tables when changing a command or workflow.
- Keep reports, logs, caches, and credentials out of git. Never read tokens into tool output.

## Required verification

```sh
make check
make test-recipe
make test-scale
make test-lifecycle
git diff --check
```

`make lint` needs `uv` and Node/npm. The playground itself needs Docker Compose, Make, and Python only. CI uses Python 3.12 and real Docker.

Recipes are plain DAG files, not native Action packages. Keep upstream steps out of git: refresh the pinned source before `make recipe`, verify its checksum, validate the generated spec, then atomically publish it under `dags/`. Never silently run an old deployment after refresh failure. Review the upstream diff before updating the source revision and checksum; see `docs/recipes.md`. Avoid worker-local child DAG loading or nested Dagu CLI processes for recipe deployment.

Acceptance checks must assert observable behavior, not just exit zero. Check workflow statuses, worker IDs, actual logs, exact file contents, workdir selection, peer-filesystem absence, overlapping branch execution, and exact retry count. Keep the intentionally failed `expected-failure` run; it tests blocked dependencies, not a broken suite. Never mock Docker or Dagu in end-to-end checks.

After scaling, restore the original replica count. `make test-lifecycle` recreates containers and returns to two workers. Never reset volumes unless explicitly requested. Leave a usable two-worker demo running after manual verification unless asked to stop it.

## Publishing and evidence

- Never commit or push unless requested as part of the task.
- Use conventional, focused commit messages; do not bypass hooks.
- Pin GitHub Actions by commit SHA and use least-privilege workflow permissions.
- Capture real dashboard screenshots under `docs/images/`; do not alter execution data for a screenshot.
- Re-run the demo before refreshing evidence, and record run IDs in `docs/verification.md`.
- Report exact commands and observed results; distinguish local verification from remote CI.
- MIT covers this repository, not Dagu's upstream GPL-3.0 image.
