# CloudForge AI 🚀

> **Production DevSecOps & Platform Engineering Control Plane for AWS & Kubernetes**
> Developers self-serve AWS infrastructure and deploy containerized workloads; Platform Engineers enforce policy-as-code guardrails, monitor SRE golden signals, and optimize cloud spend.

---

## 🏛️ System Architecture

```mermaid
flowchart TD
    subgraph UI ["Developer & Platform Console (Next.js 16)"]
        portal["Developer Portal\n/infrastructure"]
        deployUI["Deployment Console\n/deployments"]
        opsUI["Operations & SRE\n/dashboard"]
        finopsUI["FinOps Intelligence\n/finops"]
    end

    subgraph CoreServices ["Core Platform Services (Go)"]
        projectSvc["Project Service\n:8080"]
        infraSvc["Infrastructure Service\n:8081\n(Terraform Runner)"]
        deploySvc["Deployment Service\n:8082\n(EKS Engine)"]
    end

    subgraph IntelligenceServices ["Intelligence & Telemetry (Python / FastAPI)"]
        aiopsSvc["AIOps Service\n:8084\n(Anomaly Detection & Remediation)"]
        finopsSvc["FinOps Service\n:8083\n(Cost Explorer, Budgets, Rightsizing)"]
    end

    subgraph Observability ["Observability Stack"]
        prom["Prometheus :9090"]
        grafana["Grafana :3001"]
        alertmgr["Alertmanager :9093"]
    end

    subgraph AWS ["Amazon Web Services (AWS)"]
        tf["Terraform Engine\n(init → validate → plan → hash → apply)"]
        vpc["VPC & Subnets"]
        ec2["EC2 Compute"]
        s3["S3 Storage"]
        rds["RDS PostgreSQL"]
        eks["EKS Cluster"]
        alb["Application Load Balancer"]
        ce["AWS Cost Explorer & Budgets API"]
    end

    portal -->|Provision Requests| infraSvc
    infraSvc -->|Isolated Workspace Execution| tf
    tf -->|Provision Resources| vpc & ec2 & s3 & rds & eks & alb

    deployUI -->|Deploy Workloads| deploySvc
    deploySvc -->|Deploy & Pod Telemetry| eks

    opsUI -->|Golden Signals| prom
    prom -->|Telemetry Collection| deploySvc & alertmgr & grafana

    aiopsSvc -->|PromQL Analysis| prom
    aiopsSvc -.->|Remediation Guardrail| portal

    finopsUI -->|Cost & Optimization Queries| finopsSvc
    finopsSvc -->|Read-Only Boto3| ce
    finopsSvc -->|Pre-Provisioning Cost Estimates| infraSvc
```

---

## ⚡ Key Capabilities

### 1. Self-Service AWS Infrastructure Provisioning
- **6 Core AWS Resources**: Provision standard building blocks without hand-crafting HCL:
  - `aws_vpc`: CIDR blocks, DNS hostnames & support, custom tags
  - `aws_ec2`: Instance types, Amazon Linux SSM resolution or custom AMIs, subnet placement
  - `aws_s3`: Object versioning, server-side encryption, public access block, TLS transport enforcement
  - `aws_rds`: PostgreSQL engines, storage allocation, subnet groups
  - `aws_eks`: Multi-AZ subnets, managed node groups, cluster versioning
  - `aws_lb`: Application Load Balancers, target groups, HTTP/HTTPS listeners
- **Strict Human-in-the-Loop Lifecycle**:
  `Create → Plan → Awaiting Approval → Approve & Apply → Active` (and symmetric `Destroy Plan → Awaiting Approval → Approve & Destroy`).
- **Tamper-Proof Plan Execution**: Computes SHA-256 hashes of generated Terraform binary plans with an enforced 30-minute approval TTL. Applies are rejected if plans are modified, corrupted, or expired.
- **Strict Safety Guardrail**: AI never directly mutates AWS resources. All cloud infrastructure modifications require human authorization through deterministic Terraform plans.

### 2. Application Deployment Platform
- **EKS Workload Delivery**: Automates container rollouts across development, staging, and production environments.
- **Live Pod Telemetry**: Real-time replica tracking, container health checks, commit SHA badges, and live deployment log viewers.
- **One-Click Rollbacks**: Human-authorized rollback mechanism restoring known-healthy deployment revisions.

### 3. Operations & SRE Observability Console
- **SRE Golden Signals**: Real-time tracking of Availability (%), Request Rate (req/sec), Error Rate (%), P95 Latency (ms), In-Flight Requests, and Active Deployments.
- **Multi-Window Multi-Burn-Rate Alerts**: Google SRE error budget alerting monitoring 99.9% availability, request success, and latency budgets across 5m, 30m, 1h, and 6h windows.
- **Service Health Grid**: Continuous health monitoring covering all platform microservices.
- **Prometheus & Grafana**: Pre-configured scrape configurations and dashboards for operational diagnostics.

### 4. FinOps Closed-Loop Cost Intelligence
- **Real AWS Integration**:
  - Connects to **AWS Cost Explorer** for daily cost trends and per-service attribution.
  - Queries **AWS Budgets API** for real-time spend vs budget thresholds and forecasting.
  - Inspects resources via the **AWS Resource Groups Tagging API**.
- **Terraform Plan Cost Estimation**: Pre-calculates monthly unit costs before mutating AWS. Flags soft limit ($100) and hard limit ($500) policy violations.
- **Evidence-Based Rightsizing**:
  - Analyzes CPU & memory utilization against provisioned capacities.
  - Emits rightsizing recommendations (e.g. `t3.large` at $75/mo with 8% CPU → downsize to `t3.medium` at $40/mo → **$35/mo savings**).
  - Enforces zero hallucinated savings: savings are computed only when backed by explicit pricing evidence.
- **Cost Anomaly Detection**: Statistical Z-score deviation detection (Critical, High, Medium) with sparkline visualizations.
- **Offline Demo Fallback**: Graceful offline fallback demonstrating full telemetry when live AWS credentials are not yet configured.

### 5. AIOps Remediation & Guardrails
- **Automated Root Cause Analysis (RCA)**: Investigates cluster capacity exhaustion, database provisioning anomalies, and crash loops.
- **Human-Approved Remediations**: Remediation actions require operator review and approval with minimum sample thresholds before execution.

---

## 🛠️ Technology Stack

| Domain | Technologies |
|---|---|
| **Frontend** | Next.js 16 (App Router, React 19, TypeScript, Tailwind CSS) |
| **Backend Services** | Go 1.25, `net/http`, `pgx/v5` PostgreSQL driver |
| **AI & FinOps** | Python 3.12, FastAPI, Pydantic v2, `boto3`, NumPy |
| **IaC & Provisioning** | HashiCorp Terraform 1.16 |
| **Cloud Provider** | Amazon Web Services (AWS) |
| **Observability** | Prometheus 3.5, Grafana 12.1, Alertmanager 0.28 |
| **Database** | PostgreSQL 16 Alpine |
| **Containerization** | Docker, Docker Compose (Multi-stage non-root builds) |
| **CI / Automation** | GitHub Actions |

---

## 📁 Repository Structure

```text
cloudforge-ai/
├── .github/
│   └── workflows/
│       ├── ci.yml                 # Unified CI matrix with hardened ci-gate aggregator
│       └── security.yml           # Gitleaks, Trivy filesystem/config/image scans, SBOM
├── frontend/                      # Next.js 16 Platform Console
│   ├── src/app/                   # App Router pages (/infrastructure, /deployments, /finops, /dashboard)
│   ├── src/components/            # UI components and approval modals
│   └── src/lib/                   # API clients and authentication helpers
├── infrastructure/
│   └── terraform/
│       ├── bootstrap/             # S3 remote state bucket and DynamoDB lock table
│       └── environments/dev/      # VPC, ECR, and core module declarations
├── monitoring/
│   └── prometheus/                # Prometheus configuration and SLO burn-rate rules
├── scripts/
│   └── bootstrap-local-auth.py    # Local operator credential generator
├── services/
│   ├── project-service/           # Workspace & project registry (Go)
│   ├── infrastructure-service/    # Terraform IaC generator and sandboxed runner (Go)
│   ├── deployment-service/        # Kubernetes / EKS deployment engine (Go)
│   ├── finops-service/            # AWS pricing evidence, cost explorer, & rightsizing (Python)
│   └── aiops-service/             # Incident investigation & remediation guardrails (Python)
├── tests/                         # CI pipeline hardening and end-to-end verification
├── docker-compose.yml             # Unified 10-service local development stack
├── trivy.yaml                     # Trivy scanner configuration
├── .trivyignore                   # Documented security scan exceptions
├── .gitleaks.toml                 # Secret scanning rule configuration
├── .env.example                   # Environment configuration template
└── README.md
```

---

## 🚀 Quickstart & Local Setup

### 1. Clone the Repository
```bash
git clone https://github.com/sufiyannadeem/cloudforge-ai.git
cd cloudforge-ai
```

### 2. Configure Environment & Credentials
Copy the example environment template:
```bash
cp .env.example .env
```

Open `.env` and configure a secure local PostgreSQL password:
```env
# Database
POSTGRES_PASSWORD=your-secure-local-password

# AWS Credentials (Optional: enables live AWS provisioning & FinOps monitoring)
AWS_ACCESS_KEY_ID=your-aws-access-key-id
AWS_SECRET_ACCESS_KEY=your-aws-secret-access-key
AWS_REGION=eu-west-1
AWS_DEFAULT_REGION=eu-west-1

# FinOps Role
CLOUDFORGE_FINOPS_ROLE=platform-engineer
```

> **AWS Credential Best Practices:**
> - **Local Development:** CloudForge can also read credentials automatically from `~/.aws/credentials` or short-lived session tokens (`AWS_SESSION_TOKEN`).
> - **Production Deployments:** Never use long-lived access keys in production. Instead, utilize IAM-based workload identity via **EKS Pod Identity** or **IAM Roles for Service Accounts (IRSA)**, or the standard AWS SDK default credential chain.

### 3. Bootstrap Operator Authentication
Run the interactive authentication bootstrap helper. It generates independent session and internal service tokens without printing secrets:
```bash
python3 scripts/bootstrap-local-auth.py
```
- Select role `platform-engineer` for infrastructure provisioning and approval authority, or `viewer` for read-only access.
- For local development over plain HTTP, `CLOUDFORGE_AUTH_COOKIE_SECURE=false` is set automatically. (Set to `true` behind HTTPS in production).

### 4. Start the Platform
Launch the complete microservice stack:
```bash
docker compose up -d --build
```

Verify that all containers are healthy:
```bash
docker compose ps
```

### 5. Access Platform Consoles

| Service | Port | Endpoint URL | Description |
|---|---|---|---|
| **CloudForge UI** | `3000` | [http://localhost:3000](http://localhost:3000) | Main Platform Engineering console (Next.js 16) |
| **Developer Portal** | `3000` | [http://localhost:3000/infrastructure](http://localhost:3000/infrastructure) | AWS Infrastructure Provisioning |
| **Deployments** | `3000` | [http://localhost:3000/deployments](http://localhost:3000/deployments) | EKS Application Delivery |
| **Operations (SRE)** | `3000` | [http://localhost:3000/dashboard](http://localhost:3000/dashboard) | Golden Signals & Service Health |
| **FinOps Intelligence**| `3000` | [http://localhost:3000/finops](http://localhost:3000/finops) | AWS Cost Explorer & Rightsizing |
| **Project Service** | `8080` | [http://localhost:8080](http://localhost:8080) | Core Project & Workspace API |
| **Infrastructure Service** | `8081` | [http://localhost:8081](http://localhost:8081) | Terraform Provisioning Engine |
| **Deployment Service** | `8082` | [http://localhost:8082](http://localhost:8082) | Deployment Delivery Service |
| **FinOps Service** | `8083` | [http://localhost:8083](http://localhost:8083) | Cost Intelligence & Policy Engine |
| **AIOps Service** | `8084` | [http://localhost:8084](http://localhost:8084) | Remediation & Incident Service |
| **Prometheus** | `9090` | [http://localhost:9090](http://localhost:9090) | Telemetry & SLO Alert Engine |
| **Grafana** | `3001` | [http://localhost:3001](http://localhost:3001) | SRE Metrics Dashboards |
| **Alertmanager** | `9093` | [http://localhost:9093](http://localhost:9093) | Alert Grouping & Routing |

### Docker Management Commands
```bash
# View service logs
docker compose logs -f project-service

# Stop all services
docker compose down

# Stop and wipe PostgreSQL volumes (Warning: resets local database)
docker compose down -v
```

---

## 🔌 API Endpoints & Health Checks

### Project Service API (`http://localhost:8080`)

#### Create a project
```bash
curl -i -X POST http://localhost:8080/projects \
  -H "Content-Type: application/json" \
  -d '{
    "name": "CloudForge Demo",
    "description": "Demo project",
    "repository_url": "https://github.com/example/cloudforge-demo",
    "default_branch": "main"
  }'
```

#### Get a project by UUID
```bash
curl -i http://localhost:8080/projects/<PROJECT_ID>
```

#### List projects (with pagination)
```bash
curl -i "http://localhost:8080/projects?limit=20&offset=0"
```
* Default limit: `20` (max `100`), default offset: `0`.

#### Update a project
```bash
curl -i -X PATCH http://localhost:8080/projects/<PROJECT_ID> \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Updated Project",
    "description": "Updated description"
  }'
```

#### Delete a project
```bash
curl -i -X DELETE http://localhost:8080/projects/<PROJECT_ID>
```
* Expected response: `204 No Content`.

### Health Check Endpoints
Each service provides `/health` or `/health/live` endpoints for container orchestration:
```bash
curl -i http://localhost:8080/health
```
Expected response:
```json
{
  "service": "project-service",
  "status": "ok"
}
```
* Responses include an `X-Request-ID` header for distributed request tracing.

---

## 🗄️ Database & Embedded Migrations

### Local PostgreSQL Configuration

| Setting | Value |
|---|---|
| Database | `cloudforge` |
| Username | `cloudforge` |
| Password | From `.env` (`POSTGRES_PASSWORD`) |
| Host from machine | `localhost:5432` |
| Host inside Compose | `postgres:5432` |

### Database Migrations
Migrations run automatically when services start. The migration runner:
1. Creates the migration tracking table (`schema_migrations`).
2. Discovers embedded SQL migration files.
3. Evaluates unapplied migration steps.
4. Executes migrations inside a transaction.
5. Commits and updates the version history.

---

## 🧪 Testing & Verification

Run tests from the repository root:

```bash
# Infrastructure Service
(cd services/infrastructure-service && go test -v ./...)

# Project Service
(cd services/project-service && go test ./...)

# Deployment Service
(cd services/deployment-service && go test ./...)

# FinOps Service (149 passed)
PYTHONPATH=services/finops-service .venv/bin/pytest services/finops-service/app

# AIOps Service (110 passed)
PYTHONPATH=services/aiops-service .venv/bin/pytest services/aiops-service/app

# Frontend Type Check & ESLint
(cd frontend && npx tsc --noEmit && npx eslint src/app/)

# CI Pipeline Security & Gate Hardening Tests (16 passed)
.venv/bin/pytest tests/test_ci_pipeline_hardening.py
```

### Database Integration Tests
Repository integration tests against PostgreSQL require `TEST_DATABASE_URL` and a running test database:
```bash
export TEST_DATABASE_URL="postgres://cloudforge:${POSTGRES_PASSWORD}@localhost:5432/cloudforge_test?sslmode=disable"
(cd services/infrastructure-service && go test -v ./internal/repository/...)
(cd services/project-service && go test -v ./internal/repository/...)
```
*(Note: If `TEST_DATABASE_URL` is not set, repository integration tests are intentionally skipped).*

---

## 🔒 Security & Safety Principles

1. **Human Approval Gates**: Terraform `apply` and `destroy` cannot execute autonomously. Every plan requires an explicit human review and cryptographic hash verification before execution.
2. **Deterministic FinOps**: Cost optimization recommendations require human authorization. FinOps never issues mutating AWS API calls.
3. **Sensitive Data Redaction**: Terraform runner output automatically masks AWS access keys, secret tokens, and passwords from stdout/stderr.
4. **Isolated Workspaces**: Every infrastructure resource is allocated an isolated directory preventing Terraform state collisions.
5. **CI/CD & Supply-Chain Hardening**:
   - **Secret Scanning**: Gitleaks enforcement across all commits and branches to block credentials.
   - **Vulnerability Failure Gates**: Trivy filesystem, dependency, and container image scans configured with strict `exit-code: 1` failure gates on `HIGH` and `CRITICAL` findings.
   - **Justified Policy Exceptions**: Documented in `.trivyignore` (e.g. S3 state bootstrap AES256 server-side encryption preventing bootstrap circular dependencies prior to KMS provisioning).
   - **Terraform Policy & Formatting Gates**: Automated `terraform fmt -check`, `terraform validate`, and Trivy IaC configuration policy enforcement.
   - **Artifact Traceability**: Container images tagged with immutable Git commit SHAs (`cloudforge-<service>:${{ github.sha }}`) and OpenContainers metadata labels (`org.opencontainers.image.revision`, `org.opencontainers.image.source`).
   - **Commit Loop Protection**: Workflow `permissions: contents: read`, `persist-credentials: false`, and `[skip ci]` / `[ci skip]` guards preventing automated Git push loops.
   - **Hardened CI Gate**: The `ci-gate` job evaluates all required upstream checks with `if: always()`, identifies individual job failures, and flags unexpected skips.
   - **SBOM Generation**: Automated CycloneDX Software Bill of Materials (SBOM) generation and artifact publication for all container images and the root repository.

---

## 📄 License
Apache 2.0. Built for Cloud Platform Engineering & Production DevSecOps.
