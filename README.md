# aspergillus

NASA-grade Python linter built on [Fixit](https://fixit.readthedocs.io/)/[LibCST](https://libcst.readthedocs.io/).

Named after *Aspergillus nidulans*, the first fungus NASA intentionally
grew on the International Space Station.

## What it does

Enforces structural code quality rules derived from NASA's Power of 10,
adapted for Python. Complements ruff (general linting), mypy (type
checking), and ruff-format (formatting) — no overlap.

## Rules

### Level 2 — Blocking

| Rule | Description |
|------|-------------|
| `ASP201` | Function too long (>60 lines) |
| `ASP202` | Low assertion density (<2 per function) |
| `ASP203` | Global mutable state |
| `ASP204` | Unbounded loop (while without provable bound) |
| `ASP205` | Impure function (calls I/O from blocklist) |
| `ASP206` | Mixed I/O and logic (functional core / imperative shell violation) |

### Level 3 — Warning

| Rule | Description |
|------|-------------|
| `ASP301` | Raise where Result type could be used |
| `ASP302` | Optional/None return type |

## Installation

```bash
uv pip install .
```

Or as a development dependency in another project:

```bash
uv add --dev aspergillus@{path/to/aspergillus}
```

## Usage

### With fixit directly

```bash
# Run all aspergillus rules
fixit lint src/

# Fixit discovers rules via [tool.fixit] in pyproject.toml
```

### As a pre-commit hook (recommended)

Add aspergillus as a git subtree in the consuming repo, then add a
local hook:

```yaml
# .pre-commit-config.yaml
- repo: local
  hooks:
    - id: aspergillus
      name: aspergillus
      entry: uv run python -m fixit lint
      language: system
      types: [python]
```

The consuming repo's `pyproject.toml` needs:

```toml
[tool.fixit]
enable = ["aspergillus.rules"]
```

## I/O Blocklist

ASP205 and ASP206 use a curated blocklist of ~40 known I/O functions
(builtins, subprocess, os, logging, socket, shutil, pathlib). Extend
per-repo:

```toml
[tool.aspergillus]
extra_io_functions = ["requests.get", "httpx.post"]
```

## Suppression

Suppress individual violations inline:

```python
CACHE: dict[str, str] = {}  # noqa: ASP203
```

## Development

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Run pre-commit (ruff + mypy + formatting)
uv run pre-commit run --all-files
```

## Design

See [docs/design.md](docs/design.md) for architecture decisions,
enforcement model, and rule rationale.
