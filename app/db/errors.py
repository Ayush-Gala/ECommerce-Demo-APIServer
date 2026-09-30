import re
from dataclasses import dataclass

_SQLCODE_RE = re.compile(r"SQLCODE=(-?\d+)")
_SQLMSG_RE = re.compile(r"\bSQL(\d{4,5})([NWC])\b")
_SQLSTATE_RE = re.compile(r"SQLSTATE=(\w{5})")
_REASON_RE = re.compile(r'[Rr]eason code(?:\s*=)?\s*"?(-?\d+)"?')

# SQL30081N comm error, SQL30108N client reroute, SQL1224N/SQL1229N agent gone.
COMMUNICATION_SQLCODES = {-30081, -30108, -30080, -1224, -1229}

LOCK_TIMEOUT_SQLCODE = -911


@dataclass
class Db2ErrorInfo:
    sqlcode: int | None
    sqlstate: str | None
    reason: int | None
    message: str


def parse_db2_error(message: str | None) -> Db2ErrorInfo:
    message = message or ""
    sqlcode = None
    m = _SQLCODE_RE.search(message)
    if m:
        sqlcode = int(m.group(1))
    else:
        m = _SQLMSG_RE.search(message)
        if m:
            num = int(m.group(1))
            sqlcode = num if m.group(2) == "W" else -num
    m = _SQLSTATE_RE.search(message)
    sqlstate = m.group(1) if m else None
    m = _REASON_RE.search(message)
    reason = int(m.group(1)) if m else None
    return Db2ErrorInfo(sqlcode=sqlcode, sqlstate=sqlstate, reason=reason, message=message.strip())


class DbError(Exception):
    """A Db2 error raised while running a named query."""

    def __init__(self, query: str, info: Db2ErrorInfo):
        super().__init__(f"{query}: {info.message}")
        self.query = query
        self.sqlcode = info.sqlcode
        self.sqlstate = info.sqlstate
        self.reason = info.reason
        self.message = info.message

    @property
    def is_lock_timeout(self) -> bool:
        return self.sqlcode == LOCK_TIMEOUT_SQLCODE

    @property
    def is_communication_error(self) -> bool:
        return self.sqlcode in COMMUNICATION_SQLCODES or (
            self.sqlstate is not None and self.sqlstate.startswith("08")
        )


def is_communication_error(exc: BaseException) -> bool:
    if isinstance(exc, DbError):
        return exc.is_communication_error
    info = parse_db2_error(str(exc))
    return info.sqlcode in COMMUNICATION_SQLCODES or bool(info.sqlstate and info.sqlstate.startswith("08"))
