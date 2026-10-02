"""Authenticated caller API and a separately scoped, live operator API."""
from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from contextlib import asynccontextmanager
import hmac
from pathlib import Path
import re
import time
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .control import ControlError
from .engine import RunManager, StopRun, check_artifact
from .policy import Policy, PolicyViolation
from .profile import TARGETS
from .schema import Action, Capability, StrictModel
from .settings import Settings
from .surface import SurfaceError


class DiscoveryRequest(StrictModel):
    goal: str = Field(min_length=6, max_length=1200)
    inputs: dict[str, Any]
    target: str | None = Field(default=None, max_length=500)


class ReplayRequest(StrictModel):
    capability: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}\.v[1-9][0-9]*$")
    inputs: dict[str, Any]
    target: str | None = Field(default=None, max_length=500)


class RevisionRequest(StrictModel):
    revision: int = Field(ge=0)


class OperatorActionRequest(RevisionRequest):
    request_id: str = Field(pattern=r"^[a-f0-9-]{32,36}$")
    action: Action


def create_api(settings: Settings | None = None, policy: Policy | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.check_api_tokens()
    manager = RunManager(settings, policy)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        cleanup = asyncio.create_task(manager.cleanup_loop())
        try:
            yield
        finally:
            cleanup.cancel()
            await asyncio.gather(cleanup, return_exceptions=True)
            await manager.close()

    app = FastAPI(title="Capability Runner", version="1.0.0", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.manager = manager
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver", "[::1]"])
    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")
    bearer = HTTPBearer(auto_error=False)
    rates = defaultdict(deque)

    def auth(role: str):
        async def authenticate(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
            expected = settings.runner_token if role == "caller" else settings.operator_token
            if credentials is None or credentials.scheme.lower() != "bearer" or not hmac.compare_digest(
                credentials.credentials, expected.get_secret_value()
            ):
                raise HTTPException(401, detail={"code": "UNAUTHORIZED"}, headers={"WWW-Authenticate": "Bearer"})
            queue = rates[role]
            now = time.monotonic()
            while queue and now - queue[0] > 60:
                queue.popleft()
            if len(queue) >= (360 if role == "operator" else 300):
                raise HTTPException(429, detail={"code": "RATE_LIMITED"}, headers={"Retry-After": "10"})
            queue.append(now)
            return role
        return authenticate

    caller = auth("caller")
    operator = auth("operator")

    def get_run(run_id: str):
        if re.fullmatch(r"[a-f0-9]{32}", run_id) is None:
            raise HTTPException(404, detail={"code": "RUN_NOT_FOUND"})
        try:
            return manager.get(run_id)
        except KeyError as error:
            raise HTTPException(404, detail={"code": "RUN_NOT_FOUND"}) from error

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"code": "CROSS_ORIGIN_DENIED"}, status_code=403)
        if request.method in {"POST", "PUT", "PATCH"}:
            try:
                size = int(request.headers["content-length"])
            except (KeyError, ValueError):
                return JSONResponse({"code": "CONTENT_LENGTH_REQUIRED"}, status_code=411)
            if size < 0 or size > 65_536:
                return JSONResponse({"code": "BODY_TOO_LARGE"}, status_code=413)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; "
            "connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError):
        # FastAPI's default error embeds input values. Do not return or log them.
        return JSONResponse({"code": "INVALID_REQUEST", "issue_count": len(error.errors())}, status_code=422)

    @app.exception_handler(ValueError)
    async def invalid_contract(request: Request, error: ValueError):
        return JSONResponse({"code": "INVALID_CONTRACT_OR_INPUT"}, status_code=422)

    @app.exception_handler(PolicyViolation)
    async def policy_error(request: Request, error: PolicyViolation):
        return JSONResponse({"code": error.code}, status_code=403)

    @app.exception_handler(ControlError)
    async def control_error(request: Request, error: ControlError):
        return JSONResponse({"code": error.code}, status_code=409)

    @app.exception_handler(SurfaceError)
    async def surface_error(request: Request, error: SurfaceError):
        return JSONResponse({"code": error.code}, status_code=409)

    @app.exception_handler(StopRun)
    async def stopped(request: Request, error: StopRun):
        return JSONResponse({"code": error.code}, status_code=429 if error.code == "CAPACITY_EXCEEDED" else 409)

    @app.get("/health", tags=["system"])
    async def health():
        return {"status": "ok", "version": "1.0.0"}

    @app.get("/", include_in_schema=False)
    async def console():
        return FileResponse(static / "index.html")

    @app.get("/api/schema", dependencies=[Depends(caller)], tags=["capabilities"])
    async def schema():
        return Capability.model_json_schema()

    @app.get("/api/capabilities", dependencies=[Depends(caller)], tags=["capabilities"])
    async def capabilities():
        return {"capabilities": [{"id": f"{item.name}.v{item.revision}", "inputs": item.inputs,
                                  "outputs": item.outputs, "checkpoint": item.checkpoint} for item in manager.catalog.all()]}

    @app.post("/api/capabilities", status_code=201, dependencies=[Depends(caller)], tags=["capabilities"])
    async def import_capability(capability: Capability):
        check_artifact(capability, manager.policy, settings.target_origin)
        return {"id": manager.catalog.save(capability)}

    @app.get("/api/capabilities/{artifact_id}", response_model=Capability, dependencies=[Depends(caller)], tags=["capabilities"])
    async def get_capability(artifact_id: str):
        try:
            return manager.catalog.load(artifact_id)
        except FileNotFoundError as error:
            raise HTTPException(404, detail={"code": "CAPABILITY_NOT_FOUND"}) from error

    @app.post("/api/discoveries", status_code=202, dependencies=[Depends(caller)], tags=["runs"])
    async def discover(body: DiscoveryRequest):
        run = manager.start("discovery", body.inputs, body.target, goal=body.goal)
        return {"run_id": run.id, "status": "accepted"}

    @app.post("/api/replays", status_code=202, dependencies=[Depends(caller)], tags=["runs"])
    async def replay(body: ReplayRequest):
        try:
            capability = manager.catalog.load(body.capability)
        except FileNotFoundError as error:
            raise HTTPException(404, detail={"code": "CAPABILITY_NOT_FOUND"}) from error
        run = manager.start("replay", body.inputs, body.target, capability=capability)
        return {"run_id": run.id, "status": "accepted"}

    @app.get("/api/runs/{run_id}", dependencies=[Depends(caller)], tags=["runs"])
    async def run_status(run_id: str):
        return await get_run(run_id).view()

    @app.post("/api/runs/{run_id}/cancel", dependencies=[Depends(caller)], tags=["runs"])
    async def cancel(run_id: str):
        get_run(run_id)
        await manager.cancel(run_id)
        return {"status": "cancelled"}

    @app.get("/api/operator/interventions", dependencies=[Depends(operator)], tags=["operator"])
    async def interventions():
        items = []
        for run in list(manager.runs.values()):
            view = await run.view(include_outputs=False)
            if view["control"]["state"] in {"PAUSED", "HUMAN"}:
                items.append(view)
        return {"interventions": items}

    @app.get("/api/operator/runs/{run_id}", dependencies=[Depends(operator)], tags=["operator"])
    async def operator_status(run_id: str):
        return await get_run(run_id).view(include_outputs=False)

    @app.post("/api/operator/runs/{run_id}/claim", dependencies=[Depends(operator)], tags=["operator"])
    async def claim(run_id: str, body: RevisionRequest):
        return await get_run(run_id).gate.claim(body.revision)

    @app.post("/api/operator/runs/{run_id}/renew", dependencies=[Depends(operator)], tags=["operator"])
    async def renew(run_id: str, body: RevisionRequest, x_control_token: str = Header(default="")):
        return await get_run(run_id).gate.renew(x_control_token, body.revision)

    @app.post("/api/operator/runs/{run_id}/resume", dependencies=[Depends(operator)], tags=["operator"])
    async def resume(run_id: str, body: RevisionRequest, x_control_token: str = Header(default="")):
        return await get_run(run_id).gate.resume(x_control_token, body.revision)

    @app.get("/api/operator/runs/{run_id}/screenshot", dependencies=[Depends(operator)], tags=["operator"])
    async def screenshot(run_id: str, revision: int, x_control_token: str = Header(default="")):
        run = get_run(run_id)
        content = await run.gate.read_live(x_control_token, revision, run.surface.screenshot)
        return Response(content, media_type="image/png", headers={"Cache-Control": "no-store"})

    @app.get("/api/operator/runs/{run_id}/controls", dependencies=[Depends(operator)], tags=["operator"])
    async def controls(run_id: str, revision: int, x_control_token: str = Header(default="")):
        run = get_run(run_id)
        observation = await run.gate.read_live(x_control_token, revision, run.surface.observe)
        return {"controls": [{"key": item.key, "label": TARGETS[item.key].locators[0].value,
                              "kind": TARGETS[item.key].action, "risk": TARGETS[item.key].risk,
                              "enabled": item.enabled and item.matches == 1} for item in observation.controls]}

    @app.post("/api/operator/runs/{run_id}/actions", dependencies=[Depends(operator)], tags=["operator"])
    async def human_action(run_id: str, body: OperatorActionRequest, x_control_token: str = Header(default="")):
        run = get_run(run_id)
        manager.policy.check_action(body.action, settings.target_origin, actor="human")
        return await run.gate.perform(x_control_token, body.revision, body.request_id, body.action,
                                     lambda: run.surface.act(body.action, run.inputs, actor="human"))

    @app.post("/api/operator/runs/{run_id}/cancel", dependencies=[Depends(operator)], tags=["operator"])
    async def operator_cancel(run_id: str):
        get_run(run_id)
        await manager.cancel(run_id)
        return {"status": "cancelled"}

    @app.get("/api/operator/runs/{run_id}/evidence/{name}", dependencies=[Depends(operator)], tags=["operator"])
    async def safe_evidence(run_id: str, name: str):
        run = get_run(run_id)
        if re.fullmatch(r"snapshot-[0-9]{3}\.dom\.json", name) is None:
            raise HTTPException(404, detail={"code": "EVIDENCE_NOT_FOUND"})
        path = run.audit.directory / name
        if not path.is_file() or path.is_symlink():
            raise HTTPException(404, detail={"code": "EVIDENCE_NOT_FOUND"})
        return FileResponse(path, media_type="application/json")

    return app
