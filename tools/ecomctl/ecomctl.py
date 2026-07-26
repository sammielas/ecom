#!/usr/bin/env python3
"""
ecomctl - a small self-service CLI for developers working on the
homelab e-commerce platform.

This exists because building this project surfaced a lot of repetitive,
manual operational toil: checking pod health across two separate
clusters by hand, re-running the same Prometheus queries to check SLO
health, and writing every incident report's boilerplate from scratch.
This tool automates all three - "treat operations as a software
problem" rather than a sequence of commands to remember.

Deliberately built with only the Python standard library plus
`requests` - no heavyweight dependencies, so any developer can run it
immediately with `pip install requests` and nothing else.

Usage:
    ecomctl status                    # pod health across both clusters
    ecomctl slo                       # current error ratio / p95 latency per service
    ecomctl incident new <slug>       # scaffold a new incident report from the template
"""

import argparse
import subprocess
import sys
import json
import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("This tool needs the 'requests' package: pip install requests")
    sys.exit(1)


CLUSTERS = {
    "staging": "k3d-devops-lab",
    "production": "k3d-devops-prod",
}

# Thresholds mirror the actual PrometheusRule definitions in
# k8s/monitoring/ecom-slo-rules.yaml - kept in sync manually for now;
# a natural next improvement is reading these directly from that file.
AVAILABILITY_SLO = 0.995      # 99.5% success rate target
LATENCY_SLO_MS = 300          # p95 latency target

INCIDENT_TEMPLATE = """## Incident Report - {title}

### Summary

<!-- One or two sentences: what broke, and what the user-visible impact was. -->

### Impact

<!-- Who/what was affected, for how long. Be specific - "checkout failed
for all users for 12 minutes" is more useful than "some errors occurred." -->

### Timeline

1. **Observed:** <!-- what you first saw -->
2. <!-- each subsequent diagnostic step, including dead ends - they're
        useful evidence of what you ruled out, not just the final answer -->

### Root cause

<!-- The actual underlying cause, not just the symptom. -->

### Resolution

<!-- What you did to fix it, with the actual commands if relevant. -->

### Prevention measures implemented

<!-- What you changed in the system so this can't happen the same way
again - not just "I fixed it," but "I changed the system." -->

### Detection if this recurs

<!-- The specific signal/command/alert that would catch this fastest
next time. -->
"""


def run(cmd: list[str]) -> str:
    """Run a shell command and return its stdout, raising on failure."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Command failed: {' '.join(cmd)}\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout


def cmd_status(args):
    """Health summary across every registered cluster, in one command."""
    for env_name, context in CLUSTERS.items():
        print(f"\n=== {env_name} ({context}) ===")
        try:
            output = run([
                "kubectl", "--context", context, "get", "pods",
                "-n", "ecom", "-o", "json",
            ])
        except SystemExit:
            print(f"  (could not reach this cluster - is it running?)")
            continue

        pods = json.loads(output)["items"]
        healthy, unhealthy = [], []
        for pod in pods:
            name = pod["metadata"]["name"]
            phase = pod["status"].get("phase", "Unknown")
            restarts = sum(
                c.get("restartCount", 0)
                for c in pod["status"].get("containerStatuses", [])
            )
            ready = all(
                c.get("ready", False)
                for c in pod["status"].get("containerStatuses", [])
            )
            if phase == "Running" and ready:
                healthy.append((name, restarts))
            elif phase not in ("Succeeded",):
                unhealthy.append((name, phase, restarts))

        print(f"  Healthy: {len(healthy)} pods")
        if unhealthy:
            print(f"  NEEDS ATTENTION:")
            for name, phase, restarts in unhealthy:
                print(f"    - {name}: {phase} (restarts: {restarts})")
        else:
            print(f"  Everything healthy.")


def cmd_slo(args):
    """Current SLI values per service, straight from the real recording rules."""
    prom_url = args.prometheus_url

    def query(expr: str):
        try:
            resp = requests.get(
                f"{prom_url}/api/v1/query",
                params={"query": expr},
                timeout=5,
            )
            resp.raise_for_status()
            return resp.json()["data"]["result"]
        except requests.RequestException as e:
            print(f"Could not reach Prometheus at {prom_url}: {e}")
            print("Is `kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090` running?")
            sys.exit(1)

    print("=== SLO Status ===\n")

    error_ratios = {r["metric"]["exported_job"]: float(r["value"][1])
                     for r in query("ecom:http_error_ratio:rate5m")}
    latencies = {r["metric"]["exported_job"]: float(r["value"][1])
                  for r in query("ecom:http_request_duration:p95_5m")}

    services = sorted(set(error_ratios) | set(latencies))
    if not services:
        print("No data yet - is there recent traffic to the app?")
        return

    for svc in services:
        err = error_ratios.get(svc, 0.0)
        lat = latencies.get(svc, 0.0)
        err_ok = err <= (1 - AVAILABILITY_SLO)
        lat_ok = lat <= LATENCY_SLO_MS
        budget_remaining_pct = max(0.0, (1 - err / (1 - AVAILABILITY_SLO))) * 100 if err > 0 else 100.0

        status = "OK" if (err_ok and lat_ok) else "AT RISK"
        print(f"{svc}: {status}")
        print(f"  Error ratio:      {err:.4%}  (budget remaining: {budget_remaining_pct:.1f}%)")
        print(f"  p95 latency:      {lat:.1f}ms  (target: <{LATENCY_SLO_MS}ms)")
        print()


def cmd_incident_new(args):
    """Scaffold a new incident report from the template this project's postmortems all follow."""
    today = datetime.date.today().isoformat()
    slug = args.slug.lower().replace(" ", "-")
    out_dir = Path("incident-reports")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"{today}-{slug}.md"

    if out_path.exists():
        print(f"Already exists: {out_path}")
        sys.exit(1)

    title = args.slug.replace("-", " ").title()
    out_path.write_text(INCIDENT_TEMPLATE.format(title=title))
    print(f"Created {out_path}")
    print(f"Fill in each section - the structure matches every other incident report in this project.")


def main():
    parser = argparse.ArgumentParser(
        prog="ecomctl",
        description="Self-service developer CLI for the homelab e-commerce platform.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_status = subparsers.add_parser("status", help="Pod health across both clusters")
    p_status.set_defaults(func=cmd_status)

    p_slo = subparsers.add_parser("slo", help="Current SLI values and error budget status")
    p_slo.add_argument(
        "--prometheus-url", default="http://localhost:9090",
        help="Prometheus API URL (default: http://localhost:9090, assumes a port-forward is active)",
    )
    p_slo.set_defaults(func=cmd_slo)

    p_incident = subparsers.add_parser("incident", help="Incident report tooling")
    incident_sub = p_incident.add_subparsers(dest="incident_command", required=True)
    p_incident_new = incident_sub.add_parser("new", help="Scaffold a new incident report")
    p_incident_new.add_argument("slug", help="Short name for the incident, e.g. 'postgres-connection-refused'")
    p_incident_new.set_defaults(func=cmd_incident_new)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
