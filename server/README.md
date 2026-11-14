# Server mod sync (Valheim)

Keeps the `TacoheimForever01` AMP instance on the exact mod versions in [`mods/valheim.json`](../mods/valheim.json).

**How it works:** you click **Publish mod pack** on GitHub. That's your approval. At 5:00 AM Pacific, the server checks GitHub. If there's a new pack, it:

1. downloads the approved versions from Thunderstore (if a download fails, it stops here and the server isn't touched),
2. stops the instance,
3. backs up `BepInEx/plugins`, `BepInEx/config` and the world saves (it keeps the last 5 backups),
4. replaces `BepInEx/plugins` with the approved mods (configs are left alone),
5. starts the instance and watches `BepInEx/LogOutput.log` for up to 5 minutes,
6. rolls back to the previous mods if any mod fails to load. That pack is then skipped until you publish a new one.

If there's no new pack, it does nothing and the server isn't restarted.

## One-time setup

**Prerequisite:** in AMP, set **TacoheimForever01 → Configuration → System Settings → System → Startup Mode** to **Start**. The script restarts the whole instance, and this setting makes Valheim come back up on its own.

1. In Webmin, open **Others → Command Shell** (it runs as root) and run:
   ```
   curl -fsSL https://raw.githubusercontent.com/kwilliams14/tacosupreme-mods/main/server/install.sh | bash
   ```
   This installs everything to `/home/amp/tacosupreme-modsync` and turns on the 5 AM timer. Both checks it prints at the end should say **OK**.

2. Preview what it would do. This changes nothing:
   ```
   sudo -u amp python3 /home/amp/tacosupreme-modsync/modsync.py --dry-run
   ```
   It lists what's in `BepInEx/plugins` now and what it would install. On the first run, it reorganizes your hand-uploaded DLLs into one folder per mod.

3. Pick one:
   - **Run it for real now, while you can watch** (recommended; it restarts Valheim for about 1–2 minutes):
     ```
     sudo -u amp python3 /home/amp/tacosupreme-modsync/modsync.py
     ```
   - **Or** tell it the server already matches the current pack, so nothing happens until the next publish:
     ```
     sudo -u amp python3 /home/amp/tacosupreme-modsync/modsync.py --adopt
     ```

## Everyday commands (Webmin Command Shell)

| What | Command |
|---|---|
| See the log | `tail -n 40 /home/amp/tacosupreme-modsync/logs/modsync.log` |
| When's the next run? | `systemctl list-timers tacosupreme-modsync.timer` |
| Sync right now instead of waiting for 5 AM | `sudo -u amp python3 /home/amp/tacosupreme-modsync/modsync.py` |
| Retry a pack that was rolled back | `sudo -u amp python3 /home/amp/tacosupreme-modsync/modsync.py --force` |
| Pause the 5 AM sync | `systemctl disable --now tacosupreme-modsync.timer` |
| Resume it | `systemctl enable --now tacosupreme-modsync.timer` |
| Update this script | re-run the `curl ... install.sh` line (your settings and backups are kept) |

Backups are in `/home/amp/tacosupreme-modsync/backups/`, one folder per install, named with the date and the pack it came before.

## Optional: get a GitHub issue when a sync fails

Failures are always written to the log. To also get a GitHub notification:

1. On GitHub, go to **Settings → Developer settings → Fine-grained tokens → Generate new token**.
2. Set **Repository access** to `tacosupreme-mods` only, with **Permissions → Issues: Read and write**.
3. Paste the token into `"github_token"` in `/home/amp/tacosupreme-modsync/config.json`. Only the `amp` user can read that file.

## Settings (`config.json`)

| Key | Default | Meaning |
|---|---|---|
| `instance` | `TacoheimForever01` | AMP instance name |
| `game_dir` | `.../TacoheimForever01/Valheim/896660` | folder that contains `BepInEx` |
| `instance_dir` | `.../TacoheimForever01` | searched for `worlds_local` folders to back up |
| `keep_backups` | `5` | how many backups to keep |
| `health_timeout_sec` | `300` | how long to wait for mods to load |
| `ampinstmgr` | blank (auto-detect) | full path to `ampinstmgr`, if it isn't found automatically |
| `github_token` | blank | optional, see above |
