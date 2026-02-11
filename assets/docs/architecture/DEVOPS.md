# DocFlow – Deployment & Operations Guide

> DevOps-Strategie, Konfigurationsmanagement, Monitoring & Skalierung  
> Version: 0.1.0 | Status: Draft | Date: 2026-02-11

---

## 1. Docker-Architektur

### 1.1 Übersicht

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Network: docflow-net               │
│                                                              │
│  ┌──────────────┐  ┌───────────┐  ┌───────┐  ┌───────────┐ │
│  │  docflow-api │  │   tika    │  │ redis │  │   minio   │ │
│  │  (FastAPI)   │  │  (Parser) │  │(cache)│  │ (storage) │ │
│  │  :8000       │──│  :9998    │  │ :6379 │  │ :9000     │ │
│  └──────────────┘  └───────────┘  └───────┘  └───────────┘ │
│        │                                          optional   │
└────────┼────────────────────────────────────────────────────┘
         │
    ┌────▼────┐
    │  :8000  │  ← Reverse Proxy (Nginx/Traefik) in Production
    └─────────┘
```

### 1.2 Multi-Stage Dockerfile

Das Dockerfile nutzt einen **2-Stage-Build**:

| Stage | Base Image | Zweck | Enthält |
|-------|-----------|-------|---------|
| `builder` | `python:3.12-slim` | Dependency-Installation | uv, pip, Build-Tools |
| `runtime` | `python:3.12-slim` | Production-Runtime | .venv, App-Code, Tesseract |

**Resultierende Image-Größe:** ~250 MB (statt ~1.2 GB bei Single-Stage)

**Security-Maßnahmen:**
- Non-root User `appuser` (UID 1000)
- Kein pip/uv im Runtime-Image
- Read-only Filesystem möglich (`--read-only` + tmpfs)
- Health Check eingebaut

### 1.3 Compose-Profile

| Profil | Befehl | Use Case |
|--------|--------|----------|
| Default | `docker compose up` | API + Tika + Redis |
| Development | `docker compose -f ... -f ...dev.yml up` | + Hot-Reload, Debug-Logs |
| Production | `docker compose -f ... -f ...prod.yml up` | + Replicas, JSON-Logs |
| Mit MinIO | `docker compose --profile storage up` | + S3-kompatibler Storage |

### 1.4 Container Health Checks

| Service | Health Check | Interval | Start Period |
|---------|-------------|----------|-------------|
| docflow-api | `GET /api/v1/health` | 30s | 15s |
| tika | `GET /tika` | 30s | 30s |
| redis | `redis-cli ping` | 10s | 5s |
| minio | `mc ready local` | 30s | 10s |

---

## 2. CI/CD Pipeline

### 2.1 Pipeline-Architektur

```
PR / Push
   │
   ├─► Lint ──────────┐
   │                   │
   ├─► Type Check ─────┤
   │                   │
   └─► Security Scan ──┤
                       │
                  Unit Tests
                       │
                Integration Tests (Tika + Redis Services)
                       │
                Build & Push Image (GHCR)
                       │
               ┌───────┴────────┐
               │  Tag v*.*.* ?  │
               └───────┬────────┘
                       │ yes
                 Create Release
                 (auto-changelog)
```

### 2.2 Container Registry: GitHub Container Registry (GHCR)

**Warum GHCR:**
- Integriert in GitHub (keine externe Registry nötig)
- Kostenlos für Open-Source-Projekte
- `GITHUB_TOKEN` reicht – kein extra Secret nötig
- Unterstützt Multi-Arch Images (amd64 + arm64)

**Image-Tagging-Strategie:**

| Trigger | Tags | Beispiel |
|---------|------|---------|
| Push `main` | `latest`, `main`, `sha-abc1234` | `ghcr.io/org/docflow:latest` |
| Push `develop` | `develop`, `sha-abc1234` | `ghcr.io/org/docflow:develop` |
| Tag `v1.2.3` | `1.2.3`, `1.2`, `1`, `sha-abc1234` | `ghcr.io/org/docflow:1.2.3` |

### 2.3 Semantic Versioning & Release

**Workflow:**
1. Entwickler nutzen [Conventional Commits](https://www.conventionalcommits.org/)
2. Release via `make release-patch` / `release-minor` / `release-major`
3. Git-Tag `v*.*.* ` triggert `build-and-push` + `release` Jobs
4. [git-cliff](https://github.com/orhun/git-cliff) generiert automatisch Changelog
5. GitHub Release wird erstellt mit Changelog als Body

**Conventional Commit Prefixes:**

| Prefix | Semver-Impact | Beispiel |
|--------|-------------|---------|
| `feat:` | Minor | `feat: add batch upload endpoint` |
| `fix:` | Patch | `fix: handle empty PDF pages` |
| `feat!:` / `BREAKING CHANGE:` | Major | `feat!: change API response format` |
| `docs:`, `chore:`, `ci:` | – | Kein Release |

### 2.4 Security Scanning

| Tool | Scan-Target | Wann | Output |
|------|-------------|------|--------|
| **Trivy (FS)** | Python-Dependencies | Jeder Push/PR | SARIF → GitHub Security |
| **Trivy (Image)** | Docker-Image | Nach Build | SARIF → GitHub Security |
| **Dependabot** | Dependencies | Wöchentlich (auto) | PRs mit Updates |

---

## 3. Konfigurationsmanagement

### 3.1 Konfigurationsquellen (Priorität)

```
1. Environment Variables        ← höchste Priorität (12-Factor)
2. .env File                    ← lokale Entwicklung
3. config/docflow.yaml          ← Defaults & komplexe Strukturen
4. Hardcoded Defaults           ← Fallback im Code
```

### 3.2 Environment Variables vs. Config Files

| Verwende ENV für... | Verwende YAML für... |
|---------------------|---------------------|
| Secrets (API Keys, Passwords) | Pipeline-Konfiguration (Processor-Reihenfolge) |
| Umgebungsspezifisches (URLs, Ports) | Komplexe verschachtelte Strukturen |
| Feature Flags (on/off) | Default-Werte die selten ändern |
| Container-Orchestrierung | Adapter-spezifische Einstellungen |

### 3.3 Pydantic Settings Pattern

```python
# src/docflow/infrastructure/config.py
from pydantic_settings import BaseSettings

class DocFlowSettings(BaseSettings):
    """Zentrale Konfiguration – ENV-Vars überschreiben Defaults."""

    model_config = SettingsConfigDict(
        env_prefix="DOCFLOW_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # App
    env: str = "development"
    log_level: str = "INFO"
    log_format: str = "text"  # text | json
    port: int = 8000
    workers: int = 4
    max_file_size_mb: int = 100

    # Tika
    tika_url: str = "http://localhost:9998"
    tika_timeout: int = 120

    # OCR
    ocr_enabled: bool = True
    ocr_engine: str = "tesseract"
    ocr_language: str = "deu"

    # Storage
    storage_backend: str = "local"
    storage_path: str = "/data/documents"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = False
```

### 3.4 Secrets Management

| Empfehlung | Umgebung |
|-----------|----------|
| `.env` File (gitignored) | Lokale Entwicklung |
| GitHub Actions Secrets | CI/CD |
| Docker Secrets / Compose `secrets:` | Docker Swarm / Self-Hosted |
| External Secrets Operator + Vault | Kubernetes / Enterprise |

**Regeln:**
- `.env` ist in `.gitignore` — **niemals committen**
- `.env.example` zeigt die Struktur **ohne echte Werte**
- In Production: ENV-Vars direkt setzen, kein `.env` File im Container
- Secrets rotieren: API Keys, DB-Passwörter periodisch ändern

---

## 4. Monitoring & Observability

### 4.1 Structured Logging

```python
# src/docflow/infrastructure/logging.py
import structlog
import logging
import sys

def setup_logging(log_level: str = "INFO", log_format: str = "json"):
    """Konfiguriert structured logging für die gesamte Applikation."""

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.EventRenamer("msg"),
            renderer,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
    )

    # Auch stdlib logging als JSON (für uvicorn etc.)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )
```

**Log-Ausgabe (JSON, Production):**
```json
{
  "msg": "document_extracted",
  "level": "info",
  "timestamp": "2026-02-11T10:30:00Z",
  "document_id": "abc-123",
  "extractor": "tika",
  "mime_type": "application/pdf",
  "text_length": 42000,
  "confidence": 0.95,
  "duration_ms": 1250,
  "request_id": "req-456"
}
```

### 4.2 Health Endpoints

```python
# Implementiert in: src/docflow/adapters/inbound/api/routes/health.py

# GET /api/v1/health → Aggregierter Status
{
    "status": "healthy",        # healthy | degraded | unhealthy
    "version": "0.1.0",
    "uptime_seconds": 3600,
    "checks": {
        "tika": {"status": "healthy", "latency_ms": 12},
        "redis": {"status": "healthy", "latency_ms": 1},
        "storage": {"status": "healthy", "free_space_gb": 45.2}
    }
}

# GET /api/v1/health/ready → Kubernetes Readiness
# GET /api/v1/health/live  → Kubernetes Liveness
```

**Drei Health-Level:**

| Endpoint | Zweck | Prüft |
|----------|-------|-------|
| `/health/live` | Liveness | App-Prozess läuft |
| `/health/ready` | Readiness | Tika erreichbar, Storage verfügbar |
| `/health` | Full Check | Alle Dependencies + Metriken |

### 4.3 Metriken (Prometheus-kompatibel)

```python
# Empfehlung: prometheus-fastapi-instrumentator

from prometheus_fastapi_instrumentator import Instrumentator

# In app.py:
Instrumentator().instrument(app).expose(app, endpoint="/metrics")
```

**Custom Metriken:**

| Metrik | Typ | Beschreibung |
|--------|-----|-------------|
| `docflow_documents_processed_total` | Counter | Verarbeitete Dokumente |
| `docflow_extraction_duration_seconds` | Histogram | Extraktionsdauer |
| `docflow_extraction_errors_total` | Counter | Fehlgeschlagene Extraktionen |
| `docflow_document_size_bytes` | Histogram | Dokumentgrößen |
| `docflow_ocr_confidence` | Histogram | OCR-Konfidenz |
| `docflow_active_jobs` | Gauge | Aktuell verarbeitete Jobs |

**Prometheus Scrape Config:**
```yaml
# prometheus.yml
scrape_configs:
  - job_name: docflow
    metrics_path: /metrics
    static_configs:
      - targets: ["docflow-api:8000"]
```

### 4.4 Tracing

**Empfehlung: OpenTelemetry (OTEL)**

```python
# Über die Pipeline hinweg:
# Request → Ingestion → Extraction → Processing → Delivery

from opentelemetry import trace

tracer = trace.get_tracer("docflow")

async def process_document(self, document: Document):
    with tracer.start_as_current_span("process_document") as span:
        span.set_attribute("document.id", str(document.id))
        span.set_attribute("document.mime_type", document.metadata.mime_type.value)

        with tracer.start_as_current_span("extraction"):
            result = await self.extractor.extract(document)

        with tracer.start_as_current_span("processing"):
            processed = await self.pipeline.execute(result.raw_text, context)

        with tracer.start_as_current_span("formatting"):
            output = await self.formatter.format(processed)
```

**Phase-1-Empfehlung:** Structured Logging + Prometheus-Metriken.  
**Phase-2:** OpenTelemetry Tracing hinzufügen (Jaeger/Tempo als Backend).

---

## 5. Skalierung

### 5.1 Skalierungsstrategie

```
Phase 1 (MVP):      Single Node, Docker Compose
Phase 2 (Scale):    Horizontal Scaling, Queue-basiert
Phase 3 (K8s):      Kubernetes mit Helm
```

### 5.2 Horizontal Scaling der FastAPI Workers

**Option A: Uvicorn Workers (einfach)**
```bash
# Dockerfile CMD oder ENV
DOCFLOW_WORKERS=4  # 2 * CPU_CORES + 1
uvicorn ... --workers 4
```

**Option B: Docker Compose Replicas (empfohlen ab Phase 2)**
```yaml
# docker-compose.prod.yml
services:
  docflow-api:
    deploy:
      replicas: 3
```
→ Erfordert Reverse Proxy (Traefik/Nginx) für Load Balancing.

### 5.3 Tika als Shared Service

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ docflow-api │    │ docflow-api │    │ docflow-api │
│  (Worker 1) │    │  (Worker 2) │    │  (Worker 3) │
└──────┬──────┘    └──────┬──────┘    └──────┬──────┘
       │                  │                  │
       └──────────┬───────┴──────────────────┘
                  │
           ┌──────▼──────┐
           │    Tika     │  ← Shared, Stateless
           │  (1-2 inst) │
           └─────────────┘
```

- Tika ist **stateless** → ein oder wenige Instanzen reichen
- Bei hoher Last: 2-3 Tika-Instanzen hinter internem LB
- Tika braucht mehr RAM als CPU (1-2 GB empfohlen)

### 5.4 Queue-basierte Verarbeitung

```
                    ┌─────────┐
API Request ──────► │  Redis  │ ──────► Worker 1 ──► Tika
                    │  Queue  │ ──────► Worker 2 ──► Tika
                    └─────────┘ ──────► Worker 3 ──► Tika
```

**Empfehlung:** [ARQ](https://github.com/samuelcolvin/arq) (async Redis Queue für Python)

```python
# Async Job mit ARQ
from arq import create_pool
from arq.connections import RedisSettings

async def process_document_job(ctx, document_id: str, options: dict):
    """Background Job für Dokumentenverarbeitung."""
    service = ctx["document_service"]
    await service.process(document_id, options)

class WorkerSettings:
    functions = [process_document_job]
    redis_settings = RedisSettings.from_dsn("redis://redis:6379")
    max_jobs = 10
    job_timeout = 300  # 5 Minuten
```

### 5.5 Kubernetes-Readiness (Helm Chart Konzept)

```
helm/docflow/
├── Chart.yaml
├── values.yaml
├── templates/
│   ├── deployment.yaml        # FastAPI Deployment
│   ├── service.yaml           # ClusterIP Service
│   ├── ingress.yaml           # Ingress Controller
│   ├── hpa.yaml               # Horizontal Pod Autoscaler
│   ├── configmap.yaml         # docflow.yaml
│   ├── secret.yaml            # API Keys etc.
│   ├── tika-deployment.yaml   # Tika als sidecar oder shared
│   └── _helpers.tpl
└── README.md
```

**Key values.yaml Struktur:**
```yaml
# helm/docflow/values.yaml
replicaCount: 2

image:
  repository: ghcr.io/your-org/docflow
  tag: "latest"
  pullPolicy: IfNotPresent

resources:
  limits:
    cpu: "1"
    memory: 512Mi
  requests:
    cpu: 250m
    memory: 256Mi

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70

tika:
  enabled: true
  replicaCount: 1
  resources:
    limits:
      memory: 2Gi

redis:
  enabled: true  # oder external
  architecture: standalone

ingress:
  enabled: true
  className: nginx
  hosts:
    - host: docflow.example.com
      paths:
        - path: /
          pathType: Prefix

probes:
  liveness:
    path: /api/v1/health/live
    initialDelaySeconds: 10
  readiness:
    path: /api/v1/health/ready
    initialDelaySeconds: 15
```

---

## 6. Empfohlener Evolutionspfad

| Phase | Infrastruktur | Aufwand |
|-------|--------------|---------|
| **Phase 1 – MVP** | Docker Compose, Local Storage, GitHub Actions CI | 1-2 Wochen |
| **Phase 2 – Production** | + Redis Queue, + Prometheus/Grafana, + Trivy Scanning | 2-3 Wochen |
| **Phase 3 – Scale** | + K8s Helm Chart, + HPA, + OpenTelemetry | 3-4 Wochen |
| **Phase 4 – Enterprise** | + Vault Secrets, + GitOps (ArgoCD), + Multi-Region | nach Bedarf |

**Empfehlung: Starte mit Phase 1.** Docker Compose + GitHub Actions deckt 90% der Use Cases ab. Kubernetes erst wenn nötig.

---

## 7. Quick Start

```bash
# 1. Repository klonen
git clone https://github.com/your-org/doc-flow.git
cd doc-flow

# 2. Environment konfigurieren
cp .env.example .env
# → .env anpassen

# 3. Development Stack starten
make dev

# 4. API testen
curl http://localhost:8000/api/v1/health

# 5. Dokument verarbeiten
curl -X POST http://localhost:8000/api/v1/documents/sync \
  -F "file=@test.pdf" \
  -F "output_format=markdown"
```

### Production Deployment

```bash
# 1. Image bauen & pushen (oder CI/CD nutzen)
make build

# 2. Production Stack starten
make prod

# 3. Mit Skalierung
make prod-scale  # 3 API Replicas
```
