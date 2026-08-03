"""FastAPI entry point exposing the assembled multi-agent stack as
POST /query (docs/spec.md Section 3).

Named `app/`, not `scripts/` - genai-block6-multiagent's own pip-installed
package is itself named `scripts` (its own repo's directory name), so this
repo's own entry point package needs a different name to avoid the two
colliding under the same top-level import name once both are installed
side by side.

Run with: uvicorn app.api:app --reload (from the repo root).
"""
import logging

from block5_agent.schemas import QuestionInput
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import field_validator
from scripts.orchestrator import run_multi_agent_async

app = FastAPI()
logger = logging.getLogger(__name__)

# Plain-language, never a raw exception message or stack trace - this is
# the outermost layer a user touches, one level past Block 6's own
# internal safety net (docs/spec.md's failure-handling section).
SERVICE_UNAVAILABLE_MESSAGE = (
    "The multi-agent service is temporarily unavailable. Please try again shortly."
)


class QueryRequest(QuestionInput):
    """QuestionInput's fields, plus this repo's own blank-string check.

    QuestionInput itself (Block 5's schema, reused as-is) has no such
    check - every value crossing this repo's own boundary must be
    validated before use, per this project's input-validation rule.
    """

    @field_validator("condition", "lab", "drug_a", "drug_b")
    @classmethod
    def field_not_blank(cls, value: str, info) -> str:
        if not value.strip():
            raise ValueError(f"{info.field_name} must not be empty or whitespace-only")
        return value


@app.post("/query")
async def query(request: QueryRequest):
    question = QuestionInput(**request.model_dump())
    try:
        return await run_multi_agent_async(question)
    except Exception as exc:
        # Full traceback goes to the server log; the response body stays
        # generic - matching genai-block4-rag-eval's own scripts/api.py
        # convention of {"error": ..., "detail": type(e).__name__}.
        logger.exception("run_multi_agent_async failed")
        return JSONResponse(
            status_code=503,
            content={"error": SERVICE_UNAVAILABLE_MESSAGE, "detail": type(exc).__name__},
        )
