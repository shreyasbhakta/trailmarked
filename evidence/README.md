# Evidence

All of this was produced by actually running the system (`scripts/run.py` +
the mock bank app), not hand-written. Correlation IDs tie every file below
back to one run.

## 1. Discovery run (genuine, LLM-driven)

```
python -m services.discovery_plane.cli \
  --goal "Look up member 1001 and report their current balance" \
  --capability-id member_balance_lookup --tenant default \
  --base-url http://localhost:4000/default/members --input member_id=1001
```

- `discovery_run.log` — stdout of the CLI: the run's final status and the
  compile result. `run_id=run_553fbde5df52`,
  `correlation_id=corr_4d31a5f16499471f942e6247551f4edc`.
- `discovery_run_events.json` — the full event stream for that run
  (`ObservationCaptured` → `ActionDecided` → `ActionExecuted` →
  `StepSucceeded`, repeated per step, ending in `RunSucceeded`), pulled
  straight from the event log by `run_id`.

The planner (`claude-sonnet-5`, tool-calling, no scripted actions) drove the
browser through the search form — navigate → fill the member id field →
click Search → **assert** it actually landed on member 1001's detail page →
extract the balance — using only an accessibility-tree snapshot per turn.
The assert step matters: it's what makes the checkpoint in the compiled
capability real rather than decorative (see below).

It took several attempts to get a genuinely clean run during development:
early attempts failed because the model guessed a `css=#acct-balance`
selector that doesn't exist in this tenant's markup, and then a `text=`
locator built from a *concatenated parent* accessible name ("$ 4,823.11")
rather than the leaf node's actual text. Both are genuine, unscripted
findings about accessibility-tree perception vs. Playwright's actuation
layer (documented in `REPORT.md`), not something papered over — the planner
prompt was tightened in response (`services/discovery_plane/planner.py`),
and the run above is the result.

## 2. Compiled capability artifact

`capability_artifact.json` — `member_balance_lookup` v1, `BACKWARD`
compatible (first version), compiled from the run above by
`services/capability_registry/compiler.py`. Note:

- `step_3` is the `assert` step, with a real `checkpoint` (`chk_3`,
  `assertion=text_present`, `expected=1001`) pointing at it — this
  checkpoint is genuinely evaluated on every replay, not just recorded.
- `step_4`'s (`extract`) `strategy_chain`: primary `text=4,823.11` (what the
  actor actually resolved during discovery) with `css=table >>
  text=4,823.11` preserved as a fallback (the LLM's second candidate).

## 3. Replay — clean success

```
python -m services.replay_runtime.cli --capability-id member_balance_lookup \
  --tenant default --input entry_url=http://localhost:4000/default/members \
  --input member_id=1001
```

- `replay_success.log` — `run_id=replay_9aa426bfffc5`, outcome
  `BUSINESS_OUTCOME`, `current_balance=4,823.11`, zero retries. No LLM call
  anywhere in this path; the checkpoint at `step_3` was evaluated and
  passed before the extract step ever ran.
- `replay_success_events.json` — `ReplayRequested` →
  `ReplayStepExecuted` × 5 → `ReplaySucceeded`.

## 4. Replay — hitting an injected error (classifier + dead-letter path + screenshot)

Same capability, same tenant, a different member id (`1002` instead of the
`1001` the capability was recorded against):

```
python -m services.replay_runtime.cli --capability-id member_balance_lookup \
  --tenant default --input entry_url=http://localhost:4000/default/members \
  --input member_id=1002
```

- `replay_hard_failure.log` — `run_id=replay_a77b503e8e80`. Steps 0–2
  (navigate, fill, click) succeed normally. Step 3's checkpoint
  (`text_present`, expected `"1001"`) is evaluated against the real page —
  member 1002's detail page obviously doesn't contain "1001" — and no
  recognized business-outcome marker ("Member Not Found",
  "Permission Denied") is present either, so this classifies as
  `HARD_FAILURE` immediately (`retry_count=0` — a failed assertion on a
  successfully-loaded page is not a transient condition, so it isn't
  retried the way a timeout would be), dead-lettered as
  `dlq_400f9f008749432e` with full expected-vs-observed context:
  ```json
  {
    "expected": "text_present=1001",
    "observed": "url=http://localhost:4000/default/members/1002 title=Member Detail - Branch Teller System",
    "screenshot_path": ".../services/replay_runtime/screenshots/replay_a77b503e8e80.png"
  }
  ```
- `replay_hard_failure_screenshot.png` — the actual page Playwright was
  looking at the moment the checkpoint failed (member 1002 — Marcus Reyes,
  balance $124.50) — the richer failure signal, captured automatically by
  `replay_runtime` on every `HARD_FAILURE`, not staged for this file.
- `replay_hard_failure_events.json` — `ReplayRequested` →
  `ReplayStepExecuted` × 4 → `ReplayHardFailure`.
- `escalation_events.json` — the hard failure automatically opened an
  escalation saga (`InterventionRequested`, carrying the dead-letter event
  id and the same expected/observed/screenshot context), which was then
  claimed and released by an operator in this same evidence run
  (`ControlClaimed` → `ControlReturned`, `status=TERMINATED`). All three
  events carry both the saga's `run_id` and its `correlation_id`.

This is also a real, honest finding about the recorded capability's
generalization limits, not just a manufactured failure: because the
discovered checkpoint asserts the literal member id seen during discovery
(`"1001"`) rather than a parameterized condition, this specific capability
only replays cleanly for the exact member it was recorded against — a
different member id is correctly and loudly rejected rather than silently
returning the wrong person's balance. Re-parameterizing checkpoints (so
`expected` can reference an input, the way step `param_bindings` already
do) is a natural next step, noted in `REPORT.md`'s Cuts section.
