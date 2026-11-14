"""Daily Thunderstore check for the Taco Supreme mod packs.

Compares the versions in mods/<game>.json with the latest on Thunderstore.
If anything is newer, opens (or updates) one GitHub issue and @mentions the
owner so GitHub sends an email/app notification. Run with --dry-run locally
to print the report without touching GitHub.
"""
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://thunderstore.io/api/experimental/package/{}/"
ISSUE_LABEL = "mod-update"


def version_key(v):
    parts = []
    for p in v.split("."):
        parts.append((0, int(p)) if p.isdigit() else (1, p))
    return parts


def fetch_latest(pkg):
    req = urllib.request.Request(API.format(pkg), headers={"User-Agent": "tacosupreme-mod-check"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    latest = data["latest"]
    return latest["version_number"], data.get("date_updated", "")[:10]


def check(manifest):
    updates, errors = [], []
    for mod in manifest["mods"]:
        try:
            latest, updated = fetch_latest(mod["thunderstore"])
        except Exception as e:  # network or API problem: report, don't crash
            errors.append(f"- {mod['name']}: could not check ({e})")
            continue
        if version_key(latest) > version_key(mod["installed"]):
            ns, name = mod["thunderstore"].split("/")
            updates.append({
                "name": mod["name"],
                "installed": mod["installed"],
                "latest": latest,
                "updated": updated,
                "changelog": f"https://thunderstore.io/c/{manifest['community']}/p/{ns}/{name}/changelog/",
            })
    return updates, errors


def report(manifest, updates, errors):
    game = manifest["game"]
    lines = [f"@{manifest['notify']} New {game} mod versions are out.", "",
             "| Mod | In our pack | Latest | Released | Changelog |",
             "|---|---|---|---|---|"]
    for u in updates:
        lines.append(f"| {u['name']} | {u['installed']} | **{u['latest']}** | {u['updated']} | [changelog]({u['changelog']}) |")
    if errors:
        lines += ["", "Some mods could not be checked:", *errors]
    lines += ["", "**Next steps**",
              "1. Read the changelogs above.",
              "2. Go to **Actions → Publish mod pack → Run workflow** (pin any mod you want to hold back).",
              "3. That's it. The website updates right away, the server installs the pack at 5:00 AM Pacific, "
              "and this issue closes itself.", "",
              f"<!-- updates:{','.join(u['name'] + '@' + u['latest'] for u in updates)} -->"]
    return "\n".join(lines)


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def publish(manifest, body, updates):
    title = f"{manifest['game']} mod updates available"
    gh("label", "create", ISSUE_LABEL, "--color", "F0A04B", "--description", "Newer mod versions on Thunderstore", "--force")
    found = json.loads(gh("issue", "list", "--state", "open", "--label", ISSUE_LABEL, "--search", f'"{title}" in:title', "--json", "number,body"))
    if not found:
        gh("issue", "create", "--title", title, "--label", ISSUE_LABEL, "--body", body)
        print("Opened a new issue.")
        return
    issue = found[0]
    marker = body.rsplit("<!-- updates:", 1)[1]
    if marker in issue["body"]:
        print(f"Issue #{issue['number']} already lists these updates. Nothing new.")
        return
    gh("issue", "edit", str(issue["number"]), "--body", body)
    new = ", ".join(f"{u['name']} {u['latest']}" for u in updates)
    gh("issue", "comment", str(issue["number"]), "--body", f"@{manifest['notify']} More updates since this issue opened: {new}")
    print(f"Updated issue #{issue['number']}.")


def main():
    dry = "--dry-run" in sys.argv
    for path in sorted((ROOT / "mods").glob("*.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        updates, errors = check(manifest)
        print(f"{manifest['game']}: {len(updates)} update(s), {len(errors)} error(s)")
        if not updates:
            for e in errors:
                print(e)
            continue
        body = report(manifest, updates, errors)
        if dry:
            print(body)
        else:
            publish(manifest, body, updates)


if __name__ == "__main__":
    main()
