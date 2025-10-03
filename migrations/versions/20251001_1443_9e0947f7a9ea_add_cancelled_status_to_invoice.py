"""add cancelled status to invoice

Revision ID: 9e0947f7a9ea
Revises: 955b3d9f188b
Create Date: 2025-10-01 14:43:02.511124

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9e0947f7a9ea'
down_revision: Union[str, Sequence[str], None] = '955b3d9f188b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade():
    # Drop the old constraint
    op.drop_constraint('ck_invoice_status', 'invoices', type_='check')
    
    # Create new constraint with CANCELLED
    op.create_check_constraint(
        'ck_invoice_status',
        'invoices',
        "status IN ('DRAFT','ISSUED','PAID','PARTIAL','CANCELLED')"
    )


def downgrade():
    # Drop the new constraint
    op.drop_constraint('ck_invoice_status', 'invoices', type_='check')
    
    # Restore old constraint
    op.create_check_constraint(
        'ck_invoice_status',
        'invoices',
        "status IN ('DRAFT','ISSUED','PAID','PARTIAL')"
    )