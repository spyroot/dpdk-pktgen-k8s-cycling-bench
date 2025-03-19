#!/usr/bin/env bash
#
# 📦 install_sonobuoy.sh
#
# Installs Sonobuoy v0.57.3 on Ubuntu
# Author: Mus

SONO_VERSION="0.57.3"
SONO_URL="https://github.com/vmware-tanzu/sonobuoy/releases/download/v${SONO_VERSION}/sonobuoy_${SONO_VERSION}_linux_amd64.tar.gz"
TARBALL="sonobuoy_${SONO_VERSION}_linux_amd64.tar.gz"

set -euo pipefail

echo "📥 Downloading Sonobuoy v${SONO_VERSION}..."
curl -L "${SONO_URL}" -o "${TARBALL}"

echo "📂 Extracting Sonobuoy..."
tar -xf "${TARBALL}"

echo "🚚 Moving Sonobuoy to /usr/local/bin..."
sudo mv sonobuoy /usr/local/bin

echo "🧹 Cleaning up..."
rm -f "${TARBALL}"

echo "🔍 Verifying installation..."
if command -v sonobuoy &>/dev/null; then
    echo "✅ Sonobuoy $(sonobuoy version) has been successfully installed."
else
    echo "❌ Error: Sonobuoy was not found in PATH!"
    exit 1
fi
