# Block 4's RAG service, built from a pinned genai-block4-rag-eval commit.
# Dockerfile owned by this repo, not added to Block 4's own - avoids
# reopening an already-reviewed block (docs/spec.md Section 1).
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends git \
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

EXPOSE 8000
ENTRYPOINT ["python", "/entrypoint.py"]
