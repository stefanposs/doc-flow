# ADR-002: Docker-First Deployment-Strategie

## Status

**Accepted** – 2026-02-11

## Context

DocFlow muss für Enterprise-Kunden einfach deploybar sein. Verschiedene Deployment-Szenarien:

1. **Entwickler** wollen mit einem Befehl die gesamte Plattform lokal starten
2. **Kleine Teams** deployen auf einem einzelnen Server (VM/Bare Metal)
3. **Enterprise** braucht Kubernetes-Kompatibilität und horizontale Skalierung
4. **CI/CD** muss reproduzierbar bauen und testen

## Decision

Wir verfolgen eine **Docker-First-Strategie** mit folgenden Kernelementen:

### 1. Multi-Stage Dockerfile
- Stage 1 (Builder): Dependency-Installation mit `uv`
- Stage 2 (Runtime): Minimales Image mit nur Runtime-Dependencies
- Non-root User, Health Checks, optimierte Layer-Reihenfolge

### 2. Docker Compose als primäres Deployment-Tool
- `docker-compose.yml` als Basis-Stack (API + Tika + Redis)
- `docker-compose.dev.yml` Override für Entwicklung (Hot-Reload)
- `docker-compose.prod.yml` Override für Production (Replicas, Log-Limits)
- Compose Profiles für optionale Services (MinIO)

### 3. GitHub Container Registry (GHCR)
- Images werden automatisch via GitHub Actions gebaut und gepusht
- Semantic Versioning Tags (`v1.2.3` → `1.2.3`, `1.2`, `1`, `latest`)
- Multi-Arch Support (amd64 + arm64)
- Kein externes Registry-Konto nötig

### 4. Kubernetes-Ready (aber nicht Kubernetes-First)
- Health Endpoints (`/live`, `/ready`, `/health`) folgen K8s-Konventionen
- Stateless Application Design
- Konfiguration über Environment Variables (12-Factor)
- Helm Chart als Phase-3-Erweiterung

## Consequences

### Positive
- **Einfacher Einstieg:** `docker compose up` startet alles
- **Reproduzierbar:** Gleiche Images in Dev, CI, Staging, Production
- **Skalierbar:** Von Single Node (Compose) zu Multi Node (K8s) ohne App-Änderung
- **Sicher:** Non-root, minimales Base Image, Security Scanning in CI

### Negative
- Docker-Dependency: Alle Entwickler brauchen Docker Desktop / Podman
- Image-Größe: ~250 MB durch Tesseract OCR-Abhängigkeiten
- Lokale Entwicklung ohne Docker erfordert manuelle Tika/Redis-Installation

### Risiken
- Tika-Image ist ~500 MB und hat langsamen Cold Start (~30s)
  - Mitigation: `start_period` im Health Check, Tika vorwärmen
- Redis als Single Point of Failure bei Queue-basierter Verarbeitung
  - Mitigation: Redis ist optional (Fallback auf In-Memory), Sentinel für HA

## Alternatives Considered

| Alternative | Abgelehnt weil |
|------------|---------------|
| Kubernetes-First | Zu komplex für MVP und kleine Teams |
| Serverless (Lambda) | Tika benötigt persistenten Prozess, Cold Starts zu lang |
| Bare Metal / systemd | Nicht reproduzierbar, schwer skalierbar |
| Podman Compose | Geringere Verbreitung, Docker-kompatibel wenn nötig |
