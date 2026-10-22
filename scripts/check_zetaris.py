"""Quick live check of the Zetaris adapter: python scripts/check_zetaris.py"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["SAMPLE_MODE"] = "false"  # always hit the live cluster

from app.adapters.zetaris import ZetarisError, run_sql  # noqa: E402

QUERIES = ["SELECT 1", "SHOW LIGHTNING DATABASES"]


def main() -> int:
    failures = 0
    for sql in QUERIES:
        print(f"== {sql}")
        try:
            result = run_sql(sql)
        except ZetarisError as error:
            failures += 1
            print(f"FAILED: {error}")
            continue
        print(json.dumps(result, indent=2, ensure_ascii=False)[:2000])
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
