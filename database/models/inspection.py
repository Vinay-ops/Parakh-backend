import uuid
from datetime import date, datetime, time

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, Text, Time, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base

# Inspection lifecycle. ML processing has not been integrated yet, so a scan
# creates an inspection in PENDING_ML and the ML team's integration will move
# it to COMPLIANT / NON_COMPLIANT once real results exist.
INSPECTION_STATUSES = ("PENDING_ML", "COMPLIANT", "NON_COMPLIANT", "FAILED")


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
    product_image_url: Mapped[str] = mapped_column(Text, nullable=True)
    inspection_date: Mapped[date] = mapped_column(Date, nullable=True)
    inspection_time: Mapped[time] = mapped_column(Time, nullable=True)
    compliance_status: Mapped[str] = mapped_column(
        String(32), default="PENDING_ML", nullable=True
    )
    compliance_score: Mapped[float] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )