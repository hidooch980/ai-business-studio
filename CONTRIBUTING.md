# Contributing

## Development setup

Requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
uvicorn backend.app.main:app --reload
```

On Windows PowerShell, activate with .venv\\Scripts\\Activate.ps1.

## Quality checks

```bash
ruff check .
pytest
```

## Engineering rules

- Keep domain logic inside its owning module; avoid cross-module database shortcuts.
- Add tests for bug fixes and new behavior.
- Use decimal arithmetic for money; do not use binary floating point for financial amounts.
- Use immutable ledger entries and compensating reversals for financial or inventory corrections.
- Make event handlers idempotent and persist outbox events in the same transaction as business changes.
- Do not introduce network dependencies into core offline POS flows.
- Do not add secrets, personal data, real transaction data, or production artifacts.
- Document migrations, API changes, and operational risks.
- Mark incomplete integrations as unavailable or sandbox-only; never imply live connectivity without verified tests.
