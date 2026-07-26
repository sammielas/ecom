#!/usr/bin/env bash
# Usage: ./set-canary-weight.sh <canary-weight-0-to-100>
#
# Example progressive rollout:
#   ./set-canary-weight.sh 10   # 90/10 - initial canary, small blast radius
#   ./set-canary-weight.sh 50   # 50/50 - canary looks healthy, expand it
#   ./set-canary-weight.sh 100  # 100/0 - canary fully promoted, old version gets no traffic
#
# Watch error rates/latency (e.g. via `ecomctl slo` or the Grafana
# dashboard) between each step before increasing further - that
# observation step is the entire point of a canary rollout versus just
# deploying everything at once.
set -euo pipefail

CANARY_WEIGHT="$1"
STABLE_WEIGHT=$((100 - CANARY_WEIGHT))
NAMESPACE="deploy-strategies-lab"

if ! [[ "$CANARY_WEIGHT" =~ ^[0-9]+$ ]] || [ "$CANARY_WEIGHT" -lt 0 ] || [ "$CANARY_WEIGHT" -gt 100 ]; then
  echo "Usage: $0 <canary-weight-0-to-100>"
  exit 1
fi

echo "Setting weights - stable: ${STABLE_WEIGHT}%, canary: ${CANARY_WEIGHT}%"

kubectl patch traefikservice product-service-weighted -n "$NAMESPACE" --type merge -p "
spec:
  weighted:
    services:
      - name: product-service-stable-svc
        port: 8000
        weight: ${STABLE_WEIGHT}
      - name: product-service-canary-svc
        port: 8000
        weight: ${CANARY_WEIGHT}
"

echo "Done. Verify with:"
echo "  kubectl get traefikservice product-service-weighted -n $NAMESPACE -o yaml"
