"""phase4

Revision ID: 5b5013568221
Revises: 
Create Date: 2026-09-22 00:47:59.397735

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b5013568221'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("extracted_events", sa.Column("reminded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("email_messages", sa.Column("followed_up_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("email_messages", "followed_up_at")
    op.drop_column("extracted_events", "reminded_at")
