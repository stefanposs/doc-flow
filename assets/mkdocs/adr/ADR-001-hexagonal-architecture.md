# ADR-001: Hexagonale Architektur (Ports & Adapters) für DocFlow

## Status

**Accepted** – 2026-02-11

## Context

DocFlow ist eine Enterprise-Plattform zur Dokumenten-Extraktion, die folgende zentrale Herausforderungen adressieren muss:

1. **Technologie-Austauschbarkeit:** Verschiedene Kunden setzen unterschiedliche Technologie-Stacks ein (AWS Textract vs. Apache Tika, Google Vision vs. Tesseract, verschiedene LLMs). Die Architektur muss den Wechsel einer Technologie ermöglichen, ohne die Geschäftslogik zu verändern.

2. **Testbarkeit:** Die Kernlogik (Routing, Pipeline-Orchestrierung, Validierung) muss ohne externe Abhängigkeiten (Tika-Server, Tesseract-Binary, Cloud-APIs) testbar sein.

3. **Enterprise-Konfigurierbarkeit:** Unternehmen müssen per Konfiguration entscheiden können, welche Adapter aktiv sind, ohne Code zu ändern.

4. **Open-Source + Enterprise Dualität:** Das Open-Source-Projekt liefert Standard-Adapter (Tika, Tesseract). Enterprise-Kunden können eigene Adapter als Plugins einbringen.

5. **Inkrementelle Erweiterbarkeit:** Neue Extraktoren, OCR-Engines, Post-Processoren und Output-Formate müssen ohne Änderung bestehenden Codes hinzugefügt werden können (Open/Closed Principle).

## Decision

Wir verwenden die **Hexagonale Architektur (Ports & Adapters)** nach Alistair Cockburn als primäres Architekturmuster für DocFlow.

### Kernelemente der Entscheidung

#### 1. Ports als Python ABCs (Abstract Base Classes)

Jede externe Technologie wird durch ein Port-Interface abstrahiert:

```python
# Domain definiert den Port
class ExtractorPort(ABC):
    @abstractmethod
    async def extract(self, document: Document) -> ExtractionResult: ...

# Infrastruktur implementiert den Adapter
class TikaExtractorAdapter(ExtractorPort):
    async def extract(self, document: Document) -> ExtractionResult: ...
```

#### 2. Dependency Injection via Factory/Registry

Adapter werden zur Laufzeit über ein Registry-Pattern aufgelöst:

```python
class AdapterRegistry:
    def get_extractor(self, name: str) -> ExtractorPort: ...
    def get_ocr_engine(self, name: str) -> OCRPort: ...
    def get_processor(self, name: str) -> PostProcessorPort: ...
    def get_formatter(self, name: str) -> OutputFormatterPort: ...
```

Die Registry liest die Konfiguration (`docflow.yaml`) und instanziiert die passenden Adapter.

#### 3. Vier Outbound Ports

| Port | Verantwortung | Standard-Adapter |
|------|--------------|-----------------|
| `ExtractorPort` | Text-Extraktion aus Dokumenten | TikaExtractorAdapter |
| `OCRPort` | Optical Character Recognition | TesseractOCRAdapter |
| `PostProcessorPort` | Text-Nachbearbeitung | CleanupProcessor, StructureProcessor |
| `OutputFormatterPort` | Ergebnis-Formatierung | MarkdownFormatter |

Zusätzliche Infrastruktur-Ports:
| Port | Verantwortung | Standard-Adapter |
|------|--------------|-----------------|
| `StoragePort` | Dokumenten-Speicherung | LocalFileStorage |
| `EventBusPort` | Domain-Event-Verteilung | InMemoryEventBus |

#### 4. Inbound Ports (Application Services)

Die Application Services sind die einzigen Einstiegspunkte in die Domain:

```python
class DocumentService:
    """Inbound Port – wird von Driving Adapters aufgerufen."""
    def __init__(self, extractor: ExtractorPort, ocr: OCRPort, ...): ...
    async def process_document(self, file: UploadFile, options: ProcessingOptions) -> Result: ...
```

#### 5. Driving Adapters (Inbound)

| Adapter | Technologie | Use Case |
|---------|------------|----------|
| `FastAPIAdapter` | FastAPI | REST API |
| `CLIAdapter` | Click/Typer | Kommandozeile |
| `FileWatcherAdapter` | Watchdog | Batch-Verarbeitung |

## Consequences

### Positive

- **Technologie-Freiheit:** Jeder Adapter kann unabhängig ausgetauscht werden. Ein Wechsel von Tika zu AWS Textract erfordert nur einen neuen Adapter + Konfigurationsänderung.
- **Hervorragende Testbarkeit:** Die gesamte Domain-Logik kann mit In-Memory-Adaptern getestet werden. Keine Docker-Container, keine Cloud-APIs in Unit-Tests nötig.
- **Plugin-Ökosystem:** Dritte können eigene Adapter entwickeln und per Konfiguration einbinden – ideal für Enterprise-Kunden.
- **Klare Abhängigkeitsrichtung:** Domain → Ports ← Adapter. Die Domain hat null externe Abhängigkeiten.
- **Parallele Entwicklung:** Teams können unabhängig an Adaptern arbeiten, solange sie das Port-Interface einhalten.
- **Konfigurationsgetrieben:** Adapter-Auswahl zur Laufzeit über YAML/ENV, kein Code-Deploy nötig für Technologiewechsel.

### Negative

- **Initiale Komplexität:** Mehr Boilerplate und Abstraktion als ein monolithisches Design. Für ein MVP wirkt die Struktur zunächst overengineered.
- **Indirektion:** Debug-Pfade sind länger, da Aufrufe durch Port-Interfaces laufen. Stack Traces sind weniger direkt.
- **Lernkurve:** Neue Entwickler müssen das Hexagonale Muster verstehen, bevor sie produktiv beitragen können.
- **Performance-Overhead:** Die Indirektion durch Interfaces hat einen minimalen Overhead (vernachlässigbar gegenüber I/O-Kosten von Extraktion/OCR).

### Risks

- **Over-Abstraction:** Gefahr, zu viele Ports zu definieren. Mitigation: Nur Ports für tatsächlich austauschbare Technologien erstellen.
- **Leaky Abstractions:** Adapter-spezifische Konzepte könnten in Port-Interfaces einsickern. Mitigation: Regelmäßige Reviews der Port-Interfaces.
- **Configuration Complexity:** Zu viele Konfigurationsoptionen können verwirrend sein. Mitigation: Sinnvolle Defaults, Validierung beim Start.

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **Layered Architecture (Classic)** | Einfach, bekannt, weniger Boilerplate | Schlechte Austauschbarkeit, Domain hängt von Infrastruktur ab, schwer testbar ohne Mocks |
| **Clean Architecture (Uncle Bob)** | Ähnliche Vorteile wie Hexagonal, gut dokumentiert | Mehr Schichten (Use Cases, Presenters), für unser Use Case überdimensioniert |
| **Microservices** | Maximale Unabhängigkeit, separate Skalierung | Viel zu komplex für Phase 1, Netzwerk-Overhead, Operational Complexity |
| **Simple Modular Monolith** | Schnell implementierbar, einfach zu deployen | Austauschbarkeit nur durch Refactoring, keine klare Dependency Rule |
| **Strategy Pattern only** | Minimale Abstraktion, schnell umgesetzt | Keine klare Architekturgrenze, wird bei Wachstum zum Big Ball of Mud |

### Warum nicht Clean Architecture?

Clean Architecture und Hexagonal Architecture sind eng verwandt. Wir bevorzugen Hexagonal, weil:
1. Die Port/Adapter-Terminologie besser zu unserem Plugin-Konzept passt
2. Weniger Schichten → weniger Boilerplate in Python
3. Die Unterscheidung in Driving/Driven Adapters ist für unser Szenario (API rein, Technologien raus) intuitiver

### Warum nicht Microservices?

Microservices wären für Phase 1 massives Over-Engineering. Die Hexagonale Architektur ermöglicht aber einen späteren Split: Jeder Bounded Context kann bei Bedarf zu einem eigenen Service werden, da die Kommunikation bereits über Ports abstrahiert ist.

## References

- Cockburn, A. – "Hexagonal Architecture" (2005)
- Vernon, V. – "Implementing Domain-Driven Design" (2013)
- Hombergs, T. – "Get Your Hands Dirty on Clean Architecture" (2019)
- Python ABC Documentation – https://docs.python.org/3/library/abc.html
