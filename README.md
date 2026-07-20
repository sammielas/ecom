# Homelab E-Commerce — Kubernetes & DevSecOps Practice Lab

A small e-commerce app built specifically to practice real DevOps/Kubernetes
skills: containerization, StatefulSets, Ingress, HPA, CronJobs, GitOps, and a
full CI/CD pipeline with security scanning baked in.

The application itself is intentionally simple (3 Python microservices + a
static frontend) — the complexity here is entirely in the infrastructure and
pipeline around it, which is the point.

---

## Architecture

```
                        ┌─────────────┐
                        │   frontend   │  (nginx, static HTML/JS)
                        │  reverse-    │
                        │  proxies     │
                        │  /api/*      │
                        └──────┬───────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                     │
   ┌──────▼──────┐     ┌───────▼───────┐     ┌───────▼───────┐
   │ user-service │     │product-service│     │ order-service │
   │  (FastAPI)   │     │   (FastAPI)   │     │   (FastAPI)   │
   └──────┬───────┘     └───────┬───────┘     └───────┬───────┘
          │                     │        calls both ──┘
          │              ┌──────┴──────┐      of these
          │              │    Redis    │      services
          │              │   (cache)   │
          │              └─────────────┘
          │
   ┌──────▼──────────────────────┐
   │         Postgres            │
   │  (StatefulSet + PVC)        │
   └──────────────────────────────┘
```

- **user-service** — Postgres-backed user records
- **product-service** — Postgres-backed product catalog, cached in Redis
- **order-service** — Places orders; calls user-service and product-service over HTTP
- **frontend** — Static HTML/JS + nginx, reverse-proxies `/api/*` to the backend services internally (same pattern works unchanged in both Docker Compose and Kubernetes, and avoids CORS entirely since everything is same-origin from the browser's perspective)

---

## Running locally with Docker Compose

Fastest way to test application changes before touching Kubernetes at all.

```bash
docker compose up --build
```

Open the app at **http://localhost:8090**. It shows live health status for
all three backend services, and lets you create products/users and place
orders directly from the browser.

Shut down (and wipe the database volume for a clean slate):

```bash
docker compose down -v
```

### Manual API checks (optional — the frontend covers this too)

```bash
curl -X POST http://localhost:8001/users -H "Content-Type: application/json" \
  -d '{"username": "alice", "email": "alice@example.com"}'

curl -X POST http://localhost:8002/products -H "Content-Type: application/json" \
  -d '{"name": "Wireless Mouse", "price": 25.99, "stock": 100}'

curl -X POST http://localhost:8003/orders -H "Content-Type: application/json" \
  -d '{"user_id": 1, "product_id": 1, "quantity": 2}'
```

---

## Running on Kubernetes (k3d)

All manifests live in `k8s/`, applied in numeric order.

### 1. Create a cluster

A 1 server + 1 agent cluster is a good balance of realism vs. resource usage
on a modest machine:

```bash
k3d cluster create devops-lab --servers 1 --agents 1 --port "8080:80@loadbalancer"
```

### 2. Build and import images (for local-only testing, without a registry)

```bash
docker compose build --provenance=false --sbom=false
k3d image import ecom-user-service:latest ecom-product-service:latest \
  ecom-order-service:latest ecom-frontend:latest -c devops-lab --mode direct
```

> **Note on `--provenance=false --sbom=false`:** newer Docker Buildx versions
> attach provenance/SBOM attestation manifests to images by default. These
> confuse `k3d image import` (and some other tools expecting a classic
> single-manifest image), producing a `content digest ... not found` error
> that has nothing to do with image corruption. Building without them avoids
> this entirely.

Postgres and Redis don't need importing — the cluster pulls those directly
from Docker Hub, same as any real cluster would.

### 3. Apply everything

```bash
cd k8s
kubectl apply -f 00-namespace.yaml
kubectl apply -f 01-postgres-secret.yaml
kubectl apply -f 02-configmap.yaml
kubectl apply -f 03-postgres-statefulset.yaml
kubectl apply -f 04-redis.yaml
kubectl apply -f 05-user-service.yaml
kubectl apply -f 06-product-service.yaml
kubectl apply -f 07-order-service.yaml
kubectl apply -f 08-frontend.yaml
kubectl apply -f 09-ingress.yaml
kubectl apply -f 10-hpa.yaml
kubectl apply -f 11-cronjob-sales-report.yaml
kubectl apply -f 12-cronjob-postgres-backup.yaml
```

### 4. Verify

```bash
kubectl get pods -n ecom -w
```

Once everything shows `1/1 Running` with restart counts staying flat, open
**http://localhost:8080** in your browser.

### What each manifest teaches

| File | Concept |
|---|---|
| `01-postgres-secret.yaml` | Secrets vs ConfigMaps — credentials never go in plaintext ConfigMaps |
| `03-postgres-statefulset.yaml` | StatefulSets — stable pod identity + per-replica PVC via `volumeClaimTemplates` |
| `05/06/07-*-service.yaml` | Deployments, readiness/liveness probes, resource requests/limits |
| `09-ingress.yaml` | Single entrypoint routing, Traefik (k3s's default ingress controller) |
| `10-hpa.yaml` | Horizontal Pod Autoscaling based on real CPU metrics |
| `11/12-cronjob-*.yaml` | CronJobs — scheduled reporting and database backups, with proper `concurrencyPolicy` and history limits |

### Load-testing the HPA

```bash
kubectl run load-generator --image=busybox --restart=Never -n ecom -- \
  /bin/sh -c "while true; do wget -q -O- http://product-service:8000/products; done"

kubectl get hpa -n ecom -w
```

Clean up afterward:

```bash
kubectl delete pod load-generator -n ecom
```

---

## CI/CD Pipeline (DevSecOps)

`.github/workflows/ci-cd.yml` implements a full pipeline, entirely running
in GitHub's cloud (not on your local machine):

```
push to main
     │
     ▼
┌─────────────────────────────────────────┐
│ 1. Test        pytest, real Postgres     │
│                service container         │
│ 2. SAST         SonarCloud               │
│ 3. SCA          Trivy filesystem scan    │
│ 4. Build        docker build (no         │
│                 attestations)            │
│ 5. Container    Trivy image scan — fails │
│    scan         the build on HIGH/       │
│                 CRITICAL CVEs            │
│ 6. Push         GHCR (only if all above  │
│                 passed)                  │
│ 7. Update       bump image tag in        │
│    manifests    k8s/*.yaml, commit       │
└─────────────────┬─────────────────────────┘
                   │
                   ▼
      Argo CD notices the git commit and
      syncs the cluster automatically —
      CI never touches Kubernetes directly.
```

### One-time setup

1. **Create the GitHub repo and push this project.**

2. **Replace placeholders** in all `k8s/*.yaml` files:
   ```bash
   find k8s -name "*.yaml" -exec sed -i \
     's/YOUR_GITHUB_USERNAME/<your-username>/g; s/YOUR_REPO_NAME/<your-repo>/g' {} \;
   ```

3. **SonarCloud** (free for public repos): create a project at
   [sonarcloud.io](https://sonarcloud.io), update `sonar-project.properties`
   with your organization/project key, generate a token, and add it as a
   repo secret named `SONAR_TOKEN`.

4. **Make GHCR packages public** after the first pipeline run, so your
   cluster can pull them without needing an image pull secret: GitHub
   profile → Packages → each package → Package settings → Change
   visibility → Public.

5. Push a commit and watch the **Actions** tab.

### Security scanning notes

- **SonarCloud (SAST)** catches code-level issues: bugs, code smells,
  security hotspots (e.g. SQL injection patterns, hardcoded secrets) —
  before anything is even built.
- **Trivy filesystem scan (SCA)** checks `requirements.txt` for known CVEs
  in third-party packages.
- **Trivy image scan** checks the *built container*, including OS packages
  baked into the base image — catches vulnerabilities the filesystem scan
  can't see.
- **`.trivyignore`** is where you'd document any deliberately-accepted
  CVEs, with a reason and date — never used just to force a scan to pass.

---

## GitOps with Argo CD

Argo CD is installed using the lightweight **core** profile (no UI, Redis,
or Dex) — enough to demonstrate real GitOps sync behavior without the
overhead of the full install, which matters on a resource-constrained
homelab machine.

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/core-install.yaml
kubectl apply -f k8s/argocd/application.yaml
```

Check sync status:

```bash
kubectl get application -n argocd
```

With `syncPolicy.automated.selfHeal: true` set in `k8s/argocd/application.yaml`,
manually running `kubectl edit` or `kubectl delete` against anything Argo CD
manages will simply get reverted back to match git — a good thing to
deliberately test once, to see GitOps reconciliation in action.

---

## Break-it-on-purpose exercises

These are worth running deliberately to build real debugging reflexes:

| Break it | Command | What you'll see |
|---|---|---|
| Bad image tag | `kubectl set image deployment/user-service user-service=nginx:doesnotexist -n ecom` | `ImagePullBackOff`, but old pods keep serving traffic |
| Broken readiness probe | Patch the probe path to something invalid | Pod stays `Running` but `0/1 Ready`; Service silently keeps routing to old healthy pods |
| OOMKilled | Lower a container's memory limit drastically | `CrashLoopBackOff`, `Last State: Terminated, Reason: OOMKilled` |
| Missing ConfigMap/Secret | Delete `ecom-config` or `postgres-secret`, restart a deployment | `CreateContainerConfigError` |
| RBAC lockout | Create a RoleBinding, then delete it | `kubectl auth can-i` returns `no` |

For each: diagnose using only `kubectl describe pod`, `kubectl get events
--sort-by=.lastTimestamp`, and `kubectl logs`, then write a 2-3 sentence
incident note. That habit — plus the ability to explain *why* something
broke, not just that it did — is what turns a homelab into real interview
material.

---

## Known environment quirks (Windows + WSL2 + Docker Desktop)

If you're running this stack on Windows via WSL2, a few things worth
knowing in advance, all encountered and resolved while building this lab:

- **Docker Desktop periodically resets `~/.docker/config.json`**, re-adding
  a `credsStore` that can break `docker pull`/`build` on WSL2. Workaround:
  set `export DOCKER_CONFIG=/tmp/docker-empty-config` with an empty
  `{}` config, rather than editing the shared file Docker Desktop keeps
  rewriting.
- **`k3d image import` failing with `content digest ... not found`**, even
  after rebuilding/re-pulling images, is very likely the provenance/SBOM
  attestation-manifest issue described above — not corruption.
- **Low-memory WSL2 VMs** (check with `free -h`) cause node instability
  (`NodeNotReady`, pods restarting for no code-related reason) that looks
  exactly like an application bug but isn't. Set explicit memory/swap
  limits in `%USERPROFILE%\.wslconfig` and consider a 1-agent (or even
  0-agent) cluster if your machine has less than ~8GB total RAM.
