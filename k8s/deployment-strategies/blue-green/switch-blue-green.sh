#!/usr/bin/env bash
# Usage: ./switch-blue-green.sh blue    (or) ./switch-blue-green.sh green
#
# Flips the active Service's selector to the given slot, and updates the
# preview Service to point at the OTHER slot - so there's always exactly
# one active and one preview, and you can never accidentally point both
# at the same slot.
set -euo pipefail

TARGET="$1"
if [[ "$TARGET" != "blue" && "$TARGET" != "green" ]]; then
  echo "Usage: $0 <blue|green>"
  exit 1
fi

OTHER="green"
if [[ "$TARGET" == "green" ]]; then
  OTHER="blue"
fi

NAMESPACE="deploy-strategies-lab"

echo "Cutting active traffic over to: $TARGET"
kubectl patch service order-service -n "$NAMESPACE" \
  -p "{\"spec\":{\"selector\":{\"app\":\"order-service\",\"slot\":\"${TARGET}\"}}}"

echo "Pointing preview Service at: $OTHER"
kubectl patch service order-service-preview -n "$NAMESPACE" \
  -p "{\"spec\":{\"selector\":{\"app\":\"order-service\",\"slot\":\"${OTHER}\"}}}"

echo "Done. Active slot is now: $TARGET"
echo "Verify with:"
echo "  kubectl get service order-service -n $NAMESPACE -o jsonpath='{.spec.selector}'"
