# Block 4's RAG service, built from a pinned genai-block4-rag-eval commit.
# Dockerfile owned by this repo, not added to Block 4's own - avoids
# reopening an already-reviewed block (docs/spec.md Section 1).
FROM python:3.11-slim

# curl is needed at runtime for docker-compose.yml's healthcheck.
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

# Block 4's own main HEAD at the time this phase was built. Bumping this
# pin means updating the commit here, rebuilding, and re-running the
# integration tests before merging (docs/spec.md's "Version bumps").
ARG BLOCK4_COMMIT=dba8955f846d98fee70096978868bd8542bc82e3
RUN git clone https://github.com/mpaturi/genai-block4-rag-eval.git . \
    && git checkout ${BLOCK4_COMMIT}

RUN pip install --no-cache-dir -r requirements.txt

COPY docker/block4_entrypoint.py /entrypoint.py

# Non-root: uvicorn only needs to bind 8000 (non-privileged, no root
# required); everything else this container does (Pinecone/Anthropic API
# calls, reading its own git-cloned code) is a network call or a read, not
# something that needs root either.
RUN groupadd --system app && useradd --system --gid app --home /app app \
    && chown -R app:app /app
# Numeric UID, not the username - a username in USER requires the host
# system to resolve it via NSS at container-start time, which isn't
# guaranteed across every host/orchestrator; a numeric UID always works
# (hadolint DL3066). 999 is this image's actual, verified UID for `app`
# (confirmed live via `id app` against this exact useradd --system
# invocation on python:3.11-slim - not guessed), not an arbitrary choice.
USER 999

EXPOSE 8000
ENTRYPOINT ["python", "/entrypoint.py"]
