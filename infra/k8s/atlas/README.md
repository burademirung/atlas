# Atlas Helm chart

Deploys the **Atlas Deep-Research Studio** workloads to an EKS cluster:

| Object | Purpose |
|---|---|
| `api` Deployment + Service + Ingress + HPA | FastAPI / uvicorn, ALB ingress, CPU autoscaling |
| `worker` Deployment + KEDA `ScaledObject` | arq agent worker, Redis queue-depth autoscaling (scale-to-zero) |
| `ServiceAccount` ×3 | EKS Pod Identity subjects for api / worker / migration |
| `ConfigMap` | non-secret env (DB parts, Redis URL, JWT knobs, cost caps) |
| `ExternalSecret` | pulls JWT/Anthropic/Tavily/DB secrets from AWS Secrets Manager |
| migration `Job` | Alembic `upgrade head` as a `pre-install`/`pre-upgrade` hook |
| `NetworkPolicy` ×6 | default-deny + least-privilege allows (SSRF/egress controls) |
| `PodDisruptionBudget` ×2 | availability during voluntary disruptions |

It maps directly to the design spec §10 (Infrastructure & ops) and §11 (Security).

---

## Prerequisites (cluster add-ons — NOT installed by this chart)

These are cluster-scoped controllers that own CRDs. Install them once per cluster
(typically in a platform/bootstrap layer) **before** installing Atlas:

1. **KEDA** — provides `keda.sh/v1alpha1` `ScaledObject`.
   ```sh
   helm repo add kedacore https://kedacore.github.io/charts
   helm install keda kedacore/keda -n keda --create-namespace
   ```

2. **External Secrets Operator** — provides `external-secrets.io` `ExternalSecret`,
   plus a `ClusterSecretStore` named per `externalSecrets.secretStoreRef.name`
   wired to AWS Secrets Manager.
   ```sh
   helm repo add external-secrets https://charts.external-secrets.io
   helm install external-secrets external-secrets/external-secrets \
     -n external-secrets --create-namespace
   ```

3. **AWS Load Balancer Controller** — reconciles the `alb` IngressClass.
   ```sh
   helm repo add eks https://aws.github.io/eks-charts
   helm install aws-load-balancer-controller eks/aws-load-balancer-controller \
     -n kube-system --set clusterName=<CLUSTER>
   ```

4. A **NetworkPolicy-enforcing CNI** (VPC CNI network-policy controller, Calico,
   or Cilium). Without it the `NetworkPolicy` objects render but are not enforced.

5. **metrics-server** (for the API CPU HPA).

You also need:
- AWS Secrets Manager secrets at the paths in `externalSecrets.remoteRefs`.
- An EKS Pod Identity association (or IRSA) linking each ServiceAccount to its
  IAM role (created in Terraform, see `infra/terraform`).
- An ACM certificate ARN for the ALB (`ingress.certificateArn`).
- Images pushed to ECR (`image.registry` + `<component>.image.repository`).

---

## Install / upgrade

```sh
# enforce the Restricted Pod Security Standard on the namespace
kubectl create namespace atlas --dry-run=client -o yaml | kubectl apply -f -
kubectl label --overwrite namespace atlas \
  pod-security.kubernetes.io/enforce=restricted \
  pod-security.kubernetes.io/warn=restricted \
  pod-security.kubernetes.io/audit=restricted

helm upgrade --install atlas infra/k8s/atlas \
  --namespace atlas \
  --values infra/k8s/atlas/values.yaml \
  --values infra/k8s/atlas/values-prod.yaml   # your env overlay
```

Deploy by immutable digest in CD by passing the image digest as the tag:

```sh
helm upgrade --install atlas infra/k8s/atlas -n atlas \
  --set api.image.tag=sha256:<digest> \
  --set worker.image.tag=sha256:<digest>
```

Render locally without applying:

```sh
helm template atlas infra/k8s/atlas -n atlas | less
```

---

## First-install ordering caveat (migrations + ExternalSecret)

The Alembic migration runs as a `pre-install`/`pre-upgrade` **hook**, before the
main release manifests (including the `ExternalSecret`) are applied. Because ESO
reconciles the target `Secret` **asynchronously**, on a *brand-new* install the
`atlas-secrets` Secret may not yet exist when the migration Job starts.

Options:
- Pre-create the `ExternalSecret`/Secret once (apply the chart with
  `--set migration.enabled=false`, wait for the Secret to reconcile, then
  upgrade with migrations enabled), **or**
- Seed the Secret out of band on first install.

On steady-state `helm upgrade` the Secret already exists, so the hook runs
cleanly. Migrations are expand-contract / backward-compatible, so the API may
roll independently of the schema change.

---

## Key values

| Path | Meaning |
|---|---|
| `image.registry` | ECR registry host shared by all images |
| `api.hpa.*` | CPU HPA bounds/targets/behavior |
| `keda.minReplicaCount` / `keda.maxReplicaCount` | worker scale bounds (0 = scale-to-zero) |
| `keda.redis.listName` / `keda.redis.lagThreshold` | arq queue key + desired jobs-per-replica |
| `config.research.*` | per-run cost/abuse caps (§5) |
| `networkPolicy.egress.blockedCidrs` | IMDS + RFC1918 ranges denied to the worker |
| `podSecurityContext` / `securityContext` | Restricted PSS hardening |

See `values.yaml` for the full, commented set.

---

## Uninstall

```sh
helm uninstall atlas -n atlas
```

`ExternalSecret` uses `deletionPolicy: Retain`, so the underlying k8s Secret is
left in place on uninstall; delete it manually if desired.
