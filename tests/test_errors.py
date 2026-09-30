import pytest

from app.db.errors import DbError, parse_db2_error

LOCK_TIMEOUT_MSG = (
    "[IBM][CLI Driver][DB2/LINUXX8664] SQL0911N  The current transaction has been rolled back because of a "
    'deadlock or timeout.  Reason code "68".  SQLSTATE=40001 SQLCODE=-911'
)


def test_parse_lock_timeout():
    info = parse_db2_error(LOCK_TIMEOUT_MSG)
    assert (info.sqlcode, info.sqlstate, info.reason) == (-911, "40001", 68)


def test_parse_deadlock_reason_2():
    info = parse_db2_error(LOCK_TIMEOUT_MSG.replace('"68"', '"2"'))
    assert info.reason == 2


def test_parse_sqlcode_from_message_id_when_sqlcode_missing():
    info = parse_db2_error('SQL0204N  "COMMERCE.NOPE" is an undefined name.  SQLSTATE=42704')
    assert info.sqlcode == -204
    assert info.sqlstate == "42704"
    assert info.reason is None


def test_parse_empty():
    info = parse_db2_error(None)
    assert info.sqlcode is None and info.sqlstate is None and info.reason is None


@pytest.mark.parametrize(
    "msg,expected",
    [
        ("SQL30081N  A communication error has been detected. SQLSTATE=08001 SQLCODE=-30081", True),
        ("SQL1224N  The database manager is not able to accept new requests. SQLSTATE=55032 SQLCODE=-1224", True),
        (LOCK_TIMEOUT_MSG, False),
    ],
)
def test_communication_error_classification(msg, expected):
    assert DbError("q", parse_db2_error(msg)).is_communication_error is expected
