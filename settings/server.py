#!/usr/bin/env python3
"""Tiny local settings page for agent-guards. Python 3 standard library only.

Serves settings/index.html on 127.0.0.1, reads live readings from the memguard and
diskguard scripts, and writes ~/.config/agent-guards/config.json when you press Save.
"""
import argparse
import http.server
import json
import os
import secrets
import socketserver
import subprocess
import sys
import tempfile
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.environ.get("AGENT_GUARDS_CONFIG") or os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "agent-guards", "config.json")
TOKEN = secrets.token_urlsafe(24)
BIN = None

DEFAULTS = {
    "memory": {"warn_used_pct": 80, "block_used_pct": 90, "use_macos_pressure": True,
               "orphan_min_age_min": 30, "stale_orphan_age_min": 240},
    "disk": {"unit": "gb", "warn_free": 50, "block_free": 20},
    "cleanup": {"auto_clean": True, "project_dirs": "~/Documents, ~/Projects, ~/code, ~/dev",
                "next_cache_idle_days": 3, "node_modules_idle_days": 0,
                "xcode_derived_data_days": 7, "keep_browser_versions": 2},
}

# (section, key, min, max) for every number the page may write.
NUMBERS = [
    ("memory", "warn_used_pct", 10, 99), ("memory", "block_used_pct", 10, 99),
    ("memory", "orphan_min_age_min", 1, 10080), ("memory", "stale_orphan_age_min", 0, 10080),
    ("disk", "warn_free", 0, 100000), ("disk", "block_free", 0, 100000),
    ("cleanup", "next_cache_idle_days", 1, 365), ("cleanup", "node_modules_idle_days", 0, 365),
    ("cleanup", "xcode_derived_data_days", 0, 365), ("cleanup", "keep_browser_versions", 1, 10),
]
BOOLS = [("memory", "use_macos_pressure"), ("cleanup", "auto_clean")]


def load_config():
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        with open(CONFIG) as f:
            saved = json.load(f)
        if not isinstance(saved, dict):   # e.g. [] or null: ignore it, the page can save over it
            saved = {}
        for section, values in saved.items():
            if isinstance(values, dict) and section in cfg:
                cfg[section].update(values)
    except (OSError, ValueError, RecursionError):
        pass
    return cfg


def validate(data):
    cfg = load_config()
    try:
        for section, key, lo, hi in NUMBERS:
            raw = data[section][key]
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                return None, f"{section}.{key} must be a number"
            v = float(raw)
            if not lo <= v <= hi:
                return None, f"{section}.{key} must be between {lo} and {hi}"
            if section != "disk" and v != int(v):
                return None, f"{section}.{key} must be a whole number"
            cfg[section][key] = int(v) if v == int(v) else round(v, 1)
        for section, key in BOOLS:
            if not isinstance(data[section][key], bool):
                return None, f"{section}.{key} must be true or false"
            cfg[section][key] = data[section][key]
        unit = data["disk"]["unit"]
        if unit not in ("gb", "pct"):
            return None, "disk.unit must be gb or pct"
        cfg["disk"]["unit"] = unit
        dirs = data["cleanup"]["project_dirs"]
        if not isinstance(dirs, str):
            return None, "project folders must be text"
        dirs = dirs.strip()
        if len(dirs) > 1000 or any(c in dirs for c in "\"\\$`") or any(ord(c) < 32 or c in "\u2028\u2029\x7f" for c in dirs):
            return None, "project folders: plain comma-separated paths only"
        for d in (x.strip() for x in dirs.split(",")):
            if not d:
                continue
            if not (d.startswith("~/") or d.startswith("/")):
                return None, f"project folders must start with ~/ or / ({d})"
            if ".." in d.split("/"):
                return None, f"project folders: '..' isn't allowed ({d})"
            full = os.path.realpath(os.path.expanduser(d))
            home = os.path.realpath(os.path.expanduser("~"))
            if not full.startswith(home + os.sep):
                return None, f"project folders must be inside your home folder ({d})"
        cfg["cleanup"]["project_dirs"] = dirs
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as e:
        return None, f"missing or bad value: {e}"
    m, d = cfg["memory"], cfg["disk"]
    if m["block_used_pct"] <= m["warn_used_pct"]:
        return None, "Memory: the block level must be higher than the warn level"
    if d["unit"] == "pct" and d["warn_free"] > 100:
        return None, "Disk: a percentage can't be above 100"
    if d["block_free"] >= d["warn_free"]:
        return None, "Disk: the block level must be below the warn level"
    return cfg, None


def save_config(cfg):
    target = os.path.realpath(CONFIG)   # keep a symlinked config.json a symlink
    os.makedirs(os.path.dirname(target), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(target), prefix=".config.", suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(cfg, f, indent=2)
            f.write("\n")
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def readings():
    out = {}
    for name in ("memguard", "diskguard"):
        try:
            r = subprocess.run([os.path.join(BIN, name), "json"], capture_output=True, text=True, timeout=10)
            out[name] = json.loads(r.stdout)
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            out[name] = {"error": str(e)}
    return out


class Handler(http.server.BaseHTTPRequestHandler):
    timeout = 10              # drop clients that stall
    server_version = "agent-guards"
    sys_version = ""

    def log_message(self, *args):
        pass

    def do_GET(self):
        self._safe(self._get)

    def do_POST(self):
        self._safe(self._post)

    def _safe(self, fn):
        try:
            fn()
        except Exception as e:  # never drop the connection without an answer
            try:
                self._send(500, json.dumps({"error": f"server error: {type(e).__name__}"}))
            except Exception:
                pass

    def _host_ok(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def _get(self):
        if not self._host_ok():
            return self._send(403, '{"error":"forbidden"}')
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), encoding="utf-8") as f:
                html = f.read().replace("__TOKEN__", TOKEN)
            return self._send(200, html, "text/html")
        if path == "/api/state":
            return self._send(200, json.dumps({"config": load_config(), "config_path": CONFIG,
                                               "readings": readings()}))
        return self._send(404, '{"error":"not found"}')

    def _post(self):
        if not self._host_ok() or self.headers.get("X-Token") != TOKEN:
            return self._send(403, '{"error":"forbidden"}')
        if self.path != "/api/config":
            return self._send(404, '{"error":"not found"}')
        try:
            length = max(0, min(int(self.headers.get("Content-Length") or 0), 20000))
            data = json.loads(self.rfile.read(length))
        except (ValueError, RecursionError):
            return self._send(400, '{"error":"bad JSON"}')
        cfg, err = validate(data)
        if err:
            return self._send(400, json.dumps({"error": err}))
        try:
            save_config(cfg)
        except OSError as e:
            return self._send(500, json.dumps({"error": f"couldn't save {CONFIG}: {e.strerror}"}))
        return self._send(200, json.dumps({"ok": True, "config": cfg, "config_path": CONFIG,
                                           "readings": readings()}))


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = False   # never share a port with another app's listener
    request_queue_size = 64


def main():
    global BIN
    ap = argparse.ArgumentParser(description="agent-guards settings page")
    ap.add_argument("--bin", default=os.path.join(os.path.dirname(HERE), "bin"))
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()
    BIN = os.path.abspath(args.bin)
    httpd = None
    if not 1024 <= args.port <= 65515:
        sys.exit("--port must be between 1024 and 65515")
    for port in range(args.port, args.port + 20):
        try:
            httpd = Server(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if httpd is None:
        sys.exit(f"No free port between {args.port} and {args.port + 19}")
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print(f"agent-guards settings: {url}\nConfig file: {CONFIG}\nPress Ctrl+C to stop.", flush=True)
    if not args.no_open:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
