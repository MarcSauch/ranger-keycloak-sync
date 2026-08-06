import importlib
import os
import threading
import time
from typing import Dict, List, Set

from pydantic import BaseModel, Field

from sync_logic import LOG, SyncRunner


fastapi_mod = importlib.import_module("fastapi")
FastAPI = fastapi_mod.FastAPI
HTTPException = fastapi_mod.HTTPException


class SyncRequest(BaseModel):
    include_users: List[str] | None = Field(default=None)
    include_roles: List[str] | None = Field(default=None)
    include_groups: List[str] | None = Field(default=None)
    merge_with_env_filters: bool = Field(default=True)

    @staticmethod
    def _normalize_str_list(value: List[str] | None) -> Set[str] | None:
        if value is None:
            return None

        normalized: Set[str] = set()
        for item in value:
            trimmed = item.strip()
            if trimmed:
                normalized.add(trimmed)
        return normalized

    def include_users_set(self) -> Set[str] | None:
        return self._normalize_str_list(self.include_users)

    def include_roles_set(self) -> Set[str] | None:
        return self._normalize_str_list(self.include_roles)

    def include_groups_set(self) -> Set[str] | None:
        return self._normalize_str_list(self.include_groups)


class SyncApi:
    def __init__(self) -> None:
        self.runner = SyncRunner()
        self._lock = threading.Lock()

    def trigger(self, payload: SyncRequest) -> Dict[str, object]:
        if not self._lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="A sync is already in progress")

        started = time.time()
        try:
            summary = self.runner.run_sync_once(
                include_users=payload.include_users_set(),
                include_roles=payload.include_roles_set(),
                include_groups=payload.include_groups_set(),
                merge_with_defaults=payload.merge_with_env_filters,
            )
            summary["duration_seconds"] = round(time.time() - started, 3)
            return summary
        except HTTPException:
            raise
        except Exception as exc:
            LOG.exception("API-triggered sync failed: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        finally:
            self._lock.release()


sync_api = SyncApi()
app = FastAPI(title="Ranger Keycloak Sync API", version="1.0.0")


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/sync")
def trigger_sync(payload: SyncRequest) -> Dict[str, object]:
    return sync_api.trigger(payload)


def run_api() -> None:
    uvicorn_mod = importlib.import_module("uvicorn")
    host = os.getenv("SYNC_API_HOST", "0.0.0.0")
    port = int(os.getenv("SYNC_API_PORT", "8000"))
    uvicorn_mod.run(app, host=host, port=port)