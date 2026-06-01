"""
UiPath Orchestrator — async API gateway.

Handles authentication (on-prem / cloud-oauth / cloud-pat) and
provides typed helpers for every major Orchestrator endpoint.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Any, Dict, List, Type, TypeVar
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from .schemas import (
    AuditLog,
    Asset,
    Folder,
    FolderSummary,
    Job,
    JobMetrics,
    Machine,
    OAuthTokenPayload,
    OrchestratorSettings,
    ProcessSchedule,
    QueueDefinition,
    QueueItem,
    QueueMetrics,
    Release,
    Robot,
    RobotLog,
    Session,
)

T = TypeVar("T", bound=BaseModel)

# HTTP statuses worth retrying: rate-limit + transient server errors.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

# Cap how much of an error body we echo back — Orchestrator can return large
# HTML error pages that would otherwise flood the agent's context.
_MAX_ERROR_BODY = 500


class OrchestratorError(RuntimeError):
    """An Orchestrator request failed. Carries the HTTP status for callers/agents."""

    def __init__(self, method: str, path: str, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.method = method
        self.path = path
        super().__init__(f"Orchestrator {method} {path} → {status_code}: {detail}")


class Orchestrator:
    """Async client that communicates with a single UiPath Orchestrator tenant."""

    def __init__(self, settings: OrchestratorSettings) -> None:
        self._cfg = settings
        self._token: str | None = None
        self._token_expiry: float = 0.0
        # Serialises token refresh so concurrent tool calls trigger one handshake,
        # not a stampede against the identity endpoint.
        self._token_lock = asyncio.Lock()
        self._http = httpx.AsyncClient(
            verify=not settings.skip_tls_verify,
            timeout=httpx.Timeout(settings.request_timeout, connect=min(10.0, settings.request_timeout)),
            limits=httpx.Limits(max_connections=settings.max_connections),
        )
        self._api_root = self._resolve_api_root()

    # ── URL resolution ──────────────────────────────────────

    def _resolve_api_root(self) -> str:
        """Build the base API URL depending on deployment type."""
        raw = self._cfg.base_url.rstrip("/")

        if self._cfg.auth_strategy == "on-prem":
            return raw  # on-prem OData sits at the root

        if "orchestrator_" in raw.lower():
            return raw

        tenant = self._cfg.tenant
        if raw.lower().endswith(f"/{tenant.lower()}"):
            return f"{raw}/orchestrator_"

        return f"{raw}/{tenant}/orchestrator_"

    def _identity_endpoint(self) -> str:
        """Cloud OAuth2 token endpoint."""
        parsed = urlparse(self._cfg.base_url)
        segments = [s for s in parsed.path.split("/") if s]
        org = f"/{segments[0]}" if segments else ""
        return f"{parsed.scheme}://{parsed.netloc}{org}/identity_/connect/token"

    def _onprem_auth_endpoint(self) -> str:
        return f"{self._cfg.base_url.rstrip('/')}/api/account/authenticate"

    # ── Authentication ──────────────────────────────────────

    async def _acquire_token(self) -> str:
        """Return a valid bearer token, refreshing if necessary."""

        # PAT — use directly, no handshake
        if self._cfg.auth_strategy == "cloud-pat":
            return self._cfg.access_token  # type: ignore[return-value]

        # Reuse cached token when it is still fresh (5-min buffer)
        if self._token and time.time() < self._token_expiry - 300:
            return self._token

        async with self._token_lock:
            # Re-check under the lock: another task may have refreshed while we waited.
            if self._token and time.time() < self._token_expiry - 300:
                return self._token

            if self._cfg.auth_strategy == "cloud-oauth":
                self._token, self._token_expiry = await self._oauth_handshake()
            elif self._cfg.auth_strategy == "on-prem":
                self._token, self._token_expiry = await self._onprem_handshake()
            else:
                raise RuntimeError(f"Unsupported auth strategy: {self._cfg.auth_strategy}")

            return self._token

    async def _oauth_handshake(self) -> tuple[str, float]:
        resp = await self._http.post(
            self._identity_endpoint(),
            data={
                "grant_type": "client_credentials",
                "client_id": self._cfg.client_id,
                "client_secret": self._cfg.client_secret,
                "scope": (
                    "OR.Execution OR.Queues OR.Folders OR.Jobs OR.Assets "
                    "OR.Robots OR.Machines OR.Monitoring OR.Settings OR.Audit OR.License"
                ),
            },
        )
        resp.raise_for_status()
        tok = OAuthTokenPayload(**resp.json())
        return tok.access_token, time.time() + tok.expires_in

    async def _onprem_handshake(self) -> tuple[str, float]:
        resp = await self._http.post(
            self._onprem_auth_endpoint(),
            json={
                "tenancyName": self._cfg.tenant,
                "usernameOrEmailAddress": self._cfg.username,
                "password": self._cfg.password,
            },
        )
        resp.raise_for_status()
        body = resp.json()
        token = body.get("result")
        if not token:
            raise RuntimeError(f"On-prem auth did not return a token: {body}")
        return token, time.time() + 72_000  # ~20 h conservative refresh

    # ── Generic HTTP plumbing ───────────────────────────────

    async def _call(
        self,
        method: str,
        path: str,
        *,
        params: Dict[str, Any] | None = None,
        body: Any = None,
        folder_id: int | None = None,
        max_retries: int = 3,
    ) -> Any:
        """Make an authenticated request, refreshing on 401 and backing off on transient errors."""
        fid = folder_id if folder_id is not None else self._cfg.folder_id
        url = f"{self._api_root.rstrip('/')}/{path.lstrip('/')}"

        attempt = 0
        while True:
            token = await self._acquire_token()
            headers: Dict[str, str] = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            if fid is not None:
                headers["X-UIPATH-OrganizationUnitId"] = str(fid)

            try:
                resp = await self._http.request(method, url, headers=headers, params=params, json=body)
            except httpx.TransportError as exc:
                # Connection reset, read/connect timeout, DNS failure, etc. — transient.
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt + random.uniform(0, 0.5))
                    attempt += 1
                    continue
                raise OrchestratorError(method, path, 0, f"transport error: {exc}") from exc

            if resp.is_success:
                return resp.json()

            # Expired/invalid token: drop the cache and retry once with a fresh one.
            if resp.status_code == 401 and attempt == 0 and self._cfg.auth_strategy != "cloud-pat":
                self._token, self._token_expiry = None, 0.0
                attempt += 1
                continue

            # Transient failures: exponential backoff with jitter (Retry-After wins).
            if resp.status_code in _RETRYABLE_STATUS and attempt < max_retries:
                delay = self._retry_after_seconds(resp)
                if delay is None:
                    delay = 2 ** attempt + random.uniform(0, 0.5)  # jitter avoids sync'd retries
                await asyncio.sleep(delay)
                attempt += 1
                continue

            raise OrchestratorError(method, path, resp.status_code, self._trim(resp.text))

    @staticmethod
    def _retry_after_seconds(resp: httpx.Response) -> float | None:
        """Parse a ``Retry-After`` header expressed as whole seconds, if present."""
        raw = resp.headers.get("Retry-After")
        if raw and raw.isdigit():
            return float(raw)
        return None

    @staticmethod
    def _trim(text: str) -> str:
        """Clip an error body so large HTML pages don't flood the response."""
        text = (text or "").strip()
        return text if len(text) <= _MAX_ERROR_BODY else text[:_MAX_ERROR_BODY] + "… (truncated)"

    async def _odata_list(
        self,
        path: str,
        model: Type[T],
        *,
        params: Dict[str, Any] | None = None,
        folder_id: int | None = None,
    ) -> List[T]:
        data = await self._call("GET", path, params=params, folder_id=folder_id)
        return [model(**item) for item in data.get("value", [])]

    async def _count(self, path: str, *, flt: str | None = None, folder_id: int | None = None) -> int:
        """Return the ``@odata.count`` for a collection (optionally filtered)."""
        params: Dict[str, Any] = {"$top": 0, "$count": "true"}
        if flt:
            params["$filter"] = flt
        data = await self._call("GET", path, params=params, folder_id=folder_id)
        return data.get("@odata.count", 0)

    @staticmethod
    def _odata_str(value: str) -> str:
        """Escape a string literal for safe interpolation into an OData $filter."""
        return value.replace("'", "''")

    async def _group_count(
        self, path: str, field: str, *, flt: str | None = None, folder_id: int | None = None
    ) -> Dict[str, int]:
        """Count rows grouped by ``field`` in a single OData ``$apply`` round trip.

        Returns a ``{field_value: count}`` map. Replaces the N-calls-per-bucket pattern.
        """
        apply = f"groupby(({field}),aggregate($count as count))"
        if flt:
            apply = f"filter({flt})/{apply}"
        data = await self._call("GET", path, params={"$apply": apply}, folder_id=folder_id)
        return {row[field]: row.get("count", 0) for row in data.get("value", []) if row.get(field) is not None}

    # ── Folders ─────────────────────────────────────────────

    async def list_folders(self, *, limit: int = 50, skip: int = 0) -> List[Folder]:
        return await self._odata_list(
            "/odata/Folders",
            Folder,
            params={"$top": limit, "$skip": skip, "$orderby": "DisplayName asc"},
        )

    # ── Robots ──────────────────────────────────────────────

    async def list_robots(self, *, folder_id: int | None = None, limit: int = 50, skip: int = 0) -> List[Robot]:
        endpoint = "/odata/Robots"
        if folder_id:
            endpoint = f"/odata/Robots/UiPath.Server.Configuration.OData.GetRobotsFromFolder(folderId={folder_id})"
        return await self._odata_list(
            endpoint, Robot, params={"$top": limit, "$skip": skip, "$orderby": "Name asc"}, folder_id=folder_id
        )

    # ── Machines ────────────────────────────────────────────

    async def list_machines(self, *, limit: int = 50, skip: int = 0) -> List[Machine]:
        return await self._odata_list(
            "/odata/Machines", Machine, params={"$top": limit, "$skip": skip, "$orderby": "Name asc"}
        )

    # ── Assets ──────────────────────────────────────────────

    async def list_assets(self, *, folder_id: int | None = None, limit: int = 50) -> List[Asset]:
        return await self._odata_list(
            "/odata/Assets", Asset, params={"$top": limit, "$orderby": "Name asc"}, folder_id=folder_id
        )

    async def get_robot_asset(self, robot_id: int, asset_name: str) -> Any:
        path = f"/odata/Assets/UiPath.Server.Configuration.OData.GetRobotAssetByRobotId(robotId={robot_id},assetName='{self._odata_str(asset_name)}')"
        return await self._call("GET", path)

    # ── Queues ──────────────────────────────────────────────

    async def list_queues(self, *, folder_id: int | None = None) -> List[QueueDefinition]:
        return await self._odata_list("/odata/QueueDefinitions", QueueDefinition, folder_id=folder_id)

    async def enqueue_item(
        self,
        queue_name: str,
        content: Dict[str, Any],
        *,
        priority: str = "Normal",
        reference: str | None = None,
        folder_id: int | None = None,
    ) -> Any:
        payload = {
            "itemData": {
                "Name": queue_name,
                "Priority": priority,
                "SpecificContent": content,
                "Reference": reference,
            }
        }
        return await self._call("POST", "/odata/Queues/UiPathODataSvc.AddQueueItem", body=payload, folder_id=folder_id)

    async def query_queue_items(
        self,
        *,
        queue_id: int | None = None,
        status: str | None = None,
        folder_id: int | None = None,
        limit: int = 50,
        skip: int = 0,
    ) -> Dict[str, Any]:
        filters: list[str] = []
        if queue_id:
            filters.append(f"QueueDefinitionId eq {queue_id}")
        if status:
            filters.append(f"Status eq '{self._odata_str(status)}'")

        params: Dict[str, Any] = {"$top": limit, "$skip": skip, "$orderby": "CreationTime desc", "$count": "true"}
        if filters:
            params["$filter"] = " and ".join(filters)

        data = await self._call("GET", "/odata/QueueItems", params=params, folder_id=folder_id)
        return {"items": [QueueItem(**i) for i in data.get("value", [])], "total": data.get("@odata.count")}

    async def compute_queue_metrics(self, queue_name: str, *, folder_id: int | None = None) -> QueueMetrics:
        defs = await self._call(
            "GET", "/odata/QueueDefinitions",
            params={"$filter": f"Name eq '{self._odata_str(queue_name)}'"}, folder_id=folder_id,
        )
        if not defs.get("value"):
            raise ValueError(f"Queue '{queue_name}' not found")
        qid = defs["value"][0]["Id"]

        grouped = await self._group_count(
            "/odata/QueueItems", "Status", flt=f"QueueDefinitionId eq {qid}", folder_id=folder_id
        )
        buckets = {
            label: grouped.get(label, 0)
            for label in ("New", "InProgress", "Successful", "Failed", "Abandoned")
        }

        done = buckets["Successful"] + buckets["Failed"]
        return QueueMetrics(
            queue_id=qid,
            queue_name=queue_name,
            total=sum(buckets.values()),
            new=buckets["New"],
            in_progress=buckets["InProgress"],
            successful=buckets["Successful"],
            failed=buckets["Failed"],
            abandoned=buckets["Abandoned"],
            success_rate_pct=round(buckets["Successful"] / done * 100, 1) if done else None,
        )

    # ── Jobs ────────────────────────────────────────────────

    async def query_jobs(
        self,
        *,
        folder_id: int | None = None,
        state: str | None = None,
        release_name: str | None = None,
        limit: int = 50,
    ) -> List[Job]:
        filters: list[str] = []
        if state:
            filters.append(f"State eq '{self._odata_str(state)}'")
        if release_name:
            filters.append(f"ReleaseName eq '{self._odata_str(release_name)}'")
        params: Dict[str, Any] = {"$top": limit, "$orderby": "CreationTime desc"}
        if filters:
            params["$filter"] = " and ".join(filters)
        return await self._odata_list("/odata/Jobs", Job, params=params, folder_id=folder_id)

    async def inspect_job(self, job_id: int, *, folder_id: int | None = None) -> Any:
        return await self._call("GET", f"/odata/Jobs({job_id})", folder_id=folder_id)

    async def launch_process(
        self,
        release_key: str,
        *,
        input_args: Dict[str, Any] | None = None,
        count: int = 1,
        folder_id: int | None = None,
    ) -> Any:
        payload = {
            "startInfo": {
                "ReleaseKey": release_key,
                "Strategy": "JobsCount",
                "JobsCount": count,
                "InputArguments": json.dumps(input_args) if input_args else None,
            }
        }
        return await self._call("POST", "/odata/Jobs/UiPath.Server.Configuration.OData.StartJobs", body=payload, folder_id=folder_id)

    async def cancel_job(self, job_id: int, *, force: bool = False, folder_id: int | None = None) -> Any:
        strategy = "Kill" if force else "SoftStop"
        return await self._call(
            "POST",
            f"/odata/Jobs({job_id})/UiPath.Server.Configuration.OData.StopJob",
            body={"strategy": strategy},
            folder_id=folder_id,
        )

    async def compute_job_metrics(self, *, folder_id: int | None = None) -> JobMetrics:
        grouped = await self._group_count("/odata/Jobs", "State", folder_id=folder_id)
        counts = {
            state: grouped.get(state, 0)
            for state in ("Pending", "Running", "Successful", "Faulted", "Stopped")
        }

        done = counts["Successful"] + counts["Faulted"]
        return JobMetrics(
            total=sum(counts.values()),
            pending=counts["Pending"],
            running=counts["Running"],
            successful=counts["Successful"],
            faulted=counts["Faulted"],
            stopped=counts["Stopped"],
            success_rate_pct=round(counts["Successful"] / done * 100, 1) if done else None,
        )

    # ── Releases ────────────────────────────────────────────

    async def list_releases(self, *, folder_id: int | None = None, process_key: str | None = None) -> List[Release]:
        params: Dict[str, Any] = {}
        if process_key:
            params["$filter"] = f"ProcessKey eq '{self._odata_str(process_key)}'"
        return await self._odata_list("/odata/Releases", Release, params=params, folder_id=folder_id)

    # ── Sessions ────────────────────────────────────────────

    async def list_sessions(self, *, folder_id: int | None = None, limit: int = 50) -> List[Session]:
        return await self._odata_list("/odata/Sessions", Session, params={"$top": limit}, folder_id=folder_id)

    # ── Schedules ───────────────────────────────────────────

    async def list_schedules(self, *, folder_id: int | None = None, limit: int = 50) -> List[ProcessSchedule]:
        return await self._odata_list("/odata/ProcessSchedules", ProcessSchedule, params={"$top": limit}, folder_id=folder_id)

    # ── Logs ────────────────────────────────────────────────

    async def query_robot_logs(
        self,
        *,
        folder_id: int | None = None,
        job_key: str | None = None,
        level: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int = 100,
        skip: int = 0,
    ) -> Dict[str, Any]:
        filters: list[str] = []
        if job_key:
            filters.append(f"JobKey eq '{self._odata_str(job_key)}'")
        if level:
            filters.append(f"Level eq '{self._odata_str(level)}'")
        if since:
            filters.append(f"TimeStamp ge {since}")
        if until:
            filters.append(f"TimeStamp le {until}")

        params: Dict[str, Any] = {"$top": limit, "$skip": skip, "$orderby": "TimeStamp desc", "$count": "true"}
        if filters:
            params["$filter"] = " and ".join(filters)

        data = await self._call("GET", "/odata/RobotLogs", params=params, folder_id=folder_id)
        return {"entries": [RobotLog(**e) for e in data.get("value", [])], "total": data.get("@odata.count")}

    # ── Audit ───────────────────────────────────────────────

    async def query_audit_trail(
        self,
        *,
        action: str | None = None,
        user: str | None = None,
        component: str | None = None,
        limit: int = 50,
        skip: int = 0,
    ) -> List[AuditLog]:
        filters: list[str] = []
        if action:
            filters.append(f"Action eq '{self._odata_str(action)}'")
        if user:
            filters.append(f"UserName eq '{self._odata_str(user)}'")
        if component:
            filters.append(f"Component eq '{self._odata_str(component)}'")
        params: Dict[str, Any] = {"$top": limit, "$skip": skip, "$orderby": "ExecutionTime desc"}
        if filters:
            params["$filter"] = " and ".join(filters)
        return await self._odata_list("/odata/AuditLogs", AuditLog, params=params)

    # ── Composite analytics ─────────────────────────────────

    async def get_faulted_jobs(self, *, folder_id: int | None = None, limit: int = 50) -> List[Job]:
        return await self.query_jobs(folder_id=folder_id, state="Faulted", limit=limit)

    async def summarize_folder(self, folder_id: int) -> FolderSummary:
        robots_n = await self._count(
            f"/odata/Robots/UiPath.Server.Configuration.OData.GetRobotsFromFolder(folderId={folder_id})"
        )
        queues_n = await self._count("/odata/QueueDefinitions", folder_id=folder_id)
        releases_n = await self._count("/odata/Releases", folder_id=folder_id)
        jm = await self.compute_job_metrics(folder_id=folder_id)
        folder_r = await self._call("GET", f"/odata/Folders({folder_id})")

        return FolderSummary(
            folder_id=folder_id,
            folder_name=folder_r.get("DisplayName", "Unknown"),
            jobs={
                "Pending": jm.pending,
                "Running": jm.running,
                "Successful": jm.successful,
                "Faulted": jm.faulted,
                "Stopped": jm.stopped,
            },
            total_jobs=jm.total,
            queues=queues_n,
            releases=releases_n,
            robots=robots_n,
        )

    async def get_dashboard(self, *, folder_id: int | None = None) -> Dict[str, Any]:
        jm = await self.compute_job_metrics(folder_id=folder_id)
        return {"job_metrics": jm.model_dump()}

    async def analyze_process(self, process_name: str, *, folder_id: int | None = None, depth: int = 100) -> Dict[str, Any]:
        jobs = await self.query_jobs(folder_id=folder_id, release_name=process_name, limit=depth)
        if not jobs:
            return {"process": process_name, "success_rate_pct": 0, "analyzed": 0}
        finished = [j for j in jobs if j.EndTime and j.StartTime]
        ok = [j for j in finished if j.State == "Successful"]
        rate = round(len(ok) / len(finished) * 100, 1) if finished else 0
        return {"process": process_name, "success_rate_pct": rate, "analyzed": len(jobs), "successful": len(ok)}

    async def count_entities(self) -> Dict[str, int]:
        return {
            "processes": await self._count("/odata/Releases"),
            "assets": await self._count("/odata/Assets"),
            "queues": await self._count("/odata/QueueDefinitions"),
            "schedules": await self._count("/odata/ProcessSchedules"),
        }

    async def aggregate_session_states(self) -> Dict[str, int]:
        sessions = await self.list_sessions(limit=500)
        buckets: Dict[str, int] = {}
        for s in sessions:
            key = s.State or "Unknown"
            buckets[key] = buckets.get(key, 0) + 1
        return buckets

    # ── Lifecycle ───────────────────────────────────────────

    async def close(self) -> None:
        await self._http.aclose()
