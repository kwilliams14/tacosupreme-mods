#!/usr/bin/env python3
"""Taco Supreme Valheim mod sync.

Runs on the game server (as the `amp` user) every day at 5:00 AM Pacific.
If a new mod pack has been published on GitHub (mods/valheim.json), it:

  1. downloads the exact approved mod versions from Thunderstore,
  2. stops the AMP instance,
  3. backs up BepInEx/plugins, BepInEx/config and the world saves,
  4. replaces BepInEx/plugins with the approved mods,
  5. starts the instance and checks the BepInEx log,
  6. rolls back to the backup if the mods fail to load.

If nothing new was published, it does nothing (no restart).

Usage:
  modsync.py              normal run (what the 5 AM timer does)
  modsync.py --dry-run    show what would change; touch nothing
  modsync.py --force      reinstall the current pack even if it's already installed
  modsync.py --adopt      record the current pack as installed without touching the server

Settings live in config.json next to this script. Python 3.8+, standard library only.
"""
import datetime as dt
import fcntl
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_FILE = HERE / "config.json"
STATE_FILE = HERE / "state.json"
LOCK_FILE = HERE / ".lock"
LOG_DIR = HERE / "logs"
STAGING = HERE / "staging"

DEFAULTS = {
    "manifest_url": "https://raw.githubusercontent.com/kwilliams14/tacosupreme-mods/main/mods/valheim.json",
    "download_url": "https://thunderstore.io/package/download/{ns}/{name}/{ver}/",
    "instance": "TacoheimForever01",
    "game_dir": "/home/amp/.ampdata/instances/TacoheimForever01/Valheim/896660",
    "instance_dir": "/home/amp/.ampdata/instances/TacoheimForever01",
    "backup_dir": str(HERE / "backups"),
    "keep_backups": 5,
    "ampinstmgr": "",            # blank = find it automatically
    "health_timeout_sec": 300,   # how long to wait for mods to load after start
    "github_token": "",          # optional: fine-grained token with Issues: write, to report failures
    "github_repo": "kwilliams14/tacosupreme-mods",
}

SKIP_EXT = (".pdb", ".mdb", ".xml")
META = {"manifest.json", "icon.png", "readme.md", "changelog.md", "license", "license.md", "license.txt"}
UA = {"User-Agent": "tacosupreme-modsync"}
LOG_OK = "Chainloader startup complete"
LOG_BAD = ("Could not load [", "[Fatal", "Error loading [")


# ---------------------------------------------------------------- helpers

_log_fh = None


def log(msg):
    line = f"{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(line, flush=True)
    if _log_fh:
        _log_fh.write(line + "\n")
        _log_fh.flush()


def load_config():
    cfg = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    return cfg


def get(url, timeout=120):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def fetch_manifest(cfg):
    url = cfg["manifest_url"]
    if url.startswith("http"):
        url += ("&" if "?" in url else "?") + f"t={int(time.time())}"  # dodge GitHub's raw cache
    return json.loads(get(url, timeout=30))


def read_state():
    return json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}


def write_state(manifest):
    STATE_FILE.write_text(json.dumps({
        "pack_version": manifest["pack"]["version"],
        "installed_at": dt.datetime.now().isoformat(timespec="seconds"),
        "mods": {m["thunderstore"]: m["installed"] for m in manifest["mods"]},
    }, indent=2) + "\n", encoding="utf-8")


def amp(cfg, *args):
    exe = cfg["ampinstmgr"] or shutil.which("ampinstmgr") or "/opt/cubecoders/amp/ampinstmgr"
    log(f"  ampinstmgr {' '.join(args)}")
    r = subprocess.run([exe, *args], capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(f"ampinstmgr {' '.join(args)} failed ({r.returncode}): {(r.stderr or r.stdout).strip()[-400:]}")


def stop(cfg):
    amp(cfg, "--StopInstance", cfg["instance"])
    time.sleep(5)


def start(cfg):
    amp(cfg, "--StartInstance", cfg["instance"])


# ---------------------------------------------------------------- mods

def stage_mods(cfg, manifest):
    """Download every approved mod into STAGING/plugins. The server is untouched."""
    if STAGING.exists():
        shutil.rmtree(STAGING)
    plugins = STAGING / "plugins"
    plugins.mkdir(parents=True)
    for mod in manifest["mods"]:
        ns, name = mod["thunderstore"].split("/")
        ver = mod["installed"]
        blob = get(cfg["download_url"].format(ns=ns, name=name, ver=ver))
        folder = plugins / f"{ns}-{name}"
        n = 0
        with zipfile.ZipFile(io.BytesIO(blob)) as pkg:
            entries = [(i, i.filename.replace("\\", "/")) for i in pkg.infolist() if not i.is_dir()]
            has_plugins = any(p.lower().startswith("plugins/") for _, p in entries)
            for info, path in entries:
                if has_plugins:
                    if not path.lower().startswith("plugins/"):
                        continue
                    rel = path[len("plugins/"):]
                else:
                    if "/" not in path and path.lower() in META:
                        continue
                    if path.lower().startswith(("config/", "patchers/")):
                        continue
                    rel = path
                if not rel or rel.lower().endswith(SKIP_EXT) or ".." in Path(rel).parts:
                    continue
                dest = folder / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(pkg.read(info))
                n += 1
        if not n:
            raise RuntimeError(f"{mod['name']} {ver}: package had no plugin files")
        log(f"  downloaded {mod['name']} {ver} ({n} files)")
    return plugins


def world_dirs(cfg):
    root = Path(cfg["instance_dir"])
    found = [p for p in root.rglob("*") if p.is_dir() and p.name in ("worlds_local", "worlds")]
    return [p for p in found if not any(q != p and q in p.parents for q in found)]


def backup(cfg, version):
    game = Path(cfg["game_dir"])
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    dest = Path(cfg["backup_dir"]) / f"{stamp}_before_{version}"
    dest.mkdir(parents=True)
    for sub in ("plugins", "config"):
        src = game / "BepInEx" / sub
        if src.exists():
            shutil.copytree(src, dest / sub, symlinks=True)
    worlds = world_dirs(cfg)
    if worlds:
        with tarfile.open(dest / "worlds.tar.gz", "w:gz") as tar:
            for w in worlds:
                tar.add(w, arcname=str(w.relative_to(cfg["instance_dir"])))
    log(f"  backup saved to {dest} (plugins, config, {len(worlds)} world folder(s))")
    old = sorted(p for p in Path(cfg["backup_dir"]).iterdir() if p.is_dir())
    for p in old[:-int(cfg["keep_backups"])]:
        shutil.rmtree(p)
        log(f"  removed old backup {p.name}")
    return dest


def swap_plugins(cfg, new_plugins):
    target = Path(cfg["game_dir"]) / "BepInEx" / "plugins"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(new_plugins, target)


def check_health(cfg, started_at):
    """Wait for BepInEx to finish loading; fail on missing/broken mods."""
    log_path = Path(cfg["game_dir"]) / "BepInEx" / "LogOutput.log"
    deadline = time.time() + int(cfg["health_timeout_sec"])
    while time.time() < deadline:
        time.sleep(5)
        if not log_path.exists() or log_path.stat().st_mtime < started_at:
            continue
        text = log_path.read_text(encoding="utf-8", errors="replace")
        bad = [l.strip() for l in text.splitlines() if any(b in l for b in LOG_BAD)]
        if bad:
            return False, "Mods failed to load:\n" + "\n".join(bad[:10])
        if LOG_OK in text:
            return True, "BepInEx loaded all mods"
    return False, f"BepInEx did not finish loading within {cfg['health_timeout_sec']}s (see {log_path})"


def report_failure(cfg, title, body):
    if not cfg.get("github_token"):
        return
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{cfg['github_repo']}/issues",
            data=json.dumps({"title": title, "body": body}).encode(),
            headers={**UA, "Authorization": f"Bearer {cfg['github_token']}",
                     "Accept": "application/vnd.github+json"},
            method="POST")
        urllib.request.urlopen(req, timeout=30).read()
        log("  opened a GitHub issue about the failure")
    except Exception as e:
        log(f"  could not open GitHub issue: {e}")


# ---------------------------------------------------------------- main

def run(args):
    cfg = load_config()
    manifest = fetch_manifest(cfg)
    want = manifest["pack"]["version"]
    have = read_state().get("pack_version")
    log(f"Published pack: {want}   Installed on server: {have or 'unknown'}")

    if "--adopt" in args:
        write_state(manifest)
        log(f"Recorded pack {want} as installed. Server not touched.")
        return 0
    if want == have and "--force" not in args:
        log("Server is up to date. Nothing to do.")
        return 0
    if want == read_state().get("failed_version") and "--force" not in args:
        log(f"Pack {want} failed before and was rolled back. Publish a new pack, or run with --force to retry.")
        return 0

    log("Downloading approved mods from Thunderstore...")
    new_plugins = stage_mods(cfg, manifest)

    current = Path(cfg["game_dir"]) / "BepInEx" / "plugins"
    before = sorted(p.name for p in current.iterdir()) if current.exists() else []
    after = sorted(p.name for p in new_plugins.iterdir())
    if "--dry-run" in args:
        log("DRY RUN. Would replace BepInEx/plugins:")
        log(f"  now:   {', '.join(before) or '(empty)'}")
        log(f"  after: {', '.join(after)}")
        log("Nothing was changed.")
        return 0

    log(f"Installing pack {want}...")
    stop(cfg)
    try:
        saved = backup(cfg, want)
    except Exception:
        log("Backup failed, so no mods were changed. Starting the server back up.")
        start(cfg)
        raise
    try:
        swap_plugins(cfg, new_plugins)
        started = time.time()
        start(cfg)
        ok, detail = check_health(cfg, started)
    except Exception as e:
        ok, detail = False, f"Error during install: {e}"

    if ok:
        write_state(manifest)
        shutil.rmtree(STAGING, ignore_errors=True)
        log(f"SUCCESS: pack {want} installed. {detail}.")
        return 0

    log(f"FAILED: {detail}")
    st = read_state()
    st["failed_version"] = want
    STATE_FILE.write_text(json.dumps(st, indent=2) + "\n", encoding="utf-8")
    log("Rolling back to the previous mods...")
    try:
        stop(cfg)
        target = Path(cfg["game_dir"]) / "BepInEx" / "plugins"
        if target.exists():
            shutil.rmtree(target)
        if (saved / "plugins").exists():
            shutil.copytree(saved / "plugins", target, symlinks=True)
        start(cfg)
        log("Rolled back. Server restarted with the previous mods.")
        rolled = "The server was rolled back to the previous mods and restarted."
    except Exception as e:
        log(f"ROLLBACK FAILED: {e}. Restore by hand from {saved}")
        rolled = f"Rollback failed ({e}). Restore by hand from `{saved}`."
    report_failure(cfg, f"Server mod sync failed for pack {want}",
                   f"The 5 AM sync could not install Valheim pack **{want}**.\n\n```\n{detail}\n```\n\n{rolled}\n\n"
                   f"Full log: `{LOG_DIR / 'modsync.log'}` on the server.")
    return 1


def main():
    global _log_fh
    LOG_DIR.mkdir(exist_ok=True)
    _log_fh = open(LOG_DIR / "modsync.log", "a", encoding="utf-8")
    lock = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("Another sync is already running. Exiting.")
        return 1
    log("=" * 60)
    try:
        return run(sys.argv[1:])
    except Exception as e:
        log(f"ERROR: {e}")
        report_failure(load_config(), "Server mod sync error", f"The mod sync stopped with an error:\n\n```\n{e}\n```")
        return 1


if __name__ == "__main__":
    sys.exit(main())
