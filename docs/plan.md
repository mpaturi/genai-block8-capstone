# Block 8 — Capstone: Implementation Plan

This plan turns `docs/spec.md`'s confirmed architecture into phases.
Unlike Block 7, this is a single repo — no "which repo does this land
in" question.

## 1. Working from current main

Same verification discipline used throughout this project: at the start
of each phase, confirm `spec.md`'s code-level claims (Block 6's import
path, the `RAG_API_URL`/`NEO4J_URI` shape, Block 4's server entry point,
Block 3's loader) still match what's actually on `main` in those repos
— they were traced against real code, but time passes between spec and
build. Cosmetic drift gets noted and the phase continues; structural
drift means stopping to fix `docs/spec.md` first, per the same rule
`docs/tasks.md` will restate exactly once.

## 2. Phases

Three phases, strictly sequential — this repo doesn't have the
"independent, can happen in any order" phases Block 7 did, because each
piece here is built on top of the last.

**Phase 1 — Core app.** The entry point (FastAPI or CLI — decided at
this phase's start, not before) that accepts a question and calls
Block 6's `run_multi_agent`, pinned to a specific reviewed Block 6
commit. Its own try/except boundary around that call, returning a clear
error instead of a raw stack trace if Block 6 is unreachable or raises
past its own safety net. Contract tests written first, per the spec's
test-first rule: given a question, expect a structured answer; given
Block 6 unreachable (mocked for this phase — no containers yet), expect
the defined error response. This phase can be built and tested without
Docker at all, using a local Python environment with Block 6 installed.
Satisfies the "runs end-to-end" and "test-first" parts of the spec's
acceptance criteria, in isolation from containerization.

**Phase 2 — Containerization.** Depends on Phase 1 having merged.
Three things: a `Dockerfile` for this repo's own app (Phase 1's entry
point, built on the pinned Block 6 commit); a `Dockerfile` for Block 4,
built from a pinned `genai-block4-rag-eval` commit — written and owned
here, not added to Block 4's repo; and a Neo4j service definition seeded
on first startup by re-running Block 3's confirmed-idempotent
`load_graph.py` against a pinned Block 3 commit's committed CSVs. One
`docker-compose.yml` wires all three together, with `RAG_API_URL` and
`NEO4J_URI` pointing at the in-network service names, and credentials
read from a git-ignored `.env`. A new set of integration tests — the
ones Phase 1's mocked tests couldn't cover — run against the real
three-service stack: ask a real question, get a real answer, confirm
the whole chain works, not just Block 8's own code in isolation.
Satisfies "runs end-to-end from one command" and the "reproducible
container" acceptance criterion for real, plus the reproducibility
caveat already stated in the spec (Neo4j self-contained, Pinecone
external).

**Phase 3 — CI/CD, observability, README.** Depends on Phase 2 having
merged — CI's integration tests need the compose stack Phase 2 built,
and the README documents the finished thing, not a plan of it. GitHub
Actions workflow: re-runs Block 5 and Block 6's existing test/eval
suites against this repo's pinned commits (proving those commits are
healthy), plus Phase 2's new integration tests (proving the assembled
stack works) — trigger scope and secrets pattern confirmed against how
Block 5's own CI already does this, not invented fresh, per the spec's
open follow-ups. The lightweight observability view: reuses LangSmith
as-is, adds one small script or page surfacing Block 5's cost/token
logging and Block 7's query-size/runtime/retry signals — decided at
this phase's start whether that's a static script or a small always-on
page. README: architecture diagram, this spec and plan linked or
embedded, a link to Block 7's `SECURITY.md` as the threat model, an
"AI-assisted workflow" note, and "what I'd do next." Repo pinned on the
GitHub profile as the last step. Satisfies every remaining acceptance
criterion at once — this phase is where "done" actually becomes true.

## 3. Suggested order

There's only one order: Phase 1, then Phase 2, then Phase 3. Each
depends on the last one having actually merged, not just opened as a
PR — same discipline as the Block 6 pin-bump phase in Block 7's plan.

## 4. What doesn't get its own phase

Deciding FastAPI vs. CLI, deciding the observability view's exact
shape, and confirming the CI secrets pattern are all small decisions
made at the start of the phase they belong to, not separate phases —
matching how Block 7's plan handled small in-phase decisions. Repo
pinning on the GitHub profile is a one-line last step folded into
Phase 3, not its own phase.
