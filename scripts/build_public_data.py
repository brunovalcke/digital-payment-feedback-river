#!/usr/bin/env python3
"""Build privacy-safe JSON consumed by the static dashboard."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from feedback_river import build_payload, load_source, transform


def main() -> None:
    output = Path(os.environ.get("PUBLIC_DATA", "public/data.json"))
    records = transform(load_source(), os.environ.get("ANONYMIZATION_SALT", "feedback-river-public-v1"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build_payload(records), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"Wrote {len(records)} anonymized records to {output}")


if __name__ == "__main__":
    main()
