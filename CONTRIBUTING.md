# Contributing to Gammondator

Thanks for contributing.

## Prerequisites

- Python 3.11+
- `venv`

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Run the app:

```bash
uvicorn app.main:app --reload
```

Open:

- `http://127.0.0.1:8000`

## Tests

```bash
python -m pytest -q
```

## Lint / Style

We use Ruff (modern combined linter for PEP 8 / pyflakes-style checks and imports).

```bash
python -m ruff check .
```

Auto-fix safe issues:

```bash
python -m ruff check . --fix
```

## Coding Standards

- Keep changes focused and minimal.
- Add tests for behavior changes and bug fixes.
- Keep API behavior backward compatible unless explicitly changing contract.
- Prefer clear naming and small functions over clever code.

## Pull Requests

- Include a short description of what changed and why.
- Include test evidence (`pytest` output).
- If UI behavior changed, include screenshot(s).

## Branching

Recommended branch prefix:

- `codex/<topic>`
