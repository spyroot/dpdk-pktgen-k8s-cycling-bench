#!/bin/bash
#
# XPS Tuner Utility
#
# Supports both ladder (per-queue) and pool (all IRQs share CPUs) modes.
# This script tunes Transmit Packet Steering (XPS) settings for network interfaces.
#
# Author: Mus spyroot@gmail.com
#
# Usage:
#   ./xps_tuner.sh [pool|core] [options]
#
# Modes:
#   pool  - Assign a range of CPUs to all TX queues of a network interface.
#   core  - Assign one CPU per TX queue of a network interface in a round-robin manner.
#
# Options:
#   -i | --interface <iface>       Specify interface (default: direct)
#   -p | --prefix <vf_prefix>      Specify SRIOV VF prefix for matching (default: sriov)
#   -s | --start-core <start>      Specify starting CPU core (default: 12)
#   -e | --end-core <end>          Specify ending CPU core (default: 19)
#   -h | --help                    Display this help message
#
# Examples:
#
# Pool Mode:
#   ./xps_tuner.sh pool -i direct -s 12 -e 19
#     Assigns the range of CPUs 12-19 to all TX queues of the "direct" interface.
#
#   ./xps_tuner.sh pool -i eth0 -s 20 -e 27
#     Assigns the range of CPUs 20-27 to all TX queues of the "eth0" interface.
#
# Core Mode:
#   ./xps_tuner.sh core -i direct -s 12
#     Assigns each TX queue of the "direct" interface to a specific CPU starting from CPU 12.
#
#   ./xps_tuner.sh core -i eth0 -s 20
#     Assigns each TX queue of the "eth0" interface to a specific CPU starting from CPU 20.
#
# SRIOV Mode:
#   ./xps_tuner.sh pool -p sriov -s 20 -e 27
#     Applies the pool algorithm to all SRIOV interfaces matching the prefix "sriov".
#
#   ./xps_tuner.sh core -p sriov -s 20
#     Applies the core algorithm to all SRIOV interfaces matching the prefix "sriov".
#
# Display Updated XPS Settings:
#   ./xps_tuner.sh core -i direct -s 12
#     Displays the updated XPS settings for each TX queue after allocation.
#
# Algorithms:
#
# Pool Mode:
#   - All TX queues of a network interface share the same CPU mask.
#   - A range of CPUs (start-core to end-core) is calculated into a CPU mask.
#   - The mask is applied to every TX queue of the network interface.
#
# Core Mode:
#   - Each TX queue is assigned a specific CPU core in a round-robin manner.
#   - Iterates over TX queues and assigns the next CPU core, wrapping back to
#     the starting core when the end is reached.
#
# Default values


iface="direct"
if_vf_sriov="sriov"
start_core=12
end_core=19

function usage() {
    echo "Usage: $0 [pool|core] [options]"
    echo "Options:"
    echo "  -i | --interface <iface>       Specify interface (default: direct)"
    echo "  -p | --prefix <vf_prefix>      Specify SRIOV VF prefix (default: sriov)"
    echo "  -s | --start-core <start>      Specify starting core (default: 12)"
    echo "  -e | --end-core <end>          Specify ending core (default: 19)"
    echo "  -h | --help                    Display this help message"
    echo ""
    echo "Modes:"
    echo "  pool                           Assign a range of CPUs to each TX queue"
    echo "  core                           Assign one CPU per TX queue"
    echo ""
    exit 1
}

if [[ $# -lt 1 ]]; then
    usage
fi

mode=$1
shift

while [[ $# -gt 0 ]]; do
    case "$1" in
        -i|--interface)
            iface=$2
            shift 2
            ;;
        -p|--prefix)
            if_vf_sriov=$2
            shift 2
            ;;
        -s|--start-core)
            start_core=$2
            shift 2
            ;;
        -e|--end-core)
            end_core=$2
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
    esac
done

function cpu_to_mask() {
    local cpu=$1
    printf "%X" $((1 << $cpu))
}

function range_to_mask() {
    local start=$1
    local end=$2
    local mask=0
    for ((i=start; i<=end; i++)); do
        mask=$((mask | (1 << i)))
    done
    printf "%X" $mask
}

function display_xps_cpus() {
    local interface=$1
    echo "Displaying XPS settings for interface: $interface"
    for queue in /sys/class/net/"$interface"/queues/tx-*; do
        echo -n "$(basename "$queue"): "
        cat "$queue"/xps_cpus
    done
}

function tx_pool_per_txq() {
    cpu_mask=$(range_to_mask "$start_core" "$end_core")
    echo "Calculated CPU mask: $cpu_mask"

    for queue in /sys/class/net/"$iface"/queues/tx-*; do
        echo "$cpu_mask" > "$queue"/xps_cpus || echo "Failed to assign $queue"
        echo "Assigned $(basename "$queue") to CPUs $start_core-$end_core"
    done

    display_xps_cpus "$iface"
}

function tx_per_core() {
    local interface=$1
    local start_cpu=$2

    local cpu=$start_cpu
    for queue in /sys/class/net/"$interface"/queues/tx-*; do
        local mask=$(cpu_to_mask $cpu)
        echo "$mask" > "$queue"/xps_cpus || echo "Failed to assign $queue"
        echo "Assigned $(basename "$queue") to CPU $cpu"
        ((cpu++))
    done

    display_xps_cpus "$interface"
}

function process_sriov_vfs() {
    local mode=$1
    for vf_iface in $(ip link show | grep $if_vf_sriov | awk -F': ' '{print $2}'); do
        if [[ "$mode" == "pool" ]]; then
            tx_pool_per_txq "$vf_iface"
        elif [[ "$mode" == "core" ]]; then
            tx_per_core "$vf_iface" "$start_core"
        else
            echo "Unknown mode: $mode"
        fi
    done
}

if [[ "$mode" == "pool" ]]; then
    tx_pool_per_txq "$iface"
elif [[ "$mode" == "core" ]]; then
    tx_per_core "$iface" "$start_core"
else
    echo "Invalid mode: $mode. Please use 'pool' or 'core'."
    exit 1
fi

process_sriov_vfs "$mode"

for vf_iface in $(ip link show | grep "$if_vf_sriov" | awk -F': ' '{print $2}'); do
    display_xps_cpus "$vf_iface"
done
