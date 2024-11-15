#!/bin/bash
#
# This script allow you to tun xps txq.
# It designed so you optimize regular or vm like interface
# and set of sriov adapters.
#
#
# Mus spyroot@gmail.com

# Default configuration

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
