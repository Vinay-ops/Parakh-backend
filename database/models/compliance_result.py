import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base


class ComplianceResult(Base):
    __tablename__ = "compliance_results"

    id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # References the internal inspections.id (UUID) — never the public id.
    inspection_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("inspections.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=True)
    required_value: Mapped[str] = mapped_column(String(255), nullable=True)
    detected_value: Mapped[str] = mapped_column(String(255), nullable=True)
    bounding_box: Mapped[dict] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )