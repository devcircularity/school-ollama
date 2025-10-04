from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal, Optional
from datetime import datetime

from sqlalchemy import (
    String, Integer, Boolean, Numeric, ForeignKey, DateTime,
    CheckConstraint, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

Category = Literal["TUITION", "COCURRICULAR", "OTHER"]
BillingCycle = Literal["TERM", "ANNUAL", "ONE_OFF"]


class FeeStructure(Base):
    __tablename__ = "fee_structures"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    level: Mapped[str] = mapped_column(String(32), nullable=False)
    term: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    items: Mapped[list["FeeItem"]] = relationship(
        "FeeItem",
        back_populates="structure",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_fee_structures_school_term_year", "school_id", "term", "year"),
        UniqueConstraint(
            "school_id", "year", "term", "level", "name",
            name="uix_fee_structure_unique"
        ),
    )


class FeeItem(Base):
    __tablename__ = "fee_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)

    fee_structure_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fee_structures.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    class_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("classes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    item_name: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal('0.00'))
    is_optional: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    category: Mapped[Category] = mapped_column(String(24), default="OTHER", nullable=False)
    billing_cycle: Mapped[BillingCycle] = mapped_column(String(16), default="TERM", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    structure: Mapped["FeeStructure"] = relationship("FeeStructure", back_populates="items")

    __table_args__ = (
        CheckConstraint("billing_cycle IN ('TERM','ANNUAL','ONE_OFF')", name="ck_fee_items_billing_cycle"),
        CheckConstraint("category IN ('TUITION','COCURRICULAR','OTHER')", name="ck_fee_items_category"),
        CheckConstraint("amount >= 0", name="ck_fee_items_amount_positive"),
        Index("ix_fee_items_school_structure_class", "school_id", "fee_structure_id", "class_id"),
        UniqueConstraint(
            "fee_structure_id", "class_id", "item_name",
            name="uix_fee_item_structure_class_name"
        ),
    )