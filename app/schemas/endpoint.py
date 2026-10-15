
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class EndpointCreate(BaseModel):
    url: HttpUrl
    secret: str = Field(min_length=16, max_length=255)


class EndpointUpdate(BaseModel):
    url: HttpUrl | None = None
    secret: str | None = Field(default=None, min_length=16, max_length=255)
    is_active: bool | None = None


class EndpointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: HttpUrl
    is_active: bool
    created_at: datetime
