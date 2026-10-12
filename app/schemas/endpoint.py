
from pydantic import BaseModel, HttpUrl, Field


class EndpointCreate(BaseModel):
    url: HttpUrl
    secret: str = Field(min_length=16, max_length=255)
