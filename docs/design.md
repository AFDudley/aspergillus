# aspergillus — NASA-Grade Python Linter

A Python linter that enforces NASA-grade software engineering practices,
built on Fixit/LibCST. Named after Aspergillus nidulans, the first fungus
NASA intentionally grew on the ISS.

## What It Is

A standalone Python project (`aspergillus`) that provides Fixit lint rules
organized by NASA quality level (from `02-nasa-grade-software-engineering-guide.md`).
Rules live in the package, consumed by any repo as a git subtree. Each level
builds on the previous one.

**Goal**: Level 3 (type safety + explicit error handling), reached incrementally
through Level 2 (pure functions + immutability). Level 1 (static analysis +
code hygiene) is already handled by ruff, mypy, and ansible-lint.

## Rule Set

### Level 2 Rules (Blocking)

| Rule     | Description                                | Detection                                 | Difficulty |
|----------|--------------------------------------------|-------------------------------------------|------------|
| `ASP201` | Function too long (>60 lines)              | Line count                                | Easy       |
| `ASP202` | Missing assertions (<2 per function)       | Assert count per FunctionDef              | Easy       |
| `ASP203` | Global mutable state (`CACHE = {}`)        | Module-level assignment to mutable type   | Easy       |
| `ASP204` | Unbounded loop (`while` without bound)     | Loop AST analysis                         | Medium     |
| `ASP205` | Impure function (calls I/O from blocklist) | Call name matching against blocklist       | Medium     |
| `ASP206` | Mixed I/O and logic (FC/IS violation)      | I/O call + statement count heuristic      | Medium     |

### Level 3 Rules (Warning)

| Rule     | Description                                | Detection                                 | Difficulty |
|----------|--------------------------------------------|-------------------------------------------|------------|
| `ASP301` | Raise where Result type could be used      | Raise + return path analysis              | Medium     |
| `ASP302` | Optional/None return type                  | Return annotation check                   | Easy       |

Bare except, missing annotations, and broad exception catches are already
covered by ruff and mypy. No duplication.

### Level 1 (External Tools — Not Aspergillus)

Level 1 is static analysis and code hygiene, handled entirely by existing
tools in the pre-commit pipeline:

| Tool | What it covers |
|------|----------------|
| ruff | General linting, import sorting, pyflakes, pycodestyle |
| black / ruff-format | Code formatting |
| mypy / pyright | Type checking |
| bandit | Security linting |
| pre-commit hooks | Trailing whitespace, YAML/JSON validation, merge conflicts |

Aspergillus does not duplicate these. Level 1 is a prerequisite — repos
must have these tools configured before aspergillus rules are meaningful.

Reference configs for Level 1 are provided in `src/aspergillus/configs/`:
- `level1-pyproject.toml` — ruff, mypy, bandit, pytest settings
- `level1-pre-commit-config.yaml` — pre-commit hooks for all Level 1 tools

Copy the relevant sections into your project to establish Level 1 baseline.

### Level 4 Rules (Planned — Not Implemented)

Design by contract, property-based testing, and mutation testing.

| Rule     | Description                                | Detection                                 | Difficulty |
|----------|--------------------------------------------|-------------------------------------------|------------|
| `ASP401` | Missing precondition assertions            | Function params not validated via assert  | Medium     |
| `ASP402` | Missing postcondition assertions           | Return value not validated before return  | Medium     |
| `ASP403` | Missing class invariant check              | Class with mutable state, no invariant method called after mutation | Hard |
| `ASP404` | No property-based tests for pure function  | Pure function (no ASP205) without corresponding hypothesis test | Hard |

Level 4 enforcement requires cross-file analysis (matching functions to
their tests), which is beyond single-file Fixit rules. Implementation
options:
- Custom Fixit rules that scan test files for hypothesis decorators
- Separate CLI pass that correlates source and test modules
- Integration with pytest plugin for mutation score reporting

Reference: NASA guide section "Level 4: Contracts + Targeted Unit Tests"
(`exophial/docs/REFERENCE/02-nasa-grade-software-engineering-guide.md`)

### Level 5 Rules (Planned — Not Implemented)

Formal verification via bounded model checking. Apply selectively to
safety-critical or financial logic only.

| Rule     | Description                                | Detection                                 | Difficulty |
|----------|--------------------------------------------|-------------------------------------------|------------|
| `ASP501` | Unverified financial calculation           | Arithmetic on monetary types without Z3 proof | Very Hard |
| `ASP502` | Unverified state machine transition        | State enum transitions without model check | Very Hard |
| `ASP503` | Unverified invariant preservation          | Class invariant not formally proven across all methods | Very Hard |

Level 5 is not a linter in the traditional sense. It requires:
- Z3 or similar SMT solver integration
- Manual annotation of proof obligations
- Selective application (5-15x cost, only for critical paths)

Candidates for Level 5 in our codebase:
- Bonding curve calculations (sniper)
- Staking/delegation arithmetic
- Firewall rule generation (correctness proof that rules don't conflict)

Reference: NASA guide section "Level 5: Formal Verification"
(`exophial/docs/REFERENCE/02-nasa-grade-software-engineering-guide.md`)

## Enforcement Model

- **Level 2 rules block** — pre-commit fails on violations
- **Level 3 rules warn** — reported but don't block commits
- Controlled via `--level` flag: `--level 2` blocks on Level 2 only,
  `--level 3` blocks on both
- Per-rule suppression via `# noqa: ASP2XX` comments

## I/O Blocklist

The purity (ASP205) and FC/IS (ASP206) rules need to know which functions
do I/O. This is a curated set, not a complete analysis:

```python
IO_FUNCTIONS = {
    # builtins
    "print", "input", "open",
    # subprocess
    "subprocess.run", "subprocess.call", "subprocess.Popen",
    # urllib
    "urllib.request.urlopen", "urllib.request.build_opener",
    # os
    "os.system", "os.popen", "os.remove", "os.mkdir", "os.makedirs",
    # logging
    "logging.info", "logging.warning", "logging.error", "logging.debug",
    "log.info", "log.warning", "log.error", "log.debug",
    # socket/network
    "socket.socket", "socket.connect",
    # file system
    "shutil.copy", "shutil.move", "shutil.rmtree",
    "pathlib.Path.write_text", "pathlib.Path.read_text",
    "pathlib.Path.unlink", "pathlib.Path.mkdir",
}
```

Extensible per-repo via `pyproject.toml`:

```toml
[tool.aspergillus]
extra_io_functions = ["requests.get", "httpx.post"]
```

## Package Structure

```
aspergillus/
├── pyproject.toml              # fixit, libcst deps, CLI entry point
├── src/
│   └── aspergillus/
│       ├── __init__.py
│       ├── rules/
│       │   ├── __init__.py
│       │   ├── level2.py       # ASP201-206
│       │   └── level3.py       # ASP301-302
│       └── io_blocklist.py     # Known impure functions
├── tests/
│   ├── test_level2.py
│   └── test_level3.py
├── .pre-commit-config.yaml     # Self-linting (ruff, mypy, ruff-format)
└── .pre-commit-hooks.yaml      # Hook definition (unused — subtree model)
```

## Integration (Subtree)

Consumers pull aspergillus as a git subtree and use a `repo: local`
pre-commit hook:

```yaml
- repo: local
  hooks:
    - id: aspergillus
      name: aspergillus
      entry: uv run python -m aspergillus --level 2
      language: system
      types: [python]
```

The consumer's `pyproject.toml` adds `fixit` and `libcst` to dependencies,
or invokes aspergillus from its own venv.

## What It Does NOT Do

- No type checking (mypy handles that)
- No formatting (ruff-format handles that)
- No general linting (ruff handles that)
- No auto-fix in v0.1 — report only. Auto-fix is a future goal enabled
  by LibCST's concrete syntax tree preservation.

## Project Setup

- **Location**: `~/code/git_puller/repos/aspergillus`
- **No upstream** — local git repo for now
- **Own pebbles DB** — standalone issue tracking
- **Own pyproject.toml** — deps: `fixit`, `libcst`, `ruff`, `mypy`, `pre-commit`
- **Python 3.10+**
- **Pre-commit on itself** — ruff, mypy, ruff-format

## Implementation Order

1. Scaffold repo, pyproject.toml, pebbles init
2. `ASP201` (function length) + `ASP202` (assertions) — easy wins, prove
   the Fixit integration works
3. `ASP203` (global mutable state) + `ASP204` (unbounded loops)
4. I/O blocklist + `ASP205` (impurity) + `ASP206` (FC/IS violation)
5. `ASP301` (raise vs Result) + `ASP302` (Optional return)
6. Add as subtree to biscayne-agave-runbook, wire into pre-commit, run
   against `snapshot_download.py`

## Research Source

Based on research by Michelangelo (maniple worker, 2026-03-10):
- Ruff has no custom rule support and no timeline
- Fixit (Meta/Instagram) is the best fit: local rules, auto-fix capable,
  LibCST-based, built-in test framework, pre-commit integration
- No existing NASA Power of 10 Python linter — greenfield
- NASA guide: `exophial/docs/REFERENCE/02-nasa-grade-software-engineering-guide.md`
