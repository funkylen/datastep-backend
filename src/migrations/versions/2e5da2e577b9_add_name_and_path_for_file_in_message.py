"""add name and path for file in message

Revision ID: 2e5da2e577b9
Revises: f79c428cf17b
Create Date: 2024-07-06 05:23:37.083043

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '2e5da2e577b9'
down_revision: Union[str, None] = '88435e18ac16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('message', sa.Column('file_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('message', sa.Column('filename', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('message', 'filename')
    op.drop_column('message', 'file_path')
    # ### end Alembic commands ###
