# This repo's own app (Phase 1's entry point). Built on requirements.txt's
# currently-pinned genai-block6-multiagent commit - see requirements.txt's
# own comment and this phase's PR description for why that pin is still
# provisional (points at an unmerged packaging PR branch, not that repo's
# main).
FROM python:3.11-slim

# git is needed at build time only, for pip to clone the git+https-pinned
# block6_multiagent dependency below.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# Non-root: uvicorn only needs to bind 8000 (non-privileged, no root
# required) and read its own already-installed code - no reason for the
# request-handling process itself to run as root.
RUN groupadd --system app && useradd --system --gid app --home /app app \
    && chown -R app:app /app
USER app

EXPOSE 8000
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
