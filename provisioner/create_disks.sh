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
USERNAME="vmware"      # Username for SSH
WORKER_HOSTS=("10.100.18.104")  # List of worker nodes to process
DISK="/dev/sdc"        # Disk to partition (e.g., /dev/sdc)
SUDO_PASSWORD="VMware1!"  # Sudo password (if required)

#read -sp "Enter your sudo password: " SUDO_PASSWORD
#echo

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
check_disk_empty() {
    local disk=$1
    if ssh "$USERNAME@$host" "lsblk -f | grep -q '$disk'"; then
        echo "Error: $disk is already in use or has a filesystem."
        return 1
    fi
    return 0
}

# Function to check if the disk is the system disk
check_if_system_disk() {
    local disk=$1
    if ssh "$USERNAME@$host" "mount | grep -q '$disk'"; then
        echo "Error: $disk is mounted, likely as the system disk."
        return 1
    fi
    return 0
}

# Function to check if the required tools are installed on the remote host
check_required_tools() {
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
ping_ssh_host() {
    local host=$1
    if ! ssh -o ConnectTimeout=5 "$USERNAME@$host" "echo 'SSH ping success' &>/dev/null"; then
        echo "SSH to $host failed or is unreachable."
        return 1
    fi
    return 0
}

# Function to install lsblk if missing
install_lsblk() {
    local host=$1
    echo "Installing util-linux on $host (to provide lsblk)..."
    ssh "$USERNAME@$host" "echo '$SUDO_PASSWORD' | sudo -S apt-get update && sudo apt-get install -y util-linux"
}

# Function to run commands as root
run_as_root() {
    local host=$1
    shift
    local cmd="$@"
    ssh "$USERNAME@$host" "echo '$SUDO_PASSWORD' | sudo -S bash -c \"$cmd\""
}

# Function to format a logical volume with ext4 filesystem
function format_lv() {
    local lv=$1
    run_as_root "$host" "sudo mkfs.ext4 $lv"
}

# Function add disk to fstab
function add_to_fstab() {
    local host=$1
    local lv_path=$2
    local mount_point=$3
    local uuid=$(ssh "$USERNAME@$host" "echo '$SUDO_PASSWORD' | sudo -S blkid -s UUID -o value $lv_path")
    local fstab_entry="UUID=$uuid $mount_point ext4 defaults,noatime,nodiratime,data=writeback,commit=120 0 0"
    ssh "$USERNAME@$host" "echo '$SUDO_PASSWORD' | sudo -S tee -a /etc/fstab <<< \"$fstab_entry\""
    echo "Added $lv_path to /etc/fstab with mount point $mount_point"
}


for host in "${WORKER_HOSTS[@]}"; do
    echo "Checking SSH connectivity to $host..."

    # SSH "ping" the host to check if we can execute a command
    if ! ping_ssh_host "$host"; then
        continue
    fi

    if ! check_required_tools "$host"; then
        echo "Skipping $host due to missing required tools."
        continue
    fi

    if ! ssh "$USERNAME@$host" "command -v lsblk &>/dev/null"; then
        install_lsblk "$host"
    fi

    disk_size=$(ssh "$USERNAME@$host" "lsblk -d -o SIZE -n -b $DISK | awk '{print \$1 / 1024 / 1024 / 1024}'")
    echo "Disk size: ${disk_size} GB"

    num_volumes=$(calculate_volumes "$disk_size" "$TARGET_SIZE")
    echo "Disk will provide ${num_volumes} volumes of size ${TARGET_SIZE}"

    if ! check_disk_empty "$DISK"; then
        echo "Disk $DISK is already in use or not suitable for partitioning."
        continue
    fi

    if ! check_if_system_disk "$DISK"; then
        echo "$DISK is the system disk, skipping."
        continue
    fi

    # Now run all commands as root
    run_as_root "$host" "pvcreate $DISK"
    run_as_root "$host" "vgcreate vg_disk $DISK"

    for ((i=1; i<=num_volumes; i++)); do
        lv_name="lv_$i"
        echo "Creating logical volume: $lv_name"
        run_as_root "$host" "lvcreate -L $TARGET_SIZE -n $lv_name vg_disk"

        format_lv "/dev/vg_disk/$lv_name"
        echo "Logical volume $lv_name formatted with ext4."

        mount_point="/mnt/local-storage/pv$i"
        echo "Adding $lv_name to /etc/fstab with mount point $mount_point"
        run_as_root "$host" "mkdir -p $mount_point"
        add_to_fstab "/dev/vg_disk/$lv_name" "$mount_point"
    done

    # Display the logical volumes created
    run_as_root "$host" "lvdisplay"
done
