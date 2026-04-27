## First-time setup

1. `cp .claude/settings.json.template .claude/settings.json`
2. Replace `<ABSOLUTE_PATH_TO_REPO>` with your local checkout path (twice).
3. Restart Claude Code so it picks up the MCP server config.

The backend itself derives all paths at runtime — no edits needed to Python code if the repo lives somewhere else.
