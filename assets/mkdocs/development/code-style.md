# Code Style

## Python

### Formatter & Linter: Ruff

[Ruff](https://docs.astral.sh/ruff/) handles both formatting and linting:

```toml
[tool.ruff]
target-version = "py312"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "S", "B", ...]
```

### Type Checking: mypy

```toml
[tool.mypy]
python_version = "3.12"
strict = true
```

### Commands

```bash
just lint        # ruff check
just format      # ruff format
just fix         # format + lint-fix
just typecheck   # mypy
```

---

## Conventions

### Python

- **Imports**: Sorted by `isort` (via Ruff). First-party: `docflow`
- **Docstrings**: Google style
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes
- **Type hints**: Required on all public functions (mypy strict)
- **Async**: Use `async def` for all I/O-bound operations

### Commits

Follow [Conventional Commits](https://www.conventionalcommits.org/) — see [Contributing](contributing.md).

---

## Pre-Commit Checks

Run before every commit:

```bash
just check      # lint + typecheck
```
