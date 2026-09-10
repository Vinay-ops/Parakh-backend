from datetime import date, datetime, time
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class InspectionCreate(BaseModel):
    product_name: Optional[str] = Field(None, min_length=1, max_length=255)
    product_category: Optional[str] = Field(None, max_length=100)
    product_type: Optional[str] = Field(None, max_length=64)
    side_count: Literal[2, 4]


class InspectionOut(BaseModel):
    id: str
    inspection_id: str
    product_name: Optional[str]
    product_category: Optional[str]
    product_image_url: Optional[str]
    product_type: Optional[str]
    side_count: Optional[int]
    inspection_date: Optional[date]
    # The model stores SQLAlchemy Time; typed as `time` so Pydantic serializes
    # it as "HH:MM:SS" instead of failing on a str-typed field.
    inspection_time: Optional[time]
    compliance_status: Optional[str]
    compliance_score: Optional[float]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class InspectionImageOut(BaseModel):
    id: str
    inspection_id: str
    side: str
    side_order: int
    public_url: Optional[str]
    mime_type: Optional[str]
    file_size: Optional[int]
    created_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class ExtractedInformationOut(BaseModel):
    id: str
    inspection_id: str
    common_product_name: Optional[str] = None
    manufacturer_name: Optional[str] = None
    manufacturer_address: Optional[str] = None
    packer_name: Optional[str] = None
    packer_address: Optional[str] = None
    importer_name: Optional[str] = None
    importer_address: Optional[str] = None
    multi_product_names: Optional[Any] = None
    multi_product_quantities: Optional[Any] = None
    net_quantity_value: Optional[float] = None
    net_quantity_unit: Optional[str] = None
    number_count: Optional[int] = None
    mrp: Optional[float] = None
    mrp_tax_wording: Optional[str] = None
    manufacture_or_import_date: Optional[str] = None
    consumer_care_name: Optional[str] = None
    consumer_care_address: Optional[str] = None
    consumer_care_phone: Optional[str] = None
    consumer_care_email: Optional[str] = None
    commodity_dimensions: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ExtractedInformationUpdate(BaseModel):
    common_product_name: Optional[str] = None
    manufacturer_name: Optional[str] = None
    manufacturer_address: Optional[str] = None
    packer_name: Optional[str] = None
    packer_address: Optional[str] = None
    importer_name: Optional[str] = None
    importer_address: Optional[str] = None
    multi_product_names: Optional[Any] = None
    multi_product_quantities: Optional[Any] = None
    net_quantity_value: Optional[float] = None
    net_quantity_unit: Optional[str] = None
    number_count: Optional[int] = None
    mrp: Optional[float] = None
    mrp_tax_wording: Optional[str] = None
    manufacture_or_import_date: Optional[str] = None
    consumer_care_name: Optional[str] = None
    consumer_care_address: Optional[str] = None
    consumer_care_phone: Optional[str] = None
    consumer_care_email: Optional[str] = None
    commodity_dimensions: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class ComplianceRuleOut(BaseModel):
    rule_name: str
    status: str
    reason: Optional[str] = None
    required_value: Optional[str] = None
    detected_value: Optional[str] = None
    bounding_box: Optional[Any] = None

    model_config = ConfigDict(from_attributes=True)


class PaginatedInspections(BaseModel):
    items: list[InspectionOut]
    total: int
    page: int
    page_size: int
