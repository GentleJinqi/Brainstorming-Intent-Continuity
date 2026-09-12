# Changelog

All notable changes to Brainstorming Intent Continuity are documented here.
The project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Focused post-apply validation with `--current-only`, an explicit record ID and
  expected revision, and a scope-bearing receipt. It checks current dependencies
  without auditing unrelated records or older saved versions. Existing full
  validation and complete-registry snapshot checks are preserved.

### Changed

- Partial activation pauses dependent Brainstorming/BIC work while independent
  authorized work continues. Structural loading evidence, forward-only recovery
  and controlled-bootstrap confirmation remain required.
- Clarify that BIC supplies input to the existing native workflow under current
  user, project and runtime authority, without adding stages or repeat approvals.


## [0.2.0] - 2026-09-06

### Added

- Explicit round facts for one deliverable discussion result, whole-round ending
  confirmation, and scoped reopening without treating execution repair as a new
  design round.
- Exact current/saved reads, original-version preservation on confirmed ending
  and durable handoff, and optional immutable history/topic parts with event
  navigation and later correction lookup.
- Schema 2 project-local storage with shared reader/exclusive writer locking,
  alternating working slots, and one manifest publication per complete revision.

### Changed

- Supply and consider BIC material in the same native Brainstorming spec design
  and review, preserving native methods, ordering and approvals. Recover exact
  missing inputs or obtain an incident-specific omission decision while
  continuing independent work.
- Keep every generated draft, temporary file, record, preserved input and session
  binding inside the project using BIC. Setting a binding saves the expected
  current revision; existing bindings continue to resolve their saved input.
- Include registered saved versions, parts and corrections in complete-registry
  Git snapshots, excluding inactive working slots and session runtime state.

### Compatibility

- Schema 1 remains readable and validatable; writes require explicit project
  migration with `migrate --expected-schema 1`. Migration preserves IDs,
  revisions, body bytes and pending flags, recording unknown ending status.
  Older writers hold schema 2 read-only rather than update it.
- Legacy `bind --plugin-data` returns `binding_migration_required`; rebind with
  an explicit project and expected current revision. Old external binding files
  remain unchanged. No automatic cross-project migration is performed.

### Validation

- The behavioral candidate passed 84 mechanical tests before release preparation.
  Actual `gpt-6-astra` / `ultra` runs covered two pairs of historical design
  replays (native Brainstorming versus native Brainstorming with BIC) and four
  controlled turns for corrections, explicit ending and unavailable versions.
- Core intent and key corrections were retained in the sampled designs. The
  candidate added reading and execution overhead: root-turn elapsed time rose
  by about 11.4% and 45.2%, and non-cached input tokens by 45.3% and 32.1%, in
  the two pairs. These are root-task measurements, not whole-agent totals or
  billing figures.
- Candidate runs also retrieved additional memory context, so the replays were
  not strictly equal-input comparisons. The observations establish tested
  behavior, not general quality improvement, efficiency gains, statistical
  non-inferiority, or model-specific superiority. Long-term use, context
  compaction benefits and an independent spec-reviewer handoff remain unproven.

## [0.1.4] - 2026-08-26

### Changed

- Document the supported existing-installation upgrade path through marketplace
  refresh, plugin reinstall, version verification, and a new-Task activation
  boundary without deleting project-owned BIC records.

### Fixed

- Return exact current/history paths from `apply` and record-scoped `validate`
  so a new lineage can supply its promised handoff pointer without guessing.
- Reject malformed session binding files and entries through the JSON
  fail-closed path instead of leaking a Python traceback.
- Include the required project argument in the Skill's post-apply validation
  command.
- Reconcile controlled bootstrap reconstructions to applicable native project
  authority, which takes precedence over recovered Task history and BIC
  defaults and can forbid a record or write.

## [0.1.3] - 2026-08-26

### Fixed

- Fail closed instead of reporting BIC armed when the prompt contains the
  paired names but Superpowers Brainstorming was not structurally loaded.
- End partial-activation turns immediately and make later recovery forward-only
  unless the user explicitly confirms a controlled bootstrap.

### Changed

- Report every successful record update with a low-distraction, one-line
  semantic delta and BIC-owned state.

## [0.1.2] - 2026-08-26

### Fixed

- Use the plugin-qualified Skill invocation required by Codex so explicit BIC
  activation loads the installed Skill instead of leaving the bare name as
  ordinary prompt text.

## [0.1.1] - 2026-08-26

### Added

- An explicit companion Skill for Superpowers Brainstorming.
- Lazy, project-local intent records with separate `current.md` and
  `history.md` authorities.
- Current Intent Map and Evolution Map Mermaid projections.
- Deterministic schema validation, revision protection, session binding, and
  complete-registry Git snapshots.
- Exact record pointers for specs, plans, task briefs, handoffs, and fidelity
  review.
- A GitHub repository marketplace package and 19 deterministic writer tests.

[Unreleased]: https://github.com/GentleJinqi/Brainstorming-Intent-Continuity/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/GentleJinqi/Brainstorming-Intent-Continuity/compare/v0.1.4...v0.2.0
[0.1.4]: https://github.com/GentleJinqi/Brainstorming-Intent-Continuity/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/GentleJinqi/Brainstorming-Intent-Continuity/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/GentleJinqi/Brainstorming-Intent-Continuity/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/GentleJinqi/Brainstorming-Intent-Continuity/releases/tag/v0.1.1
