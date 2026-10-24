"""Exercise real distributed runs and independently inspect worker filesystems."""

import json
from datetime import datetime, timezone

from scripts.client import ROOT, Client, Run, compose, container, replicas, require


def owner(run: Run) -> str:
    return run["workerId"].split("@")[0]


def verify_files(run: Run, workers: list[str]) -> None:
    path = f"/tmp/dagu-playground/{run['dagRunId']}"
    for worker in workers:
        hostname = container(worker, "hostname")
        if hostname == owner(run):
            content = container(worker, "cat", f"{path}/output/final.txt")
            require(content == "HELLO FROM AN ISOLATED WORKER", "Wrong file content")
            container(worker, "test", "!", "-e", f"{path}/output/copy.txt")
            continue
        container(worker, "test", "!", "-e", path)
    compose("exec", "-T", "dagu", "test", "!", "-e", path)


def main() -> None:
    client = Client()
    workers = replicas()
    require(len(workers) >= 2, "Demo needs at least two workers; run make up")
    registered = client.ready(len(workers))
    capacity = sum(worker["totalPollers"] for worker in registered)
    print(f"Registered {len(registered)} workers; {capacity} concurrent run slots")

    # Fill every slot so long-poll scheduling must use each registered worker.
    identities = [client.start("hello-worker", hold=8) for _ in range(capacity)]
    hello = [client.finished("hello-worker", identifier) for identifier in identities]
    jobs = [
        (name, client.start(name))
        for name in (
            "file-pipeline",
            "parallel-workdirs",
            "retry-recovery",
            "local-server",
        )
    ]
    observed = {run["workerId"] for run in hello}
    require(
        observed == {worker["id"] for worker in registered}, "Distribution incomplete"
    )
    for run in hello:
        require(
            client.log(run, "identify_worker").strip() == owner(run),
            "Identity mismatch",
        )

    results = [client.finished(name, identifier) for name, identifier in jobs]
    pipeline, parallel, retry, local = results
    verify_files(pipeline, workers)
    require(
        "HELLO FROM AN ISOLATED WORKER" in client.log(pipeline, "verify"), "Missing log"
    )
    require("/input" in client.log(pipeline, "transform"), "Input workdir not used")
    require("/output" in client.log(pipeline, "verify"), "Output workdir not used")

    branches = {node["step"]["id"]: node for node in parallel["nodes"]}
    require(
        max(branches[key]["startedAt"] for key in ("alpha", "beta"))
        < min(branches[key]["finishedAt"] for key in ("alpha", "beta")),
        "Branches did not overlap",
    )
    require(
        client.log(parallel, "join").strip() == "alpha\nbeta", "Incorrect join result"
    )
    require("/alpha" in client.log(parallel, "alpha"), "Alpha workdir not used")
    require("/beta" in client.log(parallel, "beta"), "Beta workdir not used")
    retried = next(
        node for node in retry["nodes"] if node["step"]["id"] == "flaky_operation"
    )
    require(retried["retryCount"] == 1, "Expected exactly one retry")
    require(
        "Recovered on retry" in client.log(retry, "flaky_operation"), "Recovery missing"
    )
    require(local["workerId"] == "local", "Local override ran on a worker")
    server = compose("exec", "-T", "dagu", "hostname")
    require(
        f"server={server}" in client.log(local, "identify_server"),
        "Server identity mismatch",
    )

    runs = hello + results
    for run in runs:
        print(
            f"  {run['statusLabel']:10} {run['name']:20} {run['workerId']} {run['dagRunId']}"
        )
    report = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "workers": registered,
        "runs": runs,
        "checks": [
            "distribution",
            "filesystem-isolation",
            "workdirs",
            "parallelism",
            "retry",
            "local",
        ],
    }
    directory = ROOT / ".artifacts"
    directory.mkdir(exist_ok=True)
    (directory / "demo.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Demo verified. Dashboard: {client.base}; report: .artifacts/demo.json")


if __name__ == "__main__":
    main()
