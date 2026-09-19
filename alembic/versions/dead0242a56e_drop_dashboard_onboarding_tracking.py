"""drop dashboard onboarding tracking columns

The onboarding checklist lived behind login, but businesses can't log in
until an admin creates their account — so it never reached anyone who
wasn't already a customer. That flow moved to the public landing page
instead; these columns tracked state only the removed dashboard UI used.

Revision ID: dead0242a56e
Revises: 7b8e39bca263
Create Date: 2026-09-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dead0242a56e'
down_revision: Union[str, None] = '7b8e39bca263'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('businesses', schema=None) as batch_op:
        batch_op.drop_column('live_at')
        batch_op.drop_column('test_completed_at')


def downgrade() -> None:
    with op.batch_alter_table('businesses', schema=None) as batch_op:
        batch_op.add_column(sa.Column('test_completed_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('live_at', sa.DateTime(), nullable=True))
