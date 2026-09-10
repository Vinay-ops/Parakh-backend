import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base

# Valid side labels for a packaged-commodity inspection.
VALID_SIDES = ("front", "back", "left", "right")


class InspectionImage(Base):
    """One captured image for a specific side of a package inspection.

    Uniqueness: (inspection_id, side) — retaking a side replaces the existing
    row via upsert in the service layer, so there is never more than one image
    per side per inspection.
    """

    __tablename__ = "inspection_images"

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    inspection_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("inspections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    side_order: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    # Retained only for migration compatibility. New records never persist a
    # public URL; authenticated callers receive an on-demand signed URL.
    public_url: Mapped[str] = mapped_column(Text, nullable=True)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
