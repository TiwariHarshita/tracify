"""Add report editor definition and revision; preserve existing drafts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "trace_phase6_editor"
down_revision = 'f3a33ec406a0'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("reports", sa.Column("definition", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("reports", sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1")))

def downgrade():
    op.drop_column("reports", "revision")
    op.drop_column("reports", "definition")
