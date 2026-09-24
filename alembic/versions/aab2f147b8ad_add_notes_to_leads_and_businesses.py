"""add notes to leads and businesses

Revision ID: aab2f147b8ad
Revises: 5732621b88b1
Create Date: 2026-09-24 11:55:35.372137

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aab2f147b8ad'
down_revision: Union[str, None] = '5732621b88b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('businesses', schema=None) as batch_op:
        batch_op.add_column(sa.Column('notes', sa.Text(), nullable=True))
    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.add_column(sa.Column('notes', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('leads', schema=None) as batch_op:
        batch_op.drop_column('notes')
    with op.batch_alter_table('businesses', schema=None) as batch_op:
        batch_op.drop_column('notes')
