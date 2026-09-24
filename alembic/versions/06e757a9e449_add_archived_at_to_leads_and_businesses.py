"""add archived_at to leads and businesses

Revision ID: 06e757a9e449
Revises: aab2f147b8ad
Create Date: 2026-09-24 12:01:17.968495

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '06e757a9e449'
down_revision: Union[str, None] = 'aab2f147b8ad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('businesses', schema=None) as batch_op:
        batch_op.add_column(sa.Column('archived_at', sa.DateTime(), nullable=True))
    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.add_column(sa.Column('archived_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.drop_column('archived_at')
    with op.batch_alter_table('businesses', schema=None) as batch_op:
        batch_op.drop_column('archived_at')
