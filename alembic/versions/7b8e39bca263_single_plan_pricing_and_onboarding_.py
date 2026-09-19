"""single-plan pricing (drop plan_tier) and dashboard onboarding tracking

Revision ID: 7b8e39bca263
Revises: 88902c89f679
Create Date: 2026-09-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7b8e39bca263'
down_revision: Union[str, None] = '88902c89f679'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('businesses', schema=None) as batch_op:
        batch_op.drop_constraint('ck_business_plan_tier', type_='check')
        batch_op.drop_column('plan_tier')
        batch_op.add_column(sa.Column('test_completed_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('live_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('businesses', schema=None) as batch_op:
        batch_op.drop_column('live_at')
        batch_op.drop_column('test_completed_at')
        batch_op.add_column(sa.Column('plan_tier', sa.String(length=20), nullable=False, server_default='starter'))
        batch_op.create_check_constraint('ck_business_plan_tier', "plan_tier IN ('starter','growth','pro')")
