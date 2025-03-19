#!/bin/bash
#
# This script creates multiple logical volumes (LVs) on each worker node.
# It is intended for use in a Kubernetes local storage provisioner setup.
#
# Use Case:
# -------------
# Imagine you have a new disk, e.g., /dev/sdc, on your worker nodes, and you want
# to partition it into multiple smaller volumes.
# For instance, if the disk size is 1TB and you want to create 50GB volumes, this script will:
# 1. Check the disk size.
# 2. Calculate how many 50GB volumes can fit into the disk.
# 3. Create a physical volume (PV), volume group (VG), and logical volumes (LVs).
# 4. Format each logical volume with the ext4 filesystem.
# 5. Add entries to /etc/fstab for persistent mounting.
#
# Example:
# 1TB disk /dev/sdc will be divided into 20 x 50GB logical volumes.
#
# Requirements:
# --------------
# This script assumes that:
# 1. The disk to partition is not the system disk (i.e., it should not have the OS installed).
# 2. The worker nodes have the required tools (`lsblk`, `pvcreate`, `vgcreate`, `lvcreate`) installed.
# 3. The user has appropriate sudo permissions on the worker nodes.

TARGET_SIZE="50G"      # Size of each volume to be created
USERNAME="capv"      # Username for SSH
DISK="/dev/sdc"            # Disk to partition (e.g., /dev/sdc)
SUDO_PASSWORD="VMware1!"  # Sudo password (if required)
LOG_FILE="/tmp/storage-setup.log"

if ! command -v sshpass &>/dev/null; then
    echo "Installing sshpass..."
    sudo apt-get update && sudo apt-get install -y sshpass
fi

#read -sp "Enter your sudo password: " SUDO_PASSWORD
#echo

function log() {
    echo "$(date +'%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

function get_worker_nodes() {
    kubectl get nodes --selector='!node-role.kubernetes.io/control-plane' -o jsonpath='{.items[*].status.addresses[?(@.type=="InternalIP")].address}'
}

function check_and_install_tools() {
    local host=$1
    for cmd in "lsblk" "pvcreate" "vgcreate" "lvcreate"; do
        if ! ssh "$USERNAME@$host" "command -v $cmd &>/dev/null"; then
            log "⚠️ Installing missing tool: $cmd on $host..."
            ssh "$USERNAME@$host" "echo '$SUDO_PASSWORD' | sudo -S tdnf install -y lvm2"
        fi
    done
}

# Function to calculate how many volumes can be created
function calculate_volumes() {
    local disk_size=$1
    local target_size=$2

    local disk_size_bytes=$(echo "$disk_size" | sed 's/G//' | awk '{print $1 * 1024 * 1024 * 1024}')
    local target_size_bytes=$(echo "$target_size" | sed 's/G//' | awk '{print $1 * 1024 * 1024 * 1024}')

    local num_volumes=$((disk_size_bytes / target_size_bytes))
    echo $num_volumes
}

# Function to check if the disk is empty (no filesystem or partitions)
function check_disk_empty() {
    local disk=$1
    if ssh "$USERNAME@$host" "lsblk -f | grep -q '$disk'"; then
        echo "❌ Error: $disk is already in use or has a filesystem."
        return 1
    fi
    return 0
}

# Function to check if the disk is the system disk
function check_if_system_disk() {
    local disk=$1
    if ssh "$USERNAME@$host" "mount | grep -q '$disk'"; then
        echo "❌ Error: $disk is mounted, likely as the system disk."
        return 1
    fi
    return 0
}

# Function to check if the required tools are installed on the remote host
function check_required_tools() {
    local host=$1
    for cmd in "lsblk" "pvcreate" "vgcreate" "lvcreate"; do
        if ! ssh "$USERNAME@$host" "command -v $cmd &>/dev/null"; then
            echo "Error: $cmd is not installed on $host."
            return 1
        fi
    done
    return 0
}

# Function to check SSH connection
function ping_ssh_host() {
    local host=$1
    if ! ssh -o ConnectTimeout=5 "$USERNAME@$host" "echo 'SSH ping success' &>/dev/null"; then
        echo "❌ SSH to $host failed or is unreachable."
        return 1
    fi
    return 0
}

# Function to install lsblk if missing
function install_lsblk() {
    local host=$1
    echo "🔄 Installing util-linux on $host (to provide lsblk)..."

    if ssh "$USERNAME@$host" "command -v yum &>/dev/null"; then
        ssh "$USERNAME@$host" "echo '$SUDO_PASSWORD' | sudo -S yum install -y util-linux"
    elif ssh "$USERNAME@$host" "command -v apt-get &>/dev/null"; then
        ssh "$USERNAME@$host" "echo '$SUDO_PASSWORD' | sudo -S apt-get update && sudo apt-get install -y util-linux"
    else
        echo "❌ Error: Could not detect package manager on $host!"
        exit 1
    fi
}


function run_as_root() {
    local host=$1
    shift
    local cmd="$@"

    # Debug output: Show the command being executed
    echo "DEBUG: Executing on $host: $cmd"

    ssh "$USERNAME@$host" "echo '$SUDO_PASSWORD' | sudo -S bash -c \"$cmd\""
}

# Function to format a logical volume with ext4 filesystem
function format_lv() {
    local host=$1
    local lv=$2

#    # Debug output: Show the logical volume being formatted
#    echo "DEBUG: Wiping any existing file system signatures on $lv..."

    # Wipe existing file system signatures before formatting
    run_as_root "$host" "sudo wipefs -a \"$lv\""

#    # Debug output: Show the formatting command
#    echo "DEBUG: Formatting logical volume $lv with ext4 on $host..."

    # Format the logical volume with ext4
    run_as_root "$host" "sudo mkfs.ext4 -F \"$lv\""

    echo "✅ Logical volume $lv formatted with ext4."
}



function add_to_fstab() {
    local host=$1
    local lv_path=$2
    local mount_point=$3
    local uuid=""

    # Debugging: Print input arguments
    echo "DEBUG: add_to_fstab called with:"
    echo "       host: $host"
    echo "       lv_path: $lv_path"
    echo "       mount_point: $mount_point"

    # Retry logic: Attempt to get UUID multiple times
    for attempt in {1..3}; do
        echo "DEBUG: Executing on $host: sudo blkid -s UUID -o value $lv_path"
        uuid=$(ssh "$USERNAME@$host" "echo '$SUDO_PASSWORD' | sudo -S blkid -s UUID -o value $lv_path 2>&1")

        if [[ -n "$uuid" ]]; then
            echo "✅ DEBUG: Retrieved UUID=$uuid for $lv_path on $host"
            break
        fi

        echo "⚠️ DEBUG: Attempt $attempt: UUID not found for $lv_path on $host. Retrying..."
        sleep 2
    done

    if [[ -z "$uuid" ]]; then
        echo "❌ ERROR: UUID not found for $lv_path on $host after multiple attempts. Check formatting!"
        return 1
    fi

    local fstab_entry="UUID=$uuid $mount_point ext4 defaults,noatime,nodiratime,data=writeback,commit=120 0 0"

    echo "DEBUG: Adding fstab entry: $fstab_entry"

    ssh "$USERNAME@$host" "echo '$SUDO_PASSWORD' | sudo -S tee -a /etc/fstab <<< \"$fstab_entry\""
    echo "✅ DEBUG: Added $lv_path to /etc/fstab with mount point $mount_point (UUID=$uuid)"
}


function deploy_ssh_key() {
    local host=$1
    if [[ ! -f ~/.ssh/id_ed25519 ]]; then
        log "SSH key not found. Generating new key..."
        ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N "" <<< "y"
    fi
    log "Pushing SSH key to $host..."
    sshpass -p "$SUDO_PASSWORD" ssh-copy-id -o StrictHostKeyChecking=no "$USERNAME@$host"
}


function delete_lvs() {
    local host=$1

    run_as_root "$host" "lvdisplay /dev/vg_disk"

    run_as_root "$host" "lvremove -f /dev/vg_disk/*" 2>/dev/null
    echo "Removed logical volumes on $host"

    run_as_root "$host" "vgremove -f vg_disk"
    echo "Removed volume group vg_disk on $host"

    run_as_root "$host" "pvremove -f $DISK"
    echo "Removed physical volume $DISK on $host"

    run_as_root "$host" "wipefs -a $DISK"
    echo "Cleared any remaining signatures on $DISK"

    echo "Logical volumes, volume group, and physical volume should be removed now."
}


function check_if_pv_exists() {
    local host=$1
    if ssh "$USERNAME@$host" "sudo pvdisplay $DISK &>/dev/null"; then
        return 0
    else
        return 1
    fi
}


# Get all worker nodes dynamically
WORKER_NODES=($(get_worker_nodes))

if [ ${#WORKER_NODES[@]} -eq 0 ]; then
    log "No worker nodes found. Exiting."
    exit 1
fi

log "Found worker nodes: ${WORKER_NODES[*]}"

for host in "${WORKER_NODES[@]}"; do
    deploy_ssh_key "$host"
done

log "SSH key deployment completed. Now proceeding with storage setup..."

for host in "${WORKER_NODES[@]}"; do
    log "Checking and installing required tools on $host..."
    check_and_install_tools "$host"
done

log "LVM2 installation verified. Proceeding with storage setup..."

# Check if action is --delete
if [[ "$1" == "--delete" ]]; then
    # Delete logical volumes
    for host in "${WORKER_NODES[@]}"; do
        echo "Deleting LVs on $host..."
        delete_lvs "$host"
    done
    exit 0
fi

for host in "${WORKER_NODES[@]}"; do
    echo "Checking SSH connectivity to $host..."

    # SSH "ping" the host to check if we can execute a command
    if ! ping_ssh_host "$host"; then
        continue
    fi

    if ! check_required_tools "$host"; then
        log "⚠️ Skipping $host due to missing required tools."
        continue
    fi

    if ! ssh "$USERNAME@$host" "command -v lsblk &>/dev/null"; then
        install_lsblk "$host"
    fi

    disk_size=$(ssh "$USERNAME@$host" "lsblk -d -o SIZE -n -b $DISK | awk '{print \$1 / 1024 / 1024 / 1024}'")
    log "📏 Disk size: ${disk_size} GB"

    num_volumes=$(calculate_volumes "$disk_size" "$TARGET_SIZE")
    log "📦 Disk will provide ${num_volumes} volumes of size ${TARGET_SIZE}"

    if ! check_disk_empty "$DISK"; then
        log "❌ Disk $DISK is already in use or not suitable for partitioning."
        continue
    fi

    if ! check_if_system_disk "$DISK"; then
        log "❌ $DISK is the system disk, skipping."
        continue
    fi

    # Now run all commands as root
    if ! check_if_pv_exists "$host"; then
        log "Disk $DISK is not yet initialized. Initializing physical volume..."
        run_as_root "$host" "sudo pvcreate -ff $DISK"
    else
        log "Disk $DISK is already initialized as a physical volume. Skipping pvcreate."
        run_as_root "$host" "echo 'y' | sudo -S pvcreate -ff $DISK"
    fi

    run_as_root "$host" "vgcreate vg_disk $DISK"

    for ((i=1; i<=num_volumes; i++)); do
        lv_name="lv_$i"
        echo "Creating logical volume: $lv_name"
        run_as_root "$host" "lvcreate --yes -L $TARGET_SIZE -n $lv_name vg_disk"

        format_lv "$host" "/dev/vg_disk/$lv_name"
        log "✅ Logical volume $lv_name formatted with ext4."

        mount_point="/mnt/local-storage/pv$i"
        log "🔧 Adding $lv_name to /etc/fstab with mount point $mount_point"
        run_as_root "$host" "mkdir -p $mount_point"
        add_to_fstab "$host" "/dev/vg_disk/$lv_name" "$mount_point"
    done

    run_as_root "$host" "lvdisplay"
done
