from fastapi import APIRouter, Depends, Query

from app.db import queries
from app.db.pool import Db2Pool
from app.routes.deps import get_pool

router = APIRouter(prefix="/api", tags=["customers"])


@router.get("/customers")
def list_customers(limit: int = Query(50, ge=1, le=1000), pool: Db2Pool = Depends(get_pool)):
    with pool.connection() as conn:
        items = queries.list_customers(conn, limit)
    return {"items": items}
