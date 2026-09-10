from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ProfileOut(BaseModel):
    id: str
    user_id: str
    full_name: Optional[str]
    email: Optional[str]
    profile_image_url: Optional[str]
    role: Optional[str]
    department: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class ProfileUpdate(BaseModel):
    # `role` and identity fields are intentionally not updatable by clients.
    model_config = ConfigDict(extra="forbid")

    full_name: Optional[str] = Field(None, max_length=255)
    profile_image_url: Optional[str] = Field(None, max_length=2000)
    department: Optional[str] = Field(None, max_length=100)