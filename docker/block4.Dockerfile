# Block 4's RAG service, built from a pinned genai-block4-rag-eval commit.
# Dockerfile owned by this repo, not added to Block 4's own - avoids
# reopening an already-reviewed block (docs/spec.md Section 1).
FROM python:3.11-slim

# curl is needed at runtime for docker-compose.yml's healthcheck.
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
USER app

EXPOSE 8000
ENTRYPOINT ["python", "/entrypoint.py"]
