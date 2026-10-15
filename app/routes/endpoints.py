from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.endpoint import WebhookEndpoint
from app.schemas.endpoint import EndpointCreate, EndpointRead, EndpointUpdate

router = APIRouter(prefix="/endpoints", tags=["endpoints"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_endpoint_or_404(endpoint_id: int, db: Session) -> WebhookEndpoint:
    endpoint = db.get(WebhookEndpoint, endpoint_id)
    if endpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Endpoint not found",
        )
    return endpoint


@router.post("", response_model=EndpointRead, status_code=status.HTTP_201_CREATED)
def create_endpoint(endpoint: EndpointCreate, db: Session = Depends(get_db)):
    db_endpoint = WebhookEndpoint(url=str(endpoint.url), secret=endpoint.secret)
    try:
        db.add(db_endpoint)
        db.commit()
        db.refresh(db_endpoint)
        return db_endpoint
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create endpoint",
        ) from error


@router.get("", response_model=list[EndpointRead])
def get_endpoints(db: Session = Depends(get_db)):
    statement = select(WebhookEndpoint).order_by(WebhookEndpoint.id)
    return db.scalars(statement).all()


@router.get("/{endpoint_id}", response_model=EndpointRead)
def get_endpoint(endpoint_id: int, db: Session = Depends(get_db)):
    return get_endpoint_or_404(endpoint_id, db)


@router.patch("/{endpoint_id}", response_model=EndpointRead)
def update_endpoint(
    endpoint_id: int,
    updates: EndpointUpdate,
    db: Session = Depends(get_db),
):
    endpoint = get_endpoint_or_404(endpoint_id, db)
    values = updates.model_dump(exclude_unset=True)
    # Null is treated as "leave unchanged" for nullable request fields.
    values = {field: value for field, value in values.items() if value is not None}
    if "url" in values and values["url"] is not None:
        values["url"] = str(values["url"])
    for field, value in values.items():
        setattr(endpoint, field, value)

    try:
        db.commit()
        db.refresh(endpoint)
        return endpoint
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update endpoint",
        ) from error


@router.delete("/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_endpoint(endpoint_id: int, db: Session = Depends(get_db)) -> Response:
    endpoint = get_endpoint_or_404(endpoint_id, db)
    try:
        db.delete(endpoint)
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete endpoint",
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
