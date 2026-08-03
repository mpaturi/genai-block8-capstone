"""Integration tests against the real three-service docker-compose stack
(docs/tasks.md Phase 2) - the entry point, the call into
run_multi_agent_async, Block 4's real Pinecone-backed retrieval, and
Block 3's real Neo4j-backed cohort enumeration, all live. Phase 1's
mocked contract tests (tests/test_api.py) couldn't cover this - Block 6
was stubbed out there entirely.

Requires: `docker-compose up` already running, with a real, populated
.env (PINECONE_API_KEY/PINECONE_INDEX_NAME/ANTHROPIC_API_KEY/
NEO4J_USER/NEO4J_PASSWORD). Not collected by a plain `pytest` run (see
pytest.ini's norecursedirs) - run explicitly with:
    pytest tests/integration
"""
import requests

APP_URL = "http://localhost:8000/query"

# Block 6's own eval question q1 (docs/eval question set, mirrored here) -
# a condition/lab/drug combination known to exist in Block 3's committed
# CSV data, so this isn't a shot in the dark against unknown data.
REAL_QUESTION_PAYLOAD = {
    "condition": "Essential hypertension",
    "lab": "SBP",
    "comparison": "above",
    "value": 140,
    "drug_a": "Lisinopril",
    "drug_b": "Amlodipine",
}


def test_real_question_returns_reconciled_answer_with_real_retrieval():
    response = requests.post(APP_URL, json=REAL_QUESTION_PAYLOAD, timeout=180)

    assert response.status_code == 200
    body = response.json()

    # Proves the whole chain actually ran, not a degraded fallback that
    # would still return 200 - both agents succeeded and reconciled.
    assert body["mode"] == "reconciled"
    assert body["confidence"] == "high"
    assert body["total_patients"] > 0

    # Proves retrieval returned real results, not a well-formed "I don't
    # know" that would mask an unpopulated or unreachable Pinecone index
    # (docs/tasks.md's explicit Phase 2 concern) - a real citation, with
    # non-empty snippet text pulled from an actual patient record.
    assert len(body["citations"]) > 0
    first_citation = body["citations"][0]
    assert first_citation["snippet"].strip() != ""
    assert isinstance(first_citation["patient_id"], int)


def test_rag_service_is_directly_reachable():
    # Confirms Block 4's own container is up and its index is populated
    # enough to answer, independent of Block 8's own entry point - if
    # this fails but the /query test above passes, the failure is in
    # Block 8's own wiring, not Block 4's.
    # Mirrors block5_agent's rag_tool.py request shape exactly - a bare
    # question with no condition/lab/comparison/value metadata filter
    # gets the stricter DEFAULT_THRESHOLD and legitimately returns 0
    # results here, which would make this test meaningless (indistinguishable
    # from a real retrieval failure).
    response = requests.post(
        "http://localhost:8001/query",
        json={
            "question": "patients with essential hypertension and SBP above 140",
            "condition": "Essential hypertension",
            "lab": "SBP",
            "comparison": "above",
            "value": 140,
        },
        timeout=60,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["retrieved_count"] > 0
