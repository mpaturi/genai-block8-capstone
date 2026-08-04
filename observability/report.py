"""Lightweight observability view (docs/spec.md's Observability section).

Not a new platform - LangSmith already provides per-run tracing as-is
(nothing to build there, see the note this script prints). This script
only surfaces what Block 5/Block 6 already log to
data/eval/run_log.jsonl on every run_multi_agent_async call: cost, token
usage, latency, and outcome mode/confidence/discrepancy signals.

Decided as a static, run-on-demand script rather than a small always-on
page: this is a single-operator capstone project, not a multi-user
dashboard, so there's no one else who'd need concurrent or real-time
access - a page would be a second long-running service to build,
containerize, and maintain for a handful of aggregate numbers a script
already prints in under a second.

Block 7's query-size/runtime/retry signals (named in docs/spec.md as
something to surface here) are not included - confirmed against Block
7's real repo that no such logging exists yet anywhere, not even on an
unmerged branch (Block 7 is still at the spec/plan/tasks stage). Add
those columns here once Block 7 actually ships them.

Run with: python observability/report.py (from the repo root, after
data/eval/run_log.jsonl has at least one entry - i.e. after `docker-
compose up` and at least one real /query call).
"""
import json
import os
import statistics
import sys
from pathlib import Path

LOG_PATH = Path("data/eval/run_log.jsonl")

# Every field print_report() aggregates over. A run missing any of these
# (an older log format, or a run that failed before cost was recorded)
# can't be included - see _valid_runs() below.
REQUIRED_FIELDS = ("cost_usd", "tokens", "latency_ms", "mode", "confidence", "discrepancy_flag")


def load_runs(log_path: Path) -> tuple[list[dict], int]:
    """Returns (runs, total_line_count) - total_line_count is every
    non-blank line actually read, whether it parsed as JSON or not, so
    print_report() can show total-vs-usable ("N of M total") rather than
    just the post-filter count on its own.
    """
    if not log_path.exists():
        print(f"No runs logged yet - {log_path} does not exist.")
        print("Run `docker-compose up` and send at least one /query request first.")
        sys.exit(1)

    runs = []
    total_line_count = 0
    with log_path.open(encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            total_line_count += 1
            try:
                runs.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"[warn] skipping malformed line {line_number} in {log_path}")

    if not runs:
        print(f"{log_path} exists but has no valid entries yet.")
        sys.exit(1)

    return runs, total_line_count


def _valid_runs(runs: list[dict]) -> list[dict]:
    """Same tolerance load_runs() already has for malformed JSON, extended
    to individual runs missing a required field: skip with a warning and
    exclude from aggregates, rather than crashing (direct indexing) or
    silently defaulting to 0 (understates cost/token totals with no
    signal - inconsistent with how this project treats silent
    degradation everywhere else).
    """
    valid = []
    for run_number, run in enumerate(runs, start=1):
        missing_field = next((field for field in REQUIRED_FIELDS if field not in run), None)
        if missing_field is not None:
            print(f"[warn] skipping run {run_number} - missing field '{missing_field}'")
            continue
        valid.append(run)
    return valid


def print_report(runs: list[dict], total_line_count: int) -> None:
    runs = _valid_runs(runs)
    total_cost = sum(run["cost_usd"] for run in runs)
    total_tokens = sum(run["tokens"] for run in runs)
    latencies = [run["latency_ms"] for run in runs]

    mode_counts: dict[str, int] = {}
    confidence_counts: dict[str, int] = {}
    discrepancy_count = 0
    for run in runs:
        mode_counts[run["mode"]] = mode_counts.get(run["mode"], 0) + 1
        confidence_counts[run["confidence"]] = confidence_counts.get(run["confidence"], 0) + 1
        if run["discrepancy_flag"]:
            discrepancy_count += 1

    print(f"Runs logged: {len(runs)} (of {total_line_count} total)")
    print(f"Total cost:  ${total_cost:.6f}")
    print(f"Total tokens: {total_tokens}")
    print(f"Latency (ms): mean={statistics.mean(latencies):.1f}, "
          f"median={statistics.median(latencies):.1f}, max={max(latencies):.1f}")
    print(f"Mode breakdown: {mode_counts}")
    print(f"Confidence breakdown: {confidence_counts}")
    print(f"Discrepancy rate: {discrepancy_count}/{len(runs)}")

    project = os.environ.get("LANGCHAIN_PROJECT", "block8-capstone")
    print()
    print(f"Per-run traces: see LangSmith, project '{project}' (LangSmith tracing is")
    print("reused as-is - no separate trace viewer is built here).")


if __name__ == "__main__":
    print_report(*load_runs(LOG_PATH))
