# E-Commerce Microservices Lab

A minimal 3-service e-commerce app used to practice Kubernetes concepts:
StatefulSets, Ingress, CronJobs, HPA, Secrets, ConfigMaps, NetworkPolicies, and troubleshooting.

## Services

- **user-service** (port 8001) — Postgres-backed user records
- **product-service** (port 8002) — Postgres-backed product catalog, cached in Redis
- **order-service** (port 8003) — Places orders; calls user-service and product-service over HTTP
- **frontend** (port 8080) — Static HTML/JS page that talks to the three APIs directly from the browser

## Run locally with Docker Compose

```bash
docker compose up --build
```

Wait ~10-15 seconds for Postgres to become healthy and services to start.

## Use the frontend

Open `http://localhost:8080` in your browser. It shows live health status for
all three services, lets you list/create products and users, and place an
order — all calling the APIs directly from your browser via JavaScript
`fetch()`. No build tooling, no framework — just static HTML/JS served by
nginx, useful once you get to Ingress since it becomes a fourth real workload
to route.

## Test the flow end-to-end (via curl, optional — the frontend covers this too)

Create a user:

```bash
curl -X POST http://localhost:8001/users \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "email": "alice@example.com"}'
```

Create a product:

```bash
curl -X POST http://localhost:8002/products \
  -H "Content-Type: application/json" \
  -d '{"name": "Wireless Mouse", "price": 25.99, "stock": 100}'
```

Place an order (referencing the IDs returned above — likely `1` and `1` on a fresh DB):

```bash
curl -X POST http://localhost:8003/orders \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "product_id": 1, "quantity": 2}'
```

Fetch the order back:

```bash
curl http://localhost:8003/orders/1
```

Check health endpoints:

```bash
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
```

## What to verify before moving to Kubernetes

- [ ] All three `/health` endpoints return `200`
- [ ] Creating a user and product works
- [ ] Placing an order succeeds when user_id/product_id are valid
- [ ] Placing an order with an invalid `user_id` or `product_id` returns a `400`, not a crash
- [ ] Fetching the same product twice is fast the second time (Redis cache hit — check product-service logs)
- [ ] Stopping `user-service` and then trying to place an order returns a clean `503`, not a hang

## Shut down

```bash
docker compose down -v
```

(`-v` also removes the Postgres volume, so you get a clean DB next time)
