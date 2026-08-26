# Changelog

All notable changes to Brainstorming Intent Continuity are documented here.
The project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.4] - 2026-08-26

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

[Unreleased]: https://github.com/GentleJinqi/Brainstorming-Intent-Continuity/compare/v0.1.4...HEAD
[0.1.4]: https://github.com/GentleJinqi/Brainstorming-Intent-Continuity/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/GentleJinqi/Brainstorming-Intent-Continuity/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/GentleJinqi/Brainstorming-Intent-Continuity/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/GentleJinqi/Brainstorming-Intent-Continuity/releases/tag/v0.1.1
