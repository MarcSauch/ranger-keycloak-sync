import importlib
import os
import threading
import time
from typing import Any, Dict, List, Set

from sync_logic import LOG, SyncRunner


fastapi_mod = importlib.import_module("fastapi")
FastAPI = fastapi_mod.FastAPI
HTTPException = fastapi_mod.HTTPException


def _normalize_str_list(value: Any, field_name: str) -> Set[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a JSON array of strings")

    normalized: Set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise HTTPException(status_code=400, detail=f"{field_name} must contain only strings")
        item = item.strip()
        if item:
            normalized.add(item)
    return normalized


class SyncApi:
    def __init__(self) -> None:
        self.runner = SyncRunner()
        self._lock = threading.Lock()

    def trigger(self, payload: Dict[str, Any]) -> Dict[str, object]:
        if not self._lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="A sync is already in progress")

        started = time.time()
        try:
            include_users = _normalize_str_list(payload.get("include_users"), "include_users")
            include_roles = _normalize_str_list(payload.get("include_roles"), "include_roles")
            include_groups = _normalize_str_list(payload.get("include_groups"), "include_groups")

            merge_with_env_filters = payload.get("merge_with_env_filters", True)
            if not isinstance(merge_with_env_filters, bool):
                raise HTTPException(status_code=400, detail="merge_with_env_filters must be a boolean")

            summary = self.runner.run_sync_once(
                include_users=include_users,
                include_roles=include_roles,
                include_groups=include_groups,
                merge_with_defaults=merge_with_env_filters,
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
def trigger_sync(payload: Dict[str, Any]) -> Dict[str, object]:
    return sync_api.trigger(payload)


def run_api() -> None:
    uvicorn_mod = importlib.import_module("uvicorn")
    host = os.getenv("SYNC_API_HOST", "0.0.0.0")
    port = int(os.getenv("SYNC_API_PORT", "8000"))
    uvicorn_mod.run(app, host=host, port=port)