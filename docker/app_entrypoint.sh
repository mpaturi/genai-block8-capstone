#!/bin/sh
# Fixes ownership of the bind-mounted ./data directory at container start,
# then drops from root to the non-root `app` user before running the real
# server.
#
# This can't be done at image build time: a bind mount always reflects the
# host directory's own ownership/permissions at runtime (Docker only
# applies image-baked ownership to a *named* volume being initialized
# fresh, never to a bind mount) - confirmed live, not assumed: Docker
# Desktop presented the host's pre-existing ./data/eval (created outside
# Docker, before this bind mount existed) as owned by root:root inside the
# container regardless of what the image's build-time chown had set, and
# scripts/run_log.py's write to data/eval/run_log.jsonl failed with
# PermissionError as the non-root `app` user. Running as root only long
# enough to fix that one directory's ownership, then dropping to `app` for
# everything else, is the standard shape for this problem.
set -e

mkdir -p /app/data/eval /app/data/logs
chown -R app:app /app/data

exec su -s /bin/sh -c 'exec uvicorn app.api:app --host 0.0.0.0 --port 8000' app
