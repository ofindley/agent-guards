---
name: agent-guards
description: Memory and disk safeguards for agent work. Use before starting anything heavy (dev or preview servers, builds, renders, game engines, headless browsers, video or image processing, dependency installs, big downloads, parallel agents or workflows), when a memguard or diskguard hook warns or blocks a command, or when the user asks about memory, disk space, cleanup, or changing these limits.
---

# Agent Guards

Two small scripts that stop agents from freezing the machine or filling the disk.

- `memguard` watches memory. Levels: **OK**, **WARN**, **CRITICAL** (blocks heavy commands).
- `diskguard` watches free disk space. Same levels.
- Limits are the user's own choice, stored in `~/.config/agent-guards/config.json`.

The scripts live in this skill's `bin/` folder. Below, `<skill>` means this skill's folder
(usually `~/.claude/skills/agent-guards`).

## Before heavy work

Run both checks first:

```bash
<skill>/bin/agent-guards check
```

It prints the memory and disk level. Exit code 0 = OK, 1 = WARN, 2 = CRITICAL.

Heavy work means: starting a dev or preview server, a build, a render, a game engine,
a headless browser, video or image batches, `npm install` and other installs, large downloads,
or spawning parallel agents.

## At WARN

Keep going, but carefully:

- **Memory:** reuse servers that are already running instead of starting new ones. Run heavy jobs
  one at a time. Keep subagents to the minimum. Stop what you started as soon as it's done.
- **Disk:** keep outputs small. Delete intermediate files (frames, proxies, scratch renders,
  temp downloads) once the final output exists. Don't keep several variants of the same output.
- Mention the warning to the user in one line.

## At CRITICAL (blocked)

Start nothing new. The hook will block heavy commands anyway.

1. See what is using resources: `<skill>/bin/memguard status` or `<skill>/bin/diskguard status`
   (and `<skill>/bin/diskguard report` for the big folders).
2. Stop servers and background jobs you started that are no longer needed.
3. Tell the user, and suggest the safe cleanups:
   - `<skill>/bin/memguard clean` stops orphaned dev servers whose session is gone.
   - `<skill>/bin/diskguard clean` removes rebuildable caches only. Run it with `-n` first to preview.
4. Only if the user explicitly says to go ahead anyway, prefix the one command with
   `MEMGUARD_OVERRIDE=1` or `DISKGUARD_OVERRIDE=1`. Never add an override on your own.

## Rules

- Never delete the user's files to make room. Cleanup is limited to caches tools rebuild on their
  own. For anything else, show `<skill>/bin/diskguard report` and let the user decide.
- Never kill processes that belong to another live session or the user's own apps. `memguard clean`
  only targets orphaned dev tooling.
- Clean up after yourself: stop every server, watcher, and headless browser you started.

## Changing the limits

If the user wants different limits, run `<skill>/bin/agent-guards settings`. It opens a local page
with sliders, live readings, and a Save button. Or edit `~/.config/agent-guards/config.json`
directly (see `config.example.json`). Env vars like `MEMGUARD_BLOCK_USED_PCT=85` or
`DISKGUARD_WARN=100` override the file for one run.
