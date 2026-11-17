# agent-guards

Stops AI coding agents (Claude Code, Codex, your own scripts) from freezing your computer or
filling your disk.

- **memguard**: when memory is nearly full, agents can't start more dev servers, builds or renders.
- **diskguard**: when disk space is nearly full, agents can't run installs, big downloads or renders.

You pick the limits on a small settings page. Below the warning limit the agent gets a reminder to
go easy. Below the block limit, heavy commands are stopped and the agent is told why.

Works on macOS. The memory and disk checks also work on Linux.

## Install

You need Claude Code and `python3` (already on macOS). `jq` is optional.

**1. Download it into your Claude Code skills folder**

```bash
git clone https://github.com/ofindley/agent-guards ~/.claude/skills/agent-guards
```

**2. Choose your limits** (opens a page in your browser; press Ctrl+C in the terminal when done)

```bash
~/.claude/skills/agent-guards/bin/agent-guards settings
```

If you skip this, the defaults are: warn at 80% memory used, block at 90%; warn below 50 GB free
disk, block below 20 GB.

**3. Turn on the blocking**

Claude Code runs a small check (a "hook") before every command the agent runs. Add it to
`~/.claude/settings.json`:

- If the file doesn't exist, create it with the contents of
  [`hooks/settings.example.json`](hooks/settings.example.json).
- If it exists but has no `"hooks"` section, paste the `"hooks"` section from that example in.
- If it already has `"hooks"` → `"PreToolUse"`, add just the `{ "matcher": "Bash", ... }` entry
  from the example to that list.

Easiest: ask Claude, "add the agent-guards hooks from hooks/settings.example.json to my
~/.claude/settings.json". Then restart Claude Code.

**4. Check it works**

```bash
~/.claude/skills/agent-guards/bin/agent-guards check
```

You should see `memory: OK` and `disk: OK`. To see a block without actually running low,
pretend the limit is 1%:

```bash
echo '{"tool_input":{"command":"npm run dev"}}' | MEMGUARD_BLOCK_USED_PCT=1 MEMGUARD_WARN_USED_PCT=1 ~/.claude/skills/agent-guards/bin/memguard hook
```

It prints something like:

```
memguard BLOCKED this command: CRITICAL: 32% memory used (warn at 1%, block at 1%), ...
Starting more heavy work now risks freezing the machine. Before retrying:
  1. Run ~/.claude/skills/agent-guards/bin/memguard status to see what is using memory.
  ...
```

**5. Optional (macOS): automatic cleanup**

A background job that runs every 10 minutes. It stops dev servers that agents left running after
their session ended, clears caches that rebuild themselves, and shows a notification when space or
memory is low. It runs once as soon as you install it, so preview first:

```bash
~/.claude/skills/agent-guards/bin/memguard clean -n
```

```bash
~/.claude/skills/agent-guards/bin/diskguard clean -n
```

```bash
~/.claude/skills/agent-guards/bin/agent-guards watchdog install
```

## Everyday commands

All live in `~/.claude/skills/agent-guards/bin/`.

| Command | What it does |
| --- | --- |
| `agent-guards check` | Memory and disk level: OK, WARN or CRITICAL |
| `agent-guards status` | Biggest apps, leftover dev servers, and what cleanup would free |
| `agent-guards settings` | Open the settings page |
| `memguard clean -n` | List leftover dev servers. Without `-n`, stops them |
| `diskguard clean -n` | List caches cleanup would remove. Without `-n`, removes them |
| `diskguard report` | Big folders worth a look. Never deleted automatically |

To type them without the full path:

```bash
mkdir -p ~/.local/bin && ln -s ~/.claude/skills/agent-guards/bin/* ~/.local/bin/
```

(`~/.local/bin` needs to be on your PATH.)

## What gets blocked

Only when a limit is crossed, and only commands that start heavy work:

- **memguard:** dev servers, builds, tests and renders, such as `npm run dev`, `next dev`, `vite`,
  `node app.js`, `cargo build`, `docker run`, `xcodebuild`, `ffmpeg`.
- **diskguard:** installs, downloads, builds and copies, such as `npm install`, `pip install`,
  `git clone`, `curl -o`, `docker pull`, `cp -R`, `ffmpeg`.

Everyday commands like `ls`, `git commit`, `node -v`, `docker ps`, `curl` without saving a file,
`--version` / `--help`, and `docker compose down` are never blocked. Text inside quotes, comments
and commit messages doesn't count. Commands wrapped in `bash -c "..."`, `timeout`, `nice`, `env`,
`npm --prefix ...` and similar are still checked.

It can't see inside your own scripts: `./build.sh` runs even if the script installs things.

**Letting one command through:** if you decide it's fine, tell the agent to put
`MEMGUARD_OVERRIDE=1` or `DISKGUARD_OVERRIDE=1` in front of that command, for example
`DISKGUARD_OVERRIDE=1 npm install`. The agent is told never to do this without your OK.

## What cleanup deletes

Only things that rebuild themselves:

- Next.js `.next` build folders in projects you haven't touched for 3 days (and no dev server running)
- Old browser downloads from Puppeteer and Playwright (keeps the newest 2)
- Xcode build files (DerivedData) older than 7 days
- iOS simulators Xcode already marks "unavailable" (their iOS version was removed), including their app data
- Unused uv and pnpm cache entries
- npm and bun download caches, only when the disk is at the block level
- `node_modules` in idle projects: **off unless you turn it on** in settings

It never touches your documents, code, photos, videos or git repos. It only looks in project
folders inside your home folder, never follows a shortcut (symlink) out of a cache folder, and skips
`node_modules` that's committed to git. If your settings file can't be read, automatic cleanup
turns itself off until you fix it.

**Leftover dev servers** are dev tools whose agent session has closed. Only these programs count:
Next.js and Vite dev servers, other dev tools run from a project's `node_modules`
(webpack, Storybook, Astro, Remotion and similar), `npm run dev`-style commands,
`python -m http.server`, `ffmpeg`, headless Godot, and browsers that Puppeteer or Playwright
downloaded. A file or folder name that merely contains one of those words (like
`vim next-server.md`) never counts, and your own apps, editors, terminals and databases are never
touched.

One catch: a long job you started yourself in the background (with `nohup` or `&`) and then closed
the terminal looks the same. The watchdog stops these after 4 hours, or after 30 minutes when
memory is at the block level. Raise those times in settings if you run long renders that way, and
check `memguard clean -n` before installing the watchdog.

## Settings

Saved in `~/.config/agent-guards/config.json` (example: [`config.example.json`](config.example.json)).
A value that doesn't make sense (a typo, a negative number) is ignored and the default is used.

Environment variables override the file for one run, for example
`MEMGUARD_BLOCK_USED_PCT=85` or `DISKGUARD_WARN=100`.

## Uninstall

1. If you installed the watchdog: `~/.claude/skills/agent-guards/bin/agent-guards watchdog uninstall`
2. Remove the agent-guards entries from `"hooks"` in `~/.claude/settings.json`, then restart Claude Code.
3. Delete the files:

```bash
rm -rf ~/.claude/skills/agent-guards ~/.config/agent-guards ~/.local/state/agent-guards
```

If you added the shortcuts, also remove `~/.local/bin/agent-guards`, `memguard` and `diskguard`.

## Linux

The checks, hook and cleanup work. The watchdog is macOS only; on Linux run
`~/.claude/skills/agent-guards/bin/agent-guards watch` from cron every 10 minutes instead.
Linux needs `jq` or `python3` to read your settings.

## License

MIT
