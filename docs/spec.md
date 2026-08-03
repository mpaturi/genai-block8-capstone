# Block 8 — Capstone: Spec

`genai-block8-capstone`. Integrates the knowledge base, RAG service, and
multi-agent system into one deployed app. This document defines the
scope, architecture, and acceptance criteria the implementation must
satisfy.

## 1. Scope

This repo does not rebuild anything. Its one direct dependency is the
multi-agent system, `genai-block6-multiagent`, pinned to a specific
reviewed commit — same policy already established between Block 6 and
Block 5 (LLM03 in Block 7's `spec.md`), never a floating branch. Block 6
in turn already depends on Block 5 (vendored) and already calls the RAG
service (`genai-block4-rag-eval`) and the graph knowledge base
(`genai-block3-graph-kb`) internally as tools — Block 8 does not pin
those two independently; they arrive transitively through Block 6.

**Confirmed (traced against real code, file:line cited):** Block 6 does
not vendor or reimplement retrieval. `orchestrator.py:18` imports
`run_agent` from the `block5_agent` pip package (installed from a
pinned commit of `genai-block5-agent`, per `requirements.txt:1`). Block
5's clinical node calls `search_patients()` in `block5_agent/rag_tool.py`,
which makes a live HTTP `POST` to `f"{RAG_API_URL}/query"`
(`rag_tool.py:38-72`) — the docstring states outright that it wraps
Block 4's `POST /query` endpoint. Separately, drug counting/verification
(Role 1) and cohort enumeration (Role 2, Block 6's own
`scripts/cohort_tool.py`) both connect to Neo4j directly via the driver
(`NEO4J_URI`). So Block 6 has a **hard runtime dependency**, not a
build-time one, on both Block 4's live `/query` endpoint and a reachable
Neo4j instance.

**Confirmed on the Block 4 side:** `genai-block4-rag-eval` has a runnable
FastAPI server (`scripts/api.py`, single route `POST /query`, started
with `uvicorn scripts.api:app` from the repo root) but no Dockerfile or
container config of any kind today — it's a bare local Python process.
It needs three env vars (`PINECONE_API_KEY`, `PINECONE_INDEX_NAME`,
`ANTHROPIC_API_KEY`) and a populated Pinecone index — `api.py` does not
build the index itself, but `genai-block4-rag-eval` already has a
script that does: `run_all.py` chains `check_connection` →
`create_index` → `ingest` → `verify`, and `ingest` is delete-and-reload
idempotent, safe to run more than once. Pinecone the hosted service
stays external — nothing to be done about that — but the requirement
this repo places on anyone running it changes from "bring an
already-populated index" to "bring your own Pinecone API key," the same
low bar as the LLM API key.

The Block 4 container is built from a pinned `genai-block4-rag-eval`
commit, via a Dockerfile written and owned by this repo — not added to
Block 4's own repo, to avoid reopening an already-reviewed block. On
first startup, the container runs Block 4's own `run_all.py` against
whatever `PINECONE_API_KEY`/`PINECONE_INDEX_NAME` the caller supplies,
so a fresh clone builds and populates its own index rather than
depending on one that already exists. `RAG_API_URL` points to the
Block 4 service's in-network name.

**Confirmed on the Neo4j side:** unlike Pinecone, Neo4j is not a hosted
service here — it runs as a local Docker container
(`genai-block3-graph-kb`'s `neo4j-omop`), plain `bolt://localhost:7687`,
data persisted in a named Docker volume. Depending on that specific
local container already being up would make Block 8 fragile in any
environment other than the one it was originally set up on — so
`docker-compose.yml` gets its own Neo4j service instead, using the
confirmed-idempotent loading script
(`load_graph.py`, safe to re-run, `MERGE`-based) from a pinned Block 3
commit to populate it fresh. Same pattern as the Block 4 decision:
Dockerfile/compose config for the dependency lives in this repo, not
added to Block 3's.

So `docker-compose.yml` needs three services: the Block 8 app container,
a Block 4 container (built from a pinned commit, Dockerfile owned by
this repo), and a Neo4j container seeded by re-running Block 3's pinned,
idempotent `load_graph.py` on first startup.

**Version bumps:** the three pins don't all live in the same place, so
they don't all bump the same way. Block 6's pin lives in this repo's
dependency file (pip), bumped the same way the Block 6→Block 5 pin was
already handled — a one-line change, tested, committed. Block 4 and
Block 3's pins live inside their respective Dockerfiles/compose config,
since they're built as containers here rather than installed as
packages — bumping either means updating the pinned commit reference
where the Dockerfile checks it out or clones it, then rebuilding and
re-running the integration tests before merging, since a stale
Dockerfile-level pin won't surface as a dependency-resolution error the
way a stale pip pin would.

This repo's own code is the glue: an entry point, deployment config,
CI/CD, and the observability layer. No new agent logic, no new tools, no
new prompts.

## 2. What "done" looks like

Matches the block's acceptance criteria directly:

- Runs end-to-end from one command (`docker-compose up`) — a
  reproducible container, not a public URL. Anyone can clone the repo
  and get the identical running app on their own machine. No hosting
  cost, no public exposure of an app whose threat model just documented
  its own risks.
- CI/CD (GitHub Actions) runs two things on every push, and they prove
  two different claims: Block 5 and Block 6's existing test and eval
  suites, re-run against this repo's pinned commits, prove that combining
  three repos' dependencies into one shared environment didn't introduce
  a version conflict or environment-specific break — not a re-litigation
  of tests that already passed in their own CI, but a check on this
  repo's specific integration. They do not prove the three services work
  together inside Block 8's assembled stack. That's what a small, new
  set of integration tests owned by this
  repo proves instead (the entry point, the call into `run_multi_agent`,
  against the real three-service compose stack). Block 8 does not
  re-test agent or retrieval logic that's already tested in its own
  repo; a regression in either layer fails the build, same rule Block 5
  already established. The reused Block 5/6 suites need no live secrets
  at all — both already run with stub/fixture flags
  (`USE_RAG_FIXTURES`, `USE_STUB_ANSWER_FN`) specifically so their CI
  makes no paid calls, confirmed in their own code, and this repo's CI
  reuses that same setup rather than inventing one. Only the new
  integration test genuinely needs live secrets (GitHub Actions repo
  secrets, not the local `.env` file), since it has to hit the real
  assembled stack — a cheap gate on every push, plus one deliberately
  reserved real test, not a tradeoff between cost and coverage.
- Observability: reuse Block 5/6's existing LangSmith tracing as-is for
  per-run traces. Add one lightweight custom view (a script or simple
  page, not a new platform) that pulls together what already exists —
  Block 5's cost/token logging, Block 7's query-size/runtime logging and
  retry/error signals — into one place. Nothing here re-implements
  tracking that already exists elsewhere; it surfaces it.
- README includes: architecture diagram, the spec (this document, linked
  or embedded), a link to Block 7's `SECURITY.md` as "the threat model,"
  and a "what I'd do next" section.
- Built spec-first (this document → plan → tasks → implementation);
  the spec, plan, tasks, and notable prompts are committed alongside
  the code, and the README carries an "AI-assisted workflow" note
  (where AI helped, where it was corrected, what was decided and why)
  — per the study plan's standing practice for every repo, not
  optional for this one.
- Repo pinned on the GitHub profile as the flagship project.

## 3. Architecture

A single entry point (FastAPI app or CLI — decided at implementation
time) that:

1. Accepts a user question.
2. Calls into Block 6's `run_multi_agent` (sync, if the entry point is a
   CLI) or `run_multi_agent_async` (if it's FastAPI) — same underlying
   call, matching whichever entry point gets chosen. It internally
   coordinates the Clinical agent (Block 5, reused as a role) and the
   Cohort agent, drawing on the RAG service (Block 4) and the graph
   knowledge base (Block 3) as Block 6 already does today.
3. Returns the reconciled `MultiAgentAnswer`.
4. Every call is traced via the existing LangSmith integration; cost,
   token usage, query-size/runtime, and retry/error signals are logged
   and readable from the custom observability view.

**Credentials:** the container reads LLM, Neo4j, and Pinecone
credentials from a `.env` file that is git-ignored, never committed.
`docker-compose.yml` references the variable names, not values; anyone
running this locally supplies their own keys. README documents exactly
which variables are required and where to get each one.

**Failure handling at this repo's own boundary:** Block 6 already has
its own internal safety net (`reconcile_node_safe`), but Block 8's entry
point is the outermost layer a user touches. It wraps its own call into
Block 6 in its own try/except — if anything escapes Block 6's safety net
anyway, or Block 6 itself is unreachable, the user gets a clear,
plain-language error, never a raw stack trace (HTTP 503 if the entry
point ends up being FastAPI; an equivalent clear failure message if it
ends up being a CLI — the exact form follows whichever the plan/tasks
stage decides). This is a new, small piece of error handling that
belongs to this repo, not a duplicate of Block 6's.

**Reproducibility caveat:** both Neo4j and Pinecone are now
self-contained in the sense that matters — Neo4j's container seeds
itself fresh from committed CSVs, and Block 4's container builds and
populates its own Pinecone index on first startup via Block 4's own
`run_all.py`, using whatever key the caller supplies. Pinecone the
hosted service is still an external dependency in the literal sense
(this repo doesn't run it), but a fresh clone with a valid Pinecone API
key gets a genuinely working stack, not a degraded one — closing the
gap where "reproducible" was previously true for Neo4j but not for
Pinecone. If the bootstrap step turns out too slow to run on every
container start, the fallback is to check once at startup whether the
index is populated and fail with a clear error if it isn't, rather than
starting and silently returning degraded retrieval results that look
like a normal "I don't know" answer.

**Test-first:** matching prior blocks' practice, the entry point's
contract tests are written before the entry point itself — given a
question, expect a structured answer; given Block 6 unreachable, expect
the defined error response, not an exception. The agent implements
against these tests, not the other way around.

This is deliberately underspecified on exact module names, log formats,
and file locations — those get confirmed against real `main` at
plan/tasks time, not guessed at here, matching the verification rule
already used in Block 7's own plan.

## 4. Explicitly out of scope

- Rebuilding or modifying Block 1–2's pipelines, Block 3's graph
  modeling, Block 4's retrieval logic, or Block 5/6's agent logic. This
  repo consumes them, pinned, as-is.
- A public-facing deployment. Reproducible container only, per the
  block's "public URL **or** reproducible container" acceptance
  criterion.
- Building a new observability platform. Reuse and surface, not
  reinvent.
- Any change to Block 7's threat model or hardening — Block 8 only
  links to and depends on Block 7's finished `SECURITY.md`.

## 5. Open follow-ups

The architecture questions raised during spec development (Block 4's
integration shape, Block 4's container status, Neo4j's hosting model,
and the OMOP CSV source data) have all been confirmed against real code
and are folded into Section 1. What remains open:

- Confirm exact CI/CD trigger scope (every push to any branch, or only
  to `main`/PRs) once GitHub Actions config is drafted. Cost is no
  longer the deciding factor for the reused Block 5/6 suites (they run
  stubbed, no live calls) — only the new integration test's live calls
  need a deliberate trigger-scope decision.
  **Resolved (Phase 3):** the reused Block 5/6 suites run on every push;
  the live-secrets integration test only runs on a push to `main` or a
  PR targeting `main` — reasoning stated in that phase's PR.
- Confirm whether the Pinecone bootstrap runs on every container start
  (simplest, safe since `ingest` is idempotent, but slower) or only
  when the index is first detected as empty (faster, more moving
  parts) — decide at Phase 2's start based on how slow a full re-ingest
  actually is in practice.
  **Resolved (Phase 2):** only when the index is found empty or missing
  — decided from an actual measurement, not an estimate: a cold
  bootstrap of the real dataset took about a minute end to end.
- Confirm whether the custom observability view is a static script run
  on demand or a small always-on page — decided at the start of the
  phase that builds it, based on how much is actually worth building
  versus just querying LangSmith directly.
  **Resolved (Phase 3):** a static script (`observability/report.py`).
  Reasoning: single-operator project, no one else needs concurrent or
  real-time access to a handful of aggregate numbers.
- Confirm the exact list of required `.env` variables once the entry
  point's actual credential needs are known.
  **Resolved (Phase 3):** documented in `README.md`'s required-variables
  table, with where to get each one.

## 6. Related documents

`docs/plan.md` breaks this scope into phases; `docs/tasks.md` breaks
each phase into concrete steps.
