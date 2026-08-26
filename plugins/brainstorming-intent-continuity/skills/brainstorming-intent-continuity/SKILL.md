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

Reply with `BIC armed — explicit session mode; no project record exists until a
semantic event.` Arming itself writes nothing. Superpowers Brainstorming alone
is intentional no-continuity mode. Do not arm from a quoted Skill name, a
negated request, fenced/pasted documentation, or a prompt-string match.

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

## Maintain one intent lineage

Continue a lineage when a decision serves its accepted outcome and constraints.
Start a new one for an independent outcome, not a requirement/example/extension
of the current one. Ask once before writing if materially ambiguous. A repeated
invocation is not a new intent.

Text is authority. Put current decisions, prohibitions, rationale, proof, edge
cases, and open questions in `current.md`; put rejected/superseded directions
and reasons in `history.md`. Remove superseded text from current. Both files
need their respective Mermaid projections, which are synchronized visual aids,
not authority. Before drafting, read
[`references/record-format.md`](references/record-format.md) for the fixed
headings, dual-Mermaid, layout, and schema contract.

Apply these placement rules literally:

- `current.md` states only the operative rule or prohibition. Any earlier,
  proposed, rejected, or superseded direction and its reason belongs only in
  `history.md`, even when it would fit grammatically under an edge-case heading.
- For a separate future intent that has not started and has no qualifying
  event, the current lineage may retain only the out-of-scope boundary. Keep
  that future intent's goal and constraints outside both files until it starts
  its own lineage; never mix them into the active record. Inside either BIC
  file, use only a generic boundary such as `A separate future intent is out
  of scope.` Do not name, list, paraphrase, or negate that future intent's
  internal goal or constraints merely to explain their exclusion.

## Use the deterministic writer

Resolve the runtime-supplied path to this `SKILL.md` once before calling the
writer; never assume the target project's working directory contains companion
source:

```bash
BIC_SKILL_MD="/absolute/path/supplied-by-the-runtime/SKILL.md"
BIC_SKILL_DIR="$(cd "$(dirname "$BIC_SKILL_MD")" && pwd -P)"
test -f "${BIC_SKILL_DIR}/SKILL.md"
```

Inspect the enrolled project before a write:

```bash
python3 "${BIC_SKILL_DIR}/scripts/bic.py" status --project PROJECT
```

The root authors both drafts, then applies them with the exact revision:

```bash
python3 "${BIC_SKILL_DIR}/scripts/bic.py" apply \
  --project PROJECT --current-draft CURRENT.md --history-draft HISTORY.md \
  --expected-revision N
```

For a new lineage omit `--record-id` and use expected revision `0`; for an
update provide the stable ID and current revision. Run
`"${BIC_SKILL_DIR}/scripts/bic.py" validate` after apply. A revision mismatch
fails closed: re-read authority, never last-write-wins or invent a replacement.

Bind only the exact session, project, record, and revision with
`"${BIC_SKILL_DIR}/scripts/bic.py" bind` using plugin data outside the
project; look it up read-only before recovery. Use
`"${BIC_SKILL_DIR}/scripts/bic.py" commit-snapshot` only with explicit
authority to commit the manifest plus every registered lineage's
current/history files as one complete BIC registry snapshot. It is never
record-scoped. Otherwise `commit_pending` is the complete result.
Run `"${BIC_SKILL_DIR}/scripts/bic.py" COMMAND --help` for flags; the
record-format reference owns the contract.

## Recover, degrade, and hand off honestly

- Recover only from a valid explicit pointer or exact binding. Missing/stale
  bindings and multiple plausible records never permit guessing; ask once or
  require explicit arming.
- Unknown schema or unverified compatibility is read-only
  `compatibility_hold`, never silent migration. An unavailable Skill/hook is
  `BIC not armed`; explicit pairing remains the fallback.
- On write/commit failure preserve validated content where possible and report
  BIC-owned dirty or `commit_pending`, never whole-worktree cleanliness.

For a spec, plan, task brief, implementation handoff, or review, give the
exact record ID, revision, and current/history paths:

```text
BIC pointer: BIC-0007 rev 3
current: PROJECT/.brainstorming-intent/records/BIC-0007/current.md
history: PROJECT/.brainstorming-intent/records/BIC-0007/history.md
```

For a new lineage the required order is: complete `apply` successfully;
capture its returned record ID, revision, current path, and history path; put
all four fields in the handoff; only then start dependent work. A proposed
draft or placeholder is never a handoff pointer.

Do not substitute a copied transcript. Map only relevant decisions into the
consumer artifact. Update BIC authority before dependent execution when
user-approved meaning changes; implementation details remain controller
rulings. Fidelity review checks the linked record's approved decisions,
forbidden regressions, and observable proof with implementation evidence.
