# ranger-keycloak-sync

Sync Keycloak realm roles and user groups to Apache Ranger, and keep membership aligned over time.

## What It Does

- Reads users, realm-role mappings, and group memberships from Keycloak.
- Ensures users exist in Ranger.
- Ensures groups exist in Ranger before assigning users to them.
- Creates missing Ranger roles with a configurable prefix.
- Adds users to mapped Ranger groups.
- Grants and optionally revokes Ranger role membership to match Keycloak.
- Runs once or on a recurring interval.

## Requirements

- Python 3.10+
- Network access to both Keycloak Admin API and Ranger Admin API
- A Keycloak client configured for one of these OAuth grant types:
	- `client_credentials` (service account)
	- `password` (resource owner username/password)

## Configuration

Copy `.env.example` to `.env` and set values for your environment.

Required values:

- `KEYCLOAK_BASE_URL`
- `KEYCLOAK_REALM`
- `KEYCLOAK_CLIENT_ID`
- `RANGER_USERNAME`
- `RANGER_PASSWORD`
- `RANGER_SERVICE_NAME`

Authentication-specific required values:

- For `KEYCLOAK_GRANT_TYPE=client_credentials`:
	- `KEYCLOAK_CLIENT_SECRET`
- For `KEYCLOAK_GRANT_TYPE=password`:
	- `KEYCLOAK_USERNAME`
	- `KEYCLOAK_PASSWORD`

Common optional values:

- `KEYCLOAK_GRANT_TYPE` (default: `client_credentials`)
- `KEYCLOAK_TOKEN_SCOPE` (optional)
- `RANGER_NORMALIZE_USERNAMES` (default: `true`)
- `RANGER_USERNAME_SEPARATOR` (default: `_`)
- `RANGER_GROUP_PREFIX` (default: empty)
- `RANGER_NORMALIZE_GROUP_NAMES` (default: `true`)
- `RANGER_GROUP_SEPARATOR` (default: `_`)
- `SYNC_INTERVAL_SECONDS` (default: `86400`)
- `SYNC_ONCE` (default: `false`)
- `SYNC_REMOVE_MISSING_USERS` (default: `true`)
- `KEYCLOAK_ROLE_EXCLUDE` (comma-separated list)
- `RANGER_ROLE_PREFIX` (default: `kc_`)
- `LOG_LEVEL` (default: `INFO`)

Username normalization notes:

- By default, usernames from Keycloak are normalized before Ranger API calls.
- Spaces and unsupported characters are replaced with `RANGER_USERNAME_SEPARATOR`.
- Example: `test user` becomes `test_user`.

Group normalization notes:

- Keycloak group path is used first (for uniqueness), then normalized before Ranger API calls.
- `/` and unsupported characters are replaced with `RANGER_GROUP_SEPARATOR`.
- Optional `RANGER_GROUP_PREFIX` can be used to namespace synced groups.
- Example: `/team/data-engineering` becomes `team_data-engineering` with default separator.

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