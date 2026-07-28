# ranger-keycloak-sync

Sync Keycloak realm roles to Apache Ranger roles and keep role membership aligned over time.

## What It Does

- Reads users and realm-role mappings from Keycloak.
- Ensures users exist in Ranger.
- Creates missing Ranger roles with a configurable prefix.
- Grants and optionally revokes Ranger role membership to match Keycloak.
- Runs once or on a recurring interval.

## Requirements

- Python 3.10+
- Network access to both Keycloak Admin API and Ranger Admin API
- A Keycloak client with `client_credentials` enabled

## Configuration

Copy `.env.example` to `.env` and set values for your environment.

Required values:

- `KEYCLOAK_BASE_URL`
- `KEYCLOAK_REALM`
- `KEYCLOAK_CLIENT_ID`
- `KEYCLOAK_CLIENT_SECRET`
- `RANGER_USERNAME`
- `RANGER_PASSWORD`
- `RANGER_SERVICE_NAME`

Common optional values:

- `SYNC_INTERVAL_SECONDS` (default: `86400`)
- `SYNC_ONCE` (default: `false`)
- `SYNC_REMOVE_MISSING_USERS` (default: `true`)
- `KEYCLOAK_ROLE_EXCLUDE` (comma-separated list)
- `RANGER_ROLE_PREFIX` (default: `kc_`)
- `LOG_LEVEL` (default: `INFO`)

## Run Locally

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the sync process:

```bash
python sync.py
```

## Run With Docker Compose

1. Create `.env` from `.env.example` and provide real credentials.
2. Build and start:

```bash
docker compose up --build -d
```

3. Follow logs:

```bash
docker compose logs -f ranger-keycloak-sync
```

4. Stop:

```bash
docker compose down
```

## Files

- `sync.py`: Main sync worker.
- `.env.example`: Example configuration values.
- `Dockerfile`: Container image definition.
- `docker-compose.yml`: Service startup definition.