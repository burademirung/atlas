# infra/k8s

Kubernetes packaging for **Atlas (Deep-Research Studio)**. The application ships
as a single Helm chart; cluster-wide add-ons are installed separately (they own
CRDs and controllers and have a different lifecycle than the app).

```
infra/k8s/
  README.md            # this file
  atlas/               # the Atlas Helm chart
    Chart.yaml
    values.yaml
    README.md          # install guide + prerequisites
    templates/
      _helpers.tpl
      serviceaccount.yaml      # api / worker / migration SAs (Pod Identity)
      configmap.yaml           # non-secret env
      externalsecret.yaml      # ESO -> AWS Secrets Manager
      api-deployment.yaml      # FastAPI (startup/liveness/readiness probes, Restricted PSS)
      api-service.yaml
      ingress.yaml             # ALB ingress (TLS, health checks)
      api-hpa.yaml             # CPU HPA
      worker-deployment.yaml   # arq worker (long grace + preStop drain)
      worker-scaledobject.yaml # KEDA Redis queue-depth scaler (scale-to-zero)
      migration-job.yaml       # Alembic upgrade head (Helm pre-upgrade hook)
      networkpolicy.yaml       # default-deny + explicit allows (SSRF/egress)
      poddisruptionbudget.yaml # api + worker PDBs
      NOTES.txt
```

## Architecture mapping

The chart implements the Kubernetes slice of the design spec
(`docs/.../deep-research-studio-design.md` §10/§11):

- **Two independently scaled tiers.** The stateless `api` scales on CPU (HPA);
  the `worker` scales on **Redis queue depth via KEDA** (plain HPA cannot read
  queue depth) and scales to zero when idle.
- **Restricted Pod Security Standard** everywhere: `runAsNonRoot`,
  non-root UID, `allowPrivilegeEscalation: false`, `readOnlyRootFilesystem`,
  `seccompProfile: RuntimeDefault`, all capabilities dropped. The namespace
  should be labelled `pod-security.kubernetes.io/enforce: restricted`.
- **Default-deny NetworkPolicies** with least-privilege allows: API → Redis +
  PgBouncer; worker → Redis + PgBouncer + HTTPS 443 (IMDS/RFC1918 excluded to
  block SSRF → IMDS credential theft); DNS and EKS Pod Identity egress allowed.
- **Secrets** are never baked into images or values: the External Secrets
  Operator pulls them from AWS Secrets Manager into a k8s Secret consumed via
  `envFrom`.
- **Schema migrations** run as a Helm `pre-install`/`pre-upgrade` hook
  (expand-contract), so deploys are reversible without down-migrations.
- **Graceful rollouts**: API uses `maxUnavailable: 0` + `preStop` drain so
  in-flight SSE streams survive; the worker uses a long
  `terminationGracePeriodSeconds` so the current run checkpoints before exit.

## Add-on prerequisites

KEDA, External Secrets Operator, the AWS Load Balancer Controller, a
NetworkPolicy-enforcing CNI, and metrics-server must be present in the cluster.
Install instructions are in [`atlas/README.md`](./atlas/README.md).

## Related

- `infra/terraform/` — VPC, EKS, RDS, ElastiCache, ECR, IAM (Pod Identity),
  Secrets Manager, Cloudflare. Provisions the cluster + the IAM roles bound to
  the ServiceAccounts in this chart.
- `apps/api/` — the FastAPI app and Alembic migrations baked into the API image.
