# Block 8 — Capstone: Tasks

Concrete, ordered checklists for each phase in `docs/plan.md`.

**Branching rule for this block:** strictly sequential — every phase
branches off `main` only after the previous phase has actually merged,
not just opened as a PR. There's no independent-phase case here, unlike
Block 7; each phase is built on top of the last. Every branch name
follows `phase-N-description` (e.g. `phase-1-core-app`), so it's always
clear which phase a given branch belongs to.

**Verification rule for this block:** every phase's step checks
the spec's code-level claims against the real code in the repos it
touches before building anything. If what's changed is cosmetic — a
rename, a moved file, same actual behavior and data shape — note it and
keep going. If what's changed is structural — different fields, a
described flow that no longer exists, something this phase depends on
being removed or reworked — stop, fix `docs/spec.md` first, and only
resume once the spec matches reality again.

**Every phase ends the same way:** push the branch, open a PR against
`main`, and stop. Do not merge — merging is gated on external approval,
per house rules.

## Phase 1 — Core app (branch: `phase-1-core-app`)

- [ ] Branch off `main` in `genai-block8-capstone` as `phase-1-core-app`.
      Deviation: branched off `phase-0-docs` instead - PR #1 (the docs)
      was still open/unmerged at the time, so `main` had no `docs/` yet.
- [x] Verify: does Block 6's `run_multi_agent` signature, its import path
      (the `block5_agent` pip package), and the `MultiAgentAnswer` shape
      still match what `spec.md` documents? Apply the verification rule
      above if not.
- [x] Decide FastAPI vs. CLI for the entry point — this is the one
      decision the spec deliberately left open until this point.
- [x] Pin `genai-block6-multiagent` to a specific reviewed commit in this
      repo's dependency file, matching Block 6→Block 5's own pinning
      pattern — never a floating branch.
- [x] Write the entry point's contract tests first, before any
      implementation: given a question, expect a structured answer
      (Block 6 mocked/stubbed for this phase — no containers yet); given
      Block 6 unreachable or raising, expect the defined clear-error
      response, not an exception. Run them and confirm they fail —
      proves they're actually testing something real.
- [x] Implement the entry point against those tests: accept a question,
      call `run_multi_agent`, wrap the call in its own try/except per
      the spec's failure-handling section.
- [x] Run the tests again, confirm they pass, and confirm no other test
      in the repo broke.
- [x] Commit the pinned dependency, the tests, and the implementation —
      as separate commits if that stays clean, combined if splitting
      them adds no clarity (judgment call at implementation time).
- [ ] Push, open PR against `main`. Deviation: PR #2 targets
      `phase-0-docs`, not `main` - same reason as the branch-off note
      above.

## Phase 2 — Containerization (branch: `phase-2-containerization`)

- [ ] Confirm Phase 1 has actually merged — this phase doesn't start
      until that's true.
- [ ] Branch off `main` in `genai-block8-capstone` as
      `phase-2-containerization` (now includes Phase 1).
- [ ] Verify: does Block 4's server entry point (`scripts/api.py`, `POST
      /query`, started via `uvicorn scripts.api:app`) and its three
      required env vars, and Block 3's `load_graph.py` plus its
      committed CSV paths, still match what `spec.md` documents? Apply
      the verification rule above if not.
- [ ] Write a `Dockerfile` for this repo's own app (Phase 1's entry
      point, built on the pinned Block 6 commit).
- [ ] Write a `Dockerfile` for Block 4, built from a pinned
      `genai-block4-rag-eval` commit — lives in this repo, not added to
      Block 4's. On first container startup, run Block 4's own
      idempotent `run_all.py` (`check_connection` → `create_index` →
      `ingest` → `verify`) against the caller's own `PINECONE_API_KEY`/
      `PINECONE_INDEX_NAME`, so a fresh clone builds its own populated
      index instead of needing one that already exists. Decide whether
      this runs on every start or only when the index is found empty.
- [ ] Write the Neo4j service definition, seeded on first startup by
      re-running Block 3's confirmed-idempotent `load_graph.py` (pinned
      commit) against the committed CSVs.
- [ ] Write `docker-compose.yml` wiring all three services together:
      `RAG_API_URL` and `NEO4J_URI` point at in-network service names;
      credentials are read from a git-ignored `.env`.
- [ ] Run `docker-compose up`, confirm all three services start cleanly
      and the entry point is reachable.
- [ ] Write integration tests against the real three-service stack —
      ask a real question through the running compose stack, get a real
      answer, confirming the whole chain works end to end, not just
      Block 8's own code in isolation (Phase 1's mocked tests couldn't
      cover this). Confirm retrieval actually returns real results, not
      just a well-formed "I don't know" that would mask an unpopulated
      or unreachable Pinecone index.
- [ ] Run the integration tests, confirm they pass.
- [ ] Commit the Dockerfiles and compose config as one logical change,
      the integration tests as a separate commit.
- [ ] Push, open PR against `main`.

## Phase 3 — CI/CD, observability, README (branch: `phase-3-ci-observability-readme`)

- [ ] Confirm Phase 2 has actually merged — CI's integration tests need
      the compose stack Phase 2 built.
- [ ] Branch off `main` in `genai-block8-capstone` as
      `phase-3-ci-observability-readme`.
- [ ] Confirm Block 5 and Block 6's existing suites still run stubbed
      (`USE_RAG_FIXTURES`, `USE_STUB_ANSWER_FN` or equivalent) in their
      own CI, matching what's already confirmed — no live secrets
      needed to re-run them here.
- [ ] Write the GitHub Actions workflow: re-run Block 5 and Block 6's
      existing test/eval suites stubbed, on every push (cheap, no live
      calls, no cost concern). Plus Phase 2's integration tests against
      the compose stack, using real secrets — decide that test's trigger
      scope (every push, or only `main`/PRs) since it's the one piece
      that costs real money per run.
- [ ] Add the required secrets in the repo's GitHub Actions settings —
      only needed for the one integration test that hits the real stack.
- [ ] Run the workflow, confirm it passes — then deliberately break one
      test or eval score and confirm the build actually fails, proving
      the gate works rather than just appearing green.
- [ ] Decide the observability view's shape (static script run on
      demand, or a small always-on page) and build it: reuse LangSmith
      as-is for traces, surface Block 5's existing cost/token logging
      and Block 7's query-size/runtime/retry signals in one place — no
      new tracking logic, just surfacing what already exists.
- [ ] Write the README: architecture diagram, this spec and plan linked
      or embedded, a link to Block 7's `SECURITY.md` as "the threat
      model," an "AI-assisted workflow" note (where AI helped, where it
      was corrected, what was decided and why), a "what I'd do next"
      section, and the exact list of required `.env` variables with
      where to get each one.
- [ ] Pin the repo on the GitHub profile.
- [ ] Commit the CI/CD config, the observability view, and the README as
      separate commits — three different concerns sharing one phase.
- [ ] Push, open PR against `main`.
