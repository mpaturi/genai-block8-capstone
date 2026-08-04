# This repo's own app (Phase 1's entry point). Built on requirements.txt's
# currently-pinned genai-block6-multiagent commit - pinned to that repo's
# real, merged main HEAD (see requirements.txt's own comment).
FROM python:3.11-slim

# git is needed at build time only, for pip to clone the git+https-pinned
# block6_multiagent dependency below. curl is needed at runtime for
# docker-compose.yml's healthcheck (mirrors docker/block4.Dockerfile's
# same git curl pairing).
#
# Deliberately not version-pinned (hadolint DL3008 flags this): an exact
# Debian package version can disappear from the mirror by the time
# python:3.11-slim gets rebuilt, turning a routine rebuild into a broken
# build - a worse failure mode than the version drift being guarded
# against. git/curl are stable system utilities here, not
# security-sensitive libraries this repo's own threat model cares about
# pinning exactly (that's what requirements.txt's real dependency pins
# are for).
RUN apt-get update && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# Non-root: uvicorn only needs to bind 8000 (non-privileged, no root
# required) and read its own already-installed code - no reason for the
# request-handling process itself to run as root. Not switched via USER
# here, though - see docker/app_entrypoint.sh for why the container still
# starts as root and drops privileges itself at runtime instead.
RUN groupadd --system app && useradd --system --gid app --home /app app \
    && chown -R app:app /app

COPY docker/app_entrypoint.sh /app_entrypoint.sh
RUN chmod +x /app_entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app_entrypoint.sh"]
