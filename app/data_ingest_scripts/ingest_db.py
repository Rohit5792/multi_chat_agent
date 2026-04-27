"""
Reads the first Excel file found in data/, creates the employees and
employee_snapshots tables if they don't exist, and upserts all rows.

The Excel file has one sheet per employee. Each sheet contains one or more
monthly snapshot blocks in a key-value pair layout (key | value | key | value |
key | value across 6 columns). A new block begins wherever column A contains
'Id'. Blocks are ordered newest-first; all are ingested regardless of order.

Run via: uv run ingest
"""
import glob
import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import DB_URL
from app.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Excel label → schema column name  (keys are lowercased for matching)
# ---------------------------------------------------------------------------
_KEY_MAP: dict[str, str] = {
    "id":                                                      "id",
    "name":                                                    "name",
    "contact":                                                 "contact",
    "as on (date)":                                            "as_on_date",
    "last updated on (date)":                                  "last_updated_on",
    "deployed to":                                             "deployed_to",
    "neuleap connect lead":                                    "neuleap_connect_lead",
    "company connect lead":                                    "company_connect_lead",
    "project":                                                 "project_name",
    "project start (date)":                                    "project_start_date",
    "project end (date)":                                      "project_end_date",
    "project tech stack":                                      "project_tech_stack",
    "project overview":                                        "project_overview",
    "nps":                                                     "nps",
    "how was neulearn capstones helpful?":                     "neulearn_capstones_helpful",
    "skill in hand":                                           "skill_in_hand",
    "skills acquired from project / potential / not in capstone?": "skills_acquired",
    "skills to develop / future safe":                         "skills_to_develop",
    "potential new opportunities":                             "potential_new_opportunities",
    "plan of action":                                          "plan_of_action",
    "blockers if any / potential escalation - runway?":        "blockers",
    "any other feedback":                                      "any_other_feedback",
}

_DATE_COLS: frozenset[str] = frozenset({
    "as_on_date", "last_updated_on", "project_start_date", "project_end_date",
})

_SNAPSHOT_COLS: list[str] = [
    "employee_id", "as_on_date", "last_updated_on", "deployed_to",
    "neuleap_connect_lead", "company_connect_lead", "project_name",
    "project_start_date", "project_end_date", "project_tech_stack",
    "project_overview", "nps", "neulearn_capstones_helpful",
    "skill_in_hand", "skills_acquired", "skills_to_develop",
    "potential_new_opportunities", "plan_of_action", "blockers",
    "any_other_feedback",
]

# ---------------------------------------------------------------------------
# DB setup
# ---------------------------------------------------------------------------

def _ensure_db_dir(db_url: str) -> None:
    """For SQLite URLs, create the parent directory if it doesn't exist."""
    url = make_url(db_url)
    if url.drivername.startswith("sqlite") and url.database and url.database != ":memory:":
        db_path = Path(url.database)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        if not db_path.exists():
            logger.info("Database not found — will be created at %s", db_path)
        else:
            logger.info("Using existing database at %s", db_path)


_ensure_db_dir(DB_URL)
_engine = create_engine(DB_URL)

_CREATE_EMPLOYEES = text("""
CREATE TABLE IF NOT EXISTS employees (
    id                      INTEGER PRIMARY KEY,
    name                    VARCHAR,
    contact                 VARCHAR,
    created_timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated_timestamp  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

_CREATE_EMPLOYEE_SNAPSHOTS = text("""
CREATE TABLE IF NOT EXISTS employee_snapshots (
    employee_id                 INTEGER REFERENCES employees(id),
    as_on_date                  DATE,
    last_updated_on             DATE,
    deployed_to                 VARCHAR,
    neuleap_connect_lead        VARCHAR,
    company_connect_lead        VARCHAR,
    project_name                VARCHAR,
    project_start_date          DATE,
    project_end_date            DATE,
    project_tech_stack          TEXT,
    project_overview            TEXT,
    nps                         DECIMAL,
    neulearn_capstones_helpful  DECIMAL,
    skill_in_hand               TEXT,
    skills_acquired             TEXT,
    skills_to_develop           TEXT,
    potential_new_opportunities TEXT,
    plan_of_action              TEXT,
    blockers                    TEXT,
    any_other_feedback          TEXT,
    created_timestamp           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated_timestamp      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (employee_id, as_on_date)
)
""")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_excel(data_dir: str = "data") -> str:
    files = (
        glob.glob(os.path.join(data_dir, "*.xlsx"))
        + glob.glob(os.path.join(data_dir, "*.xls"))
    )
    if not files:
        raise FileNotFoundError(f"No Excel file found in '{data_dir}/'")
    if len(files) > 1:
        raise ValueError(
            f"Multiple Excel files found in '{data_dir}/'. Keep only one.\nFound: {files}"
        )
    return files[0]


def _to_none(value):
    """Convert pandas NA / NaN / NaT to None so SQLAlchemy writes NULL."""
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _to_date(value):
    """Coerce any date-like value to a Python date object, or None."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "date"):          # pandas Timestamp / datetime
        return value.date()
    try:
        return pd.to_datetime(str(value)).date()
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse_sheet(raw: pd.DataFrame, sheet_name: str) -> list[dict]:
    """
    Parse one sheet's key-value layout into a list of flat record dicts.

    Layout per row: col0=key | col1=value | col2=key | col3=value | col4=key | col5=value
    A new record block begins at every row where col0 (case-insensitive) == 'id'.
    """
    block_start_indices = raw.index[
        raw[0].astype(str).str.strip().str.lower() == "id"
    ].tolist()

    if not block_start_indices:
        logger.warning("Sheet '%s': no 'Id' rows found — skipping.", sheet_name)
        return []

    records: list[dict] = []
    for i, start in enumerate(block_start_indices):
        end = block_start_indices[i + 1] if i + 1 < len(block_start_indices) else len(raw)
        block = raw.iloc[start:end]

        record: dict = {}
        for _, row in block.iterrows():
            for k_col, v_col in ((0, 1), (2, 3), (4, 5)):
                raw_key = row[k_col]
                raw_val = row[v_col]

                if pd.isna(raw_key) or str(raw_key).strip() == "":
                    continue
                col_name = _KEY_MAP.get(str(raw_key).strip().lower())
                if col_name is None:
                    continue                     # unrecognised label — ignore
                if not pd.isna(raw_val):
                    record[col_name] = raw_val

        if not record:
            continue

        # Expose the employee PK under both names so each upsert function
        # can find what it needs without further renaming.
        record.setdefault("employee_id", record.get("id"))
        records.append(record)

    return records


def _parse_all_sheets(excel_path: str) -> list[dict]:
    """Read every sheet and return a combined list of parsed records."""
    xl = pd.ExcelFile(excel_path)
    all_records: list[dict] = []
    for sheet_name in xl.sheet_names:
        raw = pd.read_excel(excel_path, sheet_name=sheet_name, header=None)
        sheet_records = _parse_sheet(raw, sheet_name)
        logger.info("Sheet '%s': %d record(s) parsed.", sheet_name, len(sheet_records))
        all_records.extend(sheet_records)
    return all_records

# ---------------------------------------------------------------------------
# DB writes
# ---------------------------------------------------------------------------

def _create_tables() -> None:
    with _engine.begin() as conn:
        conn.execute(_CREATE_EMPLOYEES)
        conn.execute(_CREATE_EMPLOYEE_SNAPSHOTS)
    logger.info("Tables ready.")


def _upsert_employees(records: list[dict]) -> None:
    """
    Deduplicate by employee id (keep the first occurrence, which is the most
    recent block because sheets are ordered newest-first) and upsert.
    """
    seen: dict[int, dict] = {}
    for r in records:
        eid = r.get("id")
        if eid is not None and eid not in seen:
            seen[eid] = {
                "id":      _to_none(eid),
                "name":    _to_none(r.get("name")),
                "contact": _to_none(r.get("contact")),
            }

    with _engine.begin() as conn:
        for emp in seen.values():
            conn.execute(
                text(
                    "INSERT OR REPLACE INTO employees (id, name, contact) "
                    "VALUES (:id, :name, :contact)"
                ),
                emp,
            )
    logger.info("Upserted %d employee(s).", len(seen))


def _upsert_snapshots(records: list[dict]) -> None:
    skipped = 0
    with _engine.begin() as conn:
        for r in records:
            # Validate required composite-key fields are present
            if not r.get("employee_id") or not r.get("as_on_date"):
                logger.warning(
                    "Skipping snapshot for employee_id=%r: missing as_on_date.",
                    r.get("employee_id"),
                )
                skipped += 1
                continue

            # Build the row dict for columns that are present in this record
            available = [c for c in _SNAPSHOT_COLS if c in r]
            row_dict = {
                c: _to_date(r[c]) if c in _DATE_COLS else _to_none(r[c])
                for c in available
            }

            col_list    = ", ".join(available)
            placeholders = ", ".join(f":{c}" for c in available)
            conn.execute(
                text(
                    f"INSERT OR REPLACE INTO employee_snapshots ({col_list}) "
                    f"VALUES ({placeholders})"
                ),
                row_dict,
            )

    inserted = len(records) - skipped
    if skipped:
        logger.warning("Upserted %d snapshot(s), skipped %d.", inserted, skipped)
    else:
        logger.info("Upserted %d snapshot(s).", inserted)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    excel_path = _find_excel()
    logger.info("Reading: %s", excel_path)

    records = _parse_all_sheets(excel_path)
    logger.info("Total records parsed across all sheets: %d", len(records))

    _create_tables()
    _upsert_employees(records)
    _upsert_snapshots(records)

    logger.info("Ingest complete.")