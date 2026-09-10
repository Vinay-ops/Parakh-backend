import uuid
from datetime import date, datetime, time

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, Time, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base

# Inspection lifecycle. ML processing has not been integrated yet, so a scan
# creates an inspection in PENDING_ML and the ML team's integration will move
# it to COMPLIANT / NON_COMPLIANT once real results exist.
INSPECTION_STATUSES = (
    "CREATED",
    "CAPTURING",
    "PENDING_ML",
    "PROCESSING",
    "EXTRACTED",
    "COMPLIANCE_READY",
    "COMPLIANT",
    "NON_COMPLIANT",
    "FAILED",
    "CANCELLED",
)


class Inspection(Base):
    __tablename__ = "inspections"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    inspection_id: Mapped[str] = mapped_column(
        String(32), unique=True, index=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    product_name: Mapped[str] = mapped_column(String(255), nullable=True)
    product_category: Mapped[str] = mapped_column(String(100), nullable=True)
    # Legacy single-image URL kept for backward-compat; new multi-side flow
    # stores images in inspection_images. The first uploaded side image's URL
    # is also written here so the existing history/compliance UIs still work.
    product_image_url: Mapped[str] = mapped_column(Text, nullable=True)
    # Multi-side fields added in migration 0002.
    product_type: Mapped[str] = mapped_column(String(64), nullable=True)
    side_count: Mapped[int] = mapped_column(Integer, nullable=True)
    inspection_date: Mapped[date] = mapped_column(Date, nullable=True)
    inspection_time: Mapped[time] = mapped_column(Time, nullable=True)
    compliance_status: Mapped[str] = mapped_column(
        String(32), default="CREATED", nullable=True
    )
    compliance_score: Mapped[float] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
