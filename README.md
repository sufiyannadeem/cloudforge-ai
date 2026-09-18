# CloudForge AI 🚀

CloudForge AI is a production-inspired internal developer platform designed to simplify infrastructure provisioning, application deployment, and reliability operations.

The long-term goal is to combine Platform Engineering, DevOps, SRE, Observability, and AI-assisted incident investigation into one developer-focused platform.

> **Current status:** Module 1 — Project Service foundation implemented and CI-validated.

---

## 📌 Project Vision

CloudForge AI aims to provide developers with self-service capabilities for:

- Creating and managing projects.
- Provisioning infrastructure through Terraform.
- Deploying applications through GitOps.
- Monitoring application and infrastructure reliability.
- Investigating incidents using observability data and AI assistance.
- Tracking platform engineering and SRE metrics.

The platform is designed with security, automation, reliability, and operational visibility in mind.

---

## 🏗️ Planned Architecture

```text
                         ┌─────────────────────────┐
                         │       Developer         │
                         └────────────┬────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │    CloudForge Frontend  │
                         │    Next.js + TypeScript │
                         └────────────┬────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │       API Gateway       │
                         └────────────┬────────────┘
                                      │
             ┌────────────────────────┼────────────────────────┐
             │                        │                        │
             ▼                        ▼                        ▼
   ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
   │ Project Service │    │ Infrastructure  │    │ Deployment      │
   │      Go         │    │ Service         │    │ Service         │
   └────────┬────────┘    └────────┬────────┘    └────────┬────────┘
            │                      │                      │
            └──────────────────────┼──────────────────────┘
                                   │
                                   ▼
                         ┌─────────────────────────┐
                         │      PostgreSQL         │
                         └─────────────────────────┘

   Infrastructure Provisioning
              │
              ▼
        ┌───────────┐       ┌─────────────────┐
        │ Terraform │──────▶│ AWS / EKS       │
        └───────────┘       └─────────────────┘

   Application Delivery
              │
              ▼
        ┌──────────────┐
        │ GitHub       │
        │ Actions      │
        └──────┬───────┘
               │
               ▼
        ┌──────────────┐
        │ GitOps Repo  │
        └──────┬───────┘
               │
               ▼
        ┌──────────────┐
        │ Argo CD      │
        └──────┬───────┘
               │
               ▼
        ┌──────────────┐
        │ Kubernetes   │
        │ / AWS EKS    │
        └──────────────┘

   Observability
        ┌─────────────────────────────────────┐
        │ Prometheus │ Grafana │ Loki         │
        │ OpenTelemetry │ SLOs │ Error Budget │
        └─────────────────────────────────────┘

   AI Operations
        ┌─────────────────────────────────────┐
        │ Python + FastAPI                    │
        │ Incident Investigation              │
        │ Telemetry Analysis                  │
        │ Human-validated Recommendations     │
        └─────────────────────────────────────┘
