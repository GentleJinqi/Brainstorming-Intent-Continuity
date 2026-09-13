# Changelog

All notable changes to Brainstorming Intent Continuity are documented here.
The project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.2] - 2026-09-13

### English

This release contains the cumulative changes since stable `0.2.0`, including
`0.2.1`, which remained an unpublished preparation version. There is no separate
`0.2.1` release to install first.

#### Added

- Focused post-apply validation with `--current-only`, an explicit record ID and
  expected revision, and a scope-bearing receipt. It checks manifest metadata
  and the selected current dependencies, including correction parts, without
  auditing unrelated record bodies or old saved views. Full validation and
  complete-registry snapshot checks remain available.

#### Changed

- Show one truthful BIC status on every user-facing turn that actually uses it,
  merging armed and update receipts. A no-update turn creates no extra read,
  write, validation, or ending question; paused, ended, reference-only and
  incomplete activation states remain distinct.
- Ask for explicit whole-round ending only when the complete agreed result is
  reviewable. Keep already authorized native work moving while BIC remains open,
  honor explicit stops, and avoid repeating a deferred ending question each turn.
- Consider agreed current or saved BIC input before forming relevant sections of
  the same native spec, including inputs from ended discussions. Preserve material
  conditions and rationale through applicable planning and execution review
  without adding a parallel workflow, universal spec requirement, or BIC reviewer.
- Replace superseded operative wording and repair affected native spec passages,
  retaining useful history. Lifecycle-only revisions do not invalidate an
  otherwise unchanged spec.
- Preserve the agreed scope and evidence standard when carrying intent into a
  native spec, including accepted approximations and limits. Stronger guarantees
  and merely possible concerns do not become new completion conditions.
- Scope ordinary format reading to the required sections and reuse known exact
  state. Preserve revision-conflict checks, current-only post-apply validation,
  full-registry snapshots and explicit migration authority. Exploration alone
  creates no durable BIC record but does not prohibit authorized native drafts.

- On partial activation, pause dependent Brainstorming/BIC work while independent
  authorized work continues. Preserve structural loading evidence, forward-only
  recovery and controlled-bootstrap confirmation.

#### Compatibility and validation

- Preserve schema 2 storage and existing command interfaces from `0.2.0`.
  Existing schema 2 projects need no migration. Schema 1 writes still require
  explicit project migration authority; plugin upgrades do not migrate records.
- The earlier preparation passed 99 mechanical tests: 29 CLI, 46 schema 2,
  9 package and 15 validation-scope tests. These are automated checks, not 99
  model conversations or a new complete-suite run for this release.
- Local release checks cover version metadata, public package contracts and
  documentation consistency. Instruction changes describe intended workflow
  behavior; these checks do not establish general thinking-quality or
  net-efficiency gains. Installation and structural Skill loading require
  acceptance in a new task after upgrading.

Upgrade instructions: [English](README.md#upgrade-an-existing-installation).

### 简体中文

本版包含自稳定版 `0.2.0` 以来的累计变化，包括始终未发布的 `0.2.1` 准备版本；无需先安装
一个单独的 `0.2.1` 发布版。

#### 新增

- apply 后可使用 `--current-only`、准确的 record ID 与 expected revision 进行定向验证，
  回执明确报告范围。它检查 manifest 元数据和所选当前记录的依赖（包括 correction
  parts），不审计无关记录正文或旧保存视图。完整验证及完整 registry snapshot 检查保留。

#### 变化

- 实际使用 BIC 的回合给出一次真实状态，合并激活与更新回执。无更新回合不因此新增读取、
  写入、验证或结束提问；暂停、结束、仅引用和未完整激活的状态分别如实报告。
- 完整约定结果可供审阅时才请求明确的整轮结束确认；BIC 未结束时继续已获授权的原生
  工作，尊重明确停止指令，不在每个回合重复已推迟的结束提问。
- 在形成同一原生 spec 的相关章节前考虑已约定的当前或保存版 BIC 输入，包括已结束
  讨论的输入；向适用的计划和执行审查承接必要条件与理由，不另建流程、强制 spec 或
  增加 BIC reviewer。
- 替换已失效的现行表述，并修复受影响的原生 spec 段落，保留有用历史；仅含生命周期
  事实的修订不会使实质未变的 spec 失效。
- 承接意图时保留已约定范围和证据标准，包括已接受的近似与限制；更强保证和仅属可能的
  顾虑不会自动成为新的完成条件。
- 按操作读取所需格式章节并复用已知准确状态；保留修订冲突检查、写后定向验证、完整
  registry snapshot 及显式迁移授权。单纯探索不创建持久 BIC 记录，也不禁止获授权的原生草稿。
- 部分激活时暂停依赖激活的工作，继续独立获授权的工作；保留结构化加载证据、forward-only
  恢复和 controlled bootstrap 的确认要求。

#### 兼容性与验证

- 保留 `0.2.0` 的 schema 2 存储与现有命令接口。已有 schema 2 项目无需迁移；schema 1
  写入仍需该项目明确授权迁移。插件更新不会迁移记录。
- 此前准备已通过 99 项机械测试：29 项 CLI、46 项 schema 2、9 项包检查和 15 项验证范围
  测试。这些是自动化检查，不是 99 场模型对话，也不是本版完整套件的新一轮执行结果。
- 本地发布检查覆盖版本元数据、公开包契约和文档一致性。指令变化描述预期流程行为；这些
  检查不能证明普遍思考质量或净效率提升。安装与结构化 Skill 加载需在更新后的新任务中验收。

更新说明：[简体中文](README.zh-CN.md#更新已有安装)。

## [0.2.1] - 2026-09-12 (unpublished preparation / 未发布准备)

This version was prepared locally and was not published. Its changes are included
in `0.2.2`; the dated validation below describes that earlier preparation only.
本版本仅完成本地准备，未发布；其变化累计纳入 `0.2.2`，以下验证描述仅对应当时的准备。

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

### Compatibility

- Preserve the schema 2 storage and existing command interfaces from `0.2.0`.
  Existing schema 2 projects need no migration. Schema 1 remains read-only until
  an explicitly authorized project migration; plugin upgrades do not migrate
  project records.
- Existing full validation, its JSON receipt and complete-registry snapshot
  checks remain unchanged. Current-only validation requires an explicit record
  ID and expected revision and reports only its checked scope.

### Validation

- The behavioral candidate passed 99 mechanical tests on Python `3.9.18`,
  including 15 new validation-scope tests. Skill and plugin validation passed.
- Five synthetic GPT-6 Astra instruction scenarios matched the intended rules.
  The previous version already followed current higher-priority rules in the
  shared baseline scenarios; wording changes clarify ambiguity and do not
  establish general behavior improvements, latency reductions or statistical
  advantages.
- These checks do not establish structural Skill loading in a real new task
  after installing this release.


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

[Unreleased]: https://github.com/GentleJinqi/Brainstorming-Intent-Continuity/compare/v0.2.2...HEAD
[0.2.2]: https://github.com/GentleJinqi/Brainstorming-Intent-Continuity/compare/v0.2.0...v0.2.2
[0.2.1]: https://github.com/GentleJinqi/Brainstorming-Intent-Continuity/commit/0fb64f012a6af6298d11b1d9196c6ecf5364fefe
[0.2.0]: https://github.com/GentleJinqi/Brainstorming-Intent-Continuity/compare/v0.1.4...v0.2.0
[0.1.4]: https://github.com/GentleJinqi/Brainstorming-Intent-Continuity/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/GentleJinqi/Brainstorming-Intent-Continuity/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/GentleJinqi/Brainstorming-Intent-Continuity/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/GentleJinqi/Brainstorming-Intent-Continuity/releases/tag/v0.1.1
