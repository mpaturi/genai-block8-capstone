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
from pinecone.exceptions import NotFoundException, PineconeException

APP_DIR = "/app"

# Block 4's scripts/ directory isn't a package (no __init__.py) - its own
# entry points (run_all.py, verify.py) rely on being run directly, which
# adds their own directory to sys.path automatically. This entrypoint
# lives outside that directory (COPY'd to /entrypoint.py, not into
# APP_DIR/scripts), so the same thing is done explicitly here to reuse
# Block 4's own NAMESPACE/RECORDS_PATH/chunk_all_records rather than
# redeclaring them and risking drift from Block 4's real code.
sys.path.insert(0, os.path.join(APP_DIR, "scripts"))
from chunk_records import chunk_all_records  # noqa: E402
from ingest import NAMESPACE, RECORDS_PATH  # noqa: E402


def index_is_populated() -> bool:
    api_key = os.environ.get("PINECONE_API_KEY")
    index_name = os.environ.get("PINECONE_INDEX_NAME")
    if not api_key or not index_name:
        return False

    pc = Pinecone(api_key=api_key)
    try:
        pc.describe_index(index_name)
        index = pc.Index(name=index_name)
        stats = index.describe_index_stats()
    except NotFoundException:
        return False
    except PineconeException as exc:
        # Covers everything else Pinecone can raise here (bad API key,
        # unreachable control-plane, a data-plane blip on
        # describe_index_stats(), a still-initializing index, etc.) -
        # NotFoundException above is the only outcome that should trigger
        # a bootstrap; anything else is a real problem the caller needs to
        # fix, not something run_all.py can paper over, so this fails the
        # same way run_all.py failing does: a one-line diagnostic and a
        # non-zero exit, never a raw traceback.
        print(f"[block4-entrypoint] Could not reach Pinecone - check PINECONE_API_KEY is valid ({type(exc).__name__}).")
        sys.exit(1)

    # Block 4 ingests exclusively into the "patients" namespace
    # (scripts/ingest.py's NAMESPACE) - checking whether *any* namespace
    # has vectors would also read a half-finished ingest, or an index
    # shared with something else, as "populated". Comparing against the
    # expected chunk count (not just "greater than zero") is the same
    # check scripts/verify.py's get_vector_count()/check_chunk_count()
    # already do - reused here via the same NAMESPACE/RECORDS_PATH/
    # chunk_all_records rather than reinvented, so this repo's bootstrap
    # gate and Block 4's own correctness check can never silently drift
    # apart.
    namespace_stats = stats.namespaces.get(NAMESPACE)
    actual_count = namespace_stats.vector_count if namespace_stats else 0
    expected_count = len(chunk_all_records(RECORDS_PATH))
    return actual_count == expected_count


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

    # os.execvp() replaces this process image outright - unlike sys.exit()
    # (the error paths above, in index_is_populated() and here), it does
    # NOT run normal interpreter shutdown, so stdout's buffered content
    # (both this file's own print()s above, whichever branch ran) would
    # otherwise be silently discarded instead of ever reaching
    # `docker compose logs` - confirmed live: two independent cold starts
    # both showed uvicorn's own output but neither of this function's
    # print()s. One flush right here, not flush=True scattered across
    # each print() call above, so it still catches whatever's pending
    # regardless of which branch got here - including a future branch
    # added here later that nobody remembers to annotate individually.
    sys.stdout.flush()
    os.execvp("uvicorn", ["uvicorn", "scripts.api:app", "--host", "0.0.0.0", "--port", "8000"])


if __name__ == "__main__":
    main()
