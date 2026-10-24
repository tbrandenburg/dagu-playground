# Upstream recipes without clone-and-own

## What Dagu calls a recipe

The official [recipe catalog](https://dagu.sh/recipes) is backed by [`dagucloud/recipes`](https://github.com/dagucloud/recipes). A recipe is a normal workflow YAML file with accompanying metadata and a README—not an installed plugin.

The upstream README explicitly says recipes can be inspected, copied, and adapted. The [HTTP-health recipe page](https://dagu.sh/recipes/http-health-slack) offers **Download YAML** and **Copy YAML**, asks users to replace example values and configure secrets, and warns that syntax validation is not a trust guarantee.

For deployment, put a reviewed definition in the server's DAG directory, then validate and run it normally. That fits this repository's existing read-only `./dags` mount: the host can update files while the server reads them. Workers receive definitions from the coordinator and need no new mounts.

## Recipe files versus native Actions

| Mechanism                                                          | Intended use                                                                                  | Fit here                                                                                                |
| ------------------------------------------------------------------ | --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Download/copy a recipe into the DAG directory                      | Inspect and tailor one ordinary workflow                                                      | Selected; refresh before use, with no upstream workflow committed here                                  |
| [Git Sync](https://docs.dagu.sh/server-admin/git-sync)             | Keep a reviewed workflow repository or selected subdirectory synchronized into server storage | Useful for larger deployments; unnecessary configuration and writable server storage for this small lab |
| [Remote Action packages](https://docs.dagu.sh/dagu-actions/custom) | Call a reusable package using `action: owner/repo@ref`                                        | Requires a `dagu-action.yaml` manifest; the recipes repository does not supply one                      |

The inspected [catalog revision](https://github.com/dagucloud/recipes/tree/3ef31bdcae4e69c2129d1a201574bb1a746d2501) has 12 recipes and zero Action manifests. Its examples cover database backups, rclone copies, SSH operations, deployment, and monitoring; their listed prerequisites include credentials, external services, or additional tooling. The catalog reports validation with Dagu 2.13.0, so this playground separately validates and executes the selected example with its pinned 2.22.2 image.

Git Sync is not a dependency resolver. It copies tracked content into the configured storage paths; use its `path` scope and read-only publishing mode when deploying a curated repository. Do not point it at the entire recipe catalog and enable schedules without reviewing each workflow and prerequisite.

## The selected example

[`http-health-slack`](https://dagu.sh/recipes/http-health-slack) is a useful small example: a built-in HTTP GET, a ten-second request timeout, and three retries separated by ten seconds. The original also runs every five minutes and posts to Slack on failure.

For a credential-free lab, the preparer substitutes a small on-demand header and keeps the upstream **steps block unchanged**. This removes the schedule, Slack secret, and failure webhook; it selects the playground worker pool and defaults the target to `http://dagu:8080/api/v1/health`. No monitoring logic is reimplemented locally.

```sh
make recipe
```

This command:

1. Downloads the [reviewed upstream YAML](https://github.com/dagucloud/recipes/blob/3ef31bdcae4e69c2129d1a201574bb1a746d2501/recipes/http-health-slack/workflow.yaml) over HTTPS, with a bounded request and size limit.
2. Verifies SHA-256 `940e8710e61ee487a51baf278313b2432c16ab08ad564a60c19d71cb4927ff3e` before adapting anything.
3. Builds the health-only definition in memory and asks the actual Dagu server to validate it.
4. Atomically replaces the ignored `dags/recipe-health-check.yaml` file. It never replaces the bind-mounted directory.
5. Starts that ordinary DAG through the REST API and verifies the worker ID, successful upstream step, and healthy JSON response.

The workflow appears as **recipe-health-check** in the dashboard. There is no wrapper DAG, nested CLI process, custom image, YAML-parsing package, or additional service. The recipe-specific header adapter is deliberately not a general YAML parser; its known input is protected by the pinned checksum.

### Fresh downloads, reviewed updates

Every `make recipe` invocation downloads and verifies the source again. Network errors, checksum mismatches, or invalid definitions abort before starting a run. A previous valid deployment may remain on disk, but the command does not silently execute it after refresh failure.

**Fresh download does not mean tracking `main`.** The source revision and checksum are explicit constants in [`scripts/recipe.py`](/scripts/recipe.py). To update, review the upstream diff, update those constants, check the adapter still preserves the intended steps, and run `make test-recipe`. Silently accepting arbitrary changed workflow code would be less safe than reviewing an upgrade.

Starting the workflow directly in the dashboard runs the last prepared definition; it does **not** refresh upstream. Use `make recipe` when you want the refresh-before-use guarantee. `make demo` remains a separate, self-contained core playground demonstration.

The generated file persists on the host across `make down` and `make reset`, like other files under `dags/`. It is ignored by git and regenerated from upstream, not maintained as a local fork. Provenance and execution records are written to ignored `.artifacts/recipe.json`.

## Verification

```sh
make test-unit
make test-recipe
```

The HTTP tooling tests use a real loopback server to check successful download, wrong checksum, HTTP 404, and the size bound. Adapter tests check preserved steps and rejected ambiguous input. Docker acceptance refreshes and executes twice, replaces a stale local definition, verifies failure after three upstream retries against an unreachable endpoint, and confirms invalid YAML cannot replace a valid deployment.

The failing endpoint run is intentionally red in the dashboard; `make recipe` itself runs only the positive example. GitHub Actions runs the acceptance checks against real Dagu workers.

## Licensing and trust

The recipe repository is [Apache-2.0 licensed](https://github.com/dagucloud/recipes/blob/3ef31bdcae4e69c2129d1a201574bb1a746d2501/LICENSE), separately from Dagu's GPL-3.0 engine and this repository's MIT tooling. The generated file records upstream attribution and marks the health-only adaptation. No upstream recipe body is committed to this repository. If you redistribute generated recipes, retain the applicable Apache license and notices.

A checksum establishes which reviewed bytes were downloaded; it does not make code trustworthy. Review upstream changes as executable code, keep credentials out of recipes, and do not expose this unauthenticated playground publicly.
