import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from database.database import Base


class ExtractedInformation(Base):
    __tablename__ = "extracted_information"

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
    common_product_name: Mapped[str] = mapped_column(String(255), nullable=True)
    manufacturer_name: Mapped[str] = mapped_column(String(255), nullable=True)
    manufacturer_address: Mapped[str] = mapped_column(String(255), nullable=True)
    packer_name: Mapped[str] = mapped_column(String(255), nullable=True)
    packer_address: Mapped[str] = mapped_column(String(255), nullable=True)
    importer_name: Mapped[str] = mapped_column(String(255), nullable=True)
    importer_address: Mapped[str] = mapped_column(String(255), nullable=True)
    multi_product_names: Mapped[list] = mapped_column(JSON, nullable=True)
    multi_product_quantities: Mapped[list] = mapped_column(JSON, nullable=True)
    net_quantity_value: Mapped[float] = mapped_column(Float, nullable=True)
    net_quantity_unit: Mapped[str] = mapped_column(String(50), nullable=True)
    number_count: Mapped[int] = mapped_column(nullable=True)
    mrp: Mapped[float] = mapped_column(Float, nullable=True)
    mrp_tax_wording: Mapped[str] = mapped_column(String(255), nullable=True)
    manufacture_or_import_date: Mapped[str] = mapped_column(String(255), nullable=True)
    consumer_care_name: Mapped[str] = mapped_column(String(255), nullable=True)
    consumer_care_address: Mapped[str] = mapped_column(String(255), nullable=True)
    consumer_care_phone: Mapped[str] = mapped_column(String(50), nullable=True)
    consumer_care_email: Mapped[str] = mapped_column(String(255), nullable=True)
    commodity_dimensions: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )