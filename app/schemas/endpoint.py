
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr


class EndpointCreate(BaseModel):
    url: HttpUrl
    secret: SecretStr = Field(min_length=16, max_length=255)
    vendor_id: str = Field(min_length=1, max_length=128)
    event_types: list[str] = Field(min_length=1, max_length=100)


class EndpointUpdate(BaseModel):
    url: HttpUrl | None = None
    secret: SecretStr | None = Field(default=None, min_length=16, max_length=255)
    is_active: bool | None = None
    vendor_id: str | None = Field(default=None, min_length=1, max_length=128)
    event_types: list[str] | None = Field(default=None, min_length=1, max_length=100)


class EndpointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: HttpUrl
    vendor_id: str
    event_types: list[str]
    is_active: bool
    created_at: datetime
