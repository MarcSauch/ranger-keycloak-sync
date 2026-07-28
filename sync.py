import logging
import os
import time
from collections import defaultdict
from typing import Dict, List, Set
from urllib.parse import quote

import requests
from apache_ranger.client.ranger_client import RangerClient
from apache_ranger.model.grant_revoke_role_request import GrantRevokeRoleRequest
from apache_ranger.model.ranger_role import RangerRole


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
LOG = logging.getLogger("keycloak-ranger-sync")


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


class KeycloakClient:
    def __init__(self) -> None:
        self.base_url = env_required("KEYCLOAK_BASE_URL").rstrip("/")
        self.realm = env_required("KEYCLOAK_REALM")
        self.client_id = env_required("KEYCLOAK_CLIENT_ID")
        self.client_secret = env_required("KEYCLOAK_CLIENT_SECRET")
        self.verify_tls = env_bool("KEYCLOAK_VERIFY_TLS", True)

        self._token = ""
        self._token_expiry = 0.0
        self._session = requests.Session()

    def _access_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expiry - 30:
            return self._token

        token_url = (
            f"{self.base_url}/realms/{self.realm}/protocol/openid-connect/token"
        )
        resp = self._session.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=30,
            verify=self.verify_tls,
        )
        resp.raise_for_status()
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_expiry = now + int(payload.get("expires_in", 60))
        return self._token

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token()}"}

    def list_users(self) -> List[dict]:
        users: List[dict] = []
        first = 0
        page_size = int(os.getenv("KEYCLOAK_PAGE_SIZE", "200"))

        while True:
            url = f"{self.base_url}/admin/realms/{self.realm}/users"
            resp = self._session.get(
                url,
                headers=self._headers(),
                params={"first": first, "max": page_size},
                timeout=30,
                verify=self.verify_tls,
            )
            resp.raise_for_status()
            page = resp.json()
            if not page:
                break
            users.extend(page)
            if len(page) < page_size:
                break
            first += page_size

        return users

    def user_realm_roles(self, user_id: str) -> Set[str]:
        url = (
            f"{self.base_url}/admin/realms/{self.realm}/users/"
            f"{quote(user_id, safe='')}/role-mappings/realm"
        )
        resp = self._session.get(
            url,
            headers=self._headers(),
            timeout=30,
            verify=self.verify_tls,
        )
        resp.raise_for_status()
        return {role.get("name") for role in resp.json() if role.get("name")}


class RangerSync:
    def __init__(self) -> None:
        self.base_url = os.getenv("RANGER_BASE_URL", "http://ranger-admin:6080").rstrip("/")
        self.username = env_required("RANGER_USERNAME")
        self.password = env_required("RANGER_PASSWORD")
        self.service_name = env_required("RANGER_SERVICE_NAME")
        self.role_prefix = os.getenv("RANGER_ROLE_PREFIX", "kc_")
        self.remove_missing_users = env_bool("SYNC_REMOVE_MISSING_USERS", True)

        self.exclude_roles = {
            role.strip()
            for role in os.getenv("KEYCLOAK_ROLE_EXCLUDE", "") .split(",")
            if role.strip()
        }

        self._session = requests.Session()
        self._session.auth = (self.username, self.password)
        self._session.headers.update({"Content-Type": "application/json"})

        self._client = RangerClient(self.base_url, (self.username, self.password))

    def ensure_user_exists(self, user_name: str) -> None:
        get_url = f"{self.base_url}/service/xusers/users/userName/{quote(user_name, safe='')}"
        resp = self._session.get(get_url, timeout=30)

        if resp.status_code == 200:
            return

        if resp.status_code != 404:
            resp.raise_for_status()

        create_url = f"{self.base_url}/service/xusers/users/external"
        create_resp = self._session.post(create_url, json={"name": user_name}, timeout=30)

        # If another sync loop created it first, treat that as success.
        if create_resp.status_code in (200, 201, 409):
            LOG.info("Created Ranger user: %s", user_name)
            return

        create_resp.raise_for_status()

    def _role_name(self, keycloak_role: str) -> str:
        return f"{self.role_prefix}{keycloak_role}"

    def _ensure_role(self, role_name: str) -> None:
        try:
            self._client.get_role(role_name, execUser=self.username, serviceName=self.service_name)
            return
        except Exception:
            pass

        role = RangerRole(
            {
                "name": role_name,
                "description": "Auto-synced from Keycloak",
                "users": [],
                "groups": [],
                "roles": [],
            }
        )
        self._client.create_role(
            self.service_name,
            role,
            params={"execUser": self.username},
        )
        LOG.info("Created Ranger role: %s", role_name)

    def sync_role_members(self, role_name: str, desired_users: Set[str]) -> None:
        self._ensure_role(role_name)
        current = self._client.get_role(
            role_name,
            execUser=self.username,
            serviceName=self.service_name,
        )

        current_users = {member.name for member in (current.users or []) if getattr(member, "name", None)}

        to_add = sorted(desired_users - current_users)
        to_remove = sorted(current_users - desired_users) if self.remove_missing_users else []

        if to_add:
            req = GrantRevokeRoleRequest(
                {
                    "grantor": self.username,
                    "grantorGroups": [],
                    "targetRoles": [role_name],
                    "users": to_add,
                }
            )
            self._client.grant_role(
                self.service_name,
                req,
                params={"execUser": self.username},
            )
            LOG.info("Granted role %s to users: %s", role_name, ", ".join(to_add))

        if to_remove:
            req = GrantRevokeRoleRequest(
                {
                    "grantor": self.username,
                    "grantorGroups": [],
                    "targetRoles": [role_name],
                    "users": to_remove,
                }
            )
            self._client.revoke_role(
                self.service_name,
                req,
                params={"execUser": self.username},
            )
            LOG.info("Revoked role %s from users: %s", role_name, ", ".join(to_remove))

        if not to_add and not to_remove:
            LOG.info("Role %s already in sync", role_name)

    def sync(self, keycloak_data: Dict[str, Set[str]]) -> None:
        all_users = set()
        for users in keycloak_data.values():
            all_users.update(users)

        for user in sorted(all_users):
            self.ensure_user_exists(user)

        for kc_role, users in sorted(keycloak_data.items()):
            if kc_role in self.exclude_roles:
                continue
            self.sync_role_members(self._role_name(kc_role), users)


class SyncRunner:
    def __init__(self) -> None:
        self.keycloak = KeycloakClient()
        self.ranger = RangerSync()
        self.interval_seconds = int(os.getenv("SYNC_INTERVAL_SECONDS", "86400"))
        self.sync_once = env_bool("SYNC_ONCE", False)

    def _build_mapping(self) -> Dict[str, Set[str]]:
        role_to_users: Dict[str, Set[str]] = defaultdict(set)

        users = self.keycloak.list_users()
        LOG.info("Fetched %d users from Keycloak", len(users))

        for user in users:
            username = (user.get("username") or "").strip()
            user_id = user.get("id")
            if not username or not user_id:
                continue

            roles = self.keycloak.user_realm_roles(user_id)
            for role in roles:
                role_to_users[role].add(username)

        LOG.info("Collected %d realm roles from Keycloak", len(role_to_users))
        return role_to_users

    def run_forever(self) -> None:
        while True:
            try:
                mapping = self._build_mapping()
                self.ranger.sync(mapping)
                LOG.info("Sync completed")
            except Exception as exc:
                LOG.exception("Sync failed: %s", exc)

            if self.sync_once:
                return

            time.sleep(self.interval_seconds)


if __name__ == "__main__":
    SyncRunner().run_forever()
