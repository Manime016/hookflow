
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, func, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"
    __table_args__ = (Index("ix_endpoint_vendor_active", "vendor_id", "is_active"),)

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True
    )
    url: Mapped[str] = mapped_column(
        String(2048), nullable=False
    )
    vendor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_types: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    secret: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
