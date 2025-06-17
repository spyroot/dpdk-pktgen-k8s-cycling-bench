#!/bin/bash
# This script resolve all worker node TCA create ,
# Add additional disks , note it will power off VM,
# add N disk in same datastore that first disk resides on.
# if you need more advanced logic on multi datastore do it

# Mus

# Default values
DEFAULT_CLUSTER="tkg"
DEFAULT_DISK_SIZE="256"
DEFAULT_DISK_NUM="3"

GOVC_CONFIG_FILE="$HOME/.govc_config"

CLUSTER_NAME=${1:-$DEFAULT_CLUSTER}
DISK_SIZE=${2:-$DEFAULT_DISK_SIZE}
NUM_DISKS=${2:-DEFAULT_DISK_NUM}

echo "Using Cluster Name: $CLUSTER_NAME"
echo "Using Disk Size: ${DISK_SIZE}GB"
echo "Adding ${NUM_DISKS} disk(s) per VM."

function usage() {
    echo "Usage: $0 <CLUSTER_NAME> <DISK_SIZE_GB> <NUM_DISKS>"
    echo "  CLUSTER_NAME  : The cluster name (e.g., 'perf')"
    echo "  DISK_SIZE_GB  : Size of each disk in GB (e.g., 256)"
    echo "  NUM_DISKS     : How many disks to add to each VM (e.g., 2)"
    exit 1
}

# Function to install govc if not present, we need that , so we can adjust VM.
function install_govc() {
    if command -v govc &> /dev/null; then
        echo "✅ govc is already installed."
        return
    fi

    echo "⚙️  Installing govc..."
    OS=$(uname -s)
    if [[ "$OS" == "Darwin" ]]; then
        brew install govc
    elif [[ "$OS" == "Linux" ]]; then
        sudo apt-get update && sudo apt-get install -y govc
    else
        echo "❌ Unsupported OS: $OS. Please install govc manually."
        exit 1
    fi
}

# Function to install kubectl if not present
function install_kubectl() {
    if command -v kubectl &> /dev/null; then
        echo "✅ kubectl is already installed."
        return
    fi

    echo "⚙️  Installing kubectl..."
    OS=$(uname -s)
    if [[ "$OS" == "Darwin" ]]; then
        brew install kubectl
    elif [[ "$OS" == "Linux" ]]; then
        sudo apt-get update && sudo apt-get install -y kubectl
    else
        echo "❌ Unsupported OS: $OS. Please install kubectl manually."
        exit 1
    fi
}

# Function to configure vCenter credentials
function configure_vc() {
    if [[ -f "$GOVC_CONFIG_FILE" ]]; then
        echo "✅ vCenter configuration found. Loading credentials..."
        export $(grep -v '^#' "$GOVC_CONFIG_FILE" | xargs)
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

# Ensure govc and kubectl are installed, read why ^
install_govc
install_kubectl
configure_vc

if ! govc about &>/dev/null; then
    echo "❌ Error: Unable to connect to vCenter. Please check your credentials."
    exit 1
fi

echo "✅ Successfully connected to vCenter."
echo "🔍 Retrieving worker nodes..."
WORKER_NODES=$(kubectl get nodes --no-headers | grep -v "control-plane" | awk '{print $1}')

if [ -z "$WORKER_NODES" ]; then
    echo "❌ No worker nodes found. Exiting..."
    exit 1
fi

echo "✅ Worker nodes found:"
echo "$WORKER_NODES"

# We resolve datastore based on where first disk is
# i.e if VM uses local disk you might have million DSs you need indicate which one for disk create.
function get_vm_datastore() {

    local VM_NAME=$1
    # Get the first disk device (JSON format)
    DISK_DEVICE=$(govc device.ls -json -vm "$VM_NAME" | jq -r '.devices[] | select(.type == "VirtualDisk") | .name' | head -n 1)

    if [ -z "$DISK_DEVICE" ]; then
        echo "❌ No disk found for VM: $VM_NAME" >&2  # Send error to stderr
        return 1
    fi

    DISK_INFO_JSON=$(govc device.info -json -vm "$VM_NAME" "$DISK_DEVICE")
    DATASTORE_PATH=$(echo "$DISK_INFO_JSON" | jq -r '.devices[0].backing.fileName')
    DATASTORE_NAME=$(echo "$DATASTORE_PATH" | awk -F'[][]' '{print $2}')

    # TODO need check for some akward space
  #    DATASTORE_NAME=$(echo "$DATASTORE_NAME" | tr -d '[:space:]')
  #    DATASTORE_NAME=$(echo "$DATASTORE_PATH" | sed -n 's/^\[\(.*\)\] .*$/\1/p')
      # Return the properly formatted datastore name
     echo "$DATASTORE_NAME"
}


# Process each worker node
for NODE in $WORKER_NODES; do
    echo "🔄 Processing node: $NODE"
    VM_NAME=$(govc find /PERFTEST/vm -type m | grep "/$NODE$")

    if [ -z "$VM_NAME" ]; then
        echo "⚠️  No VM found in vCenter for node $NODE, skipping..."
        continue
    fi

    echo "✅ Found VM: $VM_NAME in vCenter"
    DATASTORE=$(get_vm_datastore "$VM_NAME")
    if [ -z "$DATASTORE" ]; then
        echo "❌ Could not determine datastore for VM: $VM_NAME. Skipping..."
        continue
    fi

    VM_POWER_STATE=$(govc vm.info -json "$VM_NAME" | jq -r '.VirtualMachines[0].Runtime.PowerState')

    if [ "$VM_POWER_STATE" = "poweredOn" ]; then
        echo "⏳ Shutting down VM: $VM_NAME"
        govc vm.power -off "$VM_NAME"
        sleep 3

        if govc vm.info "$VM_NAME" | grep -q "Powered on"; then
            echo "❌ VM $VM_NAME did not power off. Skipping disk addition."
            continue
        fi
        echo "✅ VM $VM_NAME is now powered off."
    else
        echo "🔌 VM $VM_NAME is already powered off."
    fi

    if govc vm.info "$VM_NAME" | grep -q "Powered on"; then
        echo "❌ VM $VM_NAME did not power off. Skipping disk addition."
        continue
    fi
    echo "✅ VM $VM_NAME is powered off."


    # this one loop and add all disks
    for ((i=1; i<=NUM_DISKS; i++)); do
        echo "💾 Adding disk #$i of size ${DISK_SIZE}GB to VM: $VM_NAME on datastore [$DATASTORE]"
        DISK_NAME="${VM_NAME}-extra-disk-${i}-$(date +%s).vmdk"
        govc vm.disk.create -vm "$VM_NAME" \
            -name "$DISK_NAME" \
            -size "${DISK_SIZE}G" \
            -ds="$DATASTORE"
        sleep 2
    done

    # Power on the VM
    echo "🔌 Powering on VM: $VM_NAME"
    govc vm.power -on "$VM_NAME"
    sleep 5
done

echo "🎉 All worker nodes processed successfully."
