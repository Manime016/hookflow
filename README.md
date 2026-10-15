# HookFlow

HookFlow accepts signed webhook events, stores them in MySQL, selects active destinations by vendor and event type, and delivers events through a durable database-backed worker. Delivery outcomes and retry history are available through the management API.

## Run locally

Requirements: Python 3.11+, MySQL 8+, and two terminal sessions for the API and worker.

1. Create a virtual environment and install dependencies: `pip install -r requirements.txt`.
2. Create the MySQL database configured by `DB_NAME` (default `hookflow`).
3. Copy `.env.example` to `.env` and replace the example secrets with long random values.
4. Apply the database migration: `alembic upgrade head`.
5. Start the API: `uvicorn app.main:app --reload`.
6. Start the durable delivery worker in another terminal: `python -m app.worker`.

Swagger UI is at `/docs`. `/health` is a liveness check and `/ready` checks database connectivity. Run automated tests with `pytest`.

## Configuration

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Optional complete SQLAlchemy URL; overrides the `DB_*` values |
| `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` | MySQL connection |
| `INGESTION_SECRET` | HMAC key for `POST /events` |
| `MANAGEMENT_API_KEY` | API key required for endpoint and event management routes |
| `MAX_REQUEST_BYTES` | Maximum request body size, default 1 MiB |
| `DELIVERY_TIMEOUT_SECONDS` | Outbound HTTP timeout, default 10 seconds |
| `MAX_DELIVERY_ATTEMPTS` | Maximum attempts per destination, default 5 |
| `RETRY_BASE_SECONDS` | First retry delay; later delays double, capped at one hour |
| `WORKER_LEASE_SECONDS` | Time before an interrupted worker job can be resumed |

Keep `.env` private. `.env.example` contains placeholders only.

## Register a destination

Management routes require `X-API-Key: $MANAGEMENT_API_KEY`. Register a destination with its vendor and the event types it accepts. Use `*` to subscribe to all types.

```http
POST /endpoints
X-API-Key: your-management-key
Content-Type: application/json
```

```json
{
  "url": "https://receiver.example/hooks",
  "secret": "a-long-random-secret-used-to-sign-deliveries",
  "vendor_id": "vendor-42",
  "event_types": ["order.created", "order.cancelled"]
}
```

Endpoint responses never include the destination secret. Management endpoints support listing, retrieving, patching, and deleting destinations.

## Send an event

`POST /events` requires an HMAC SHA-256 signature over the exact raw JSON request bytes. Send `X-HookFlow-Signature: sha256=<hex digest>`, calculated with `INGESTION_SECRET`. The optional `event_id` is a UUID; reusing it with the same payload is idempotent, and reusing it with a different payload returns `409`. To submit through Swagger UI, first calculate the digest for the exact compact JSON body, then paste `sha256=<digest>` into the `X-HookFlow-Signature` header field.

For the example below, calculate the header value with:

```python
import hashlib
import hmac

body = b'{"event_id":"b7f6998b-3124-4c76-986c-3215ed775b89","event_type":"order.created","vendor_id":"vendor-42","order_id":"order-123","data":{"total":42.5,"currency":"USD"}}'
secret = b"your-INGESTION_SECRET"
signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
print(f"sha256={signature}")
```

```json
{
  "event_id": "b7f6998b-3124-4c76-986c-3215ed775b89",
  "event_type": "order.created",
  "vendor_id": "vendor-42",
  "order_id": "order-123",
  "data": {"total": 42.5, "currency": "USD"}
}
```

The API returns `202 Accepted` after storing the event and its matching delivery jobs. Events with no active matching destination are stored with `unmatched` status. The worker polls the database independently, so jobs remain queued across API or worker restarts.

## Delivery and status APIs

The worker sends JSON with `X-HookFlow-Event-Id` and an HMAC `X-HookFlow-Signature` signed using the destination secret. It does not follow redirects or use environment-configured HTTP proxies. Destinations resolving to private, loopback, link-local, or otherwise non-public IPs are rejected to reduce SSRF risk. DNS can change between validation and connection, so production deployments should also restrict worker egress at the network layer. Configure public HTTPS destination URLs in production.

All routes below require `X-API-Key`:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/events?limit=100&offset=0` | List recent events and delivery states |
| `GET` | `/events/{event_id}` | Inspect a stored event |
| `GET` | `/events/{event_id}/deliveries` | Inspect each destination and its attempts |

2xx responses succeed. Timeouts, transport errors, 408, 425, 429, and 5xx responses are retried with exponential delays. Other HTTP errors are recorded as permanent failures. Delivery is at least once: a worker crash after the destination accepts a request but before HookFlow records the response can cause a repeat, so receiving systems should deduplicate by event ID.

## Migrations and operations

Use `alembic revision --autogenerate -m "describe change"` to create later migrations, review the generated revision, and apply it with `alembic upgrade head`. Back up MySQL before production migrations. Run one or more worker processes; row locking prevents workers from claiming the same available job on databases that support `SKIP LOCKED`. For a production deployment, terminate TLS at a trusted proxy, restrict network access to the management API, apply rate limits at the proxy, configure backups and monitoring, and use a process supervisor for both API and worker.

Run tests with `pytest`. The suite uses an isolated SQLite database and mocks external delivery calls.
