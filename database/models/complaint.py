import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base

COMPLAINT_STATUSES = ("OPEN", "UNDER_REVIEW", "RESOLVED", "REJECTED")


class Complaint(Base):
    __tablename__ = "complaints"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    complaint_id: Mapped[str] = mapped_column(
        String(32), unique=True, index=True, nullable=False
    )
    # References the internal inspections.id (UUID) — never the public id.
    inspection_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("inspections.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    user_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("auth.users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    product_name: Mapped[str] = mapped_column(String(255), nullable=True)
    complaint_title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=True)
    priority: Mapped[str] = mapped_column(String(20), default="MEDIUM", nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="OPEN", nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )