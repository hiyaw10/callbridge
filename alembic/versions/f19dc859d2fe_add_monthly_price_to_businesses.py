"""add monthly_price to businesses

Revision ID: f19dc859d2fe
Revises: 06e757a9e449
Create Date: 2026-10-01 08:58:11.195922

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f19dc859d2fe'
down_revision: Union[str, None] = '06e757a9e449'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default backfills every existing business to 99 (what every current
    # customer actually agreed to) — new businesses created after this get the
    # ORM-level default of 39 unless the admin sets something else on the form.
    with op.batch_alter_table('businesses', schema=None) as batch_op:
        batch_op.add_column(sa.Column('monthly_price', sa.Integer(), nullable=False, server_default='99'))


def downgrade() -> None:
    with op.batch_alter_table('businesses', schema=None) as batch_op:
        batch_op.drop_column('monthly_price')
