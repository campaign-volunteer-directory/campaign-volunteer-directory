#!/bin/bash
set -euo pipefail

git add -A docs/data

# Only commit when the index actually changed (the updated_at line changes
# every run and is rewritten with a commit-stable value; skip commits caused
# solely by timestamp churn).
CHANGED=false
git diff --cached --quiet -I '"updated_at":' -- docs/data/candidates.json || CHANGED=true
git diff --cached --quiet -- docs/data/sync-meta.json || CHANGED=true

if [ "$CHANGED" = false ]; then
    echo "No real changes; skipping commit"
    exit 0
fi

# Stamp the index with the commit time so the site can show freshness.
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
python3 - "$NOW" <<'EOF'
import json, sys
from pathlib import Path
p = Path("docs/data/candidates.json")
data = json.loads(p.read_text())
data["updated_at"] = sys.argv[1]
p.write_text(json.dumps(data, indent=1, ensure_ascii=False))
EOF
git add -A docs/data

git config user.name "campaign-volunteer-directory"
git config user.email "campaign-volunteer-directory@users.noreply.github.com"

git commit -m "Update candidate directory from source sheet [skip ci]"
git push
echo "Pushed $(git rev-parse --short HEAD)"
