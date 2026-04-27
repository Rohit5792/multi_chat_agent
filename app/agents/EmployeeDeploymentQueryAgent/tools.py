from sqlalchemy import create_engine, inspect, text
from app.config import DB_URL
from app.logger import get_logger

logger = get_logger(__name__)

_engine = create_engine(DB_URL)

def get_schema() -> str:
    inspector = inspect(_engine)
    parts = []
    for table_name in inspector.get_table_names():
        cols = ", ".join(
            f"{col['name']} {col['type']}"
            for col in inspector.get_columns(table_name)
        )
        parts.append(f"Table %s(%s)" % (table_name, cols))
    schema = "\n".join(parts)
    logger.debug("Schema fetched: %d table(s)", len(parts))
    return schema


def execute_sql(sql: str) -> tuple[list[str], list[tuple]]:
    logger.debug("Executing SQL: %s", sql)
    try:
        with _engine.connect() as conn:
            result = conn.execute(text(sql))
            columns = list(result.keys())
            rows = result.fetchall()
        logger.debug("SQL returned %d row(s)", len(rows))
        return columns, rows
    except Exception:
        logger.exception("SQL execution failed: %s", sql)
        raise


def format_table(columns: list[str], rows: list[tuple]) -> str:
    header = "| " + " | ".join(columns) + " |"
    separator = "|" + "|".join("---" for _ in columns) + "|"
    body_lines = ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join([header, separator] + body_lines)