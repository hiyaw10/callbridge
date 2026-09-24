"""add broadcasts table and text_messages broadcast_id

Revision ID: 5732621b88b1
Revises: 4f454871417e
Create Date: 2026-09-24 10:54:04.316305

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5732621b88b1'
down_revision: Union[str, None] = '4f454871417e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'broadcasts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('business_id', sa.Integer(), sa.ForeignKey('businesses.id'), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('recipient_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sent_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    with op.batch_alter_table('broadcasts', schema=None) as batch_op:
        batch_op.create_index('ix_broadcasts_business_id', ['business_id'])
        batch_op.create_index('ix_broadcasts_created_at', ['created_at'])

    with op.batch_alter_table('text_messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('broadcast_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_text_messages_broadcast_id', ['broadcast_id'])
        batch_op.create_foreign_key(
            'fk_text_messages_broadcast_id', 'broadcasts', ['broadcast_id'], ['id']
        )


def downgrade() -> None:
    with op.batch_alter_table('text_messages', schema=None) as batch_op:
        batch_op.drop_constraint('fk_text_messages_broadcast_id', type_='foreignkey')
        batch_op.drop_index('ix_text_messages_broadcast_id')
        batch_op.drop_column('broadcast_id')

    op.drop_table('broadcasts')
