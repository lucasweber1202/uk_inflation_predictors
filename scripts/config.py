"""Runtime settings loaded from environment variables and an optional .env."""

from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
_ENV_FILE = ROOT_DIR / ".env"

if _ENV_FILE.exists():
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if value and key not in os.environ:
            os.environ[key] = value

SCHEMA_NAME = "uk_inflation_predictors"
CATALOG_NAME = "macrobond_inhouse"
METADATA_TABLE = "metadata"
TIME_SERIES_TABLE = "time_series"
AVAILABILITY_TABLE = "availability"
SNAPSHOTS_TABLE = "source_snapshots"
LOGS_TABLE = "logs"

# Every predictor in this repository describes the United Kingdom economy. The
# fleet `country` vocabulary is ISO 4217 currency, not ISO 3166.
COUNTRY_CURRENCY = "GBP"

PROD = os.getenv("PROD", "false").lower() in ("1", "true", "yes")
DATABASE_URL = os.getenv("PREDICTORS_DB_URL", "")

# Raw downloads are kept on local disk so a stored SHA256 can be re-checked by
# hand. The directory is gitignored; nothing here assumes a cloud object store.
RAW_DIR = Path(os.getenv("PREDICTORS_RAW_DIR", str(ROOT_DIR / "_raw")))
if not RAW_DIR.is_absolute():
    RAW_DIR = ROOT_DIR / RAW_DIR

REQUEST_TIMEOUT = float(os.getenv("PREDICTORS_HTTP_TIMEOUT", "60"))
DOWNLOAD_DELAY = float(os.getenv("PREDICTORS_DOWNLOAD_DELAY", "1"))
MAX_RETRIES = int(os.getenv("PREDICTORS_MAX_RETRIES", "3"))
BACKOFF_FACTOR = float(os.getenv("PREDICTORS_BACKOFF_FACTOR", "2"))
RATE_LIMIT_BACKOFF = float(os.getenv("PREDICTORS_RATE_LIMIT_BACKOFF", "20"))
MAX_RETRY_DELAY = float(os.getenv("PREDICTORS_MAX_RETRY_DELAY", "120"))
# The largest published artifact across both v0.1 sources is under a megabyte;
# this ceiling is generous for them and still bounds memory.
MAX_DOWNLOAD_BYTES = int(os.getenv("PREDICTORS_MAX_DOWNLOAD_BYTES", str(128 * 1024 * 1024)))
USER_AGENT = os.getenv(
    "PREDICTORS_USER_AGENT",
    "uk_inflation_predictors/0.1 (+https://github.com/lucasweber1202/uk_inflation_predictors)",
)
LOG_LEVEL = os.getenv("PREDICTORS_LOG_LEVEL", "INFO")

DBX_SERVER_HOSTNAME = os.getenv("DBX_SERVER_HOSTNAME", "")
DBX_HTTP_PATH = os.getenv("DBX_HTTP_PATH", "")
AKV_VAULT_URL = os.getenv("AKV_VAULT_URL", "")
AKV_SECRET_NAME = os.getenv("AKV_SECRET_NAME", "databricks-token")


def missing_environment(prod: bool = PROD) -> list[str]:
    """Return every required environment variable that is unset, not just the first."""
    if not prod:
        return [] if DATABASE_URL else ["PREDICTORS_DB_URL"]
    required = {"DBX_SERVER_HOSTNAME": DBX_SERVER_HOSTNAME, "DBX_HTTP_PATH": DBX_HTTP_PATH}
    return sorted(name for name, value in required.items() if not value)


def unresolved_credentials(prod: bool = PROD) -> list[str]:
    """Return credential sources that are unset but may still resolve at runtime."""
    if prod and not os.getenv("DATABRICKS_TOKEN") and not AKV_VAULT_URL:
        return ["DATABRICKS_TOKEN", "AKV_VAULT_URL"]
    return []
