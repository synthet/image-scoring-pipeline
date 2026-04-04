# Claude Code hooks

Copy `settings.json.example` to `settings.json` in this folder (or merge into your user `~/.claude/settings.json`). Valid JSON only — no comments inside the file.

Official reference: https://code.claude.com/docs/en/hooks-guide

## Suggested events (names may vary by CLI version)

Configure matchers and commands per your install. Typical use cases:

- **PreToolUse** — block or log sensitive tool calls.
- **PostToolUse** — telemetry or notifications.
- **Notification** — desktop or webhook alerts on completion.

Start with an empty `"hooks": {}` and add one hook at a time; verify on a throwaway repo first.
