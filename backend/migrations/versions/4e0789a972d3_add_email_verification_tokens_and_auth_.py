"""add email verification tokens and auth rate limits

Revision ID: 4e0789a972d3
Revises: e50d94fbc75c
Create Date: 2026-10-21 16:28:27.829154

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa



revision: str = '4e0789a972d3'
down_revision: Union[str, Sequence[str], None] = 'e50d94fbc75c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    
    op.create_table('auth_rate_limits',
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('hits', sa.Integer(), nullable=False),
    sa.Column('window_end', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('hits > 0', name='ck_auth_rate_positive_hits'),
    sa.PrimaryKeyConstraint('key', name=op.f('pk_auth_rate_limits'))
    )
    op.create_index(op.f('ix_auth_rate_limits_window_end'), 'auth_rate_limits', ['window_end'], unique=False)
    op.create_table('email_action_tokens',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('purpose', sa.String(length=20), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("purpose IN ('verify_email', 'reset_password')", name='ck_email_action_purpose'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_email_action_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_email_action_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_email_action_tokens_token_hash'))
    )
    op.create_index(op.f('ix_email_action_tokens_expires_at'), 'email_action_tokens', ['expires_at'], unique=False)
    op.create_index(op.f('ix_email_action_tokens_user_id'), 'email_action_tokens', ['user_id'], unique=False)
    op.add_column('users', sa.Column('email_verified', sa.Boolean(), server_default=sa.text('false'), nullable=False))
        
    op.execute("""
        UPDATE users AS u
        SET email_verified = true
        WHERE u.password_hash IS NULL
          AND EXISTS (
              SELECT 1
              FROM auth_identities AS a
              WHERE a.user_id = u.id
                AND a.provider IN ('google', 'github')
          )
    """)

   
    op.execute("""
        DELETE FROM sessions
        WHERE user_id IN (
            SELECT id FROM users WHERE email_verified = false
        )
    """)
    


def downgrade() -> None:
    """Downgrade schema."""
    
    op.drop_column('users', 'email_verified')
    op.drop_index(op.f('ix_email_action_tokens_user_id'), table_name='email_action_tokens')
    op.drop_index(op.f('ix_email_action_tokens_expires_at'), table_name='email_action_tokens')
    op.drop_table('email_action_tokens')
    op.drop_index(op.f('ix_auth_rate_limits_window_end'), table_name='auth_rate_limits')
    op.drop_table('auth_rate_limits')
    
