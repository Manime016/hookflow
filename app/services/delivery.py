import hashlib
import hmac
import ipaddress
import json
import os
import socket
import time
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.event import DeliveryAttempt, EventDelivery, WebhookEvent


def validate_destination(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("Destination URL must be an HTTP(S) URL without embedded credentials")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))}
    except OSError as error:
        raise ValueError("Destination host could not be resolved") from error
    if not addresses:
        raise ValueError("Destination host did not resolve")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError("Destination resolves to a non-public IP address")


def event_status(deliveries: list[EventDelivery]) -> str:
    states = [delivery.status for delivery in deliveries]
    if not states:
        return "unmatched"
    if any(state in {"pending", "processing", "retrying"} for state in states):
        return "delivering"
    if all(state in {"succeeded", "skipped"} for state in states):
        if all(state == "skipped" for state in states):
            return "skipped"
        return "succeeded"
    if any(state == "succeeded" for state in states):
        return "partially_failed"
    return "failed"


def deliver_one(db: Session) -> bool:
    now = datetime.utcnow()
    stmt = (
        select(EventDelivery)
        .where(
            or_(
                EventDelivery.status.in_(["pending", "retrying"]),
                (EventDelivery.status == "processing") & (EventDelivery.lease_until < now),
            ),
            EventDelivery.next_attempt_at <= now,
        )
        .order_by(EventDelivery.next_attempt_at, EventDelivery.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    delivery = db.scalar(stmt)
    if delivery is None:
        return False

    endpoint = delivery.endpoint
    if not endpoint.is_active:
        delivery.status = "skipped"
        delivery.lease_until = None
        event = db.get(WebhookEvent, delivery.event_id)
        db.flush()
        related = db.scalars(select(EventDelivery).where(EventDelivery.event_id == event.id)).all()
        event.status = event_status(related)
        db.commit()
        return True

    if delivery.status == "processing":
        previous = db.scalar(
            select(DeliveryAttempt)
            .where(DeliveryAttempt.delivery_id == delivery.id)
            .order_by(DeliveryAttempt.attempt_number.desc())
            .limit(1)
        )
        if previous and previous.status == "processing":
            previous.status = "failed"
            previous.error = "Worker lease expired; delivery will resume"
            previous.finished_at = now

    delivery.status = "processing"
    delivery.lease_until = now + timedelta(seconds=int(os.getenv("WORKER_LEASE_SECONDS", "60")))
    delivery.attempt_count += 1
    attempt = DeliveryAttempt(delivery_id=delivery.id, attempt_number=delivery.attempt_count)
    db.add(attempt)
    db.commit()

    event = db.get(WebhookEvent, delivery.event_id)
    response_status = None
    error_text = None
    retryable = False
    try:
        validate_destination(endpoint.url)
        body = json.dumps(
            {"id": event.id, **event.payload, "created_at": event.created_at.isoformat()},
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
        signature = hmac.new(endpoint.secret.encode(), body, hashlib.sha256).hexdigest()
        timeout = float(os.getenv("DELIVERY_TIMEOUT_SECONDS", "10"))
        with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client:
            response = client.post(
                endpoint.url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-HookFlow-Event-Id": event.id,
                    "X-HookFlow-Signature": f"sha256={signature}",
                },
            )
        response_status = response.status_code
        retryable = response_status in {408, 425, 429} or response_status >= 500
        if not 200 <= response_status < 300:
            error_text = f"Destination returned HTTP {response_status}"
    except (httpx.TimeoutException, httpx.TransportError, ValueError) as error:
        retryable = not isinstance(error, ValueError)
        error_text = str(error)[:2000]

    maximum = int(os.getenv("MAX_DELIVERY_ATTEMPTS", "5"))
    attempt.response_status = response_status
    attempt.error = error_text
    attempt.finished_at = datetime.utcnow()
    if error_text is None:
        attempt.status = "succeeded"
        delivery.status = "succeeded"
    elif retryable and delivery.attempt_count < maximum:
        attempt.status = "retrying"
        delivery.status = "retrying"
        delay = min(3600, int(os.getenv("RETRY_BASE_SECONDS", "5")) * 2 ** (delivery.attempt_count - 1))
        delivery.next_attempt_at = datetime.utcnow() + timedelta(seconds=delay)
    else:
        attempt.status = "failed"
        delivery.status = "failed"
    delivery.lease_until = None
    db.flush()
    related = db.scalars(select(EventDelivery).where(EventDelivery.event_id == event.id)).all()
    event.status = event_status(related)
    db.commit()
    return True


def run_worker(poll_seconds: float = 1.0) -> None:
    while True:
        with SessionLocal() as db:
            did_work = deliver_one(db)
        if not did_work:
            time.sleep(poll_seconds)
