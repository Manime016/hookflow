# HookFlow API

HookFlow is a FastAPI service for registering and managing webhook destinations.
Each destination has a URL, a signing secret, an active flag, and a creation time.

## Requirements

- Python 3.11 or newer
- MySQL

## Run locally

1. Create and activate a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Create a MySQL database named `hookflow` (or set `DB_NAME` to another name).
4. Copy `.env.example` to `.env` and set the database connection values.
5. Create the database table with `python create_tables.py`.
6. Start the API with `uvicorn app.main:app --reload`.

The interactive API documentation is available at `/docs`.

## Configuration

The database connection uses these environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `DB_HOST` | `localhost` | MySQL server host |
| `DB_PORT` | `3306` | MySQL server port |
| `DB_USER` | `root` | MySQL user |
| `DB_PASSWORD` | empty | MySQL password |
| `DB_NAME` | `hookflow` | Database name |

## API

All endpoint records are available under `/endpoints`:

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/endpoints` | Register a destination |
| `GET` | `/endpoints` | List destinations |
| `GET` | `/endpoints/{endpoint_id}` | Get one destination |
| `PATCH` | `/endpoints/{endpoint_id}` | Change its URL, secret, or active state |
| `DELETE` | `/endpoints/{endpoint_id}` | Delete a destination |

Create request example:

```json
{
  "url": "https://example.com/webhooks",
  "secret": "replace-with-a-long-random-secret"
}
```

Secrets are accepted on create and update but are omitted from API responses.
