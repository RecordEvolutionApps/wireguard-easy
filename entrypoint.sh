#!/bin/bash

# Forwarding sysctls: on the device the agent runs this container privileged, so
# it can set its own network-namespace sysctls. Under host networking these are
# already 1 (Docker enables ip_forward on the host), so this is a no-op today —
# but once the agent moves apps onto bridge networking the container starts with
# ip_forward=0 in its own namespace, and without it VPN clients connect fine yet
# route nowhere. src_valid_mark is required by wg-quick's policy routing.
sysctl -w net.ipv4.ip_forward=1 || echo "WARNING: failed to enable net.ipv4.ip_forward — VPN clients will NOT be able to route traffic!"
sysctl -w net.ipv4.conf.all.src_valid_mark=1 || echo "WARNING: failed to set net.ipv4.conf.all.src_valid_mark"
if [ "${DISABLE_IPV6}" != "true" ]; then
  sysctl -w net.ipv6.conf.all.forwarding=1 || echo "WARNING: failed to enable net.ipv6.conf.all.forwarding — IPv6 VPN clients will NOT be able to route traffic!"
fi

settings_dir="/etc/wireguard"
data_dir="/data"

# Check if the data directory exists
if [ ! -d "$data_dir" ]; then
  echo "Error: The directory '$data_dir' does not exist."
  exit 1
fi

# Check if the settings directory exists
if [ ! -d "$settings_dir" ]; then
  echo "Error: The directory '$settings_dir' does not exist."
  exit 1
fi

# Check if the data directory is empty
if [ "$(ls -A "$data_dir")" ]; then
  echo "The directory '$data_dir' is not empty. Setting up link..."
  rm -rf "$settings_dir"
  ln -s "$data_dir" "$settings_dir"
  
else

    # Move files from settings to data using rsync
    cp -a "$settings_dir/" "$data_dir"
    if [ $? -ne 0 ]; then
    echo "Error: Failed to move files from '$settings_dir' to '$data_dir'."
    exit 1
    fi
    echo "Successfully moved contents of '$settings_dir' to '$data_dir'."

    # Remove the original settings directory
    rm -rf "$settings_dir"
    if [ $? -ne 0 ]; then
    echo "Error: Failed to remove original directory '$settings_dir'."
    exit 1
    fi
    echo "Successfully removed original directory '$settings_dir'."

    # Create a symbolic link from settings to data
    ln -s "$data_dir" "$settings_dir"
    if [ $? -ne 0 ]; then
    echo "Error: Failed to create symbolic link from '$settings_dir' to '$data_dir'."
    exit 1
    fi
    echo "Successfully created symbolic link from '$settings_dir' to '$data_dir'."
fi

# Seed the client-facing VPN endpoint for the very first boot (wg-easy applies INIT_HOST /
# INIT_PORT only while the database does not exist yet). WireGuard is UDP and does NOT travel
# over the HTTPS app subdomain — clients connect through the IronFlock tunnel's UDP edge, so the
# seed uses the agent-injected TUNNEL_DOMAIN and public tunnel port WG_PORT when present. This is
# a best-effort snapshot: the authoritative endpoint is computed by the ironflock SDK and kept in
# sync by register_device.py (started below), which rewrites the DB within seconds of any change —
# including devices whose tunnel is only activated later (the agent updates the /data/env files
# in running containers without a restart). The server always LISTENS on 51820 inside the
# container; the tunnel forwards the public port there.
export INIT_ENABLED="true"
export INIT_HOST="${INIT_HOST:-${TUNNEL_DOMAIN:-app.ironflock.com}}"
export INIT_PORT="${INIT_PORT:-${WG_PORT:-51820}}"

# Print the effective configuration on start so it can be validated in the container logs.
# The admin password is masked (presence + length only) so it is never written to the logs.
echo "=================== wg-easy startup config ==================="
echo "  INIT_ENABLED     = ${INIT_ENABLED:-<unset>}"
echo "  INIT_USERNAME    = ${INIT_USERNAME:-<unset>}"
if [ -n "${INIT_PASSWORD}" ]; then
  echo "  INIT_PASSWORD    = set (${#INIT_PASSWORD} chars, must be >= 12)"
else
  echo "  INIT_PASSWORD    = <unset>"
fi
echo "  INIT_HOST        = ${INIT_HOST:-<unset>}"
echo "  INIT_PORT        = ${INIT_PORT:-<unset>}"
echo "  ENDPOINT SYNC    = register_device.py keeps the client Endpoint in sync (background)"
echo "  INIT_DNS         = ${INIT_DNS:-<unset>}"
echo "  INIT_ALLOWED_IPS = ${INIT_ALLOWED_IPS:-<unset>}"
echo "  DISABLE_IPV6     = ${DISABLE_IPV6:-<unset>}"
echo "  INSECURE         = ${INSECURE:-<unset>}"
echo "  DEVICE_KEY       = ${DEVICE_KEY:-<unset>}"
# Persistence check: wg-easy opens file:/etc/wireguard/wg-easy.db, and this entrypoint symlinks
# /etc/wireguard -> /data, so the DB physically lives at /data/wg-easy.db. Only /data survives
# restarts, so warn loudly if that symlink is not in place.
if [ -L "$settings_dir" ] && [ "$(readlink "$settings_dir")" = "$data_dir" ]; then
  echo "  DB STORAGE       = OK ($settings_dir -> $data_dir) — DB persists at $data_dir/wg-easy.db"
else
  echo "  DB STORAGE       = WARNING: $settings_dir is NOT linked to $data_dir — the DB may NOT persist across restarts!"
fi
# Clean-slate marker: the DB is created by node on first boot, so if it already exists here we are
# starting on persisted data and INIT_* will NOT be applied (setup is already initialized).
if [ -f "$data_dir/wg-easy.db" ]; then
  echo "  DATA STATE       = EXISTING — persisted DB found at $data_dir/wg-easy.db; INIT_* is IGNORED (credentials come from the existing DB)"
else
  echo "  DATA STATE       = FRESH — clean slate, no database yet; INIT_* will create the admin user on this boot"
fi
echo "=============================================================="

# All platform integration (device registration + keeping the client Endpoint in sync with the
# tunnel) lives in register_device.py, which runs for the container's lifetime alongside the
# server. Started in the background so an unreachable router can never block the VPN itself;
# after the exec below it is reparented under dumb-init, which reaps it on container stop.
python3 -u /ironflock/register_device.py &

exec /usr/bin/dumb-init node /app/server/index.mjs