"""add frozen report share links"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "9a74034f854a"
down_revision = "trace_phase6_editor"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("report_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False), sa.Column("report_revision", sa.Integer(), nullable=False),
        sa.Column("dataset_sha256", sa.String(64), nullable=False), sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"))
    op.create_index(op.f("ix_report_snapshots_report_id"), "report_snapshots", ["report_id"])
    op.create_index(op.f("ix_report_snapshots_owner_id"), "report_snapshots", ["owner_id"])
    op.create_table("report_share_links",
        sa.Column("id", sa.Uuid(), nullable=False), sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False), sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["report_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("token_hash"))
    for name, column in [("report_id", "report_id"), ("owner_id", "owner_id"), ("snapshot_id", "snapshot_id"), ("expires_at", "expires_at")]:
        op.create_index(op.f("ix_report_share_links_" + name), "report_share_links", [column])

def downgrade():
    op.drop_table("report_share_links")
    op.drop_table("report_snapshots")
