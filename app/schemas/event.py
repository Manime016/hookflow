from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class EventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID = Field(default_factory=uuid4)
    event_type: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.-]+$")
    vendor_id: str = Field(min_length=1, max_length=128)
    order_id: str | None = Field(default=None, max_length=255)
    data: dict = Field(default_factory=dict)


class DeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    endpoint_id: int
    status: str
    attempt_count: int
    next_attempt_at: datetime


class AttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    attempt_number: int
    status: str
    response_status: int | None
    error: str | None
    started_at: datetime
    finished_at: datetime | None


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    vendor_id: str
    event_type: str
    order_id: str | None
    payload: dict
    status: str
    created_at: datetime
    deliveries: list[DeliveryRead] = Field(default_factory=list)


class DeliveryHistoryRead(DeliveryRead):
    attempts: list[AttemptRead] = Field(default_factory=list)
