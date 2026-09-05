# Brainstorming Intent Continuity record format

`bic.py` performs deterministic storage mechanics. The root/controller authors
current/history and any grouped parts, supplies lifecycle facts, and remains
responsible for meaning and genuine user approval. The tool renders identity
placeholders and managed navigation; it does not classify conversation, choose
accepted requirements, decide when to end, or add Mermaid nodes.

## Project layout and publication

State is created lazily by the first successful `apply`. All drafts, temporary
output, records, preserved inputs, and session state belong to that project's
resolved directory. Drafts may use project-local aliases only when their
resolved targets remain inside the project. Managed output paths must be
canonical and may not use symlink aliases, including aliases between slots.

```text
.brainstorming-intent/
├── manifest.json
├── records/BIC-0001/slots/a/{current,history}.md
├── records/BIC-0001/slots/b/{current,history}.md  # optional working slot
├── versions/BIC-0001/rN/{current,history}.md    # only when preserved
├── versions/BIC-0001/rN/version.json
├── parts/BIC-0001/DIGEST.md                    # only when parts exist
└── session-bindings.json                      # optional runtime state
```

Schema 2 keeps one active current/history pair. A writer takes an exclusive
lock on the existing project directory, prepares the inactive pair and complete
registered dependencies, and atomically replaces the manifest last. Readers
hold a shared lock throughout identity resolution and content reading. File
replacement fsyncs the file and parent directory. An unregistered prepared
file is not a published revision. The writer retires only precisely registered
old paths no longer needed by an active view, saved version, or correction;
it never scans for unrelated files to delete. Retirement failure leaves the
published view usable and preserves the retirement list for retry.

Manifest record fields include `revision`, `active_slot`, `current_path`,
`history_path`, `round`, `part_ids`, `event_ids`, `part_refs`, and
`commit_pending`. Record body paths remain registry-relative, such as
`records/BIC-0001/slots/a/current.md`. Resolved view paths, part paths, saved
version paths, dependencies, and `retired_paths` are project-relative and start
with `.brainstorming-intent/`. CLI body paths are absolute actual paths.

Top-level `versions` maps record ID and decimal revision string to a saved
view. `events` maps record ID and event ID to its immutable entry; `corrections`
is the registered relation list. IDs are local to their record, so another
record's `E1` cannot supply this record's corrections. Part references contain
`id`, `kind`, `path`, and SHA-256 `digest`. A view's `part_refs` fixes the exact
part identities for that revision. A saved view additionally contains
`source_kind: saved`, `descriptor_path`, and `dependencies`, a map from every
saved body/part path to its SHA-256 digest. Its `version.json` contains the same
view. The descriptor is also a registered Git dependency; it does not hash
itself. These hashes identify immutable saved material, not the whole project.

Schema 1 remains readable and validatable. Mutating it requires explicit
`migrate --expected-schema 1`; migration preserves IDs, revision, body bytes,
and pending flags, and records `round.state: unknown`. It does not infer an
ending or migrate external bindings. Unsupported schemas return
`compatibility_hold`; malformed registrations return `invalid_manifest`.

## Fixed Markdown contract

Every current draft includes these headings in order:

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

Every history draft includes these headings in order:

```text
# {{RECORD_ID}} History
Revision: {{REVISION}}
## Rejected or superseded directions
## Key turning points
## Material counterexamples
## Evolution Map
```

Each final map section must contain a closed fenced `mermaid` block. Both
`{{RECORD_ID}}` and `{{REVISION}}` are required in the submitted drafts. The
published text includes rendered identities plus any mechanical navigation;
saving a version preserves that published text without resummarizing it.

## CLI and JSON

Successful commands emit one JSON object and exit 0. Mechanical failures emit
one object with `ok: false`, a machine-readable `state`, and `error`, and exit
2. Invalid command syntax uses argparse's usage error.

```text
bic.py status --project PROJECT
bic.py validate --project PROJECT [--record-id ID]
bic.py migrate --project PROJECT --expected-schema 1
bic.py apply --project PROJECT [--record-id ID] --expected-revision N \
  --current-draft PROJECT/.tmp/current.md \
  --history-draft PROJECT/.tmp/history.md \
  [--update-draft PROJECT/.tmp/update.json]
bic.py read --project PROJECT --record-id ID (--current | --revision N) \
  [--event EVENT_ID ...]
bic.py save-version --project PROJECT --record-id ID --revision N
bic.py bind --project PROJECT --session-id SESSION --record-id ID \
  --expected-revision N
bic.py bind --project PROJECT --session-id SESSION --lookup
bic.py commit-snapshot --project PROJECT --message MESSAGE
```

For a new independent record, omit `--record-id` and use expected revision 0.
Existing uncompleted records do not prevent a new independent ID. Updates name
the record and its expected current revision; `revision_conflict` rejects a
mismatch before publication. IDs run from `BIC-0001` through `BIC-9999`;
`next_record_number: 10000` is valid exhausted state and a new allocation returns
`record_id_exhausted`. Apply reports `commit_pending`, ID, new revision, and
actual current/history paths. It never invokes Git.

`read` returns `record_id`, `revision`, `source_kind`, `round`, `current`,
`history`, `parts`, `corrections`, `events`, and `part_index`. A body is
`{path, text}`. `parts` is a map keyed by part ID. Ordinary read expands the
current/history pair and all effective topic material, retaining event metadata
and part paths as selection navigation. It does not read every historical part
body. Repeated `--event` selects events in the requested view and adds their
historical parts and registered corrections from the current project.
Unknown events return `event_not_found`; an event added after a saved revision
cannot be selected as if it belonged to that saved revision.

`--revision N` prefers the saved view, including when N is also current. Without
a saved view, it may read the current revision when exactly equal, reporting
`source_kind: current`; this is not a persistent saved reference. Other old
revisions return `version_unavailable` without substituting the latest view.
Missing saved inputs return `version_unavailable`, and changed saved identities
return `version_conflict`. Ordinary reads check the bodies they actually return;
`validate`, preservation, binding lookup, and snapshot check the full registered
dependency closure needed by those operations.

## Lifecycle updates and preservation

`--update-draft` is a strict JSON object. Allowed optional top-level fields are
`round`, `parts`, `events`, and `corrections`; unknown fields, extra entry fields,
null objects, invalid enums, duplicate IDs, and incomplete evidence are rejected.
Omitting the update is a normal semantic revision; absence of activity or an
unrelated read never changes lifecycle state.

```json
{
  "round": {
    "action": "end",
    "evidence": {
      "asked": "May this agreed result be delivered and this round ended?",
      "answer": "Yes, end this round.",
      "source": "controlled-fixture-turn-2"
    }
  }
}
```

| Action | Allowed prior state | Result | Exact evidence fields |
| --- | --- | --- | --- |
| continue | open, unknown | unchanged state | optional; if supplied, source |
| pause | open, unknown | paused | source |
| resume | paused | open | source |
| cancel | open, paused, unknown | cancelled | source |
| replace | open, paused, unknown | replaced | successor_record_id, source |
| reopen | completed | open | original_promise, defect, scope, source |
| end | open, paused, unknown | completed | asked, answer, source |

All evidence fields are non-empty strings. Replacement names a distinct
registered successor; it does not infer the successor or change its state.
The stored round contains `state`, the supplied `action`, and its `evidence`.
Ordinary apply preserves open/paused/unknown facts; completed/cancelled/replaced
rounds reject ordinary apply with `round_closed`. Explicit illegal transitions
return `invalid_transition` (continuing a completed round returns `round_closed`).
Only evidenced `reopen` reopens a completed round. The root determines whether
submitted evidence truly supports the action; this schema is not an approval
classifier.

End is a new revision containing the confirmation fact. Before one manifest
publication, the tool prepares that new pair, its immutable version directory,
and all dependencies. `save-version` preserves a currently available revision
without incrementing its semantic revision or completing its round. The same
saved version is verified and reused; divergent existing files return
`version_conflict`. Ordinary apply creates no saved version directories.
Interrupted preservation may leave unregistered prepared files; matching retry
reuses them, while incompatible bytes are reported rather than overwritten.

## Parts, navigation, and corrections

Root-provided updates use these exact shapes:

```json
{
  "parts": [{"id": "H1", "kind": "history", "draft": "PROJECT/.tmp/event.md"}],
  "events": [{
    "id": "E1", "part_id": "H1", "anchor": "original-record",
    "title": "spec input role", "conditions": "native spec design"
  }],
  "corrections": [{"target_event": "E1", "part_id": "H1", "kind": "recording_error"}]
}
```

Part/event IDs begin with an ASCII letter followed by at most 63 ASCII letters,
digits, underscores, or hyphens. Part kind is `history` or `topic`; correction
kind is `superseded` or `recording_error`. A new event must be registered with
a submitted history part and an existing Markdown-heading anchor or explicit
HTML `a`/`span` ID. Historical part IDs cannot be changed in place; append a new
part and an explicit relation. Resubmitting the same topic ID replaces only its
active content reference. Saved views retain the prior path and bytes.

The tool prepares each part as `parts/ID/DIGEST.md`. History headers contain
record/part IDs, event IDs, and a query for current corrections using the actual
project path. Without current project access, an offline old file cannot know
later corrections. After moving or cloning the project, invoke the helper with
the new project path; historical embedded commands retain their original path.
The CLI resolves all managed relative paths against the supplied project.

Root may use a 16 KiB UTF-8 active-body budget and about 8 KiB history compaction target
as adjustable initial guidance. Move whole historical events, including a
single event larger than that budget, without automatically ending or allocating
an ID. Effective requirements may use topic parts and must remain fully
available. These are root grouping decisions; the writer imposes no byte-count
ending, truncation, or revision-count trigger.

After preparing paths, the writer renders one reserved `BIC-NAV` block in each
relevant body. Current lists all effective topic IDs and exact relative paths;
root-authored text retains global constraints, scope, and conditions. History
lists event titles, conditions, exact anchors, and one current-correction query
per event. It does not append every correction relation or correction body to
the daily record. A read-to-draft round trip replaces the managed block, so
changing a topic cannot retain stale navigation or accumulate duplicate blocks.

A selected correction result includes `target_event`, `part_id`, `kind`,
`original_revision` (event registration), `view_revision` (requested input),
`source_revision` (correction registration), and its actual `path`/`text`.
The original body remains intact. `recording_error` does not imply the user
accepted the mistaken entry and later changed their mind.

## Project-local binding and full registry snapshots

Binding writes `.brainstorming-intent/session-bindings.json`. It requires an
explicit project, record ID, session ID, and expected current revision. Within
one exclusive project lock it prepares the saved version, publishes its
manifest reference, then atomically writes the binding. Binding failure may
leave a usable saved input but never reports successful binding. Retry is
idempotent while the expected revision remains current. If apply has advanced
it, a new bind attempt returns `revision_conflict`; the old saved version
remains available through `read --revision N` and its complete explicit pointer.
Existing binding lookup continues to resolve the exact saved revision even
after the active revision advances. Lookup holds a shared project lock and
never saves, updates, guesses a record, or grants semantic write authority.

Bindings retain schema 1 envelope `{schema_version: 1, sessions: {...}}`; each
entry contains the absolute canonical project, record ID, revision, and actual
saved current/history paths. Malformed state returns `invalid_bindings`, absent
sessions `unbound_session`, and mismatched record/project/path registration
`stale_binding`. Explicit `--plugin-data` returns `binding_migration_required`
with migration instructions and never changes the old external file.

Invoking `commit-snapshot` authorizes one complete registry Git snapshot: the
manifest, every active view, every saved version descriptor and its exact
registered dependencies, and correction material. It excludes inactive working
copies, temporary files, and session runtime state. It includes precise retired
paths only when tracked or already staged for deletion; a nonexistent path
never tracked is not a required `git add` target. Validation of the full
registered closure finishes before modifying manifest pending flags, index,
or HEAD.

Snapshot preserves the existing Git failure behavior: only registered paths
are committed, unrelated modified/staged state is preserved, a Git failure
restores the exact prior pending set, and post-commit mutation marks the full
live registry pending again while reporting the actual commit ID. A failed
pre-commit can leave retirement deletions staged; retry includes those exact
HEAD-only deletions in the commit target without trying to re-add absent paths.
Success reports only `bic_paths_clean`, never a claim that the whole worktree
is clean. When project authority forbids the complete snapshot, leave the
successful apply/save result pending.

## Helper lock and path contracts

`publish_update`, `read_record`, `save_version`, and `migrate_project` each own
one project lock. Binding owns its lock and calls `_save_version_locked`, which
prepares but does not publish a saved descriptor. Neither operation nests a
second file-descriptor lock. `resolve_record_view`, `prepare_parts`,
`collect_registered_dependencies`, and `resolve_corrections` run under their
caller's lock. `prepare_parts` accepts optional already-loaded `manifest` and
`revision` keyword arguments; `resolve_corrections` accepts `record_id` to scope
record-local event IDs and rejects an ambiguous unscoped lookup.
`collect_registered_dependencies` and `registry_git_paths` return
project-relative paths, including saved descriptors. CLI JSON converts actual
returned content paths to absolute paths for normal Markdown access.
