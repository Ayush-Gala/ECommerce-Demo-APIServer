"""Minimal in-memory stand-in for the ibm_db module.

Tests register responses keyed by a SQL fragment; the first matching fragment
(most recently registered wins) decides what execute() does.
"""

import re

SQL_ATTR_INFO_APPLNAME = 2410
SQL_AUTOCOMMIT_ON = 1
SQL_AUTOCOMMIT_OFF = 0


class _State:
    def reset(self):
        self.handlers = []
        self.executed = []
        self.calls = []
        self.connect_error = None
        self.last_conn_error = ""
        self.last_stmt_error = ""


STATE = _State()
STATE.reset()


def on(fragment, result):
    """result: list of row dicts, an int row count, an Exception, or a callable(params) returning one of those."""
    STATE.handlers.insert(0, (fragment, result))


def _norm(sql):
    return re.sub(r"\s+", " ", sql).strip()


class Conn:
    def __init__(self):
        self.options = {}
        self.closed = False


class Stmt:
    def __init__(self, conn, sql):
        self.conn = conn
        self.sql = _norm(sql)
        self.rows = []
        self.rowcount = 0
        self.error = ""


def connect(dsn, user, password):
    STATE.calls.append("connect")
    if STATE.connect_error:
        STATE.last_conn_error = STATE.connect_error
        raise Exception(STATE.connect_error)
    return Conn()


def set_option(resource, options, is_conn):
    resource.options.update(options)
    return True


def close(conn):
    STATE.calls.append("close")
    conn.closed = True
    return True


def prepare(conn, sql):
    return Stmt(conn, sql)


def execute(stmt, params=()):
    STATE.executed.append((stmt.sql, tuple(params)))
    for fragment, result in STATE.handlers:
        if _norm(fragment) in stmt.sql:
            if callable(result) and not isinstance(result, type):
                result = result(tuple(params))
            if isinstance(result, Exception):
                stmt.error = str(result)
                STATE.last_stmt_error = str(result)
                raise result
            if isinstance(result, int):
                stmt.rowcount = result
            else:
                stmt.rows = [dict(r) for r in result]
            return True
    stmt.rows = []
    stmt.rowcount = 0
    return True


def fetch_assoc(stmt):
    return stmt.rows.pop(0) if stmt.rows else False


def num_rows(stmt):
    return stmt.rowcount


def free_stmt(stmt):
    return True


def stmt_errormsg(stmt=None):
    return stmt.error if stmt is not None else STATE.last_stmt_error


def conn_errormsg(conn=None):
    return STATE.last_conn_error


def autocommit(conn, value=None):
    STATE.calls.append(f"autocommit:{value}")
    return True


def commit(conn):
    STATE.calls.append("commit")
    return True


def rollback(conn):
    STATE.calls.append("rollback")
    return True
