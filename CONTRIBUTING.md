# Contributing

Thank you for helping improve Brainstorming Intent Continuity.

## Before opening a change

- Use [GitHub Issues](https://github.com/GentleJinqi/Brainstorming-Intent-Continuity/issues)
  for bugs, design questions, and feature proposals.
- Keep the plugin a companion to Superpowers Brainstorming. Do not copy or
  modify Superpowers inside this repository.
- Do not include private transcripts, project records, absolute local paths,
  credentials, or user activity data in issues, fixtures, or pull requests.
- Separate a proposed convenience feature from the explicit invocation core;
  automatic activation must never be implied by documentation alone.

## Validate a change

Run the product tests from the repository root:

```bash
mkdir -p "$PWD/.tmp"
TMPDIR="$PWD/.tmp" PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

For documentation command contracts alone:

```bash
TMPDIR="$PWD/.tmp" PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_public_package.py -v
```

Keep all generated fixtures, drafts, logs and tool temporary output inside the
owning project, normally `.tmp/`; pass the same boundary to any delegate. Do not
write test output to system temporary directories or change global settings.
Use synthetic projects for schema migration and binding tests; a real project
migration, install, publication or native Skill change needs its own authority.

If you modify the Skill or plugin package, also run the Codex Skill and plugin
validators available in your local Codex installation. Describe the behavior
you tested and any remaining runtime limitations in the pull request.
For instruction changes, retain a relevant pre-change behavior observation and
test the affected consumer behavior. Executable documentation examples test CLI
compatibility, not actual Skill activation or native spec quality. Reuse valid
evidence and rerun only what the change invalidates.

## Pull requests

Keep changes narrow, update both READMEs when user-facing behavior changes, and
add an entry under `Unreleased` in `CHANGELOG.md`.

## 中文贡献说明

保持 BIC 作为原生 Superpowers Brainstorming 的 companion，不复制或修改原生 Skill 文件，
也不增加独立阶段或审批；原生方法的使用服从当前用户、项目和运行环境权威。
公开 issue、fixture 和 PR 不得包含真实聊天、项目记录、私人
绝对路径、凭据或用户活动资料。

在仓库根目录运行测试，所有夹具、草稿、日志和工具临时输出都放在所属项目内，通常为
`.tmp/`；向获准委派的代理传递同样边界，不使用系统临时目录或修改全局配置：

```bash
mkdir -p "$PWD/.tmp"
TMPDIR="$PWD/.tmp" PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

只检查公开命令文档时可将末尾改为 `discover -s tests -p test_public_package.py -v`。
迁移和绑定测试使用合成项目；真实迁移、安装、发布及原生 Skill 修改需要各自授权。修改
Skill 或插件包时，使用本地安装提供的相应 validator，并说明行为验证及运行时限制。
指令变更保留有关的修改前行为观察，再验证受影响的使用行为；命令示例测试不证明结构化
激活或原生 spec 质量。复用有效证据，只重跑被改动失效的范围。

PR 保持范围明确；用户可见行为变化同步双语 README，写入 CHANGELOG 的 `Unreleased`，
不要因开发环境或模型变化提前改动稳定版本元数据。
