"""Run from backend/. Generate ONLY the two Phase 6 report columns.

Reads the real repository's Alembic head. Never guesses a parent revision,
autogenerates unrelated changes, upgrades the DB, or edits old migrations.
"""
from pathlib import Path
import sys

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import engine

REVISION = "trace_phase6_editor"


def main():
    if not Path("alembic.ini").is_file():
        raise SystemExit("Run this command from backend/ beside alembic.ini.")
    config = Config("alembic.ini")
    scripts = ScriptDirectory.from_config(config)
    if any(item.revision == REVISION for item in scripts.walk_revisions()):
        print("Phase 6 migration already exists. Review it, then run: uv run alembic upgrade head")
        return
    heads = scripts.get_heads()
    if len(heads) != 1:
        raise SystemExit("Expected one existing Alembic head. Resolve migration branches first.")
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_heads()
        if set(current) != set(heads):
            raise SystemExit("Database is not at the existing migration head. Apply earlier migrations first.")
        columns = {item["name"] for item in inspect(connection).get_columns("reports")}
        if {"definition", "revision"} & columns:
            raise SystemExit("Report editor columns already exist without this migration. Inspect migration history before proceeding.")
    revision = command.revision(config, message="add report editor definition and revision", head=heads[0], rev_id=REVISION)
    source = '''"""Add report editor definition and revision; preserve existing drafts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "trace_phase6_editor"
down_revision = PARENT
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("reports", sa.Column("definition", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("reports", sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1")))

def downgrade():
    op.drop_column("reports", "revision")
    op.drop_column("reports", "definition")
'''.replace("PARENT", repr(heads[0]))
    Path(revision.path).write_text(source, encoding="utf-8")
    print("Created:", revision.path)
    print("Review the two added columns, then run: uv run alembic upgrade head")


if __name__ == "__main__":
    main()
