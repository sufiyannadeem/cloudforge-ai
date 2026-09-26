# CloudForge AI 🚀

CloudForge AI is a production-inspired internal developer platform designed to simplify project management, infrastructure provisioning, application delivery, and reliability operations.

> **Current status:** Module 1 foundation — Go Project Service implemented, containerized, tested, and validated through GitHub Actions CI.

## Vision

CloudForge AI is being developed as a platform engineering project combining:

- Developer self-service
- Infrastructure as Code
- CI/CD automation
- GitOps deployments
- Kubernetes and AWS operations
- SRE and observability
- AI-assisted incident investigation

Features will be added incrementally and documented only after implementation and validation.

## Current Technology Stack

| Area | Technology |
|---|---|
| Backend | Go |
| API | REST |
| Database | PostgreSQL 16 |
| Database driver | pgx/v5 |
| Migrations | Embedded SQL migrations |
| Containers | Docker |
| Local orchestration | Docker Compose |
| Testing | Go unit and integration tests |
| CI | GitHub Actions |
| Code quality | gofmt and go vet |

## Planned Technology Stack

| Area | Technology |
|---|---|
| Frontend | Next.js and TypeScript |
| Core services | Go |
| AI Operations | Python and FastAPI |
| Cache | Redis |
| Messaging | RabbitMQ |
| Infrastructure | Terraform |
| Cloud | AWS |
| Kubernetes | Amazon EKS |
| GitOps | Argo CD |
| Metrics | Prometheus |
| Dashboards | Grafana |
| Logs | Loki |
| Tracing | OpenTelemetry |
| Security | SonarQube, Trivy, Gitleaks, Checkov |

## Module 1: Project Service Foundation

The first module provides a backend service for managing CloudForge AI projects.

### Implemented capabilities

- Create projects
- Retrieve projects by UUID
- List projects with pagination
- Update projects
- Delete projects
- Request validation
- PostgreSQL persistence
- Embedded database migrations
- Health check endpoint
- Request ID middleware
- Request logging
- Strict JSON parsing
- Graceful shutdown
- Docker multi-stage build
- Non-root container execution
- Docker Compose integration
- Unit tests
- PostgreSQL integration tests
- GitHub Actions CI

## Repository Structure

```text
cloudforge-ai/
├── .github/
│   └── workflows/
│       └── ci.yml
├── services/
│   └── project-service/
│       ├── cmd/server/main.go
│       ├── internal/
│       │   ├── config/
│       │   ├── database/
│       │   ├── handler/
│       │   ├── migration/
│       │   ├── model/
│       │   ├── repository/
│       │   └── service/
│       ├── migrations/
│       ├── tests/
│       ├── Dockerfile
│       ├── .dockerignore
│       ├── go.mod
│       └── go.sum
├── docker-compose.yml
├── .gitignore
└── README.md
```

## Prerequisites

- Ubuntu or another Linux distribution
- Go 1.25 or compatible version
- Docker
- Docker Compose
- Git

Verify tools:

```bash
go version
docker --version
docker compose version
git --version
```

## Run Locally

Clone the repository:

```bash
git clone https://github.com/sufiyannadeem/cloudforge-ai.git
cd cloudforge-ai
```

Start the services:

```bash
docker compose up -d --build
```

Check container status:

```bash
docker compose ps
```

View logs:

```bash
docker compose logs -f project-service
```

Expected application messages:

```text
database migrations completed successfully
project-service listening on port 8080
```

## Health Check

```bash
curl -i http://localhost:8080/health
```

Expected response body:

```json
{
  "service": "project-service",
  "status": "ok"
}
```

The response also includes an `X-Request-ID` header.

## API Endpoints

Base URL:

```text
http://localhost:8080
```

### Create a project

```bash
curl -i -X POST http://localhost:8080/projects   -H "Content-Type: application/json"   -d '{
    "name": "CloudForge Demo",
    "description": "Demo project",
    "repository_url": "https://github.com/example/cloudforge-demo",
    "default_branch": "main"
  }'
```

### Get a project

```bash
curl -i http://localhost:8080/projects/<PROJECT_ID>
```

### List projects

```bash
curl -i "http://localhost:8080/projects?limit=20&offset=0"
```

Pagination limits:

- Default limit: `20`
- Maximum limit: `100`
- Default offset: `0`

### Update a project

```bash
curl -i -X PATCH http://localhost:8080/projects/<PROJECT_ID>   -H "Content-Type: application/json"   -d '{
    "name": "Updated Project",
    "description": "Updated description"
  }'
```

### Delete a project

```bash
curl -i -X DELETE http://localhost:8080/projects/<PROJECT_ID>
```

Expected successful status:

```text
204 No Content
```

## Database

Local PostgreSQL configuration:

| Setting | Value |
|---|---|
| Database | cloudforge |
| Username | cloudforge |
| Password | Value from local `.env` (`POSTGRES_PASSWORD`) |
| Host from host machine | localhost |
| Host inside Compose | postgres |
| Port | 5432 |

The credentials are for local development only. Production deployments should use secure secret management.

### Database migrations

Migrations run automatically when the service starts.

The migration runner:

1. Creates the migration tracking table.
2. Loads embedded SQL migration files.
3. Checks whether each migration was applied.
4. Runs unapplied migrations in a transaction.
5. Records the migration version.
6. Commits the transaction.

## Testing

From the service directory:

```bash
cd services/project-service
```

Run all tests:

```bash
go test -v ./...
```

Run tests with race detection:

```bash
go test -race ./...
```

Check formatting:

```bash
gofmt -l .
```

Run static checks:

```bash
go vet ./...
```

Build the service:

```bash
go build ./...
```

Integration tests use a separate test database:

```bash
export TEST_DATABASE_URL="postgres://cloudforge:${POSTGRES_PASSWORD}@localhost:5432/cloudforge_test?sslmode=disable"
```

## Docker Commands

Build the image:

```bash
docker build   -t cloudforge-project-service:local   ./services/project-service
```

Start the stack:

```bash
docker compose up -d --build
```

Stop the stack:

```bash
docker compose down
```

Stop the stack and remove local database data:

```bash
docker compose down -v
```

> `docker compose down -v` deletes the PostgreSQL volume and its local data.

The Docker image uses a multi-stage build and runs the application as a non-root user.

## CI Pipeline

Workflow location:

```text
.github/workflows/ci.yml
```

The CI pipeline currently performs:

1. Repository checkout
2. Go setup
3. Tool version display
4. Go formatting verification
5. Dependency download
6. PostgreSQL service startup
7. Test database creation
8. Database schema setup
9. Unit and integration tests
10. Application build
11. `go vet`
12. Docker image build

The workflow runs on pushes to `main`, `develop`, and feature branches, and on pull requests targeting `main` or `develop`.

## Planned Roadmap

### Module 1 — Project Service Foundation

- [x] Go project service
- [x] PostgreSQL integration
- [x] Project CRUD APIs
- [x] Validation
- [x] Database migrations
- [x] Dockerfile
- [x] Docker Compose
- [x] Health checks
- [x] Request IDs
- [x] Unit tests
- [x] Integration tests
- [x] GitHub Actions CI
- [x] Initial documentation

### Module 2 — Platform Engineering

- [ ] Infrastructure Service
- [ ] Terraform execution workflow
- [ ] Provisioning request tracking
- [ ] Approval workflow
- [ ] Deployment Service
- [ ] GitOps integration
- [ ] Argo CD integration

### Module 3 — CI/CD and Security

- [ ] GitHub Actions application pipeline
- [ ] Docker image publishing
- [ ] SonarQube analysis
- [ ] Trivy scanning
- [ ] Gitleaks scanning
- [ ] Checkov scanning
- [ ] Security gates

### Module 4 — SRE and AI Operations

- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Loki log collection
- [ ] OpenTelemetry tracing
- [ ] SLO tracking
- [ ] Error budgets
- [ ] Incident investigation service
- [ ] AI-assisted operational recommendations

### Module 5 — AWS Deployment

- [ ] Terraform AWS infrastructure
- [ ] Amazon EKS
- [ ] Argo CD
- [ ] TLS configuration
- [ ] Secure secrets management
- [ ] Load testing
- [ ] Disaster recovery exercises

## Engineering Principles

- Automate repetitive operational work.
- Apply security throughout the delivery lifecycle.
- Build observability into services.
- Manage infrastructure as code.
- Use Git as the source of truth for deployments.
- Require human validation for risky production changes.
- Implement and test each module incrementally.

## Interview Focus

This project is intended to demonstrate practical understanding of:

- Go service development
- REST APIs
- Layered architecture
- PostgreSQL persistence
- Database migrations
- Docker and container security
- CI/CD
- Infrastructure as Code
- GitOps
- Kubernetes
- Observability
- SRE concepts
- Platform Engineering
- AI-assisted operations

Development assistance from documentation and AI tools should be combined with personal understanding, testing, troubleshooting, and the ability to explain design decisions.

## Author

**Nadeem Sufiyan**

- GitHub: https://github.com/sufiyannadeem
- Repository: https://github.com/sufiyannadeem/cloudforge-ai

## License

License information will be added in a future update.
