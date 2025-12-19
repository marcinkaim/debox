#!/bin/sh
# /etc/profile.d/debox.sh

# Ensure the directory exists (runs with user privileges during login)
if [ ! -d "$HOME/.local/bin" ]; then
    mkdir -p "$HOME/.local/bin"
fi
