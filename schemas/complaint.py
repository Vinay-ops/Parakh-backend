from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

ComplaintStatus = Literal["OPEN", "UNDER_REVIEW", "RESOLVED", "REJECTED"]
ComplaintPriority = Literal["LOW", "MEDIUM", "HIGH"]


class ComplaintCreate(BaseModel):
    complaint_title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    product_name: Optional[str] = Field(None, max_length=255)
    category: Optional[str] = Field(None, max_length=100)
    priority: ComplaintPriority = "MEDIUM"
    # Public inspection id (INSP-...) as sent by the client; the backend
    # resolves it to the internal UUID before persisting.
    inspection_id: Optional[str] = Field(None, max_length=32)


class ComplaintUpdate(BaseModel):
    complaint_title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    category: Optional[str] = Field(None, max_length=100)
    priority: Optional[ComplaintPriority] = None
    status: Optional[ComplaintStatus] = None


class ComplaintOut(BaseModel):
    id: str
    complaint_id: str
    inspection_id: Optional[str]
    user_id: str
    product_name: Optional[str]
    complaint_title: str
    description: Optional[str]
    category: Optional[str]
    priority: Optional[str]
    status: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class PaginatedComplaints(BaseModel):
    items: list[ComplaintOut]
    total: int
    page: int
    page_size: int