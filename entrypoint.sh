#!/bin/bash

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

python3 -u /ironflock/register_device.py

# wg-easy v15 configures the VPN host/port once, on the first start, via INIT_HOST/INIT_PORT
# (the old WG_HOST variable is no longer used). Together with INIT_USERNAME/INIT_PASSWORD from
# the app settings this completes the unattended setup, so no setup wizard is shown.
export INIT_ENABLED="true"
export INIT_HOST="${INIT_HOST:-${DEVICE_KEY}-wireguard_easy-51820.app.ironflock.com}"
export INIT_PORT="${INIT_PORT:-51820}"

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
echo "  INIT_DNS         = ${INIT_DNS:-<unset>}"
echo "  INIT_ALLOWED_IPS = ${INIT_ALLOWED_IPS:-<unset>}"
echo "  DISABLE_IPV6     = ${DISABLE_IPV6:-<unset>}"
echo "  INSECURE         = ${INSECURE:-<unset>}"
echo "  DEVICE_KEY       = ${DEVICE_KEY:-<unset>}"
echo "=============================================================="


exec /usr/bin/dumb-init node /app/server/index.mjs