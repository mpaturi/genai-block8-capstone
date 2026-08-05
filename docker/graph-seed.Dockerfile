# One-shot seeding container: re-runs Block 3's confirmed-idempotent
# load_graph.py against its committed CSVs, from a pinned
# genai-block3-graph-kb commit. Dockerfile owned by this repo, not added
# to Block 3's own (docs/spec.md Section 1). Runs to completion and exits
# every `docker-compose up` - unlike the Pinecone bootstrap, this is a
# local, MERGE-based bulk load, not paid API calls, so there's no cost
# tradeoff in re-running it every time.
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

# git is needed at build time only, to clone the pinned Block 3 commit
# below.
#
# Deliberately not version-pinned (hadolint DL3008 flags this): an exact
# Debian package version can disappear from the mirror by the time
# python:3.11-slim gets rebuilt, turning a routine rebuild into a broken
# build - a worse failure mode than the version drift being guarded
# against. git is a stable system utility here, not a security-sensitive
# library this repo's own threat model cares about pinning exactly
# (that's what requirements.txt's real dependency pins are for).
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Block 3's own main HEAD at the time this phase was built. Bumping this
# pin means updating the commit here, rebuilding, and re-running the
# integration tests before merging (docs/spec.md's "Version bumps").
ARG BLOCK3_COMMIT=aa2a2cd7354c54510334c6bf6cb7a09764cf776b
RUN git clone https://github.com/mpaturi/genai-block3-graph-kb.git . \
    && git checkout ${BLOCK3_COMMIT}

# Fixes the wheel/jaraco-context CVEs noted above (upgrading setuptools
# replaces its vendored copies of both) - see that note for the full
# story, including what upgrading pip itself surfaces instead.
RUN pip install --no-cache-dir --upgrade pip setuptools wheel jaraco-context

RUN pip install --no-cache-dir -r requirements.txt

# Non-root: load_graph.py only reads its own committed CSVs and writes to
# Neo4j over the network (via the driver) - nothing here needs root.
RUN groupadd --system app && useradd --system --gid app --home /app app \
    && chown -R app:app /app
# Numeric UID, not the username - a username in USER requires the host
# system to resolve it via NSS at container-start time, which isn't
# guaranteed across every host/orchestrator; a numeric UID always works
# (hadolint DL3066). 999 is this image's actual, verified UID for `app`
# (confirmed live via `id app` against this exact useradd --system
# invocation on python:3.11-slim - not guessed), not an arbitrary choice.
USER 999

CMD ["python", "scripts/load_graph.py"]
