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
`ANTHROPIC_API_KEY`) and a Pinecone index that's already been built and
populated by a separate one-time script (`create_index.py` +
`ingest.py`) — `api.py` does not build the index itself. Pinecone is a
hosted service, not something this repo containerizes; Block 8 just
needs valid credentials pointing at an already-populated index, same
category as the LLM API key.

The Block 4 container is built from a pinned `genai-block4-rag-eval`
commit, via a Dockerfile written and owned by this repo — not added to
Block 4's own repo, to avoid reopening an already-reviewed block.
`RAG_API_URL` points to the Block 4 service's in-network name.

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
  already established. CI needs its own secrets (GitHub Actions repo
  secrets, not the local `.env` file) to run live LLM/Neo4j/Pinecone
  calls — confirm and mirror whatever pattern Block 5's own CI already
  uses for this, rather than inventing a new one.
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

**Reproducibility caveat:** Neo4j is fully self-contained — its own
container, seeded fresh from committed CSVs on first startup, no
external instance required. Pinecone is the one remaining external
dependency: it's a hosted service, so the container still needs
`PINECONE_API_KEY`/`PINECONE_INDEX_NAME` pointing at an index that's
already been built and populated (a separate one-time step, not
something this repo does). If that index isn't reachable, the container
still runs but returns empty/degraded retrieval results, same as Block
4's own "returns 'I don't know' when retrieval is empty" behavior. This
is stated plainly here rather than implied.

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
  to `main`/PRs) once GitHub Actions config is drafted — factor in that
  the eval suite makes real, paid LLM calls, so triggering it on every
  branch push has a real cost, not just a time cost.
- Confirm how Block 5's own CI currently supplies secrets for its LLM/
  Neo4j/Pinecone-dependent tests, and mirror that pattern for this
  repo's GitHub Actions secrets rather than inventing a new approach.
- Confirm whether the custom observability view is a static script run
  on demand or a small always-on page — decided at the start of the
  phase that builds it, based on how much is actually worth building
  versus just querying LangSmith directly.
- Confirm the exact list of required `.env` variables once the entry
  point's actual credential needs are known.

## 6. Related documents

`docs/plan.md` breaks this scope into phases; `docs/tasks.md` breaks
each phase into concrete steps.
