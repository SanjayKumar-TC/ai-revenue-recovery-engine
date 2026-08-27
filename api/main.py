"""M8 FastAPI application: HTTP transport over the frozen M3–M7 pipeline."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.pipeline import (
    UnknownFailureTypeError,
    fetch_audit_records,
    run_decide_pipeline,
)
from api.schemas import (
    AuditLookupResponse,
    DecideRequest,
    DecideResponse,
    HealthResponse,
)
from ml.audit.audit_writer import DEFAULT_DB_PATH
from ml.decision.decision_engine import load_model

_GENERIC_INTERNAL_ERROR = {"detail": "Internal server error"}


def create_app(audit_db_path: str | None = None, model_pipeline=None) -> FastAPI:
    application = FastAPI(title="AI Revenue Recovery Engine", version="m8")
    application.state.audit_db_path = audit_db_path or DEFAULT_DB_PATH
    if model_pipeline is None:
        pipeline, _err = load_model()
        application.state.model_pipeline = pipeline
    else:
        application.state.model_pipeline = model_pipeline

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        if isinstance(exc, (StarletteHTTPException, RequestValidationError, HTTPException)):
            raise exc
        return JSONResponse(status_code=500, content=_GENERIC_INTERNAL_ERROR)

    @application.get("/health", response_model=HealthResponse)
    def health():
        return {"status": "ok"}

    @application.post("/decide", response_model=DecideResponse)
    def decide(body: DecideRequest, request: Request):
        try:
            result = run_decide_pipeline(
                body.model_dump(),
                model_pipeline=request.app.state.model_pipeline,
                db_path=request.app.state.audit_db_path,
            )
        except UnknownFailureTypeError:
            raise HTTPException(status_code=400, detail="Unknown failure_type")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=500, detail="Internal server error")
        return result

    @application.get("/audit/{transaction_id}", response_model=AuditLookupResponse)
    def get_audit(transaction_id: str, request: Request):
        try:
            records = fetch_audit_records(
                transaction_id,
                db_path=request.app.state.audit_db_path,
            )
        except Exception:
            raise HTTPException(status_code=500, detail="Internal server error")
        if not records:
            raise HTTPException(status_code=404, detail="Not found")
        return {
            "transaction_id": transaction_id,
            "records": records,
        }

    return application


app = create_app()
