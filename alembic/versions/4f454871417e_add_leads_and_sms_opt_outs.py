"""add leads and sms_opt_outs tables

Revision ID: 4f454871417e
Revises: dead0242a56e
Create Date: 2026-09-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f454871417e'
down_revision: Union[str, None] = 'dead0242a56e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'leads',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('contact_name', sa.String(length=255), nullable=False),
        sa.Column('business_name', sa.String(length=255), nullable=False),
        sa.Column('business_address', sa.String(length=500), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        'sms_opt_outs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('business_id', sa.Integer(), sa.ForeignKey('businesses.id'), nullable=False),
        sa.Column('phone_number', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('business_id', 'phone_number', name='uq_sms_opt_out_business_phone'),
    )
    with op.batch_alter_table('sms_opt_outs', schema=None) as batch_op:
        batch_op.create_index('ix_sms_opt_outs_business_id', ['business_id'])
        batch_op.create_index('ix_sms_opt_outs_phone_number', ['phone_number'])


def downgrade() -> None:
    op.drop_table('sms_opt_outs')
    op.drop_table('leads')
