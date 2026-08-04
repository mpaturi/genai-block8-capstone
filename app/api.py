"""FastAPI entry point exposing the assembled multi-agent stack as
POST /query (docs/spec.md Section 3).

Named `app/`, not `scripts/` - genai-block6-multiagent's own pip-installed
package is itself named `scripts` (its own repo's directory name), so this
repo's own entry point package needs a different name to avoid the two
colliding under the same top-level import name once both are installed
side by side.

Run with: uvicorn app.api:app --reload (from the repo root).
"""
import asyncio
import logging

from block5_agent.schemas import QuestionInput
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import Field, field_validator
from scripts.orchestrator import run_multi_agent_async

app = FastAPI()
logger = logging.getLogger(__name__)

# Plain-language, never a raw exception message or stack trace - this is
# the outermost layer a user touches, one level past Block 6's own
# internal safety net (docs/spec.md's failure-handling section).
SERVICE_UNAVAILABLE_MESSAGE = (
    "The multi-agent service is temporarily unavailable. Please try again shortly."
)

# Nothing else bounds total request time. Block 6's own 150s
# (scripts.orchestrator._BRANCH_TIMEOUT_SECONDS) covers only the
# clinical/cohort branches, which run concurrently - not reconcile_node,
# which runs after both branches join and can itself call the live
# get_known_vocabulary() Cypher query (no query-level timeout there,
# unlike the rest of scripts/cohort_tool.py - flagged upstream as a
# follow-up, not fixed here). 180s = 150s branch ceiling + a 30s buffer
# for reconcile_node's own work. That buffer is not a guarantee the
# vocabulary query finishes in 30s if it's genuinely wedged - it isn't -
# but this wait_for's outer bound still guarantees the caller gets a 503
# by 180s instead of hanging forever, which is the actual gap being
# closed here.
REQUEST_TIMEOUT_SECONDS = 180


class QueryRequest(QuestionInput):
    """QuestionInput's fields, plus this repo's own blank-string check and
    bounds on every field.

    QuestionInput itself (Block 5's schema, reused as-is) has neither -
    every value crossing this repo's own boundary must be validated
    before use, per this project's input-validation rule. Bounds matter
    here specifically because build_rag_query()/assemble_question_text()
    (block5_agent.schemas) f-string condition/lab/drug_a/drug_b straight
    into text that reaches an LLM prompt (and, for condition/lab, a
    Pinecone-embedded RAG query) on every request - an unbounded caller
    string is unbounded prompt-injection surface on every single call.

    max_length=200 for condition, 100 for lab/drug_a/drug_b: real
    clinical condition names/phrases run longer than single lab or drug
    names (e.g. compound SNOMED-style descriptions), so condition gets a
    wider allowance; both limits are many times longer than any real
    entry in Block 3's graph vocabulary (scripts.vocabulary_check),
    generous for genuine clinical terms while still closing off
    multi-megabyte payloads.

    value: ge=0 (every lab this system knows - scripts.cohort_tool's
    LAB_PROPERTY_NAMES - is a non-negative measurement; a negative value
    can never match a real patient), le=10_000 (comfortably above any
    real unit in use - HbA1c tops out near 20, systolic BP near 300,
    glucose in the low thousands mg/dL at the extreme - while still
    rejecting a deliberately absurd float before it reaches a prompt).
    """

    condition: str = Field(max_length=200)
    lab: str = Field(max_length=100)
    drug_a: str = Field(max_length=100)
    drug_b: str = Field(max_length=100)
    value: float = Field(ge=0, le=10_000)

    @field_validator("condition", "lab", "drug_a", "drug_b")
    @classmethod
    def field_not_blank(cls, value: str, info) -> str:
        if not value.strip():
            raise ValueError(f"{info.field_name} must not be empty or whitespace-only")
        return value


@app.get("/health")
async def health():
    # TEMPORARY, for temp-ci-verification only: deliberately broken to
    # prove integration-test's readiness-poll step actually fails closed
    # instead of being present-but-inert. Will be reverted before this
    # branch is discarded - never meant to reach phase-3-ci-observability-readme.
    from fastapi import HTTPException

    raise HTTPException(status_code=500, detail="deliberately broken for CI verification")


def _service_unavailable_response() -> JSONResponse:
    # Shared by both failure paths below - a dead backend must look the
    # same to the caller whether Block 6 raised outright or degraded
    # internally to mode="both_failed". No internal exception class name
    # (e.g. "AuthenticationError", "Neo4jError") goes in the body; the
    # full traceback is logged server-side instead (logger.exception),
    # since this is the outermost boundary a user actually touches.
    return JSONResponse(
        status_code=503,
        content={"error": SERVICE_UNAVAILABLE_MESSAGE},
    )


@app.post("/query")
async def query(request: QueryRequest):
    # QueryRequest already subclasses QuestionInput, so request already
    # is one - no re-derivation needed before passing it on.
    try:
        answer = await asyncio.wait_for(
            run_multi_agent_async(request), timeout=REQUEST_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        logger.error("run_multi_agent_async exceeded %ss", REQUEST_TIMEOUT_SECONDS)
        return _service_unavailable_response()
    except Exception:
        logger.exception("run_multi_agent_async failed")
        return _service_unavailable_response()

    # Live-tested (not just mocked): whether a real downstream outage
    # surfaces here as both_failed (503, this branch) or as a degraded-
    # but-real 200 depends on whether the specific question's RAG search
    # happens to find any patients before the clinical agent's own
    # RAG-first flow ever reaches Neo4j - not visible from reading this
    # file alone. Confirmed by stopping neo4j mid-session against two
    # different questions: one where RAG found zero matches (clinical
    # agent never touched Neo4j at all, only the cohort agent failed -
    # 200, clinical_only_degraded) and one matching real patients (both
    # agents needed Neo4j, both failed - 503, both_failed, this branch).
    if answer.mode == "both_failed":
        # This check guards the exact string "both_failed" only - if
        # Block 6 ever introduces a second catastrophic-failure mode
        # under a different name, this repo silently returns 200 for it
        # unless this check is updated to match.
        # Block 6 never raises by contract - a fully dead backend (Neo4j
        # and the RAG service both unreachable) instead returns a
        # fully-formed MultiAgentAnswer with mode="both_failed",
        # total_patients=0, confidence="low". Returned verbatim, that's
        # byte-identical to a legitimate "no patients matched" 200 - a
        # monitor polling this endpoint would see 200 OK while the whole
        # stack is dead. Treat it the same as the exception path above.
        logger.error("run_multi_agent_async reported mode=both_failed")
        return _service_unavailable_response()

    # clinical_only_degraded/cohort_only_degraded stay a plain 200 on
    # purpose: unlike both_failed, one agent produced a real answer
    # backed by real data (cohort_only_degraded is even confidence="high"
    # - Role 2's count is exhaustive regardless of Role 1's availability).
    # This is a degraded-but-genuine answer, not a service outage, and
    # the caller can already see the degradation via the `mode` field
    # in the response body - HTTP status here reflects "is the service
    # up", not "is this specific answer partial".
    #
    # X-Answer-Mode is set on every 200 (reconciled included), not just
    # the degraded ones - simpler than conditional logic, and it lets a
    # monitor key off the header value directly (alert on
    # clinical_only_degraded/cohort_only_degraded, ignore reconciled)
    # without parsing the JSON body on every poll. both_failed never
    # reaches here - it already returns 503 above, an unambiguous signal
    # on its own that doesn't need this header. Returned as a JSONResponse
    # rather than the bare model, since FastAPI only serializes a
    # returned Pydantic model directly - it won't attach extra headers to
    # it.
    return JSONResponse(content=answer.model_dump(), headers={"X-Answer-Mode": answer.mode})
