# Brainstorming Intent Continuity record format

The `bic.py` writer performs deterministic mechanics only. A root/controller
must author both Markdown drafts and remains responsible for their meaning.
The writer substitutes only `{{RECORD_ID}}` and `{{REVISION}}`; it never
summarizes, classifies, or interprets conversation content.

## Project layout and manifest

Project state is created lazily by the first successful `apply`:

```text
.brainstorming-intent/
├── manifest.json
└── records/
    └── BIC-0001/
        ├── current.md
        └── history.md
```

Manifest schema version 1 contains `writer_version`, `project_state`, the next
stable record number, `commit_pending`, and a `records` object keyed by stable
`BIC-xxxx` identifiers. Each record also carries its own `commit_pending`
state; the project-level value remains true while any record is pending. An
unsupported schema enters `compatibility_hold`:
read commands report the hold and every mutating command refuses to write.
Malformed schema-v1 state, including invalid record IDs, missing or mistyped
metadata, non-canonical record paths, reused next IDs, or inconsistent pending
state, returns one `invalid_manifest` JSON result and is never used to build a
project path.

## Fixed Markdown contract

Every controller-authored current draft must contain these headings in order:

```text
# {{RECORD_ID}} Current Intent
Revision: {{REVISION}}
## Goal and non-goals
## Approved decisions
## Explicit prohibitions
## Rationale and consequences
## Observable proof
## Examples and edge cases
## Open questions
## Current Intent Map
```

`## Current Intent Map` must contain a closed fenced `mermaid` block.

Every controller-authored history draft must contain these headings in order:

```text
# {{RECORD_ID}} History
Revision: {{REVISION}}
## Rejected or superseded directions
## Key turning points
## Material counterexamples
## Evolution Map
```

`## Evolution Map` must contain a closed fenced `mermaid` block. Text is the
semantic authority; Mermaid is only its visual projection.

## Command and JSON contract

Every command writes exactly one JSON object to standard output. Success exits
0; a fail-closed result exits 2 with `ok: false`, a machine-readable `state`,
and an `error`.

```text
bic.py status --project PROJECT
bic.py apply --project PROJECT [--record-id BIC-xxxx] \
  --current-draft FILE --history-draft FILE --expected-revision N
bic.py validate --project PROJECT [--record-id BIC-xxxx]
bic.py bind --plugin-data PATH --session-id SESSION --project PROJECT \
  --record-id BIC-xxxx --expected-revision N
bic.py bind --plugin-data PATH --session-id SESSION --lookup
bic.py commit-snapshot --project PROJECT --message MESSAGE
```

For a new lineage, omit `--record-id` and require expected revision 0. For an
update, provide its stable ID and current revision. A mismatch fails closed
without changing project state. `apply` atomically replaces each record file,
then the manifest last. A successful apply records and reports
`commit_pending` together with the record ID, revision, and absolute
current/history paths; it never invokes Git. A record-scoped successful
`validate` reports the same exact pointer after checking the persisted record.
This is the no-commit path when project authority forbids a commit. Record IDs
are limited to the four-digit range
`BIC-0001` through `BIC-9999`; a valid exhausted registry uses
`next_record_number: 10000`, and a new-record apply returns
`record_id_exhausted` before reading drafts or writing project state.

`bind` writes only `PATH/session-bindings.json`. `PATH` is mandatory and must
resolve outside the project. Bindings are keyed by session ID and contain the
exact project, record, revision, current path, and history path. `--lookup` is
read-only and fails closed for missing projects, missing records, or stale
revisions or paths. A record ID is always explicit; multiple records are never
guessed.

Invoking `commit-snapshot` explicitly authorizes one complete registry Git
snapshot: the manifest plus every registered lineage's canonical `current.md`
and `history.md`. It accepts no record ID or expected revision. Before changing
the manifest, index, or `HEAD`, it validates every registered record. It then
sets every record and the project-level pending flag false and commits only the
complete BIC path closure while preserving unrelated modified and staged
state.

Success may report only `bic_paths_clean`; no output asserts that the whole
worktree is clean. A Git failure restores the exact pending set that existed
before the attempt. If a hook or other process changes any BIC path after Git
creates the commit, the fail-closed result includes that commit ID and marks
the complete live registry pending again. The former record-scoped `commit`
interface is not supported. When project authority forbids the full snapshot
commit, do not invoke `commit-snapshot`; the successful `apply` result is the
complete pending-state path.
