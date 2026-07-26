# ecomctl

A small self-service CLI for developers working on this platform.

## Why this exists

Building this project surfaced a lot of repetitive, manual operational
toil - checking pod health across two separate clusters by hand,
re-running the same Prometheus queries to check SLO health, and writing
every incident report's boilerplate from scratch each time. This tool
automates all three, treating operations as a software problem rather
than a sequence of commands to remember and re-type.

## Install

```bash
pip install requests --break-system-packages
chmod +x tools/ecomctl/ecomctl.py
```

Optionally add it to your PATH, or just run it directly:

```bash
python3 tools/ecomctl/ecomctl.py <command>
```

## Commands

### `ecomctl status`

Pod health across **both** clusters (staging and production) in one
command, instead of manually switching `kubectl` contexts back and
forth. Flags anything not `Running`/`Ready` as needing attention.

```bash
python3 tools/ecomctl/ecomctl.py status
```

### `ecomctl slo`

Current error ratio and p95 latency per service, computed from the same
Prometheus recording rules the real alerting rules use
(`k8s/monitoring/ecom-slo-rules.yaml`) - plus a rough estimate of
remaining error budget. Requires a Prometheus port-forward to be active:

```bash
kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090 &
python3 tools/ecomctl/ecomctl.py slo
```

### `ecomctl incident new <slug>`

Scaffolds a new incident report markdown file, pre-filled with the same
Summary/Impact/Timeline/Root Cause/Resolution/Prevention/Detection
structure every incident report in this project follows - so a postmortem
starts from a checklist, not a blank page.

```bash
python3 tools/ecomctl/ecomctl.py incident new "postgres-connection-refused"
# creates incident-reports/2026-07-26-postgres-connection-refused.md
```

## Known limitations / next steps

- `slo` assumes a manual port-forward is already running rather than
  establishing one itself - a natural next improvement.
- The SLO thresholds (`AVAILABILITY_SLO`, `LATENCY_SLO_MS`) are
  duplicated from `k8s/monitoring/ecom-slo-rules.yaml` rather than read
  from it directly - worth fixing so there's a single source of truth.
- `status` only checks `ecom` namespace pod readiness - could be
  extended to also surface NetworkPolicy state, HPA status, or recent
  CronJob failures in the same summary.
