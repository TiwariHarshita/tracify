"""Use the configured working role with a separate test DB; print no credentials."""
import os
import subprocess
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings


def main():
    url = make_url(get_settings().database_url)
    name = "trace_phase6_tests"
    if url.database == name:
        raise SystemExit("Choose another test database name; this name is your application's database.")
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            if not connection.execute(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}).scalar():
                connection.exec_driver_sql('CREATE DATABASE "trace_phase6_tests"')
    finally:
        engine.dispose()
    test_env = dict(os.environ)
    test_url = url.set(database=name).render_as_string(hide_password=False)
    test_env.update(DATABASE_URL=test_url, TRACE_AUTH_TEST_DATABASE_URL=test_url)
    result = subprocess.run([sys.executable, "-m", "pytest", "-q",
        "tests/test_phase3.py", "tests/test_csv_api.py", "tests/test_csv_parser.py",
        "tests/test_analytics.py", "tests/test_analytics_api.py", "tests/test_report_editor.py",
        "tests/test_sharing.py"], env=test_env)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
