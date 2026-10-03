#!/usr/bin/env bash
#
# Export MiniSuper data to a Django fixture that can be imported on the live
# server with `manage.py loaddata`.
#
# Usage:
#   ./scripts/export_data.sh                 # -> backups/minisuper_data_YYYYMMDD.json
#   ./scripts/export_data.sh /tmp/data.json  # -> explicit path
#
# Reads the same .env as manage.py, so it exports whatever database the project
# is currently pointed at (PostgreSQL when DB_NAME is set, otherwise SQLite).
#
# Excluded models are (re)created automatically by `manage.py migrate` on the
# target, so importing them would only cause primary-key clashes:
#   contenttypes, auth.permission, admin.logentry, sessions
# auth.user / auth.group ARE included (with password hashes and role links) so
# logins keep working after the import.
set -euo pipefail

cd "$(dirname "$0")/.."

# Prefer the project virtualenv; fall back to whatever python3 is on PATH.
PYTHON="${PYTHON:-../venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
  PYTHON="python3"
fi

STAMP="$(date +%Y%m%d)"
OUT="${1:-backups/minisuper_data_${STAMP}.json}"
mkdir -p "$(dirname "$OUT")"

"$PYTHON" manage.py dumpdata \
  --natural-foreign \
  --indent 2 \
  --exclude contenttypes \
  --exclude auth.permission \
  --exclude admin.logentry \
  --exclude sessions \
  --output "$OUT"

echo "Wrote $OUT"
echo "Import on the live server (after 'manage.py migrate') with:"
echo "  python manage.py loaddata $(basename "$OUT")"
