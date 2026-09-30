from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.db import queries
from app.db.errors import DbError
from app.db.pool import Db2Pool
from app.logging_setup import current_request_id
from app.routes.deps import get_pool

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


@router.get("/readyz")
def readyz(pool: Db2Pool = Depends(get_pool)):
    try:
        with pool.connection() as conn:
            queries.ping(conn)
    except DbError as exc:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "error": "db_error",
                "sqlcode": exc.sqlcode,
                "sqlstate": exc.sqlstate,
                "request_id": current_request_id(),
            },
        )
    return {"status": "ready"}


@router.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
