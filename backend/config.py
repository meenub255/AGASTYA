from pathlib import Path
import os
from datetime import datetime

DEFAULT_YEAR = datetime.now().year


BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
TEMPLATES_DIR = FRONTEND_DIR / "templates"
STATIC_DIR = FRONTEND_DIR / "static"
SQL_DIR = BASE_DIR / "sql"

# Database Configuration
# Set these environment variables or use the defaults for local development
DB_USER = os.getenv("PRAMANA_DB_USER", "postgres")
DB_PASSWORD = os.getenv("PRAMANA_DB_PASSWORD", "1234")
DB_HOST = os.getenv("PRAMANA_DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("PRAMANA_DB_PORT", "5432")
DB_SSL_MODE = os.getenv("PRAMANA_DB_SSL_MODE", "disable")

ADMIN_DB_NAME = os.getenv("PRAMANA_ADMIN_DB_NAME", "Pramana")
SOURCE_DB_NAME = os.getenv("PRAMANA_SOURCE_DB_NAME", "Pramana")
DATAMART_DB_NAME = os.getenv("PRAMANA_DATAMART_DB_NAME", "Pramana")


# Default schema names
SOURCE_SCHEMA_NAME = "source"
DATAMART_SCHEMA_NAME = "dw"

# Data Ops config
DATA_OPS_SCHEMA_NAME = os.getenv("PRAMANA_DATA_OPS_SCHEMA", "source")
DATA_OPS_FILES_DIR = BASE_DIR / "sql"
DATA_OPS_MAX_FILE_SIZE = int(os.getenv("PRAMANA_DATA_OPS_MAX_FILE_SIZE", "10485760"))

# If source and datamart are in the same DB, don't use FDW alias, use real schema name
default_fdw_schema = SOURCE_SCHEMA_NAME if SOURCE_DB_NAME == DATAMART_DB_NAME else "source_fdw"
FDW_SOURCE_SCHEMA = os.getenv("PRAMANA_FDW_SOURCE_SCHEMA", default_fdw_schema)

MANAGED_SOURCE_TABLES = (
    "mst_donor",
    "mst_program",
    "mst_school",
    "mst_instructor",
    "mst_activity_type",
    "mst_shift",
    "conf_program_school_mapping",
    "txn_session",
    "txn_feedback_answer",
    "txn_feedback_exposure",
    "mst_adhoc_session_feedback_answers",
)
