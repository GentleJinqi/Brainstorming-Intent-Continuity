# Brainstorming Intent Continuity

[简体中文](README.zh-CN.md)

Brainstorming Intent Continuity (BIC) is an explicit companion Codex Skill for
[Superpowers](https://github.com/obra/superpowers) Brainstorming.

It preserves the load-bearing meaning developed during a Brainstorming
discussion—approved decisions, rejected directions, rationale, observable
proof, and important edge cases—without copying the whole conversation or
requiring the discussion to continue into a spec or implementation plan.

BIC is community-maintained. It does not bundle, fork, or modify Superpowers,
and it is not an official Superpowers component.

## Why this exists

Brainstorming is deliberately exploratory. A useful design may emerge through
repetition, revisions, rejected alternatives, counterexamples, and gradual
clarification.

When that discussion later becomes a summary, handoff, spec, plan,
implementation task, or review, some of its most important meaning can
disappear:

- the decision remains, but its rationale is lost;
- a rejected direction becomes plausible again;
- a concrete behavior is compressed into an ambiguous label;
- an edge case never reaches implementation or verification;
- a long task or context compaction weakens earlier alignment;
- the Brainstorming discussion never reaches a spec or plan at all.

BIC adds a small, project-owned continuity record at meaningful semantic
changes. It is neither a second development workflow nor a transcript archive.

## The core model

BIC separates three kinds of information:

| Layer | Where it lives | Meaning |
| --- | --- | --- |
| Exploration | Chat | Alternatives, drafts, repetition, and unfinished reasoning |
| Current intent | `current.md` | The operative goal, decisions, prohibitions, rationale, proof, edge cases, and open questions |
| Intent history | `history.md` | Rejected or superseded directions, reasons, turning points, and material counterexamples |

An ordinary intent record has an active pair of Markdown files and two
synchronized Mermaid projections:

- `current.md` contains the **Current Intent Map**;
- `history.md` contains the **Evolution Map**.

The written sections are always the semantic authority. Mermaid diagrams are
visual projections that make the same structure easier to inspect.

The Codex agent controlling the current root task (the root controller) is
responsible for keeping each projection semantically synchronized with the
text. `bic.py` validates the required structure and fenced blocks, not the
meaning of a diagram.

A useful rule of thumb is:

> If changing this meaning later would reasonably make the result feel
> different from what was agreed during Brainstorming, it belongs in the
> continuity record.

## Installation

Superpowers must be installed separately.

Add this repository as a Codex plugin marketplace:

```bash
codex plugin marketplace add GentleJinqi/Brainstorming-Intent-Continuity
```

Install the plugin:

```bash
codex plugin add brainstorming-intent-continuity@gentlejinqi-bic
```

Start a new Codex task after installation so the Skill is available in the new
task context.

The plugin switch in the Codex app controls whether BIC is available; it does
not run BIC automatically. After changing the switch, use a new task for a
clear activation boundary.

To uninstall it:

```bash
codex plugin remove brainstorming-intent-continuity@gentlejinqi-bic
```

Uninstalling the plugin does not delete `.brainstorming-intent/` records that
already belong to your projects.

### Upgrade an existing installation

After a new BIC release, refresh the configured marketplace first:

```bash
codex plugin marketplace upgrade gentlejinqi-bic
```

If the marketplace refresh fails, stop and keep the currently installed
version. After a successful refresh, reinstall the plugin from that snapshot:

```bash
codex plugin remove brainstorming-intent-continuity@gentlejinqi-bic
codex plugin add brainstorming-intent-continuity@gentlejinqi-bic
```

Verify the installed version:

```bash
codex plugin list
```

Start a new Codex task after upgrading so the released Skill is loaded into
the new task context. Updating the plugin does not delete project-owned
`.brainstorming-intent/` records.

## Start a continuity-enabled Brainstorming task

Explicitly invoke both Skills once at the beginning of a root Brainstorming
task, or when explicitly restarting that root Brainstorming flow:

```text
$superpowers:brainstorming
$brainstorming-intent-continuity:brainstorming-intent-continuity
```

Codex namespaces a plugin-contributed Skill as `plugin-name:skill-name`. In
this package, both names are `brainstorming-intent-continuity`, so the repeated
name is intentional.

The expected acknowledgement is:

```text
BIC armed — explicit session mode; no project record exists until a semantic event.
```

That receipt is valid only when Codex has structurally loaded both Skills. If
Codex loads BIC but omits Superpowers Brainstorming, BIC fails closed and asks
you to invoke `$superpowers:brainstorming` in the next turn. If no BIC receipt
appears, invoke the plugin-qualified BIC Skill in the next turn. Neither retry
creates project state; continue only after the armed receipt appears.

A partial-activation turn ends with the fail-closed receipt. Once the missing
Skill is loaded, continuity is forward-only from that turn. To recover meaning
from an older task or the partial turn, first present a brief controlled
bootstrap reconstruction and apply it only after the user explicitly confirms
it; never treat task history as an automatic backfill source.

Before presenting that controlled bootstrap reconstruction, inspect any
applicable native project authority and reconcile the reconstruction to it.
Native authority controls project state, source routing, lifecycle, evidence,
permissions and write eligibility, and handoff ownership over recovered Task
history and BIC defaults; BIC never overrides it. Do not apply where that
authority forbids the record or write; obtain user confirmation only after
reconciliation.

Once per continuous root discussion is enough. Repeating the pair within that
discussion resumes the same armed candidate or exact record; it must not create
a duplicate intent record.

Invoking Superpowers Brainstorming without BIC is intentional no-continuity
mode. BIC is not activated by quoted Skill names, pasted documentation,
prompt-text matching, or implicit hooks.

## How the workflow behaves

It is not a separate service or an automatic semantic-event detector.

```mermaid
flowchart TD
    A["Start a root Superpowers Brainstorming task"] --> B["Invoke both Skills once"]
    B --> C{"Both structured Skills loaded?"}
    C -->|"No"| C0["BIC not armed: end this turn"]
    C0 --> C1["Invoke the missing Skill next turn"]
    C1 --> C
    C -->|"Yes"| D["BIC armed: no project write"]
    D --> E0["Explore alternatives in chat"]
    E0 --> E{"Load-bearing semantic change?"}
    E -->|"No"| E0
    E -->|"Yes"| F{"Meaning and authority clear?"}
    F -->|"No"| G["Ask once and resolve the ambiguity"]
    F -->|"Yes"| H["Root controller drafts the semantic delta"]
    G --> H
    H --> I["bic.py validates and applies a revision"]
    I --> J["current.md: operative meaning"]
    I --> K["history.md: rejected or superseded meaning"]
    J --> L["Continue Brainstorming"]
    K --> L
    L --> E0
    I --> M["Optional downstream handoff"]
    M --> N["Exact record ID, revision, and file paths"]
```

Arming alone writes nothing. Ordinary exploration remains in chat.

While BIC is armed, the root controller creates a record lazily only when it
identifies and applies the first load-bearing semantic event, such as:

- an outcome-changing approval or rejection;
- a revision or supersession of an earlier direction;
- an accepted material non-goal, counterexample, or edge case;
- a material open question being created or resolved.

The root controller identifies the semantic delta and uses existing user
authority when it is already clear. It asks once only when the meaning is
materially ambiguous. The deterministic helper script validates and writes the
supplied record; it never interprets or summarizes the conversation itself.

Possible future compaction, agent dispatch, method changes, or Skill invocation
are not semantic events by themselves.

After each successful update, BIC reports one compact visible line containing
the record/revision, a one-sentence semantic delta, and `valid /
commit_pending`. The first creation also reports both exact record paths once;
later updates do not repeat the record body unless requested or handed off.

## One result, one round

One record ID follows one deliverable discussion result, not an entire product,
Codex task, topic word, or file length. Refinements of the same result keep its
ID across tasks when writer ownership is handed off. An independent result gets
its own ID after a qualifying semantic event; this does not end the earlier round.

Before marking a round completed, the root explicitly asks whether its agreed
questions are sufficiently answered and whether the result may be delivered and
the round ended, then obtains the user's affirmative answer. Local approval,
thanks, silence, a task switch, a spec, or a revision count cannot replace this
confirmation. Discussion-only results can end without producing a spec or plan.

An `end` update records that confirmation as a new revision and saves its original
version in the same publication. Ending grants no successor authority. Native
spec drafting and review may proceed while the BIC round is still open; one
native approval question may also request ending confirmation when both concern
the same complete result.

Pause preserves an unfinished result; cancellation and replacement record their
own facts, including the successor relationship for replacement. Inactivity
implies none of them. Downstream reading or implementation does not reopen a
round. Repair execution that missed an unchanged approved design. Reopen an
ended commitment only for a concrete substantive defect, identifying the original
promise and affected scope, preserving the confirmed version and unaffected
conclusions, and obtaining ending confirmation again after revision.

## Project-owned record layout

The first successful record update creates:

```text
.brainstorming-intent/
├── manifest.json
└── records/BIC-0001/slots/a/
    ├── current.md
    └── history.md
```

`manifest.json` selects the active pair and tracks stable IDs, revisions, round
facts, saved versions, registered parts and corrections, and pending Git state.
It does not store a transcript. Later updates alternate at most two working
slots (`a` and `b`); the inactive slot is not a saved historical version.

Only when needed, the registry adds `versions/BIC-0001/rN/` for saved original
current/history and their descriptor, `parts/BIC-0001/DIGEST.md` for archived
history or effective topics, and `session-bindings.json` for session association.
Ordinary revisions do not create per-revision copies or empty archive indexes.
The writer publishes one complete revision through the manifest under a project
lock; readers obtain matching identity and bodies under the same shared lock.

All generated drafts, temporary output, records, parts, saved versions, and
bindings belong inside the project using BIC. Declare that location before
generating files, use its `.tmp/` for temporary work, and pass this boundary to
authorized delegates and tools. Resolved paths must remain inside the project.
The fixed Markdown headings, complete CLI and JSON contracts are in
[record-format.md](plugins/brainstorming-intent-continuity/skills/brainstorming-intent-continuity/references/record-format.md).

## Two files, two maps

The following example is synthetic and contains no real project data.

### Current Intent Map

Suppose a team is designing daily digest notifications. The operative record
says that notifications are opt-in, delivered once per day by email, and
scheduled using a user-selected local time.

Its `current.md` projection could be:

```mermaid
flowchart TD
    G["Goal: useful daily digest notifications"]
    D1["Approved: opt-in only"]
    D2["Approved: one email per day"]
    D3["Approved: user-selected local delivery time"]
    P1["Must not: enable notifications by default"]
    P2["Must not: send real-time push notifications"]
    V1["Proof: new accounts default to off"]
    V2["Proof: timezone integration test"]
    E1["Edge case: daylight-saving transition"]

    G --> D1
    G --> D2
    G --> D3
    D1 --> P1
    D2 --> P2
    D1 --> V1
    D3 --> V2
    D3 --> E1
```

Only operative meaning belongs in `current.md`. When a decision is
superseded, its old wording is removed from this file.

### Evolution Map

Rejected and superseded meaning moves to `history.md` together with the reason
it changed.

The corresponding history projection could be:

```mermaid
flowchart LR
    A["Default-on real-time push"]
    B["Opt-in daily email at a fixed UTC time"]
    C["Opt-in daily email at a user-selected local time"]

    A -->|"rejected: intrusive and noisy"| B
    B -->|"refined: fixed UTC caused confusing delivery times"| C
```

This preserves the load-bearing evolution without making obsolete text compete
with the current design.

## Continuing without a spec or plan

BIC does not require Brainstorming to produce a design spec, implementation
plan, or code change.

A discussion may remain entirely within Brainstorming. Its continuity record
can still be revised as important meaning changes, recovered in a later task
through an exact pointer, or inspected as the current understanding of the
intent.

When a specific revision becomes a durable spec or handoff input, save the
original bodies and their necessary topic/history dependencies with
`save-version`, reusing an identical saved version. This does not increment the
semantic revision or end the round. Continued reading in the same context needs
no new copy. An `end` update saves its new confirmed revision automatically.

A handoff identifies the project, stable ID, revision, and actual returned paths,
and states whether it requests current effective content or a saved original.
For example, after successful preservation:

```text
BIC saved pointer: <project> | BIC-0001 rev 3
current: <project>/.brainstorming-intent/versions/BIC-0001/r3/current.md
history: <project>/.brainstorming-intent/versions/BIC-0001/r3/history.md
```

Use paths returned by successful apply/preservation, never guessed paths or a
new handoff summary in place of the originals. A saved version preserves the
then-current grounds; it does not override later user authority or automatically
update or reapprove a spec.

## Supplement the same native spec

When BIC is armed and associated and native Brainstorming needs a spec, obtain
and consider its corresponding current/history or saved version during that
same native design and review. The exact version already obtained in context
can be reused. The spec still draws on conversation, project facts, applicable
requirements, native exploration and tradeoffs, and the BIC supplement.
Effective user constraints keep their authority; rejected directions stay history.

Express relevant requirements naturally in the native spec, with exact references
where useful. Include the BIC pointer and reading instruction in the existing
native review handoff, and repair omissions in that same spec. A link alone
does not express a requirement. BIC creates no second spec, required BIC headings,
extra review report, or second approval flow. Superpowers files, methods,
capabilities, invocation, ordering and approvals remain unchanged. Native
writing-plans consumes the same spec; every downstream reader need not reread
the full record. Ordinary tasks without BIC continue normally, and paths that
need no spec or plan gain none.

If an agreed input is unavailable, name the exact missing project/record/revision
or file and recover it from its explicit original source or known exact copies.
An exact version already present in context suffices; a later revision, summary,
or reconstruction does not. Do not guess another association or repeat exhausted
searches without a new lead. Carry registered later corrections with old content.
If recovery fails and no decision covers this incident, explain the omission and
its unknown impact, then ask whether the user accepts proceeding without this
particular input. Continue independent work while awaiting that answer, keep the
dependent obligation open, and do not claim the agreed supplement was used.
An accepted omission applies only to that incident; visible conversation alone
does not establish that unread material is dispensable.

## Read, preserve, and associate an input

Resolve `BIC_SKILL_DIR` from the runtime-supplied Skill path, rather than assuming
the target project contains plugin source. Replace the example project, record,
revision and session with the exact known values. These examples assume an
enrolled schema 2 project with `BIC-0001` currently at revision 3:

```bash
BIC_SKILL_MD="/absolute/path/supplied-by-the-runtime/SKILL.md"
BIC_SKILL_DIR="$(cd "$(dirname "$BIC_SKILL_MD")" && pwd -P)"
BIC_PROJECT="/absolute/path/to/your-project"
python3 "${BIC_SKILL_DIR}/scripts/bic.py" read --project "$BIC_PROJECT" --record-id BIC-0001 --current
python3 "${BIC_SKILL_DIR}/scripts/bic.py" save-version --project "$BIC_PROJECT" --record-id BIC-0001 --revision 3
python3 "${BIC_SKILL_DIR}/scripts/bic.py" read --project "$BIC_PROJECT" --record-id BIC-0001 --revision 3
python3 "${BIC_SKILL_DIR}/scripts/bic.py" bind --project "$BIC_PROJECT" --session-id SESSION --record-id BIC-0001 --expected-revision 3
python3 "${BIC_SKILL_DIR}/scripts/bic.py" bind --project "$BIC_PROJECT" --session-id SESSION --lookup
```

`read --current` returns the effective revision. `read --revision N` prefers its
saved version; if unsaved but exactly current, it returns `source_kind: current`,
whose mutable paths are not durable references. Unavailable older revisions
return `version_unavailable`, never a newer substitute.

Setting a binding saves the expected **current** revision and registers its exact
saved paths inside `.brainstorming-intent/session-bindings.json`. If current has
advanced, setting it with the old expected revision returns `revision_conflict`.
An existing binding lookup and `read --revision N` can still resolve the old saved
input. Lookup is read-only, does not arm BIC, and grants no semantic write ownership.

For unusually long unfinished rounds, archive whole historical events with stable
entries for their scope, conditions and location. Deduplicate effective content
first; when needed, group it into actual topic bodies while current retains global
constraints and navigation covering every effective topic. Effective topic bodies
remain requirements. Neither size nor revision count ends a round or changes its ID.
Ordinary reads include effective topics and history navigation, not all archived
bodies. Add `--event E1` to either read mode to obtain a relevant old event and its
registered later corrections, distinguished by original/view/source revision.
Expand related history when the entry does not settle relevance. Keep original
events intact and distinguish later supersession from `recording_error`; an
offline old file cannot establish the absence of later corrections.

## Updates and conflict handling

Each successful update advances the record revision.

The writer uses an expected-revision check. If the record has changed since it
was read, the update fails closed so the controller must re-read the current
authority. It does not silently overwrite newer meaning.

Unsupported schema versions enter a read-only compatibility hold rather than
being migrated silently.

### Explicit schema 1 migration

The `0.2.0` writer reads and validates schema 1 without changing it. Before
writing that project's old records, obtain project migration authority and run
this command using the same runtime helper/project setup above:

```bash
python3 "${BIC_SKILL_DIR}/scripts/bic.py" migrate --project "$BIC_PROJECT" --expected-schema 1
```

Migration preserves record IDs, revision numbers, current/history original bytes,
and pending flags. It records ending state as `unknown`, not inferred completion,
and does not invent unsaved historical versions. Original content moves into the
schema 2 working layout; use returned paths. The old schema 1 writer rejects
schema 2 in read-only `compatibility_hold`, so do not send a migrated project
back to an old writer for updates.

Old `bind --plugin-data ...` calls return `binding_migration_required` with the
project-local command guidance; they do not silently read, move, or alter old
external binding files. Re-establish a binding with an explicit project, session,
record and expected current revision. No other project is traversed or migrated.

## Git behavior

Applying a record update never invokes Git automatically.

The update changes only `.brainstorming-intent/` and reports
`commit_pending`. Depending on project policy, those durable records may remain
as project-owned working-tree changes.

A complete registry snapshot may be committed only through the explicit
`commit-snapshot` operation and only when commit authority has been granted.
That operation covers the manifest, every active record, saved descriptors and
their dependencies, and correction material together while preserving unrelated
staged and modified files. It excludes inactive working slots, temporary files,
and session runtime state. If a complete snapshot is not authorized, successful
record work remains `commit_pending`.

BIC reports the state of BIC-owned paths only. It never claims that the entire
worktree is clean.

## Privacy and project ownership

BIC stores the selected design meaning in the project that uses it. Those
records may contain information about that project and may later be committed
or pushed under the project's own rules. Inspect them before sharing a
repository publicly.

Optional session recovery writes `.brainstorming-intent/session-bindings.json`
inside the project. It stores the session ID, absolute project/saved-body paths,
record ID, and revision; it does not store design text or a transcript. BIC
snapshots exclude this runtime file. Absolute paths can reveal usernames or
project names, so inspect other sharing mechanisms separately.

This repository contains only product source, package metadata, public
documentation, synthetic examples, and tests. It does not include user
transcripts, project records, telemetry, hooks, or a network service. This
statement describes the plugin package, not the broader privacy behavior of
Codex or third-party tools in a user's environment.

## What BIC does not do

BIC does not:

- activate automatically whenever the word “brainstorming” appears;
- modify or replace Superpowers Brainstorming;
- save every message or preserve a complete transcript;
- treat every idea or wording change as a durable decision;
- make the helper script decide what the user meant;
- require a spec, plan, task decomposition, or implementation phase;
- create project files merely because compaction or handoff may happen;
- commit project files without explicit authority;
- guarantee that every nuance will be captured without inspection or
  correction.

The root controller remains responsible for semantic judgment. Users can
inspect and correct the Markdown authority whenever its meaning is incomplete
or inaccurate.

## Compatibility

This README describes `0.2.0`, including schema 2 and explicit discussion rounds.
Local source preparation does not establish publication or update an installed
plugin. The candidate passed 84 mechanical tests on Python `3.9.18`; actual
model testing used Codex CLI/App Server `0.153.4` with `gpt-6-astra` at `ultra`.
The observations and their limits are recorded in the changelog.

For historical compatibility, release `0.1.4` was verified on Linux with
Superpowers `6.3.0` and Codex CLI `0.149.1`. The deterministic writer requires
Python `3.9+` and POSIX file locking. Native Windows is not currently supported;
macOS has not yet been verified.

See [CHANGELOG.md](CHANGELOG.md) for release notes and
[GitHub Releases](https://github.com/GentleJinqi/Brainstorming-Intent-Continuity/releases)
for published versions.

Superpowers is an independent dependency and is not included in this
repository. Future Superpowers or Codex changes may require a compatibility
review before support is claimed.

## Contributing and feedback

Use [GitHub Issues](https://github.com/GentleJinqi/Brainstorming-Intent-Continuity/issues)
for bug reports, compatibility findings, and feature proposals.

Before posting an example, remove project names, private paths, prompts,
credentials, and other sensitive content.

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidance.

## License

[MIT](LICENSE)
