"""sms delivery status tracking: add error_code, allow undelivered

Revision ID: 35b1505c18db
Revises: d113b0d1297f
Create Date: 2026-09-14 14:20:01.517314

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '35b1505c18db'
down_revision: Union[str, None] = 'd113b0d1297f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('text_messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('error_code', sa.String(length=10), nullable=True))
        batch_op.drop_constraint('ck_textmessage_status', type_='check')
        batch_op.create_check_constraint(
            'ck_textmessage_status', "status IN ('sent','delivered','undelivered','failed')"
        )


def downgrade() -> None:
    with op.batch_alter_table('text_messages', schema=None) as batch_op:
        batch_op.drop_constraint('ck_textmessage_status', type_='check')
        batch_op.create_check_constraint(
            'ck_textmessage_status', "status IN ('sent','delivered','failed')"
        )
        batch_op.drop_column('error_code')
