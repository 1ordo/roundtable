"""advisory detail

Revision ID: c0b90e8612d5
Revises: 6940981598b0
Create Date: 2026-08-01 14:41:04.767131

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'c0b90e8612d5'
down_revision: Union[str, None] = '6940981598b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('title_ai_tags', sa.Column('detail', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('title_ai_tags', 'detail')
