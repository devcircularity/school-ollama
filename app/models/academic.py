# app/models/academic.py - Fixed without duplicate Enrollment class
from __future__ import annotations
import uuid
from datetime import date, datetime
from sqlalchemy import (
    String, Integer, Boolean, ForeignKey, Date, DateTime, Index, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base

class AcademicYear(Base):
    __tablename__ = "academic_years"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)  # e.g., 2025
    title: Mapped[str] = mapped_column(String(64), nullable=False)  # "Academic Year 2025"
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")  # DRAFT|ACTIVE|CLOSED
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    
    # Timestamp fields
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    terms: Mapped[list["AcademicTerm"]] = relationship("AcademicTerm", back_populates="year", cascade="all, delete-orphan")
    
    # Add is_active property for convenience
    @property
    def is_active(self) -> bool:
        return self.state == "ACTIVE"
    
    __table_args__ = (
        Index("uq_academic_year_per_school", "school_id", "year", unique=True),
        CheckConstraint("state IN ('DRAFT','ACTIVE','CLOSED')", name="ck_academic_year_state"),
    )


class AcademicTerm(Base):
    __tablename__ = "academic_terms"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    academic_year_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("academic_years.id", ondelete="CASCADE"), 
        index=True, 
        nullable=False
    )
    term: Mapped[int] = mapped_column(Integer, nullable=False)  # 1,2,3
    title: Mapped[str] = mapped_column(String(48), nullable=False)  # "Term 1"
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="PLANNED")  # PLANNED|ACTIVE|CLOSED
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    
    # Timestamp fields
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    year: Mapped["AcademicYear"] = relationship("AcademicYear", back_populates="terms")
    # FIXED: Import Enrollment from enrollment.py instead of defining it here
    enrollments: Mapped[list["Enrollment"]] = relationship(
        "Enrollment", 
        back_populates="term", 
        cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        Index("uq_term_per_year", "school_id", "academic_year_id", "term", unique=True),
        CheckConstraint("state IN ('PLANNED','ACTIVE','CLOSED')", name="ck_academic_term_state"),
    )


class EnrollmentStatusEvent(Base):
    __tablename__ = "enrollment_status_events"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    enrollment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("enrollments.id", ondelete="CASCADE"), 
        index=True, 
        nullable=False
    )
    prev_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    new_status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Timestamp fields
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships - use string reference for Enrollment
    enrollment: Mapped["Enrollment"] = relationship("Enrollment", back_populates="status_events")
    
    __table_args__ = (
        CheckConstraint("new_status IN ('ENROLLED','TRANSFERRED_OUT','SUSPENDED','DROPPED','GRADUATED')", name="ck_enrollment_event_status"),
        Index("ix_enrollment_events_enrollment", "school_id", "enrollment_id", "event_date"),
    )