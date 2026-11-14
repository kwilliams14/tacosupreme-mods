"""Build and publish a new Valheim mod pack from Thunderstore.

Run by the "Publish mod pack" workflow after the server has been updated.
Every mod is pulled at its latest version unless pinned with PINS, e.g.
  PINS="Epic Loot=0.14.0, Igao/Ultimate_QOL=1.0.10"
Each mod goes in its own folder (r2modman layout), so players extract the
zip straight into Valheim/BepInEx/plugins.

Env: PINS (optional), DRY_RUN=1 to build the zip without publishing.
"""
import datetime as dt
import io
import json
import os
import subprocess
import urllib.request
import zipfile
from pathlib import Path

from check_mods import API, ISSUE_LABEL, version_key

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "mods" / "valheim.json"
DIST = ROOT / "dist"
DOWNLOAD = "https://thunderstore.io/package/download/{ns}/{name}/{ver}/"
SKIP_EXT = (".pdb", ".mdb", ".xml")
META = {"manifest.json", "icon.png", "readme.md", "changelog.md", "license", "license.md", "license.txt"}
UA = {"User-Agent": "tacosupreme-mod-publish"}


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()


def parse_pins(raw):
    pins = {}
    for part in (raw or "").replace(";", ",").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            pins[k.strip().lower()] = v.strip()
    return pins


def pick_version(mod, pins):
    for key in (mod["name"].lower(), mod["thunderstore"].lower()):
        if key in pins:
            return pins[key], True
    data = json.loads(get(API.format(mod["thunderstore"])))
    return data["latest"]["version_number"], False


def add_package(out_zip, mod, version):
    ns, name = mod["thunderstore"].split("/")
    blob = get(DOWNLOAD.format(ns=ns, name=name, ver=version))
    folder = f"{ns}-{name}"
    with zipfile.ZipFile(io.BytesIO(blob)) as pkg:
        entries = [(i, i.filename.replace("\\", "/")) for i in pkg.infolist() if not i.is_dir()]
        has_plugins = any(p.lower().startswith("plugins/") for _, p in entries)
        added = 0
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
            if not rel or rel.lower().endswith(SKIP_EXT):
                continue
            out_zip.writestr(f"{folder}/{rel}", pkg.read(info))
            added += 1
    if not added:
        raise SystemExit(f"{mod['name']} {version}: package had no plugin files")
    print(f"  {mod['name']} {version}: {added} files -> {folder}/")


def sh(*args, capture=True):
    r = subprocess.run(args, check=True, capture_output=capture, text=True)
    return r.stdout if capture else ""


def release_exists(tag):
    return subprocess.run(["gh", "release", "view", tag], capture_output=True).returncode == 0


def main():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    pins = parse_pins(os.environ.get("PINS"))
    dry = os.environ.get("DRY_RUN") == "1"
    asset = manifest["pack"]["asset"]

    chosen = []
    for mod in manifest["mods"]:
        ver, pinned = pick_version(mod, pins)
        chosen.append((mod, ver, pinned))

    DIST.mkdir(exist_ok=True)
    zip_path = DIST / asset
    print("Building pack:")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as out:
        for mod, ver, _ in chosen:
            add_package(out, mod, ver)
    size = zip_path.stat().st_size

    today = dt.datetime.now(dt.timezone.utc).date()
    version = today.strftime("%Y.%m.%d")
    tag, n = f"valheim-{version}", 2
    while not dry and release_exists(tag):
        version = f"{today.strftime('%Y.%m.%d')}.{n}"
        tag, n = f"valheim-{version}", n + 1

    rows = []
    for mod, ver, pinned in chosen:
        was = mod["installed"]
        change = "" if ver == was else (f" (was {was})" if version_key(ver) > version_key(was) else f" (rolled back from {was})")
        rows.append(f"| {mod['name']} | {ver}{change}{' 📌' if pinned else ''} |")
    notes = "\n".join([
        f"Valheim mod pack for **Tacoheim Forever**, {today.isoformat()}.", "",
        "**Install BepInEx first** ([BepInExPack_Valheim](https://thunderstore.io/c/valheim/p/denikson/BepInExPack_Valheim/)), "
        "launch Valheim once, then extract this zip into `Valheim/BepInEx/plugins`. "
        "Updating? Delete the old files in `BepInEx/plugins` first.", "",
        "| Mod | Version |", "|---|---|", *rows, "",
        "Full guide: https://games.tacosupreme.us/#mods",
    ])
    print(notes)
    if dry:
        print(f"\nDRY RUN: built {zip_path} ({size} bytes), nothing published.")
        return

    notes_file = DIST / "notes.md"
    notes_file.write_text(notes, encoding="utf-8")
    sh("gh", "release", "create", tag, str(zip_path), "--title", f"Valheim mod pack {version}",
       "--notes-file", str(notes_file), "--latest")
    print(f"Published release {tag}")

    for mod, ver, _ in chosen:
        mod["installed"] = ver
    manifest["pack"].update({"release": tag, "version": version, "date": today.isoformat(), "size_bytes": size})
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    sh("git", "config", "user.name", "github-actions[bot]")
    sh("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    sh("git", "add", str(MANIFEST))
    sh("git", "commit", "-m", f"Publish Valheim mod pack {version}")
    sh("git", "push")
    print("Updated mods/valheim.json")

    issues = json.loads(sh("gh", "issue", "list", "--state", "open", "--label", ISSUE_LABEL, "--json", "number"))
    for issue in issues:
        sh("gh", "issue", "close", str(issue["number"]), "--comment",
           f"Published in [{tag}](../../releases/tag/{tag}). The site now offers this pack.")
        print(f"Closed issue #{issue['number']}")


if __name__ == "__main__":
    main()
