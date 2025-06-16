#!/bin/bash
# ---------------------------------------------------------------------------
# configure_icen.sh
#
# Mass-configures Intel E810 (icen) adapters across every ESXi host in a single
# vCenter cluster.  What it does:
# This script automates NIC tuning and driver installation across a vCenter
# cluster. It performs the following actions:
#
#  Sets DRSS (Dynamic Receive Side Scaling) queues per adapter
#  Sets Queue Pairs per VF (Virtual Function)
#  Disables RDMA (Remote Direct Memory Access)
#  Optionally disables pause frame RX/TX (flow control)
#  Enables trust on all VFs
#  Installs Intel ESXi CLI driver utilities if missing
#  Reboots hosts one-by-one if required (after tool install)
#  Moves hosts in/out of maintenance mode safely during reboot
#
# Intel also provide separate tools thus,
#   1. Ensures the Intel intnetcli component bundle is present locally;
#      downloads & unpacks if missing.
#
#   2. Connects *in parallel* to every host in the cluster:
#        • verifies the icen VIB is present + counts icen NICs
#        • sets module parameters (DRSS, NumQPsPerVF, pause frames, RDMA, trust)
#        • optionally installs the Intel bundle if not yet present
#   3. Waits for all parallel tasks to finish.
#
#   4. Reboots hosts **one at a time** when the bundle install indicates a
#      reboot is required:
#        • enters maintenance mode, waits, reboots, waits for SSH heartbeat,
#          exits maintenance
#
# Prereqs:
#   • govc, curl, unzip, sshpass
#   • script machine must reach ESXi hosts on SSH (22)
#   • root SSH password (or key) identical on every host
#
# Author : Mus  |  spyroot@gmail.com
#
# TODO either use idractl or direct method to check that boot in progress
# (this edge case if boot driver set to something else , there a bunch edge cases here)

set -euo pipefail

# Default values
SSH_USER="root"
SSH_PASS="VMware1!"
GOVC_CONFIG_FILE="$HOME/.govc_config"
DC_NAME="PERFTEST"
CLUSTER_NAME="TKG"
DRSS_VALUE=16
QPS_VALUE=16
PAUSE="yes"
DISABLE_RDMA=0
INTEL_TOOL_URL="https://downloadmirror.intel.com/839270/Intel-esx-intnetcli_8.0-1.14.1.0_24165802-package.zip"
PACKAGE_ZIP="Intel-esx-intnetcli_8.0-1.14.1.0_24165802-package.zip"
NEEDS_REBOOT=()

function validate_number() {
  [[ "$1" =~ ^[0-9]+$ ]] || { echo "❌ Invalid number for $2: '$1'"; exit 1; }
}

if [[ ! -f "$PACKAGE_ZIP" ]]; then
  echo "⬇️ Downloading Intel driver package..."
  curl -LO "$INTEL_TOOL_URL"
else
  echo "✅ Package already downloaded: $PACKAGE_ZIP"
fi

if [[ -f "$EXPECTED_INNER" ]]; then
  echo "✅ Component already unpacked: $EXPECTED_INNER"
else
  echo "📦 Unpacking $OUTER_ZIP..."
  unzip -n "$OUTER_ZIP"
fi

# Find the actual component zip inside
COMPONENT_ZIP=$(find . -name "*.zip" -not -name "$PACKAGE_ZIP" | head -n 1)
if [[ ! -f "$COMPONENT_ZIP" ]]; then
  echo "❌ Component ZIP not found inside package!"
  exit 1
fi

echo "✅ Found component: $COMPONENT_ZIP"

show_help() {
  echo ""
  echo "Usage: $0 [options]"
  echo ""
  echo "Options:"
  echo "  --user <username>         SSH username (default: root)"
  echo "  --pass <password>         SSH password (default: VMware1!)"
  echo "  --dc <datacenter>         vCenter datacenter name (default: PERFTEST)"
  echo "  --cluster <name>          vCenter cluster name (default: TKG)"
  echo "  --drss <num>              DRSS queues per adapter (default: 16)"
  echo "  --qp <num>                Queue pairs per VF (default: 16)"
  echo "  --pause <yes|no>          Adjust pause_rx and pause_tx to 0 (default: yes)"
  echo "  -h, --help                Show this help message"
  echo ""
}


while [[ $# -gt 0 ]]; do
  case "$1" in
    --user) SSH_USER="$2"; shift 2 ;;
    --pass) SSH_PASS="$2"; shift 2 ;;
    --dc) DC_NAME="$2"; shift 2 ;;
    --cluster) CLUSTER_NAME="$2"; shift 2 ;;
    --drss) DRSS_VALUE="$2"; shift 2 ;;
    --qp) QPS_VALUE="$2"; shift 2 ;;
    --pause) PAUSE="$2"; shift 2 ;;
    -h|--help) show_help; exit 0 ;;
    *) echo "❌ Unknown option: $1"; show_help; exit 1 ;;
  esac
done

# Configure vCenter
function configure_vc() {
  if [[ -f "$GOVC_CONFIG_FILE" ]]; then
    echo "✅ vCenter configuration found. Loading credentials..."
    while IFS='=' read -r key val; do
      export "$key=$val"
    done < <(grep -v '^#' "$GOVC_CONFIG_FILE")
    return
  fi

  echo "⚙️  First-time setup: Configuring vCenter..."
  read -rp "🔹 Enter vCenter IP or Hostname: " VCENTER_HOST
  read -rp "🔹 Enter vCenter Username: " VCENTER_USER
  read -rs -p "🔹 Enter vCenter Password: " VCENTER_PASS
  echo ""

  cat <<EOF > "$GOVC_CONFIG_FILE"
GOVC_URL=https://$VCENTER_HOST/sdk
GOVC_USERNAME=$VCENTER_USER
GOVC_PASSWORD=$VCENTER_PASS
GOVC_INSECURE=1
EOF

  chmod 600 "$GOVC_CONFIG_FILE"
  echo "✅ vCenter credentials saved!"
}

validate_number "$DRSS_VALUE" "DRSS"
validate_number "$QPS_VALUE" "QPsPerVF"

# this will install sshpass if missing
if ! command -v sshpass &>/dev/null; then
  echo "🔍 sshpass not found. Attempting to install..."
  if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    sudo apt-get update && sudo apt-get install -y sshpass
  elif [[ "$OSTYPE" == "darwin"* ]]; then
    if ! command -v brew &>/dev/null; then
      echo "❌ Homebrew is not installed. Install it from https://brew.sh/"
      exit 1
    fi
    brew install sshpass
  else
    echo "❌ Unsupported OS: $OSTYPE. Install sshpass manually."
    exit 1
  fi
fi

configure_vc
govc ls > /dev/null

# Helper to repeat values
function gen_list() {
  local val="$1"
  local count="$2"
  yes "$val" | head -n "$count" | tr '\n' ',' | sed 's/,$//'
}

if ! govc datacenter.info "$DC_NAME" &>/dev/null; then
  echo "❌ Datacenter '$DC_NAME' not found in vCenter. Please check the name."
  exit 1
fi

# Validate cluster exists
if ! govc find -type c "/$DC_NAME/host" | grep -q "/$DC_NAME/host/$CLUSTER_NAME"; then
  echo "❌ Cluster '$CLUSTER_NAME' not found under datacenter '$DC_NAME'."
  exit 1
fi

# Collect hostnames from vCenter
ESXI_HOSTS=()
while IFS= read -r line; do
  ESXI_HOSTS+=("$line")
done < <(govc ls -t HostSystem "/$DC_NAME/host/$CLUSTER_NAME" | awk -F'/' '{print $NF}')

echo "🔍 Found ${#ESXI_HOSTS[@]} hosts in cluster '$CLUSTER_NAME'"



for HOST in "${ESXI_HOSTS[@]}"; do
(
  esxi_host="${HOST// /}"
  echo "🔗 Connecting to $esxi_host..."

  # check that icen installed if not you should install Intel driver.
  if ! sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "${SSH_USER}@${esxi_host}" \
      "esxcli software vib list | grep -q '^icen[[:space:]]'"; then
    echo "❌ 'icen' driver not found on $esxi_host. Skipping..."
    return 0
  fi

  ICEN_COUNT=$(sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "${SSH_USER}@${esxi_host}" \
    "esxcli network nic list | awk '\$3 == \"icen\"' | wc -l")

  if [[ "$ICEN_COUNT" -eq 0 ]]; then
    echo "⚠️  No 'icen' NICs found on $esxi_host. Skipping..."
    exit
  fi

  echo "✅ Found $ICEN_COUNT icen NICs on $esxi_host"

  TRUST_ALL_VFS=$(gen_list 1 "$ICEN_COUNT")
  NUM_QP=$(gen_list "$QPS_VALUE" "$ICEN_COUNT")
  DRSS=$(gen_list "$DRSS_VALUE" "$ICEN_COUNT")
  RDMA=$(gen_list "$DISABLE_RDMA" "$ICEN_COUNT")

  if [[ "$PAUSE" == "yes" ]]; then
    PAUSE_RX=$(gen_list 0 "$ICEN_COUNT")
    PAUSE_TX=$(gen_list 0 "$ICEN_COUNT")
  else
    PAUSE_RX=""
    PAUSE_TX=""
  fi

  PARAM_STRING="trust_all_vfs=${TRUST_ALL_VFS} NumQPsPerVF=${NUM_QP} DRSS=${DRSS} RDMA=${RDMA}"
  if [[ -n "$PAUSE_RX" && -n "$PAUSE_TX" ]]; then
    PARAM_STRING+=" pause_rx=${PAUSE_RX} pause_tx=${PAUSE_TX}"
  fi

  echo "⚙️  Applying parameters to icen module on $esxi_host:"
  echo "   $PARAM_STRING"

  if sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "${SSH_USER}@${esxi_host}" \
      "esxcli system module parameters set -a -m icen -p \"$PARAM_STRING\""; then
    echo "✅ Parameters applied successfully on $esxi_host"
  else
    echo "❌ Failed to apply parameters on $esxi_host"
  fi

# we check if intel tool already installed if not block bellow will execute
# note intel tool require reboot
if sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "${SSH_USER}@${esxi_host}" \
    "esxcli software vib list | grep -q '^intnetcli[[:space:]]'"; then
  echo "✅ Driver 'intnetcli' already installed on $esxi_host. Skipping..."
  return 0
fi

echo "🚚 Copying component to $esxi_host..."
    sshpass -p "$SSH_PASS" scp -o StrictHostKeyChecking=no "$COMPONENT_ZIP" "${SSH_USER}@${esxi_host}:/tmp/" || {
    echo "❌ Failed to copy to $esxi_host"
    return 1
  }

echo "🛠️ Installing driver on $esxi_host..."
INSTALL_OUTPUT=$(sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "${SSH_USER}@${esxi_host}" \
  "esxcli software acceptance set --level=CommunitySupported && \
   esxcli software component apply -d /tmp/$(basename "$COMPONENT_ZIP")" 2>&1)

echo "$INSTALL_OUTPUT"

if echo "$INSTALL_OUTPUT" | grep -q "The update completed successfully"; then
  echo "✅ Driver installed on $esxi_host"
  if echo "$INSTALL_OUTPUT" | grep -q "Reboot Required: true"; then
    NEEDS_REBOOT+=("$esxi_host")
  fi
else
  echo "❌ Driver installation failed on $esxi_host"
fi


) &
done

wait


# note this code will block. we do reboot one by one.

echo "🔍 Checking which hosts require reboot..."

for esxi_host in "${ESXI_HOSTS[@]}"; do

  echo "🔎 Checking reboot requirement on $esxi_host..."
  if sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "${SSH_USER}@${esxi_host}" \
      "vim-cmd hostsvc/hostsummary | grep -qi 'rebootRequired = true'"; then
    echo "🔁 Host $esxi_host requires a reboot. Enabling maintenance mode..."

    sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "${SSH_USER}@${esxi_host}" \
      "esxcli system maintenanceMode set --enable true" >/dev/null

    # Wait for host to enter maintenance mode
    echo "⏳ Waiting for $esxi_host to enter maintenance mode..."
    while true; do
      MODE=$(sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "${SSH_USER}@${esxi_host}" \
        "vim-cmd hostsvc/hostsummary | grep 'inMaintenanceMode' | awk '{print \$3}'" 2>/dev/null)
      if [[ "$MODE" == "true" ]]; then
        echo "✅ $esxi_host is in maintenance mode."
        break
      fi
      sleep 5
      echo "⏳ Still waiting..."
    done

    echo "🔄 Rebooting $esxi_host..."
    sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "${SSH_USER}@${esxi_host}" reboot

    echo "🔁 Waiting for $esxi_host to come back online..."
    # We wait when host came back. (note I need move timeout , alt mode we check in vc via govc)
    while ! sshpass -p "$SSH_PASS" ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no "${SSH_USER}@${esxi_host}" 'echo online' &>/dev/null; do
      echo "⏳ Still waiting for $esxi_host..."
      sleep 10
    done

    # as soon as it came back we return to normal mode and wait
    echo "✅ $esxi_host rebooted and reachable again."
    echo "🚪 Exiting maintenance mode on $esxi_host..."
    sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no "${SSH_USER}@${esxi_host}" \
      "esxcli system maintenanceMode set --enable false" && \
      echo "✅ Maintenance mode exited on $esxi_host." || \
      echo "❌ Failed to exit maintenance mode on $esxi_host."
  else
    echo "✅ No reboot needed on $esxi_host."
  fi
done