"""Contract tests for app/api.py's /query endpoint (docs/spec.md Section 3).

Block 6 is mocked/stubbed entirely for this phase - no live LLM, Neo4j, or
Pinecone calls, no containers. These tests only prove this repo's own
entry point wires into run_multi_agent_async correctly and handles its
failure the way the spec's failure-handling section requires, not that
Block 6 itself works (that's proven in Block 6's own repo).
"""
import asyncio

import pytest
from fastapi.testclient import TestClient

from app.api import SERVICE_UNAVAILABLE_MESSAGE, app
from scripts.schemas import Citation, MultiAgentAnswer

client = TestClient(app)

VALID_QUESTION_PAYLOAD = {
    "condition": "Type 2 diabetes",
    "lab": "HbA1c",
    "comparison": "above",
    "value": 8.0,
    "drug_a": "metformin",
    "drug_b": "insulin",
}

FAKE_ANSWER = MultiAgentAnswer(
    question=(
        "Of patients with Type 2 diabetes and HbA1c > 8, how many are on "
        "metformin vs. insulin?"
    ),
    answer="42 patients match; 20 on metformin, 15 on insulin.",
    total_patients=42,
    drug_a_count=20,
    drug_b_count=15,
    confidence="high",
    mode="reconciled",
    citations=[Citation(patient_id=1, snippet="stable on metformin", source="clinical")],
    caveat=None,
    discrepancy_flag=False,
)


def test_query_returns_structured_answer_for_valid_question(monkeypatch):
    async def fake_run_multi_agent_async(question):
        # Exercises the actual passthrough behavior: request straight
        # through to run_multi_agent_async, no re-derivation step in
        # between to silently drop or mangle a field.
        assert question.condition == VALID_QUESTION_PAYLOAD["condition"]
        assert question.lab == VALID_QUESTION_PAYLOAD["lab"]
        assert question.comparison == VALID_QUESTION_PAYLOAD["comparison"]
        assert question.value == VALID_QUESTION_PAYLOAD["value"]
        assert question.drug_a == VALID_QUESTION_PAYLOAD["drug_a"]
        assert question.drug_b == VALID_QUESTION_PAYLOAD["drug_b"]
        return FAKE_ANSWER

    monkeypatch.setattr("app.api.run_multi_agent_async", fake_run_multi_agent_async)

    response = client.post("/query", json=VALID_QUESTION_PAYLOAD)

    assert response.status_code == 200
    body = response.json()
    assert body["total_patients"] == 42
    assert body["drug_a_count"] == 20
    assert body["drug_b_count"] == 15
    assert body["confidence"] == "high"
    assert body["mode"] == "reconciled"
    assert body["citations"][0]["patient_id"] == 1
    # X-Answer-Mode is set on every 200, not just degraded ones - simpler
    # than conditional logic, and a monitor can key off the header value
    # directly without parsing the body.
    assert response.headers["X-Answer-Mode"] == "reconciled"


BOTH_FAILED_ANSWER = MultiAgentAnswer(
    question=(
        "Of patients with Type 2 diabetes and HbA1c > 8, how many are on "
        "metformin vs. insulin?"
    ),
    answer=(
        "Both the clinical evidence agent and the cohort enumeration agent "
        "were unable to answer this question."
    ),
    total_patients=0,
    drug_a_count=0,
    drug_b_count=0,
    confidence="low",
    mode="both_failed",
    citations=[],
    caveat=None,
    discrepancy_flag=False,
)


def test_query_returns_503_when_block6_reports_both_failed_mode(monkeypatch):
    # Block 6 never raises by contract - a totally dead backend (Neo4j and
    # RAG both unreachable) instead returns a fully-formed MultiAgentAnswer
    # with mode="both_failed". Returned verbatim, that response is
    # byte-identical to a legitimate "no patients matched" 200. This proves
    # the entry point inspects mode itself rather than trusting a 200
    # response just because Block 6 didn't raise.
    async def fake_run_multi_agent_async(question):
        return BOTH_FAILED_ANSWER

    monkeypatch.setattr("app.api.run_multi_agent_async", fake_run_multi_agent_async)

    response = client.post("/query", json=VALID_QUESTION_PAYLOAD)

    assert response.status_code == 503
    assert response.json() == {"error": SERVICE_UNAVAILABLE_MESSAGE}


def test_query_returns_503_not_a_raw_exception_when_block6_raises(monkeypatch):
    # Block 6's run_multi_agent_async is documented to never raise - every
    # failure mode degrades to a fully-formed MultiAgentAnswer internally.
    # This simulates it raising anyway (a bug, or Block 6 being entirely
    # unreachable), proving this repo's own outer try/except - the last
    # line of defense a user actually touches - degrades cleanly instead
    # of leaking a stack trace (docs/spec.md's failure-handling section).
    async def fake_run_multi_agent_async(question):
        raise ConnectionError("Neo4j unreachable")

    monkeypatch.setattr("app.api.run_multi_agent_async", fake_run_multi_agent_async)

    response = client.post("/query", json=VALID_QUESTION_PAYLOAD)

    assert response.status_code == 503
    # Full traceback goes to the server log only (see logger.exception in
    # app/api.py) - the response body itself must not leak an internal
    # exception class name like "ConnectionError" or "AuthenticationError"
    # to the caller, the outermost boundary a user actually touches.
    assert response.json() == {"error": SERVICE_UNAVAILABLE_MESSAGE}


def test_query_returns_503_when_run_multi_agent_async_hangs_past_the_timeout(monkeypatch):
    # Nothing otherwise bounds total request time: Block 6's own 150s
    # branch ceiling only covers the clinical/cohort branches, not
    # reconcile_node (which runs after them, and can itself call the
    # live, unbounded get_known_vocabulary() Cypher query). The app-level
    # timeout is shortened here so the test doesn't wait the real
    # production number of seconds - this proves the wait_for wrapper
    # itself converts a hang into a bounded 503, not that the production
    # timeout value is reachable inside a test.
    async def hanging_run_multi_agent_async(question):
        await asyncio.sleep(2)
        return FAKE_ANSWER

    monkeypatch.setattr("app.api.run_multi_agent_async", hanging_run_multi_agent_async)
    monkeypatch.setattr("app.api.REQUEST_TIMEOUT_SECONDS", 0.05)

    response = client.post("/query", json=VALID_QUESTION_PAYLOAD)

    assert response.status_code == 503
    assert response.json() == {"error": SERVICE_UNAVAILABLE_MESSAGE}


COHORT_ONLY_DEGRADED_ANSWER = MultiAgentAnswer(
    question=(
        "Of patients with Type 2 diabetes and HbA1c > 8, how many are on "
        "metformin vs. insulin?"
    ),
    answer=(
        "Of 30 patients with Type 2 diabetes and HbA1c above 8, 12 are on "
        "metformin and 9 are on insulin. No supporting evidence citations "
        "are available for this run because the clinical evidence agent "
        "failed."
    ),
    total_patients=30,
    drug_a_count=12,
    drug_b_count=9,
    confidence="high",
    mode="cohort_only_degraded",
    citations=[],
    caveat=None,
    discrepancy_flag=False,
)


def test_query_sets_x_answer_mode_header_on_degraded_answer(monkeypatch):
    # A degraded-but-real answer still returns 200 (it's not a service
    # outage - see the both_failed test above for that case), but a
    # monitor watching this endpoint needs to tell "fully healthy" apart
    # from "degraded but real" without parsing the JSON body on every
    # poll. The header is set unconditionally on every 200 (see the
    # reconciled-mode assertion in the happy-path test above), not just
    # on degraded ones - simpler than conditional logic, and lets a
    # monitor key off the header value directly.
    async def fake_run_multi_agent_async(question):
        return COHORT_ONLY_DEGRADED_ANSWER

    monkeypatch.setattr("app.api.run_multi_agent_async", fake_run_multi_agent_async)

    response = client.post("/query", json=VALID_QUESTION_PAYLOAD)

    assert response.status_code == 200
    assert response.headers["X-Answer-Mode"] == "cohort_only_degraded"


CLINICAL_ONLY_DEGRADED_ANSWER = MultiAgentAnswer(
    question=(
        "Of patients with Type 2 diabetes and HbA1c > 8, how many are on "
        "metformin vs. insulin?"
    ),
    answer="Of the 18 patients checked, 8 are on metformin and 6 are on insulin.",
    total_patients=18,
    drug_a_count=8,
    drug_b_count=6,
    confidence="medium",
    mode="clinical_only_degraded",
    citations=[Citation(patient_id=1, snippet="stable on metformin", source="clinical")],
    caveat=None,
    discrepancy_flag=False,
)


def test_query_sets_x_answer_mode_header_on_clinical_only_degraded_answer(monkeypatch):
    # Mirrors test_query_sets_x_answer_mode_header_on_degraded_answer
    # above, for clinical_only_degraded instead of cohort_only_degraded -
    # the two degraded modes are symmetric (one agent failed, the other's
    # real answer is used alone), so both need the same explicit coverage
    # rather than trusting that testing one proves the other.
    async def fake_run_multi_agent_async(question):
        return CLINICAL_ONLY_DEGRADED_ANSWER

    monkeypatch.setattr("app.api.run_multi_agent_async", fake_run_multi_agent_async)

    response = client.post("/query", json=VALID_QUESTION_PAYLOAD)

    assert response.status_code == 200
    assert response.headers["X-Answer-Mode"] == "clinical_only_degraded"


def test_query_rejects_blank_condition_before_calling_block6(monkeypatch):
    def fail_if_called(question):
        raise AssertionError("run_multi_agent_async should not be called for invalid input")

    monkeypatch.setattr("app.api.run_multi_agent_async", fail_if_called)

    response = client.post("/query", json={**VALID_QUESTION_PAYLOAD, "condition": "   "})

    assert response.status_code == 422


@pytest.mark.parametrize("field_name,max_length", [
    ("condition", 200),
    ("lab", 100),
    ("drug_a", 100),
    ("drug_b", 100),
])
def test_query_rejects_string_field_exceeding_max_length(monkeypatch, field_name, max_length):
    # Unbounded caller text reaches an LLM prompt on every request
    # (build_rag_query/assemble_question_text f-string these fields
    # straight in) - a max_length is the cheapest way to close that off
    # before it ever leaves this boundary.
    def fail_if_called(question):
        raise AssertionError("run_multi_agent_async should not be called for invalid input")

    monkeypatch.setattr("app.api.run_multi_agent_async", fail_if_called)

    oversized_value = "a" * (max_length + 1)
    response = client.post("/query", json={**VALID_QUESTION_PAYLOAD, field_name: oversized_value})

    assert response.status_code == 422


def test_query_rejects_value_exceeding_max_bound(monkeypatch):
    def fail_if_called(question):
        raise AssertionError("run_multi_agent_async should not be called for invalid input")

    monkeypatch.setattr("app.api.run_multi_agent_async", fail_if_called)

    response = client.post("/query", json={**VALID_QUESTION_PAYLOAD, "value": 10_001})

    assert response.status_code == 422


def test_query_rejects_negative_value(monkeypatch):
    def fail_if_called(question):
        raise AssertionError("run_multi_agent_async should not be called for invalid input")

    monkeypatch.setattr("app.api.run_multi_agent_async", fail_if_called)

    response = client.post("/query", json={**VALID_QUESTION_PAYLOAD, "value": -1})

    assert response.status_code == 422
