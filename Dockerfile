# This repo's own app (Phase 1's entry point). Built on requirements.txt's
# currently-pinned genai-block6-multiagent commit - pinned to that repo's
# real, merged main HEAD (see requirements.txt's own comment).
#
# docker scout cves findings, accepted (not fixed here) - see README's
# "What I'd do next" to revisit both on a future rebuild:
#
# - perl 5.40.1-6 (this base image's own Debian trixie OS layer): 2
#   CRITICAL + 2 HIGH (CVE-2026-13221, CVE-2026-12087, CVE-2026-48959,
#   CVE-2026-48962). Not installed by this project, never invoked by
#   this app at runtime. No upstream Debian fix available as of this
#   scan ("Fixed version: not fixed" for all four).
#
# - wheel 0.45.1 / jaraco-context 5.3.0 (both HIGH) were originally
#   vendored inside this base image's pre-installed setuptools 79.0.1
#   (setuptools/_vendor/*), confirmed by inspecting the built image's
#   filesystem, not assumed - neither is a direct or transitive
#   dependency from requirements.txt. The pip/setuptools/wheel/
#   jaraco-context upgrade below was added specifically to fix these
#   two, and it worked - confirmed live, re-scanned clean for both.
#
#   But upgrading pip itself (needed to pull a current setuptools) also
#   pulls pip's *own* internal vendored copies of setuptools==70.3.0 and
#   msgpack==1.1.2 (pip/_vendor/vendor.txt - bundled for pip's own
#   pkg_resources/CacheControl needs, unrelated to the setuptools this
#   Dockerfile installs itself). Both are HIGH (CVE-2025-47273,
#   GHSA-6v7p-g79w-8964) with no fix available yet - `pip install
#   --upgrade pip` already resolves to the newest release that exists,
#   and that release is what ships these. Net effect of the upgrade
#   step: two HIGH CVEs traded for two different HIGH CVEs, same total
#   count either way - kept anyway, since reverting it wouldn't remove a
#   CVE, only swap which two show up, and it's still a real fix for the
#   two it targets. Accepted for now, same as perl above.
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

# Fixes the wheel/jaraco-context CVEs noted above (upgrading setuptools
# replaces its vendored copies of both) - see that note for the full
# story, including what upgrading pip itself surfaces instead.
RUN pip install --no-cache-dir --upgrade pip setuptools wheel jaraco-context

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
