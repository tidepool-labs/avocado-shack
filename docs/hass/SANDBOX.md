# One per-target sandbox switch (AVB-11)

The `live` list in the operator-owned `host.json` is the only permission to route
new changes to real targets. Missing or empty means sandbox, **including an older
host file with `approvals: "live"` but no `live` list**. This is a fail-closed
migration, not permission to edit the running host or to enable a till write.

```json
{"live": ["site"], "off": [], "mode_gen": 1}
```

This example keeps independent site changes live while till changes are sandboxed.
`approvals: "hold"` still pauses all new applies. `private`/`live` are retained for
old host/runbook compatibility, but cannot override `live`. Existing release
privacy, STOP, cap, named-code and baseline checks remain required.

## Operator interface (not run by the builder)

Use the existing attended `python3 hass/host.py mode` command with `--host` and,
optionally, `--target site|till`. Values are `sandbox|live`; `private` remains an
alias for sandbox, and `hold` remains the pause. The default target is site.
Changing till does not remove site from `live`. The command validates the complete
replacement, writes atomically at 0600 and serializes updates under the host lock.
Every successful update raises `mode_gen`. No command restarts a service itself.
The worker rereads the routing policy for draft and approval/apply checks; a worker
started with approval application held still needs its existing attended restart.

`"demoLock"` (absent = off) is written only by the attended `hass/host.py demo-lock
on --id ID` / `off` command: while on, new changes go to the private copy only,
only that activation's own private changes can be undone, and no release step
touches the site checkout. See the command help for its refusals.

Do not add till to the live list before AVB-22's separate write approval. A list
entry is necessary, never sufficient: merchant identity, environment-appropriate
credentials, write allow-list, owner approval and executor gates still apply.

## Bundle and approval contract

`hass.sandbox.Gate.resolve(members)` resolves a bundle once. Members name pack,
skill and target. Packs are site, front, till, reports (plus targetless core).
Reports/core use local; local never enables a real write. If any changing target
is absent from `live`, **every part** runs in sandbox. A till stock change's site
companion cannot independently decide to publish. Any unavailable sandbox part
refuses the whole bundle before showing a draft. An `off` entry names a pack or
skill and refuses it, rather than silently changing its environment.

The binding stores environment, a 12-hex digest per resolved target, applicable
off entries, member names and generation. Descriptors contain no credential bytes:
site uses the writer path (sandbox) or writer path, publish checkout, remote and
branch (live); future till uses API host, merchant and token **role**, not token.
The binding is included in the editor's draft hash and retained on applied records.
A changed policy, generation, identity or tampered binding kills the old approval
before any new target call. Chat offers a new draft/code and requires a new yes.
Checks repeat inside the private writer lock immediately before writing; the live
engine also checks before its remote work and after its cap interval wait.

Undo uses the applied draft's recorded environment, not today's switch. Recovery
checks each journal's recorded identity before settling it. If it is unavailable,
`env-gone` holds the action; no fallback to a live identity occurs. Old unbound
approvals are invalidated. Old release records without an environment binding are
held for attended reconciliation, not guessed to be live. The release CLI refuses
in sandbox/hold before constructing a live engine.

## What is wired now, and what remains downstream

The host wraps the installed site's single writer/release engine. Existing typed
ops all write site content; the new front-end and till writing ops do not exist on
this base. Unknown ops fail closed. Skill dispatch preserves skill identities in
bindings, and checks the off list before planning/read-only execution.

`Gate.execute` is the shared executor boundary for downstream packs: it preflights
all recorded endpoints before calling any of them. An executor is keyed by target,
environment and identity; it must never choose its own target from the switch.
AVB-15/17 own the real till journal, credential-role resolver, transport allow-list,
companion transaction, crash compensation and second approval. AVB-10 owns audit
lines; this change supplies their environment fields rather than creating another
log. These APIs do not authorize unapproved mixed-target plans or new live writes.

Sandbox site edits use the existing private writer, with no publication. Do not
promote its accumulated private contents by bypassing the live baseline check.
A deliberate baseline/adoption remains an attended operation with its existing
checks and confirmation.

## Offline proof and rollback

Run `python3 -B -m unittest hass.tests.test_sandbox -v`. Tests exercise whole-bundle
routing, generation/merchant changes, missing targets, hash tampering, recorded
undo/recovery, the real dispatcher, host validation and the existing release
engine against a throwaway bare Git remote. Sandbox apply and undo leave that
remote's published commit unchanged; explicitly live site changes still go through
the real release gates. Till calls use recording fake endpoints, never a merchant.

The registry-driven test runs one existing case per skill where a case file exists
(prefer a writing case; otherwise its existing refusal/read-only case). The two
built-in refusal skills with no case files run their real empty plans. This proves
routing isolation, not all skill semantics, real Clover qualification, human text
acceptance or production deployment. Existing skill suites and review remain gates.

Safe rollback is to keep all targets out of `live` / retain hold. A code revert is
an attended release with host-file compatibility reconciled first; old code does
not understand these new fields. No live host, service, merchant or public site
was changed by this build.
