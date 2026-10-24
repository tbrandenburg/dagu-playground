"""Real failure, scaling, and persisted-history acceptance checks."""

import argparse
import json

from scripts.client import ROOT, ApiError, Client, compose, replicas, require


def failures(client: Client) -> None:
    run = client.finished(
        "expected-failure", client.start("expected-failure"), "failed"
    )
    nodes = {node["step"]["id"]: node for node in run["nodes"]}
    require(
        nodes["missing_file"]["statusLabel"] == "failed", "Missing file did not fail"
    )
    require(
        nodes["must_not_run"]["statusLabel"] != "succeeded", "Dependent step succeeded"
    )
    require(not nodes["must_not_run"].get("startedAt"), "Dependent step executed")
    result = client.request(
        "dags/validate", {"spec": "steps:\n  - id: 123invalid\n    run: echo no\n"}
    )
    require(result["valid"] is False, "Invalid workflow accepted")
    require(result["errors"], "Invalid workflow must provide errors")
    try:
        client.request("dags/nonexistent-playground-workflow")
    except ApiError as error:
        require(error.status == 404, "Missing DAG must return 404")
        print(
            "Verified: missing file fails, dependent blocked, invalid DAG rejected, HTTP 404 preserved"
        )
        return
    raise RuntimeError("Missing DAG was accepted")


def scaling(client: Client) -> None:
    original = len(replicas())
    try:
        for count in (1, 3):
            compose(
                "up",
                "-d",
                "--scale",
                f"worker={count}",
                "--wait",
                "--wait-timeout",
                "120",
            )
            workers = client.ready(count)
            run = client.finished("hello-worker", client.start("hello-worker", hold=1))
            require(
                run["workerId"] in {worker["id"] for worker in workers},
                "Unknown worker",
            )
            require(run["statusLabel"] == "succeeded", "Scaled worker did not execute")
            print(
                f"Verified: {count} healthy worker(s), distributed execution succeeds"
            )
    finally:
        compose(
            "up",
            "-d",
            "--scale",
            f"worker={original}",
            "--wait",
            "--wait-timeout",
            "120",
        )
        client.ready(original)


def persistence(client: Client) -> None:
    report = json.loads((ROOT / ".artifacts/demo.json").read_text())
    compose("down", "--timeout", "20")
    compose("up", "-d", "--scale", "worker=2", "--wait", "--wait-timeout", "120")
    client.ready(2)
    for previous in report["runs"]:
        run = client.run(previous["name"], previous["dagRunId"])
        require(run["statusLabel"] == "succeeded", "History lost during down/up")
        require(run["workerId"] == previous["workerId"], "Worker provenance lost")
        if run["name"] == "hello-worker":
            require(
                client.log(run, "identify_worker").strip()
                == run["workerId"].split("@")[0],
                "Worker logs lost after worker container deletion",
            )
    run = report["runs"][-1]
    require("server=" in client.log(run, "identify_server"), "Persisted logs missing")
    print(
        f"Verified: {len(report['runs'])} run records, worker logs, and server log survive down/up"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("check", choices=["failures", "scaling", "persistence"])
    arguments = parser.parse_args()
    {"failures": failures, "scaling": scaling, "persistence": persistence}[
        arguments.check
    ](Client())
