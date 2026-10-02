#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "[1/3] Python tests"
cd "$ROOT/windows_agent"
PYTHONPATH=. python3 -m unittest discover -s tests -v

echo "[2/3] SQLite schema"
python3 - <<PY
import sqlite3
from pathlib import Path
p = Path(r"$ROOT/sql/schema.sql")
c = sqlite3.connect(":memory:")
c.executescript(p.read_text(encoding="utf-8"))
print("SQLite schema: OK")
PY

echo "[3/3] Kotlin core compile + tests"
mkdir -p "$ROOT/.build"
kotlinc \
  "$ROOT"/core-kotlin/src/main/kotlin/io/chatweight/core/*.kt \
  "$ROOT"/core-kotlin/src/test/kotlin/io/chatweight/core/TestMain.kt \
  -include-runtime -d "$ROOT/.build/chatweight-tests.jar"
java -jar "$ROOT/.build/chatweight-tests.jar"

echo "All checks passed."
