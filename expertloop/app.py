from __future__ import annotations

from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .evaluator import evaluate
from .models import ReviewRequest, ValidateRequest, RunConfig, ResumeRequest
from .service import Workbench

STATIC = Path(__file__).parent / "static"


def create_app(data_dir: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.workbench = Workbench(data_dir or Path(os.getenv("EXPERTLOOP_DATA_DIR", "state")))
        yield
        app.state.workbench.shutdown()

    app = FastAPI(title="ExpertLoop", version="0.1.0", lifespan=lifespan,
                  description="Local human-in-the-loop SQL data and evaluation workbench.")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"])

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        try:
            if int(request.headers.get("content-length", "0")) > 64_000:
                return JSONResponse({"detail": "Request body is too large"}, status_code=413)
        except ValueError:
            return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if not request.url.path.startswith(("/docs", "/redoc")):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
            )
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(KeyError)
    async def not_found(request: Request, exc: KeyError):
        return JSONResponse({"detail": "Record not found"}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(request: Request, exc: ValueError):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    def bench(request: Request) -> Workbench:
        return request.app.state.workbench

    def require_write(request: Request, x_expertloop: str = Header(default="")):
        if x_expertloop != "1":
            raise HTTPException(403, "Writes require the X-ExpertLoop: 1 header")
        origin = request.headers.get("origin")
        if origin and urlsplit(origin).netloc != request.headers.get("host"):
            raise HTTPException(403, "Cross-origin writes are not allowed")

    writes = APIRouter(prefix="/api", dependencies=[Depends(require_write)])

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "expertloop", "version": "0.1.0"}

    @app.get("/api/dashboard")
    def dashboard(w: Workbench = Depends(bench)):
        return w.dashboard()

    @app.get("/api/tasks")
    def tasks(split: Literal["development", "holdout"] | None = None,
              status: str | None = None, q: str = "", w: Workbench = Depends(bench)):
        items = w.store.tasks(split)
        if status:
            items = [t for t in items if t["review_status"] == status]
        if q:
            items = [t for t in items if q.lower() in (t["question"]+" "+t["category"]+" "+t["id"]).lower()]
        return [{k: v for k, v in t.items() if k not in ("expected", "demo_bad_sql", "reference_sql")}
                for t in items]

    @app.get("/api/tasks/{task_id}")
    def task(task_id: str, w: Workbench = Depends(bench)):
        return w.preview(task_id)

    @writes.post("/tasks/{task_id}/validate")
    def validate(task_id: str, body: ValidateRequest, w: Workbench = Depends(bench)):
        return evaluate(w.store.task(task_id), body.sql, w.fixtures)

    @writes.post("/tasks/{task_id}/review")
    def review(task_id: str, body: ReviewRequest, w: Workbench = Depends(bench)):
        return w.review(task_id, body)

    @writes.post("/generate")
    def generate(w: Workbench = Depends(bench)):
        return w.generate()

    @app.get("/api/export")
    def export(format: Literal["sft", "provenance"] = "sft", w: Workbench = Depends(bench)):
        return Response(w.export(format), media_type="application/x-ndjson",
                        headers={"Content-Disposition": f'attachment; filename="expertloop-approved-{format}.jsonl"'})

    @app.get("/api/runs")
    def runs(w: Workbench = Depends(bench)):
        return [w.run_view(r["id"], full=False) for r in w.store.runs()]

    @writes.post("/runs", status_code=201)
    def run(body: RunConfig, w: Workbench = Depends(bench)):
        return w.create_run(body)

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str, w: Workbench = Depends(bench)):
        return w.run_view(run_id)

    @writes.post("/runs/{run_id}/pause")
    def pause(run_id: str, w: Workbench = Depends(bench)):
        return w.pause(run_id)

    @writes.post("/runs/{run_id}/resume")
    def resume(run_id: str, body: ResumeRequest, w: Workbench = Depends(bench)):
        return w.resume(run_id, body.extra_requests)

    @app.get("/api/runs/{run_id}/report")
    def report(run_id: str, w: Workbench = Depends(bench)):
        return Response(w.report_markdown(run_id), media_type="text/markdown",
                        headers={"Content-Disposition": f'attachment; filename="{run_id}-report.md"'})

    @app.get("/api/runs/{run_id}/artifact")
    def artifact(run_id: str, w: Workbench = Depends(bench)):
        return Response(json.dumps({"run": w.store.run(run_id), "results": w.store.results(run_id)}, indent=2),
                        media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{run_id}-artifact.json"'})

    app.include_router(writes)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    return app


app = create_app()
