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

# Seed the VPN endpoint for the very first boot (wg-easy applies INIT_HOST / INIT_PORT only while
# the database does not exist yet). WireGuard is UDP and does NOT travel over the HTTPS app
# subdomain — clients connect through the IronFlock tunnel's UDP edge, so the host is seeded from
# the agent-injected TUNNEL_DOMAIN.
# INIT_PORT must stay 51820: wg-easy's first-boot setup writes it to BOTH the advertised client
# endpoint AND the wg ListenPort (updateHostPort), and the tunnel always forwards the public UDP
# port to 51820 inside the container — seeding the public port here would make wg listen on the
# wrong port and break every handshake. The advertised endpoint (host and public port) is
# corrected to the live tunnel values by register_device.py (started below) within seconds, also
# for devices whose tunnel is only activated later (the agent updates the /data/env files in
# running containers without a restart).
export INIT_ENABLED="true"
export INIT_HOST="${INIT_HOST:-${TUNNEL_DOMAIN:-app.ironflock.com}}"
export INIT_PORT="${INIT_PORT:-51820}"
# Updates arrive through IronFlock, not through wg-easy's own update check, which would call
# GitHub from every gateway (and fail noisily in restricted plant networks).
export DISABLE_VERSION_CHECK="${DISABLE_VERSION_CHECK:-true}"

# Print the effective configuration on start so it can be validated in the container logs.
# The admin password is masked (presence + length only) so it is never written to the logs.
echo "=================== wg-easy startup config ==================="
echo "  WG_EASY_VERSION  = ${WG_EASY_VERSION:-<unset>}"
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
echo "  INIT_IPV4_CIDR   = ${INIT_IPV4_CIDR:-<unset>}"
echo "  INIT_IPV6_CIDR   = ${INIT_IPV6_CIDR:-<unset>}"
echo "  INIT_ALLOWED_IPS = ${INIT_ALLOWED_IPS:-<unset>}"
echo "  DISABLE_IPV6     = ${DISABLE_IPV6:-<unset>}"
echo "  INSECURE         = ${INSECURE:-<unset>}"
echo "  WG_INTERFACE     = ${WG_INTERFACE:-wg0}"
echo "  ENV              = ${ENV:-<unset>}"
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
# Python self-test in the FOREGROUND: imports what the companion needs, with a timeout. Its
# output takes the same path as this banner, so a broken or hanging Python environment shows
# up here even when the background companion's own output does not.
py_check=$(timeout 20 python3 -c '
import sys, time
t = time.time()
from importlib.metadata import version
import ironflock, knowledge_core, yaml
v = version("ironflock")
print(f"OK (python {sys.version.split()[0]}, ironflock {v}, knowledge-core {knowledge_core.__version__}, imports took {time.time() - t:.1f}s)")
' 2>&1)
py_status=$?
if [ "$py_status" -eq 0 ]; then
  echo "  PYTHON CHECK     = ${py_check}"
else
  echo "  PYTHON CHECK     = FAILED (exit ${py_status}; 124/143 = still hanging after 20 s), $(command -v python3 || echo 'python3 not found'):"
  echo "${py_check}" | tail -n 15 | sed 's/^/      /'
fi
echo "=============================================================="

# All platform integration lives in register_device.py (+ endpoint_sync.py, vpn_state.py,
# ai_tools.py): keeping the client Endpoint in sync with the tunnel, publishing the gateway's
# state, clients, checklist, traffic and events to the app's tables, and serving the AI
# assistant's diagnostics tools and knowledge library. It runs for the container's lifetime
# alongside the server. Started in the background so an unreachable router can never block the
# VPN itself; after the exec below it is reparented under dumb-init, which reaps it on stop.
# stderr is merged into stdout so Python tracebacks show up in every log view, and the
# companion is restarted if it ever exits: without it the client Endpoint would silently
# stop following the tunnel. The loop is reparented under dumb-init with the exec below.
#
# SIGHUP is ignored first, and the companion inherits that: this script is PID 1 and the session
# leader, and the `exec dumb-init` below detaches from the container's TTY (TIOCNOTTY), upon
# which the kernel sends SIGHUP to the whole foreground process group, which includes this
# background job. Without the trap the companion is killed silently right after launch on
# every container that runs with a TTY. dumb-init sets its own handlers, so node is unaffected.
trap '' HUP
(
  attempt=1
  while true; do
    echo "[ironflock] launching companion (attempt ${attempt})"
    python3 -u /ironflock/register_device.py 2>&1
    echo "[ironflock] companion exited with code $?; restarting in 15 s"
    sleep 15
    attempt=$((attempt + 1))
  done
) &
echo "  COMPANION        = register_device.py started in the background (pid $!, restarted on exit); its lines are prefixed [ironflock]"

exec /usr/bin/dumb-init node /app/server/index.mjs