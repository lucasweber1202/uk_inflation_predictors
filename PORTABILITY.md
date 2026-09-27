# Standalone portability

Verified 2026-09-16. The research layer imports no collector and never searches
for sibling repositories. Code/tests operate from this clone alone; real
research receives data through explicit CSV arguments or an explicitly created
SQLAlchemy engine.

```powershell
git clone https://github.com/lucasweber1202/uk_inflation_predictors.git
Set-Location uk_inflation_predictors
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest -q
ruff check .
mypy scripts tests
python -m scripts.experiments --help
```

Python 3.11/3.12. CSV-backed execution has no required environment variables,
database or network. A database is optional and supplied explicitly by the
caller. Experiment outputs write only to the `--output` path.

Certification: standalone code PASS; standalone tests PASS; sibling required
NO; database/network required for CSV experiments NO; real data input YES.
