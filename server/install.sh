#!/usr/bin/env bash
# Installs (or updates) the Taco Supreme Valheim mod sync on the game server.
# Run as root, e.g. from Webmin > Others > Command Shell:
#   curl -fsSL https://raw.githubusercontent.com/kwilliams14/tacosupreme-mods/main/server/install.sh | bash
# Safe to run again: it updates the script and keeps your config.json and backups.
set -euo pipefail

RAW="https://raw.githubusercontent.com/kwilliams14/tacosupreme-mods/main/server"
DIR="/home/amp/tacosupreme-modsync"
UNIT="tacosupreme-modsync"

[ "$(id -u)" -eq 0 ] || { echo "Please run as root (or with sudo)."; exit 1; }
id amp >/dev/null 2>&1 || { echo "No 'amp' user found. Is AMP installed on this machine?"; exit 1; }
command -v python3 >/dev/null || { echo "python3 is missing: apt install python3"; exit 1; }

mkdir -p "$DIR"
curl -fsSL "$RAW/modsync.py" -o "$DIR/modsync.py"
chmod 755 "$DIR/modsync.py"

if [ ! -f "$DIR/config.json" ]; then
  cat > "$DIR/config.json" <<'EOF'
{
  "instance": "TacoheimForever01",
  "game_dir": "/home/amp/.ampdata/instances/TacoheimForever01/Valheim/896660",
  "instance_dir": "/home/amp/.ampdata/instances/TacoheimForever01",
  "keep_backups": 5,
  "health_timeout_sec": 300,
  "github_token": ""
}
EOF
  echo "Created $DIR/config.json"
fi
chown -R amp:amp "$DIR"
chmod 600 "$DIR/config.json"

cat > "/etc/systemd/system/$UNIT.service" <<EOF
[Unit]
Description=Taco Supreme Valheim mod sync
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=amp
Group=amp
WorkingDirectory=$DIR
Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/opt/cubecoders/amp
ExecStart=/usr/bin/python3 $DIR/modsync.py
EOF

cat > "/etc/systemd/system/$UNIT.timer" <<EOF
[Unit]
Description=Run the Valheim mod sync daily at 5:00 AM Pacific

[Timer]
OnCalendar=*-*-* 05:00:00 America/Los_Angeles
Persistent=false

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now "$UNIT.timer"

echo
echo "Installed. Checks:"
[ -d /home/amp/.ampdata/instances/TacoheimForever01/Valheim/896660/BepInEx ] \
  && echo "  OK   Valheim BepInEx folder found" \
  || echo "  WARN BepInEx folder not found. Check game_dir in $DIR/config.json"
if sudo -u amp env PATH="/usr/local/bin:/usr/bin:/bin:/opt/cubecoders/amp" sh -c 'command -v ampinstmgr' >/dev/null; then
  echo "  OK   ampinstmgr found"
else
  echo "  WARN ampinstmgr not found for the amp user. Set \"ampinstmgr\" in $DIR/config.json to its full path"
fi
echo "  Next run: $(systemctl show "$UNIT.timer" -p NextElapseUSecRealtime --value)"
echo
echo "Try it safely now (changes nothing):"
echo "  sudo -u amp python3 $DIR/modsync.py --dry-run"
