"""Top up low INVENTORY rows so long load-generator runs don't drain stock.

Usage (same DB2_* environment variables as the API server):
    python loadgen/restock.py                      # +200 units where quantity < 20
    python loadgen/restock.py --below 50 --add 500
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ibm_db  # noqa: E402

from app.config import load_settings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--below", type=int, default=20, help="restock products with fewer units than this")
    parser.add_argument("--add", type=int, default=200, help="units to add to each such product")
    args = parser.parse_args()

    conn = ibm_db.connect(load_settings().dsn, "", "")
    try:
        stmt = ibm_db.prepare(
            conn,
            "UPDATE COMMERCE.INVENTORY SET quantity = quantity + ?, updated_at = CURRENT TIMESTAMP "
            "WHERE quantity < ?",
        )
        ibm_db.execute(stmt, (args.add, args.below))
        print(f"restocked {ibm_db.num_rows(stmt)} products (+{args.add} where quantity < {args.below})")
    finally:
        ibm_db.close(conn)


if __name__ == "__main__":
    main()
