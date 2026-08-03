"""Startup entrypoint for the Block 4 (RAG service) container.

Owned by this repo (docs/spec.md Section 1), not genai-block4-rag-eval's
own - it doesn't have a Dockerfile or container entrypoint of its own
today.

Runs Block 4's own idempotent run_all.py (check_connection ->
create_index -> ingest -> verify) only when the Pinecone index is found
empty or missing, then starts the real server - not unconditionally on
every start. Re-running ingest.py's delete-and-reload every single
container start would redo real, paid Anthropic embedding/Pinecone
upsert work even when the index is already correctly populated from a
prior run; checking first avoids that cost and the extra startup time,
while still bootstrapping automatically the first time (this repo's
decision on the open follow-up in docs/spec.md/docs/tasks.md - see this
phase's PR description for the reasoning and its limits).
"""
import os
import subprocess
import sys

from pinecone import Pinecone
from pinecone.exceptions import NotFoundException

APP_DIR = "/app"


def index_is_populated() -> bool:
    api_key = os.environ.get("PINECONE_API_KEY")
    index_name = os.environ.get("PINECONE_INDEX_NAME")
    if not api_key or not index_name:
        return False

    pc = Pinecone(api_key=api_key)
    try:
        pc.describe_index(index_name)
    except NotFoundException:
        return False

    index = pc.Index(name=index_name)
    stats = index.describe_index_stats()
    return any(namespace.vector_count > 0 for namespace in stats.namespaces.values())


def main() -> None:
    os.chdir(APP_DIR)

    if index_is_populated():
        print("[block4-entrypoint] Pinecone index already populated - skipping run_all.py.")
    else:
        print("[block4-entrypoint] Pinecone index empty or missing - running run_all.py.")
        result = subprocess.run([sys.executable, "scripts/run_all.py"])
        if result.returncode != 0:
            print("[block4-entrypoint] run_all.py failed - refusing to start with an unverified index.")
            sys.exit(result.returncode)

    os.execvp("uvicorn", ["uvicorn", "scripts.api:app", "--host", "0.0.0.0", "--port", "8000"])


if __name__ == "__main__":
    main()
