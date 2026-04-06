#!/bin/bash
set -e

# Fix SSH and AWS permissions
chmod 700 /home/vscode/.ssh
chmod 600 /home/vscode/.ssh/id_* 2>/dev/null || true
chmod 700 /home/vscode/.aws 2>/dev/null || true

# Install Sapling SCM
ARCH=$(uname -m | sed 's/x86_64/x64/;s/aarch64/arm64/')
rm -rf ~/.local/share/sapling
mkdir -p ~/.local/share/sapling
curl -L "https://github.com/facebook/sapling/releases/download/0.2.20260317-201835%2B0234c21f/sapling-0.2.20260317-201835%2B0234c21f-linux-${ARCH}.tar.xz" \
  | tar xJf - -C ~/.local/share/sapling
grep -q 'sapling' ~/.bashrc || echo 'export PATH="$HOME/.local/share/sapling:$PATH"' >> ~/.bashrc
