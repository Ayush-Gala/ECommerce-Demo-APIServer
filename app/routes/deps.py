from fastapi import Request

from app.db.pool import Db2Pool


async def get_pool(request: Request) -> Db2Pool:
    return request.app.state.pool
