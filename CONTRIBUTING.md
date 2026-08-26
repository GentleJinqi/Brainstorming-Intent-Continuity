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
python3 -m unittest discover -s tests -v
```

If you modify the Skill or plugin package, also run the Codex Skill and plugin
validators available in your local Codex installation. Describe the behavior
you tested and any remaining runtime limitations in the pull request.

## Pull requests

Keep changes narrow, update both READMEs when user-facing behavior changes, and
add an entry under `Unreleased` in `CHANGELOG.md`.
