from fastapi import APIRouter, Depends, Query

from app.db import queries
from app.db.pool import Db2Pool
from app.errors import ApiError
from app.routes.deps import get_pool

router = APIRouter(prefix="/api", tags=["products"])


@router.get("/products")
def list_products(
    category: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    pool: Db2Pool = Depends(get_pool),
):
    with pool.connection() as conn:
        if category:
            items = queries.list_products_by_category(conn, category, limit, offset)
        else:
            items = queries.list_products(conn, limit, offset)
    return {"items": items, "limit": limit, "offset": offset}


@router.get("/products/{id}")
def get_product(id: int, pool: Db2Pool = Depends(get_pool)):
    conn = pool.acquire()
    product = queries.get_product(conn, id)
    if product is None:
        # BUG: the connection acquired above is never released on this path, so
        # every lookup of a missing product leaks one pool connection. Once
        # POOL_MAX_SIZE connections have leaked, every DB request waits
        # POOL_ACQUIRE_TIMEOUT and then fails with 503 db_pool_timeout.
        raise ApiError(404, "product_not_found", f"product {id} not found", product_id=id)
    pool.release(conn)
    return product


@router.get("/categories")
def list_categories(pool: Db2Pool = Depends(get_pool)):
    with pool.connection() as conn:
        items = queries.list_categories(conn)
    return {"items": items}
