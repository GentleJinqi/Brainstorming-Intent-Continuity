---
name: brainstorming-intent-continuity
description: Use when explicitly starting or restarting a root Superpowers Brainstorming session whose approved decisions must survive compaction, handoffs, specs, plans, or fidelity review; do not use for ordinary Brainstorming alone, quoted or negated invocations, pasted documentation, or prompt-text auto-detection.
---

# Brainstorming Intent Continuity

Preserve load-bearing user-approved meaning in a project record. This is an
explicit companion to Superpowers Brainstorming, not a replacement workflow or
transcript archive. The current root/controller is the sole semantic writer;
`scripts/bic.py` performs deterministic mechanics only.

## Arm one root session explicitly

Use the paired contract once when a root Brainstorming session starts or is
explicitly restarted:

```text
$superpowers:brainstorming
$brainstorming-intent-continuity:brainstorming-intent-continuity
```

Choose the activation receipt from structured Skill evidence in the current
task context, never from the names appearing in prompt text. Count a Skill as
present only when the current task context contains its full runtime `<skill>`
payload (name, path, and body). A catalog entry, plugin toggle or listing, or
prompt mention is not activation evidence:

- If the runtime has supplied both this Skill and the structured
  `superpowers:brainstorming` Skill, reply `BIC armed — explicit session mode;
  no project record exists until a semantic event.`
- If this Skill is present but structured `superpowers:brainstorming` is
  absent, reply `BIC not armed — Superpowers Brainstorming was not structurally
  loaded; invoke $superpowers:brainstorming in the next turn.` Do not create,
  update, or bind a record. End the turn immediately after that receipt; do not
  continue Brainstorming or interpret semantic content from the partial turn.
  Once that Skill is structurally supplied in the same task, give the armed
  receipt without creating project state. Continuity is forward-only from that
  turn. Do not backfill pre-activation or partial-turn content unless the user
  explicitly confirms a brief controlled bootstrap reconstruction.

Before presenting a controlled bootstrap reconstruction, inspect any applicable
native project authority and reconcile the reconstruction to it. Native
authority controls project state, source routing, lifecycle, evidence,
permissions and write eligibility, and handoff ownership over recovered Task
history and BIC defaults; BIC never overrides it. Do not apply where that
authority forbids the record or write; obtain user confirmation only after
reconciliation.

Arming itself writes nothing. Superpowers Brainstorming alone is intentional
no-continuity mode. Do not arm from a quoted Skill name, a negated request,
fenced/pasted documentation, or a prompt-string match.

On a repeat within the same root discussion, resume its armed candidate or
exact record and say so; never create a second one because of the repeat.

## Separate the three semantic layers

| Layer | Rule |
| --- | --- |
| Exploration | Alternatives, drafts, and repeated wording stay in chat; no project write. |
| Controller semantic delta | The root identifies a load-bearing proposed change and obtains user authority where needed. Subagents are read-only unless separately granted a disjoint write. |
| Durable BIC authority | After a qualifying event, the root writes current/history and passes their exact pointer onward. |

Qualifying events are an outcome-changing approval or rejection, a revision or
supersession, an accepted material non-goal/counterexample/edge case, or a
material open question created or resolved. The first event creates state
lazily; later events update it. Never write because compaction may happen, an
agent was dispatched, a method changed, or a Skill was invoked.

## Maintain one deliverable round

One ID identifies one agreed Brainstorming result that can be delivered and
ended, not a whole product, Task, topic word, or file length. Continue the same
ID while refining that result, including across Tasks with an authorized
writer handoff. Use a new ID for an independent result; it does not imply that
the earlier round completed, was cancelled, or ended. Resolve identity from the
agreed result; ask once only if ambiguity materially changes outcome or ownership.

When the whole agreed result is ready for review, explicitly ask:

> Have the questions agreed for this round been sufficiently answered? Do you
> confirm that these results can be delivered and this Brainstorming/BIC round ended?

Use the user's language; no fixed wording is required. Wait for an affirmative
answer explicitly addressing the whole round's ending. Local design approval,
thanks, praise, silence, a Task switch, a high revision number, a spec, or an
assistant final is not that confirmation. This applies to discussion-only
results too; a spec or plan is not required to end. Material questions need
answers or an explicit disposition compatible with the accepted result, not a
new checklist or review process.

If a native approval already covers the same complete result, one question may
explicitly request both that approval and the round-ending confirmation. Do not
expand a local approval into whole-round confirmation. Ending grants no
implementation, publication, or other successor authority and replaces no
native approval. Native spec drafting and review may proceed before BIC ends.

Submit the user's ending confirmation as a semantic revision with the
`round.action=end` update. The writer publishes that revision together with
its saved original version. Stop adding ordinary implementation logs to the
ended round.

| Situation | Record behavior |
| --- | --- |
| Paused | Preserve the unfinished result for continuation. |
| Cancelled | Record that the result is no longer pursued. |
| Replaced | Record the old result's replacement and its relationship to the new result. |
| No further activity | Infer none of these states; no timers or repeated status writes. |
| Downstream reading, planning, or implementation | Consume the result without reopening it. |
| Implementation fails to follow an unchanged approved design | Repair execution; do not reopen the design. |
| An ended commitment needs substantive reconsideration | Reopen only that commitment under the same ID, naming the concrete defect and affected scope; preserve the old confirmed version and unaffected conclusions. Ask and obtain ending confirmation again after the revision. |
| A new independent result is requested | Start its own ID; retain only relevant links to earlier grounds. |

## Keep effective meaning separate from history

Text is authority. `current.md` holds effective goals, constraints, necessary
reasons, and material open questions. `history.md` holds useful rejected or
superseded directions and key turns. Remove superseded requirements from
current; do not write exploratory drafts as approved decisions or accumulate
reply transcripts, implementation steps, or evidence logs.

Before authoring record drafts, read
[`references/record-format.md`](references/record-format.md) for the fixed
headings, Mermaid, layout, update, and schema contract. Mermaid projects useful
current relations or key turns; it is not authority and does not gain a node
for each revision. Do not remove effective text merely to shorten a diagram.

Apply these placement rules literally:

- `current.md` states operative rules and their still-relevant reasons. Earlier,
  proposed, rejected, or superseded directions and their reasons belong in
  `history.md`, not under current edge cases.
- For a separate future intent that has not started and has no qualifying
  event, retain only a generic boundary such as `A separate future intent is
  out of scope.` Keep that future intent's internal goals and constraints out
  of both files until it starts its own round.

Ordinary records remain two files; do not precreate empty archives, topic
indexes, or per-revision copies. For an unusually long unfinished round,
separate storage growth from meaning and round status:

- Archive complete older history events through the writer, using the
  record-format budget and stable event references. Keep useful turning-point,
  scope, condition, and exact-location entries in active history. Size alone
  never ends a round or changes its ID.
- Deduplicate effective content first. If distinct effective requirements still
  exceed the active reading budget, group them into real current topics.
  `current.md` retains global constraints and navigation covering every
  effective topic, its scope, conditions, and exact body location. Topic bodies
  remain current requirements, not optional history or substitute summaries.
- Locate history for a concrete question about rationale, old grounds,
  conditions, or conflict. If the entry does not establish relevance, expand to
  the related topic or round history as needed. A failed search does not prove
  an issue was never discussed.
- Preserve archived event text. Distinguish a later supersession from an error
  in the original record; an error is not a user changing their mind. Register
  corrections against the exact affected event and keep their entry visible
  from active history, archives, and saved versions. Read returned corrections
  with an old event; old text is not current authority. An offline old file
  cannot establish that no later correction exists.

The root supplies semantic grouping and corrections. The mechanical writer
manages paths, dependencies, and reference consistency; do not hand-build
archive or saved-version paths.

## Use project-local deterministic mechanics

Every generated draft, temporary file, record, saved version, archive, topic,
and session binding belongs inside the project using BIC. Declare the output
location before generating files; use that project's `.tmp/` for temporary
work and pass the same boundary to any authorized delegate. Direct tool
temporary output there without global configuration changes. Resolved paths
must remain inside the project; aliases do not permit outside writes.

Resolve the runtime-supplied path to this `SKILL.md` once before calling the
writer; never assume the target project contains companion source:

```bash
BIC_SKILL_MD="/absolute/path/supplied-by-the-runtime/SKILL.md"
BIC_SKILL_DIR="$(cd "$(dirname "$BIC_SKILL_MD")" && pwd -P)"
test -f "${BIC_SKILL_DIR}/SKILL.md"
```

Inspect the enrolled project with `status --project PROJECT` before a write.
The root authors current/history drafts and any structured update draft inside
the project, then calls `apply` with the exact expected revision. Use
`--update-draft PROJECT/.tmp/update.json` for the structured update described in
record-format. For a new round omit `--record-id` and use expected revision 0;
for an update provide the stable ID and current revision. Run
`validate --project PROJECT` after apply. A revision mismatch fails closed:
re-read the affected authority, never last-write-wins or invent a replacement.

All commands below use `python3 "${BIC_SKILL_DIR}/scripts/bic.py"`:

```text
read --project PROJECT --record-id BIC-xxxx --current
read --project PROJECT --record-id BIC-xxxx --revision N
read --project PROJECT --record-id BIC-xxxx --revision N --event EVENT
save-version --project PROJECT --record-id BIC-xxxx --revision N
bind --project PROJECT --session-id SESSION --record-id BIC-xxxx --expected-revision N
bind --project PROJECT --session-id SESSION --lookup
migrate --project PROJECT --expected-schema 1
```

Use `COMMAND --help` for flags; record-format owns the complete contract.
`read --current` returns the actual effective revision. `read --revision N`
prefers that saved version, or returns the exact current revision if it equals
N and is not saved. Its source kind distinguishes these cases; an unsaved
current path is not a durable reference. It never substitutes a newer revision
for an unavailable old one. `--event` locates a specific event and relevant
corrections in either read mode.

After a successful apply and validation, use this compact receipt in the
user's language:

```text
BIC updated — BIC-0007 rev 3 | Delta: <only the semantic change> | state: valid / commit_pending
```

On creation, add the returned current/history paths once. Later, repeat paths
only on request or for handoff. Binding saves the expected current revision
and records its exact project, session, ID, revision, and saved paths inside the
project's registry. Setting a binding after current advances returns
`revision_conflict`; an existing binding or `read --revision N` can still resolve
the old saved version. Lookup is read-only, is not arming, and grants no write
ownership. A missing binding can be replaced by a complete explicit pointer,
never by guessing another record. Old `--plugin-data` calls return
`binding_migration_required` and leave the old external file unchanged.

Unsupported schema or unverified compatibility is read-only
`compatibility_hold`, not silent migration. Use project-scoped `migrate` only
within actual migration authority. Preserve legacy meaning and unknown ending
status; never infer an ending confirmation from an old spec, final, commit, or
release. Do not renumber old records, invent unsaved revisions, traverse other
projects, or modify old external binding state.

Use `commit-snapshot` only with explicit authority for a complete registered
BIC snapshot, including registered versions, archives, topics, and correction
dependencies. It is never record-scoped. Otherwise `commit_pending` is the
complete result. On write or commit failure preserve valid content and report
BIC-owned pending state, never whole-worktree cleanliness. Incomplete updates
are not effective revisions; recover only the affected unfinished operation.

## Save original versions when needed

An `end` update automatically saves the confirmed revision. Otherwise save a
version when a specific revision is used as a durable spec or handoff input.
Reuse an already saved identical version. Ordinary revisions and continued
reading in the same context do not trigger copies. A pre-ending saved version
remains explicitly unfinished; the later `end` update records and saves a new
revision containing the user's ending confirmation.

Use `save-version` to preserve the original current/history bodies, identity,
and their necessary topic/archive dependencies. Do not replace them with a new
handoff summary or a second design. Use returned paths rather than mutable
current paths for a durable version reference. A saved version records the
then-current grounds; it does not override newer user authority, and a BIC
revision does not update or reapprove an old spec automatically.

For dependent handoff, first complete apply successfully and capture the
returned project, ID, revision, and paths. Save that revision when the handoff
needs a durable reference, then pass its actual saved paths. A draft,
placeholder, or guessed version path is never a handoff pointer. State whether
the pointer requests current effective content or a particular saved version.

## Supply the same native design with real BIC input

When BIC is armed and associated and the native workflow needs a spec, provide
and actually consider the corresponding current/history or saved-version
content during that same native exploration, organization, and review. Exact
content already acquired in the current context need not be read again. Read
ordinary two-file records normally; for long records use the effective-topic
entry and concrete history questions described above. Do not skip the agreed
BIC input because the visible conversation seems sufficient.

The spec combines current conversation, project facts, applicable requirements,
native design analysis, and the actual BIC supplement. Effective user
constraints retain their authority; rejected and withdrawn directions retain
historical status. Put relevant requirements naturally in the spec's own
sections, with exact source references where useful. A link alone does not
express a requirement, and BIC headings do not dictate the spec's structure.

When the native review passes materials to another reader, include the exact
BIC pointer and reading instruction in that existing handoff. Repair actual
omissions or distortions in the same spec. Do not create a parallel BIC spec,
BIC review report, or second approval flow. Leave native Skill files, methods,
capabilities, invocation, stage order, and approvals unchanged. Native
writing-plans consumes the same spec; do not require every plan to reread the
whole BIC record. Native paths that need no spec or plan gain none from BIC;
tasks without BIC continue normally.

Update the BIC record before dependent work when authorized user meaning
changes. Implementation details remain controller rulings. When fidelity
review is actually called for, assess relevant approved decisions, forbidden
regressions, and observable proof against implementation evidence; BIC does
not start that review or authorize successor work on its own.

## Recover the exact input or resolve this incident

Recover only from a valid explicit pointer or exact binding. Report the exact
project, record, revision, or file that failed. Check its explicitly associated
original location or known exact recoverable copies; this is recovery of the
same input, not a new approval step. Do not scan unrelated intent lines or
repeat exhausted searches without a new lead. Complete content of the exact
version already available in context satisfies the input despite a path failure.

Another revision, a summary, or memory reconstruction is not an exact copy.
Do not silently substitute it. Carry any registered correction with recovered
old content. Missing or stale association that leaves the intended record
unknown requires clarification, not selection of a plausible record.

If the exact input is unrecoverable and no decision covers this particular
missing input, state what is missing and that its impact cannot be fully known;
ask whether the user accepts proceeding without that input for this incident.
The user may wait for recovery or explicitly change this incident's input
agreement. Do not ask again for an already approved incident decision or turn
it into permission to skip future inputs.

Continue discussion and preparation independent of the missing input while
awaiting the answer or material. Keep the dependent input obligation and
completion judgment open; do not claim the agreed BIC supplement was used.
If the user accepts omission, proceed within that decision and report the
limited input basis. Do not introduce a separate “native context is sufficient”
test: unread material cannot be established as dispensable by inspection of
other context.
