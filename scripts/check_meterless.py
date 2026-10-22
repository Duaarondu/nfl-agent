"""Quick live check of the Meterless adapter: python scripts/check_meterless.py"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.adapters.meterless import MeterlessError, chat_text, list_models  # noqa: E402


def main() -> int:
    try:
        models = list_models()
        print(f"== GET /v1/models: {len(models)} model(s)")
        for model in models:
            print(f"  {model}")

        print(f"== chat ({os.environ.get('METERLESS_MODEL')})")
        reply = chat_text(
            [{"role": "user", "content": "Reply with one short sentence: who won Super Bowl LVIII?"}]
        )
        print(reply)
    except MeterlessError as error:
        print(f"FAILED: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
