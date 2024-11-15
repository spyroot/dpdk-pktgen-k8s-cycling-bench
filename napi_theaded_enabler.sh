#!/bin/bash
#
# Enable Threaded NAPI for Network Interfaces
# Author: Mus spyroot@gmail.com

function usage() {
    echo "Usage: $0 [-i <interface>]"
    echo "Options:"
    echo "  -i | --interface <iface>  Specify the network interface (e.g., eth0, ens1f0)"
    echo "  -h | --help               Display this help message"
    exit 1
}

function enable_gro() {
    local iface=$1
    echo "Enabling GRO for $iface..."
    ethtool -K "$iface" gro on || echo "Failed to enable GRO for $iface"
}


function enable_rss() {
    local iface=$1
    echo "Enabling RSS for $iface..."
    ethtool -L "$iface" combined 8 || echo "Failed to enable RSS for $iface"
}

# Configure adaptive interrupt coalescing for latency-sensitive applications.
#
function reduce_interrupt_coalescing() {
    local iface=$1
    echo "Tuning interrupt coalescing for $iface..."
    ethtool -C "$iface" adaptive-rx on adaptive-tx on rx-usecs 50 tx-usecs 50 || echo "Failed to tune interrupt coalescing for $iface"
}

function enable_flow_control() {
    local iface=$1
    echo "Enabling flow control for $iface..."
    ethtool -A "$iface" rx on tx on || echo "Failed to enable flow control for $iface"
}

function set_cpu_governor() {
    echo "Setting CPU governor to performance..."
    for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
        echo performance > "$cpu" || echo "Failed to set performance governor for $cpu"
    done
}

interface_pattern="sriov"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -i|--interface)
            interface_pattern=$2
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

found=0
for iface in $(ip link show | grep "$interface_pattern" | awk -F': ' '{print $2}'); do
    found=1
    if [ -e /sys/class/net/"$iface"/threaded ]; then
        echo "Enabling Threaded NAPI for $iface..."
        echo 1 > /sys/class/net/"$iface"/threaded
    else
        echo "Threaded NAPI not supported or missing for $iface."
    fi

#    set_cpu_governor
    enable_rss "$iface"
done

if [[ $found -eq 0 ]]; then
    echo "No interfaces found matching pattern '$interface_pattern'."
fi


./napi_theaded_enabler.sh -i direct