"""Tests for observability/report.py's tolerance of incomplete log lines.

load_runs() already warns and skips lines that aren't valid JSON.
print_report() didn't extend that same tolerance - it indexed every
field directly (run["cost_usd"], run["mode"], etc.), so a line missing a
field (older log format, or a run that failed before cost was recorded)
crashed the whole report with KeyError.
"""
import json

from observability.report import load_runs, print_report

VALID_RUN_1 = {
    "run_id": "a",
    "question": "q1",
    "timestamp": "t1",
    "mode": "reconciled",
    "confidence": "high",
    "discrepancy_flag": False,
    "total_patients": 10,
    "latency_ms": 100.0,
    "cost_usd": 0.01,
    "tokens": 50,
}
VALID_RUN_2 = {
    "run_id": "b",
    "question": "q2",
    "timestamp": "t2",
    "mode": "cohort_only_degraded",
    "confidence": "medium",
    "discrepancy_flag": True,
    "total_patients": 5,
    "latency_ms": 200.0,
    "cost_usd": 0.02,
    "tokens": 60,
}
# cost_usd deliberately missing - simulates an older log format, or a run
# that failed before cost was recorded.
MISSING_FIELD_RUN = {
    "run_id": "c",
    "question": "q3",
    "timestamp": "t3",
    "mode": "reconciled",
    "confidence": "high",
    "discrepancy_flag": False,
    "total_patients": 3,
    "latency_ms": 150.0,
    "tokens": 40,
}


def _write_fixture(tmp_path):
    log_path = tmp_path / "run_log.jsonl"
    lines = [
        json.dumps(VALID_RUN_1),
        json.dumps(VALID_RUN_2),
        json.dumps(MISSING_FIELD_RUN),
        "{not valid json",
    ]
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return log_path


def test_print_report_skips_malformed_and_incomplete_lines(tmp_path, capsys):
    log_path = _write_fixture(tmp_path)

    runs = load_runs(log_path)
    print_report(runs)

    output = capsys.readouterr().out

    # The malformed JSON line (already load_runs()'s job) and the
    # missing-field run (this fix's job) both get a skip warning, in the
    # same shape.
    assert "[warn] skipping malformed line 4" in output
    assert "[warn] skipping run" in output
    assert "cost_usd" in output

    # Aggregates computed only from the two complete, valid runs -
    # the missing-field run's absent cost_usd must not silently default
    # to 0 and understate the total without a warning.
    assert "Runs logged: 2" in output
    assert "Total cost:  $0.030000" in output
    assert "Total tokens: 110" in output
