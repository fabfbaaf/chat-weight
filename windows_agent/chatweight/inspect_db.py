from __future__ import annotations

import argparse
from pathlib import Path

from .db import ChatWeightDb


def main(argv=None):
    p = argparse.ArgumentParser(description="Show recent ChatWeight messages")
    p.add_argument("--db", default="chatweight.db")
    p.add_argument("--limit", type=int, default=30)
    args = p.parse_args(argv)
    db = ChatWeightDb(Path(args.db))
    try:
        print(f"messages: {db.message_count()}")
        for r in reversed(db.recent_messages(args.limit)):
            print(
                f"{r['captured_at']}  [{r['conversation_title']}] "
                f"{r['sender_name'] or r['direction']}: {r['text'] or ''}"
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
