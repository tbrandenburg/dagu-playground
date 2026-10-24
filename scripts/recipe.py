"""Refresh a reviewed upstream recipe, deploy it as a normal DAG, and run it."""

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

from scripts.client import ROOT, Client, Run, replicas, require

NAME = "recipe-health-check"
REVISION = "3ef31bdcae4e69c2129d1a201574bb1a746d2501"
SOURCE = f"https://raw.githubusercontent.com/dagucloud/recipes/{REVISION}/recipes/http-health-slack/workflow.yaml"
SHA256 = "940e8710e61ee487a51baf278313b2432c16ab08ad564a60c19d71cb4927ff3e"
DESTINATION = ROOT / "dags" / f"{NAME}.yaml"


def download(url: str, checksum: str) -> str:
    with urlopen(url, timeout=20) as response:
        content = response.read(65537)
    require(len(content) <= 65536, "Recipe exceeds the 64 KiB download limit")
    require(
        hashlib.sha256(content).hexdigest() == checksum,
        "Upstream recipe checksum mismatch",
    )
    return content.decode("utf-8")


def adapt(source: str) -> str:
    # This is a recipe-specific, checksum-guarded adapter, not a YAML parser.
    marker = "\nsteps:\n"
    require(source.count(marker) == 1, "Expected one upstream steps block")
    header = (
        f"# Source: {SOURCE}\n# License: Apache-2.0; generated health-only adaptation.\n"
        "description: Upstream HTTP health check, refreshed by make recipe.\n"
        "type: graph\nworker_selector:\n  pool: playground\n"
        "params:\n  - name: url\n    default: http://dagu:8080/api/v1/health\n"
    )
    return header + "steps:\n" + source.split(marker)[1]


def deploy(client: Client, spec: str, destination: Path = DESTINATION) -> None:
    result = client.request("dags/validate", {"spec": spec})
    require(result["valid"] is True, f"Recipe validation failed: {result['errors']}")
    # Replace the file, never the bind-mounted directory, after successful validation.
    with tempfile.NamedTemporaryFile(
        mode="w", dir=destination.parent, suffix=".tmp", delete=False
    ) as staging:
        staging.write(spec)
        path = Path(staging.name)
    try:
        path.chmod(0o644)
        os.replace(path, destination)
    finally:
        path.unlink(missing_ok=True)


def refresh(client: Client) -> str:
    source = download(SOURCE, SHA256)
    spec = adapt(source)
    deploy(client, spec)
    print(f"Downloaded and deployed {SOURCE}\nsha256={SHA256}")
    return spec


def execute(client: Client, expected: str = "succeeded", url: str | None = None) -> Run:
    body: dict[str, object] = {"params": json.dumps({"url": url})} if url else {}
    identifier = str(client.request(f"dags/{NAME}/start", body)["dagRunId"])
    run = client.finished(NAME, identifier, expected)
    require(
        run["workerId"] in {worker["id"] for worker in client.workers()},
        "Recipe did not run on a worker",
    )
    node = next(node for node in run["nodes"] if node["step"]["id"] == "health_check")
    require(node["statusLabel"] == expected, "Unexpected upstream step result")
    if expected == "succeeded":
        require(
            json.loads(client.log(run, "health_check"))["status"] == "healthy",
            "Unhealthy response",
        )
    if expected == "failed":
        require(node["retryCount"] == 3, "Upstream retry policy was not preserved")
    print(f"Verified recipe {expected}: {identifier} on {run['workerId']}")
    return run


def verify_rejection(client: Client, previous: str) -> None:
    try:
        deploy(client, "steps:\n  - id: 123invalid\n    run: echo invalid\n")
    except RuntimeError as error:
        require("Recipe validation failed" in str(error), "Unexpected validation error")
        require(
            DESTINATION.read_text() == previous,
            "Invalid recipe replaced the deployment",
        )
        print("Verified invalid recipe rejected before replacing the deployment")
        return
    raise RuntimeError("Invalid recipe was deployed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()
    client = Client()
    client.ready(len(replicas()))
    first = refresh(client)
    runs = [execute(client)]
    if args.test:
        # Prove refresh replaces a stale local deployment instead of trusting it.
        DESTINATION.write_text("# stale deployment\n")
        require(refresh(client) == first, "Refresh changed the reviewed recipe")
        require(DESTINATION.read_text() == first, "Stale deployment was reused")
        runs.append(execute(client))
        runs.append(execute(client, "failed", "http://127.0.0.1:1"))
        verify_rejection(client, first)
    directory = ROOT / ".artifacts"
    directory.mkdir(exist_ok=True)
    (directory / "recipe.json").write_text(
        json.dumps(
            {
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "source": SOURCE,
                "sha256": SHA256,
                "runs": runs,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
