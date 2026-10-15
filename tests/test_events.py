import hashlib
import hmac
import json
from datetime import datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.main import app
from app.models.endpoint import WebhookEndpoint
from app.models.event import DeliveryAttempt, EventDelivery, WebhookEvent
from app.routes.endpoints import get_db


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    yield session
    app.dependency_overrides.clear()
    session.close()
    engine.dispose()


@pytest.fixture
def client(db_session, monkeypatch):
    monkeypatch.setenv("INGESTION_SECRET", "ingestion-test-secret")
    monkeypatch.setenv("MANAGEMENT_API_KEY", "management-test-secret")
    with TestClient(app) as test_client:
        yield test_client


def signed_body(payload):
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(b"ingestion-test-secret", body, hashlib.sha256).hexdigest()
    return body, {"X-HookFlow-Signature": f"sha256={signature}"}


def test_event_is_stored_routed_and_idempotent(client, db_session):
    target = WebhookEndpoint(
        url="https://receiver.example/webhook",
        vendor_id="vendor-a",
        event_types=["order.created"],
        secret="destination-signing-secret-long-enough",
        is_active=True,
    )
    db_session.add(target)
    db_session.commit()
    event_id = str(uuid4())
    payload = {
        "event_id": event_id,
        "event_type": "order.created",
        "vendor_id": "vendor-a",
        "order_id": "order-123",
        "data": {"total": 42},
    }
    body, headers = signed_body(payload)

    first = client.post("/events", content=body, headers=headers)
    second = client.post("/events", content=body, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["id"] == event_id
    assert len(first.json()["deliveries"]) == 1
    assert db_session.scalar(select(WebhookEvent).where(WebhookEvent.id == event_id)) is not None
    assert len(db_session.scalars(select(EventDelivery)).all()) == 1


def test_event_rejects_invalid_signature(client):
    payload = {"event_type": "order.created", "vendor_id": "vendor-a", "data": {}}
    response = client.post("/events", json=payload, headers={"X-HookFlow-Signature": "sha256=bad"})
    assert response.status_code == 401


def test_management_routes_require_api_key(client):
    response = client.get("/endpoints")
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("response_code", "expected_delivery", "expected_attempt"),
    [(204, "succeeded", "succeeded"), (400, "failed", "failed"), (503, "retrying", "retrying")],
)
def test_worker_records_delivery_and_retry(client, db_session, monkeypatch, response_code, expected_delivery, expected_attempt):
    from app.services import delivery as delivery_service

    monkeypatch.setattr(delivery_service, "validate_destination", lambda _url: None)

    class FakeResponse:
        status_code = response_code

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, _url, *, content, headers):
            expected = hmac.new(endpoint.secret.encode(), content, hashlib.sha256).hexdigest()
            assert headers["X-HookFlow-Signature"] == f"sha256={expected}"
            return FakeResponse()

    monkeypatch.setattr(delivery_service.httpx, "Client", FakeClient)
    monkeypatch.setenv("RETRY_BASE_SECONDS", "0")
    endpoint = WebhookEndpoint(
        url="https://receiver.example/webhook",
        vendor_id="vendor-a",
        event_types=["order.created"],
        secret="destination-signing-secret-long-enough",
        is_active=True,
    )
    event = WebhookEvent(
        id=str(uuid4()),
        vendor_id="vendor-a",
        event_type="order.created",
        payload={"event_type": "order.created", "vendor_id": "vendor-a", "data": {}},
        status="pending",
        created_at=datetime.utcnow(),
    )
    delivery = EventDelivery(endpoint=endpoint, event=event, status="pending")
    db_session.add(delivery)
    db_session.commit()

    assert delivery_service.deliver_one(db_session) is True
    db_session.refresh(delivery)
    attempt = db_session.scalar(select(DeliveryAttempt).where(DeliveryAttempt.delivery_id == delivery.id))
    assert delivery.status == expected_delivery
    assert attempt.status == expected_attempt


def test_destination_validation_rejects_private_ip():
    from app.services.delivery import validate_destination

    with pytest.raises(ValueError, match="non-public"):
        validate_destination("http://127.0.0.1/webhook")
