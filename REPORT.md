# Trailmarked — Report

## Architecture

The platform is event-sourced, not a script pipeline. A discovery run is a
stream of domain events (`ObservationCaptured`, `ActionDecided`,
`ActionExecuted`, `StepSucceeded`/`StepFailed`, `RunSucceeded`/`RunFailed`) —
the CQRS write side, held in an in-process, SQLite-backed, append-only log
(`services/event_log`) with real streaming vocabulary: topics, per-topic
offsets, consumer groups with committed offsets, a dead-letter path, and an
outbox-fed publish path. A capability ("trailmark") is a versioned schema in
the Capability Registry (`services/capability_registry`), compiled by
folding a successful run's event stream — a read model denormalized from the
event log, governed like a schema registry with BACKWARD/FORWARD/BREAKING
compatibility rules. A replay is a consumer of replay-request events, with
idempotency, bounded retry, and a dead-letter path
(`services/replay_runtime`). Escalation to a human is an explicit saga —
`AGENT_CONTROLLED → INTERVENTION_REQUESTED → HUMAN_CONTROLLED →
CONTROL_RETURNED → (RESUMED | TERMINATED)` — not a poll loop on a flag
(`services/escalation_saga`).

Each of the five services above is its own OS process, and they talk to each
other only over gRPC on localhost — there is no shared database between
services and no direct cross-process table access; `event_log`'s SQLite file
is touched only by that one process. This is a deliberate stand-in for a real
broker/service mesh: `scripts/run.py` boots five plain Python processes with
no Docker and no Kafka, and the README calls out exactly where a real broker
(Kafka/RabbitMQ) and a real service mesh would slot in at production scale —
building either for a take-home is scope creep the system doesn't need to
prove the architecture is real.

**Protocol assignment.** Three protocols, three different reasons, not a
uniform default:

- **gRPC** for every internal service-to-service call (discovery plane →
  event log; registry → replay runtime; replay runtime → escalation saga →
  back into replay runtime for live-session actuation). `.proto` contracts
  (`proto/*.proto`) make the internal boundary as strictly typed as the
  capability schema itself — the entire point of the platform is that a
  capability's shape is a first-class, versioned contract, so the plumbing
  underneath it should not be looser than that.
- **REST/JSON** for the one external, agent-facing surface:
  `POST /capabilities/{id}/invoke`, `GET /capabilities`. This is a
  compatibility decision, not a default — external agent tooling
  (function-calling, OpenAPI schemas) is built around REST, and that
  boundary is exactly where compatibility with the outside world matters
  more than internal type strictness. Per-capability, per-tenant rate
  limiting sits here (`shared/rate_limit.py`) because this is the one door
  an agent that misfires could hammer a production banking UI through.
- **GraphQL** for the dashboard's read layer only, never for writes. One
  query nests a capability, its version history, recent runs, and each run's
  full event timeline without over- or under-fetching
  (`services/capability_registry/graphql_schema.py`). It reads a
  denormalized read-model table (`runs`, `run_events`), never the event log
  directly — kept in sync by a projector consumer
  (`services/capability_registry/projector.py`), which is the CQRS boundary
  made literal.

The live discovery timeline in the dashboard is bridged over SSE (see
`gateway.py`'s `/stream/{topic}` endpoint), which is a one-way tail of the
event log's `StreamTopic` gRPC call — chosen over a WebSocket because nothing
in that direction needs to be bidirectional.

## Artifact schema

The capability artifact (`shared/schemas.py:CapabilityArtifact`) keeps every
concern in its own field rather than folding several ideas into one:
`capability_id`, `version`, `compatibility`, `tenant_scope`, `input_params`
(typed), `steps` (ordered; each an `action_type` + `strategy_chain` of
primary-plus-fallback locators + `risk_tag` + `param_bindings`),
`checkpoints` (assertions tied to a `step_id`, never inferred), `outputs`
(typed, each naming the `step_id` it's extracted from), `success_condition`,
`provenance` (discovery run id + compiled-at timestamp), and `risk_summary`.

The registry compiler (`services/capability_registry/compiler.py`) builds
this by folding a discovery run's `ActionDecided`/`ActionExecuted` pairs:
whichever locator candidate the actor actually resolved during discovery
becomes the strategy chain's primary, with the LLM's other candidates
preserved as fallbacks — so a capability doesn't just remember one selector,
it remembers the ranked list an agent considered. `param_bindings` records
*which* input name a step's literal value came from (matched by substring
against the caller-supplied inputs at discovery time), not the literal
itself — so replay re-binds live caller arguments rather than replaying a
frozen value. Versioning (`versioning.py`) diffs a new compile's
input/output/checkpoint shape set-for-set against the latest version: an
identical shape auto-bumps as `BACKWARD`; a shape that only adds to the
previous one (nothing renamed or removed) is `FORWARD`; anything else is
`BREAKING` and lands as a new version requiring explicit promotion before
it's treated as the default.

## Determinism & error handling

Replay never calls an LLM — `services/replay_runtime/executor.py` walks a
resolved artifact's steps and resolves each one's locator strategy chain
deterministically, falling back through the chain rather than guessing.
Checkpoints are asserted against the live page, never assumed to hold.

**Idempotency**: every replay request carries an idempotency key
(`ReplayStore.find_by_idempotency_key`); a repeated key returns the
already-recorded run rather than re-executing side effects against the bank
UI a second time.

**Outbox**: every service that produces domain events (`discovery_plane`,
`replay_runtime`, `escalation_saga`) writes its local outbox row
(`shared/outbox.py`) in the same SQLite transaction as its own domain state,
then a background dispatcher thread publishes pending rows to the event log
and marks them published only once the remote `Append` succeeds. If the
process crashes between the domain write and the publish, the row is still
sitting in the outbox on restart — this is the concrete answer to "how do you
avoid losing events on crash," and it's why `Append` takes a
`producer_dedupe_key`, since outbox delivery is at-least-once by
construction.

**Circuit breaker**: `services/replay_runtime/circuit_breaker.py` tracks
consecutive run-level failures per `(tenant_id, capability_id)`; after three
in a row it trips open and fails fast for a 30s cooldown window rather than
letting every subsequent replay hit a possibly-down target app.

**Outcome classifier**: every replay resolves to exactly one of
`BUSINESS_OUTCOME` (the run reached a recognized terminal state — success or
a legitimate business rejection like "member not found" — either way not a
bug), `RECOVERABLE` (a transient technical failure — timeout, a locator that
hasn't rendered yet — retried with bounded exponential backoff plus jitter,
capped at 2 retries per step), or `HARD_FAILURE` (retries exhausted, or a
checkpoint assertion failed with no recognized business explanation) — which
dead-letters with the full failure context (step id, expected, observed) via
`EventLog.DeadLetter` and, from there, opens an escalation saga. Retries are
never applied to `BUSINESS_OUTCOME` or `HARD_FAILURE` — only to the
recoverable bucket, and only bounded.

**Confidence tracking**: the recorded flow is stable but the live app isn't
guaranteed to stay that way forever, and nothing in the replay path detects
drift *before* attempting a run — detection is reactive, discovered by
actually trying (locator fallback chains absorb small drift silently;
checkpoints catch state-level drift mid-flow; retries and the circuit
breaker absorb transient failures). To make that history visible rather than
implicit, the registry's projector (`services/capability_registry/
projector.py`) consumes `ReplaySucceeded`/`ReplayHardFailure` off the event
log and updates each capability version's `last_validated_at_ms` and
`consecutive_hard_failures` (`store.py:record_validation`), from which a
`confidence` label is derived: `FRESH` if it's ever been proven and hasn't
hard-failed twice in a row since, `NEEDS_REVIEW` otherwise — surfaced as a
badge in the Registry tab. This is deliberately just a signal, not an
action: it does not automatically re-run discovery or gate replay by itself
(see Cuts) — a human decides whether `NEEDS_REVIEW` means "re-discover this"
or "investigate the target app."

**Correlation IDs** are generated once per run (`shared/correlation.py`) and
threaded through every event payload, every gRPC call, and every dashboard
timeline entry, so `evidence/` can reconstruct one run end-to-end from a
single id.

## Heterogeneity & multi-tenant

The mock bank app (`mock_bank_app/`) ships two tenants — `default` and
`overlay_demo` — serving the same two flows (member balance lookup; open
sub-account) through genuinely different server-rendered markup: table-based
layout with plain `<td>` label text vs. a `<dl>`-based layout with real
`<label for>` associations, different button copy, different element ids and
classes. This isn't documentation of the overlay mechanism, it's a second
real target the mechanism has to work against.

A compiled capability's `tenant_scope` is `"*"` (the base). At resolve time
(`services/capability_registry/overlay.py`), a `TenantOverlay` record
(`locator_overrides` + `param_overrides`, keyed by `step_id`) is merged onto
a deep copy of the base artifact — the base itself is never mutated per
tenant, so a tenant-specific override can't leak into what other tenants (or
the version history) see. `ResolveForTenant` is the one gRPC call every
consumer (replay runtime, the REST invoke endpoint) goes through instead of
reading the base capability directly.

## Escalation & handoff

A dead-lettered hard failure calls `EscalationSaga.RequestIntervention` with
the run id, correlation id, dead-letter event id, failed step, and full
expected/observed context. The saga is a real state machine
(`services/escalation_saga/server.py` + `store.py`), not a boolean flag
polled by a loop: `AGENT_CONTROLLED → INTERVENTION_REQUESTED →
HUMAN_CONTROLLED → CONTROL_RETURNED → RESUMED|TERMINATED`, and every
transition is its own event on the `escalation.events` topic.

The "same live browser session, not a fresh one" requirement is real, not
simulated: on a hard failure, `replay_runtime` does not close its Playwright
browser — it keeps the `(playwright, browser, page)` triple alive in an
in-memory registry keyed by run id. `ClaimSession` hands the operator a
session handle; `RecordHumanAction` round-trips through
`ReplayRuntime.ActOnLiveSession` (a small addition to `replay.proto`) so the
*same* page object gets acted on from a different OS process, and the action
is recorded as a `HumanActed` event. `ReleaseControl` closes that session via
`ReplayRuntime.ReleaseLiveSession`. Resuming the deterministic replay loop
after a human hands control back — reconciling whatever state the human left
the page in with the artifact's remaining steps — is not implemented; see
Cuts.

## Safety

Three checks, each a real interception point rather than a comment:

- **Allowlist** (`shared/safety.py:check_allowlist`) — every `ActionDecided`
  is checked against a `(domain, action_type)` allowlist before it can
  become `ActionExecuted`; a violation emits `ActionBlocked` and fails the
  run instead of touching the browser.
- **Risk tagging** (`classify_risk`) — an action is tagged `risky` if it
  mutates state (click/fill/select) and its target description matches a
  mutating-action keyword (submit, confirm, transfer, open sub-account,
  close); the capability's `risk_summary.requires_preapproval` is derived
  from this, and it's the summary the Registry browser surfaces per
  capability.
- **Redaction** (`redact_payload`) — every outbox payload is redacted for
  SSNs, account-number-shaped digit runs, tokens, and password fields
  *before* it's written to the outbox table, i.e. before it can ever reach
  the event log — never as a post-hoc pass over already-persisted events.

Rate limiting is covered under Architecture (REST invocation surface).

## Cuts

- **No real Kafka/RabbitMQ.** The event log is a real single-process,
  SQLite-backed append log with topics/offsets/consumer groups/DLQ — a
  faithful stand-in for the semantics, not the operational concerns
  (partitioning, replication, multi-broker failover) a real broker would
  add at production scale.
- **No real multi-tenant infrastructure.** Tenant isolation here is a
  `tenant_id`/`tenant_scope` field and a per-tenant SQLite row, not separate
  schemas, separate credentials, or network-level isolation — enough to
  prove the overlay-resolution mechanism, not a multi-tenant platform.
- **No full operator co-browsing console.** The escalation saga's claim/act/
  release cycle is real and acts on the same live browser session, but the
  "minimal operator surface" is exactly that — three buttons and a raw
  locator/value input in the dashboard, not a rendered live view of the
  page, no cursor-sharing, no multi-viewer support.
- **No automatic re-discovery.** Confidence tracking (above) surfaces
  `NEEDS_REVIEW`; it deliberately does not act on it. Auto-triggering (or
  auto-prompting) a fresh discovery run when a capability looks stale was a
  conscious line not to cross — it would mean the system deciding on its own
  when to spend a new LLM-driven run against a live app, which quietly
  breaks the platform's own core promise that replay never involves the LLM
  and that a human is always the one who decides to re-invoke it.
- **Resuming the agent after a human releases control** is modeled as a
  saga transition (`RESUMED`) but not actually implemented — the browser
  session is closed on every release regardless of `resume_agent`, and
  nothing re-enters the deterministic replay loop with the page state the
  human left behind. A real implementation would need the replay loop to
  re-derive its position from the artifact's step list rather than assuming
  it left off cleanly.
- **No separate test suite.** The system was verified by exercising the real
  flows end-to-end (see `evidence/`) rather than by a unit/integration test
  suite — reasonable for the scope of this take-home, not for a production
  system.
- **Single-process-per-service, not horizontally scaled.** Nothing here
  runs more than one instance of any service; the outbox dispatcher, the
  circuit breaker, and the idempotency store all assume a single writer per
  SQLite file, which would need to become a real datastore (Postgres, etc.)
  before any service could be scaled out.
