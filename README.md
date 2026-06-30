# Agastya Analytics Dashboard

A Data Warehouse Analytics Dashboard built on PostgreSQL star schema using FastAPI, AdminLTE 3, and Chart.js.

## Prerequisites

- **Python 3.10+**
- **PostgreSQL 14+** (running locally or accessible remotely)
- **pip** (Python package manager)

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/meenub255/AGASTYA.git
cd AGASTYA
```

### 2. Create a Virtual Environment

```bash
python -m venv venv
```

Activate it:

- **Windows:**
  ```bash
  venv\Scripts\activate
  ```
- **Mac/Linux:**
  ```bash
  source venv/bin/activate
  ```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Set Up the Database

#### a) Create the PostgreSQL Database

Open `psql` or pgAdmin and run:

```sql
CREATE DATABASE pramana;
```

#### b) Run the Source Schema (creates raw source tables)

Connect to the `pramana` database and run the v5 source schema:

```bash
psql -U postgres -d pramana -f sql/source_schema_change_v5.sql
```

#### c) Run the Data Warehouse Schema (creates star schema in `dw` schema)

```bash
psql -U postgres -d pramana -f sql/dw_schema_change_v5.sql
```

#### d) Load Data via the Web UI

1. Start the app (step 5 below)
2. Navigate to the **Upload** page
3. Upload your Excel files (.xlsx) for each source table
4. The app will auto-map columns and import data

Alternatively, if you have raw data loaded into the source tables, run the ELT pipeline:

```bash
psql -U postgres -d pramana -f sql/elt_dim.sql
psql -U postgres -d pramana -f sql/elt_fact.sql
psql -U postgres -d pramana -f sql/elt_agg.sql
```

### 5. Start the Application

```bash
uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
```

### 6. Open in Browser

```
http://127.0.0.1:8000
```

## Configuration

All database settings are configurable via environment variables. If your PostgreSQL setup differs from the defaults, set these before starting the app:

| Variable | Default | Description |
|----------|---------|-------------|
| `PRAMANA_DB_USER` | `postgres` | PostgreSQL username |
| `PRAMANA_DB_PASSWORD` | `postgres` | PostgreSQL password |
| `PRAMANA_DB_HOST` | `127.0.0.1` | PostgreSQL host |
| `PRAMANA_DB_PORT` | `5432` | PostgreSQL port |
| `PRAMANA_DB_SSL_MODE` | `disable` | SSL mode (`disable` / `require`) |
| `PRAMANA_ADMIN_DB_NAME` | `pramana` | Database name |
| `PRAMANA_SOURCE_DB_NAME` | `pramana` | Source schema database |
| `PRAMANA_DATAMART_DB_NAME` | `pramana` | Data warehouse database |

Example (Windows):

```bash
set PRAMANA_DB_PASSWORD=mypassword
uvicorn backend.app:app --reload
```

Example (Mac/Linux):

```bash
export PRAMANA_DB_PASSWORD=mypassword
uvicorn backend.app:app --reload
```

## SQL Files Reference

| File | Purpose |
|------|---------|
| `sql/source_schema_change_v5.sql` | Source schema DDL (raw data tables) |
| `sql/dw_schema_change_v5.sql` | Data warehouse star schema (dimensions + facts) |
| `sql/elt_dim.sql` | Dimension loading (SCD Type 1) |
| `sql/elt_fact.sql` | Fact table loading |
| `sql/elt_agg.sql` | Precomputed aggregations |
| `sql/elt_run.sql` | Master orchestration script (runs all ELT steps) |

## Project Structure

```
AGASTYA/
├── backend/
│   ├── app.py                  # FastAPI main application
│   ├── config.py               # Database & path configuration
│   ├── db.py                   # PostgreSQL connection manager
│   ├── upload.py               # Excel upload & import handler
│   ├── elt_runner.py           # ELT script execution
│   ├── reset_databases.py      # Database reset utility
│   ├── models/                 # Pydantic response models
│   ├── routers/                # API route handlers (25 routers)
│   └── services/               # SQL query logic (27 services)
├── frontend/
│   ├── static/
│   │   ├── css/app.css         # Custom dashboard styles
│   │   ├── js/dashboard.js     # Charts, DataTables, filters
│   │   └── images/             # Agastya branding assets
│   └── templates/              # Jinja2 HTML templates (32 pages)
│       └── partials/           # Reusable template components
├── sql/                        # Database schema & ELT scripts
├── requirements.txt            # Python dependencies
└── README.md
```

## Tech Stack

- **Backend:** FastAPI, psycopg2, Pydantic
- **Frontend:** AdminLTE 3, Bootstrap 4, Chart.js, jQuery DataTables, Select2
- **Database:** PostgreSQL (star schema / Kimball methodology)
- **Export:** openpyxl (Excel streaming)

## License

Internal project - not for redistribution.
