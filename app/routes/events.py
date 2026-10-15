from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.models.endpoint import WebhookEndpoint
from app.models.event import EventDelivery, WebhookEvent
from app.routes.endpoints import get_db
from app.schemas.event import DeliveryHistoryRead, EventCreate, EventRead
from app.security import verify_event_signature, verify_management_key

ingestion_router = APIRouter(prefix="/events", tags=["events"])
management_router = APIRouter(
    prefix="/events", tags=["events"], dependencies=[Depends(verify_management_key)]
)


@ingestion_router.post("", response_model=EventRead, status_code=status.HTTP_202_ACCEPTED)
def receive_event(
    event: EventCreate,
    request: Request,
    x_hookflow_signature: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    verify_event_signature(x_hookflow_signature, request.scope["state"]["raw_body"])
    event_id = str(event.event_id)
    existing = db.get(WebhookEvent, event_id)
    payload = event.model_dump(mode="json", exclude={"event_id"})
    if existing:
        if existing.payload != payload:
            raise HTTPException(status_code=409, detail="Event ID was already used for another payload")
        return existing

    targets = db.scalars(
        select(WebhookEndpoint).where(
            WebhookEndpoint.vendor_id == event.vendor_id,
            WebhookEndpoint.is_active.is_(True),
        )
    ).all()
    matching = [target for target in targets if "*" in target.event_types or event.event_type in target.event_types]
    stored_event = WebhookEvent(
        id=event_id,
        vendor_id=event.vendor_id,
        event_type=event.event_type,
        order_id=event.order_id,
        payload=payload,
        status="pending" if matching else "unmatched",
    )
    for endpoint in matching:
        stored_event.deliveries.append(EventDelivery(endpoint_id=endpoint.id, status="pending"))
    db.add(stored_event)
    try:
        db.commit()
        db.refresh(stored_event)
    except IntegrityError:
        db.rollback()
        # A concurrent duplicate may have committed between the initial lookup and insert.
        existing = db.get(WebhookEvent, event_id)
        if existing:
            if existing.payload != payload:
                raise HTTPException(status_code=409, detail="Event ID was already used for another payload")
            return existing
        raise
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(status_code=503, detail="Could not store event") from error
    return stored_event


@management_router.get("", response_model=list[EventRead])
def list_events(limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
    if not 1 <= limit <= 500 or offset < 0:
        raise HTTPException(status_code=422, detail="limit must be 1..500 and offset must be nonnegative")
    statement = (
        select(WebhookEvent)
        .options(selectinload(WebhookEvent.deliveries))
        .order_by(WebhookEvent.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return db.scalars(statement).all()


@management_router.get("/{event_id}", response_model=EventRead)
def get_event(event_id: UUID, db: Session = Depends(get_db)):
    event = db.scalar(
        select(WebhookEvent)
        .options(selectinload(WebhookEvent.deliveries))
        .where(WebhookEvent.id == str(event_id))
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@management_router.get("/{event_id}/deliveries", response_model=list[DeliveryHistoryRead])
def get_delivery_history(event_id: UUID, db: Session = Depends(get_db)):
    if db.get(WebhookEvent, str(event_id)) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    statement = (
        select(EventDelivery)
        .options(selectinload(EventDelivery.attempts))
        .where(EventDelivery.event_id == str(event_id))
        .order_by(EventDelivery.id)
    )
    return db.scalars(statement).all()
