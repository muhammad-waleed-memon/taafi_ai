# Alibaba Cloud ACK Production Deployment Guide

This guide provides step-by-step instructions to deploy the refactored, production-ready, cloud-native Taafi.ai architecture to **Alibaba Cloud Container Service for Kubernetes (ACK)**.

---

## 1. Prerequisites

Ensure you have the following installed and configured on your machine:
- Alibaba Cloud CLI (`aliyun`) configured with appropriate AccessKeys.
- Kubernetes CLI (`kubectl`) pointing to your ACK cluster.
- Docker or a compatible container builder.

---

## 2. Setting Up secrets and Configurations

Before applying the Kubernetes deployments, configure the namespace and secrets:

1. Make the helper script executable:
   ```bash
   chmod +x scripts/create-secrets.sh
   ```
2. Execute the script:
   ```bash
   ./scripts/create-secrets.sh
   ```
   The script will:
   - Create the namespace `taafi-system`.
   - Request the PostgreSQL Connection DSN.
   - Request the `DASHSCOPE_API_KEY` for Qwen.
   - Securely compile these values into a Kubernetes Secret (`taafi-secret`).

---

## 3. Deploying Kubernetes Manifests

Apply the entire configuration manifest stack located in the `k8s/` folder:

```bash
# Apply ConfigMap, PVC, Services, and Deployments
kubectl apply -f k8s/
```

### Manifest Component Roles:
- **`namespace.yml`**: Defines the namespace `taafi-system`.
- **`configmap.yml`**: Configures global variables (`VALKEY_URL`, `CORE_ENGINE_URL`).
- **`secret.yml`**: Serves as a placeholder for Secrets (automatically overwritten by `create-secrets.sh`).
- **`pvc.yml`**: Mounts a 10Gi SSD storage block (`alicloud-disk-ssd`) for PostgreSQL persistent memory.
- **`postgres-deployment.yml` / `postgres-service.yml`**: Hosts the persistent PostgreSQL database.
- **`valkey-deployment.yml` / `valkey-service.yml`**: Spins up the Pub/Sub messaging channel engine.
- **`core-engine-deployment.yml` / `core-engine-service.yml`**: Deploys the FastAPI server equipped with Liveness and Readiness probes.
- **`neural-orchestrator-deployment.yml`**: Deploys the Autopilot worker daemon that reacts to deadlocks.
- **`web-dashboard-deployment.yml` / `web-dashboard-service.yml`**: Deploys the Nginx reverse-proxied React dashboard.
- **`ingress.yml`**: Maps external HTTP traffic via the Ingress Controller.

---

## 4. Ingress Configuration & Testing

To test the application externally:
1. Fetch the public IP address assigned to the Alibaba Cloud Ingress Controller load balancer:
   ```bash
   kubectl get ingress taafi-ingress -n taafi-system
   ```
2. Map your local DNS or point your browser to the output IP address.
3. Since all API routing is proxied relative (`/api/*`) via Nginx inside the frontend pods, no CORS errors will occur, and there is no need to expose port 8000 externally.

---

## 5. GitHub Actions CI/CD Pipeline

To enable automated pipelines (`.github/workflows/deploy.yml`), add the following secrets to your GitHub Repository settings:
- `ALIBABA_ACR_USERNAME`: Registry credential username.
- `ALIBABA_ACR_PASSWORD`: Registry credential password.
- `ALIBABA_ACCESS_KEY_ID`: Alibaba Cloud Access Key ID.
- `ALIBABA_ACCESS_KEY_SECRET`: Alibaba Cloud Access Key Secret.
- `ALIBABA_ACK_CLUSTER_ID`: Target ACK cluster identifier.
