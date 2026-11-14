# Taco Supreme Mod Packs

Mod packs for the Taco Supreme game servers. Install guide and server info: **https://games.tacosupreme.us**

## Valheim

Download the latest pack from [Releases](../../releases/latest) (`TacoSupreme-Valheim-ModPack.zip`).

1. **Install BepInEx first.** Get [BepInExPack_Valheim](https://thunderstore.io/c/valheim/p/denikson/BepInExPack_Valheim/), extract it into your Valheim folder, launch the game once to the main menu, then quit.
2. **Install the pack.** Extract the zip into `Valheim/BepInEx/plugins`.
3. **Updating?** Delete the old files in `BepInEx/plugins` first, then extract the new pack.

Each release lists the mods and versions it contains.

## Update alerts

A GitHub Action ([`mod-check.yml`](.github/workflows/mod-check.yml)) runs daily at 14:00 UTC. It compares the versions in [`mods/valheim.json`](mods/valheim.json) with the latest on Thunderstore. When something newer is out, it opens a **"Valheim mod updates available"** issue with changelog links and @mentions the owner, so GitHub sends a notification.

## Publishing a new pack (the approval step)

1. Go to **Actions → Publish mod pack → Run workflow**. Leave it blank to use the latest of every mod, or hold a mod back with e.g. `Epic Loot=0.14.0`. Tick **Test only** to build a pack you can download without publishing it.
2. The workflow downloads each mod from Thunderstore, builds `TacoSupreme-Valheim-ModPack.zip` (one folder per mod), publishes a release, updates `mods/valheim.json` and closes the update issue.
3. The website reads `mods/valheim.json`, so its download info and mod list update right away.
4. The game server installs the same versions at **5:00 AM Pacific** the next morning (see below).

## Server sync

[`server/modsync.py`](server/modsync.py) runs on the game server every day at 5:00 AM Pacific. If a new pack was published, it downloads the approved versions from Thunderstore, stops the `TacoheimForever01` AMP instance, backs up the mods, configs and world, installs the new mods and starts the server. If BepInEx reports a mod that fails to load, it rolls back to the previous mods automatically. If nothing new was published, it does nothing.

Setup and everyday commands: [`server/README.md`](server/README.md).

Game (Valheim) updates are handled separately by the AMP Scheduler.

## Minecraft

The Minecraft server is vanilla. If mods are added, a Minecraft pack will be published here.

---

All mods belong to their original authors and are bundled here only so players can match the server's exact versions.
