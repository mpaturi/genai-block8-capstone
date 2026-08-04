"""Contract tests for app/api.py's /query endpoint (docs/spec.md Section 3).

Block 6 is mocked/stubbed entirely for this phase - no live LLM, Neo4j, or
Pinecone calls, no containers. These tests only prove this repo's own
entry point wires into run_multi_agent_async correctly and handles its
failure the way the spec's failure-handling section requires, not that
Block 6 itself works (that's proven in Block 6's own repo).
"""
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


def test_query_rejects_blank_condition_before_calling_block6(monkeypatch):
    def fail_if_called(question):
        raise AssertionError("run_multi_agent_async should not be called for invalid input")

    monkeypatch.setattr("app.api.run_multi_agent_async", fail_if_called)

    response = client.post("/query", json={**VALID_QUESTION_PAYLOAD, "condition": "   "})

    assert response.status_code == 422
