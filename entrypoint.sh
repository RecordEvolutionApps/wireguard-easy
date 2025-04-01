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


WG_HOST="$DEVICE_KEY-wireguardeasy-51821.app.ironflock.com" node server.js