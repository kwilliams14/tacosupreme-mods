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

After the server's mods are updated, a new pack is published, `mods/valheim.json` is bumped to the new versions, and the issue is closed.

## Minecraft

The Minecraft server is vanilla. If mods are added, a Minecraft pack will be published here.

---

All mods belong to their original authors and are bundled here only so players can match the server's exact versions.
