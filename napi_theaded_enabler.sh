#!/bin/bash
#
# Enable Threaded NAPI for Network Interfaces
# Author: Mus spyroot@gmail.com

interface_pattern="sriov"
max_queues=8
enable_cpu_governor=0 # Default: do not configure the governor

function usage() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo "  -i | --interface <iface>       Specify the network interface pattern (default: sriov)"
    echo "  -q | --queues <number>         Specify the number of RSS queues (default: 8)"
    echo "  --enable-governor              Enable CPU governor configuration to performance"
    echo "  --no-governor                  Disable CPU governor configuration (default behavior)"
    echo "  -h | --help                    Display this help message"
    exit 1
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -i|--interface)
            interface_pattern=$2
            shift 2
            ;;
        -q|--queues)
            max_queues=$2
            shift 2
            ;;
        --enable-governor)
            enable_cpu_governor=1
            shift
            ;;
        --no-governor)
            enable_cpu_governor=0
            shift
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


function enable_gro() {
    local iface=$1
    echo "Enabling GRO for $iface..."
    if ethtool -K "$iface" gro on &>/dev/null; then
        echo "GRO enabled for $iface."
    else
        echo "GRO not supported for $iface."
    fi
}

function enable_rss() {
    local iface=$1
    local max_queues=$2
    echo "Enabling RSS for $iface with $max_queues queues..."

    # Attempt to set the RSS queues
    if ethtool -L "$iface" combined "$max_queues" &>/dev/null; then
        echo "RSS successfully set for $iface."
    else
        echo "RSS configuration failed or not supported for $iface."
        return
    fi

    echo "Current RSS queue configuration for $iface:"
    current_combined=$(ethtool -l "$iface" 2>/dev/null | awk '/Current hardware settings:/ {getline; print $2}')
    if [[ -n $current_combined ]]; then
        echo "Combined queues: $current_combined"
    else
        echo "Unable to retrieve current RSS queue settings for $iface."
    fi
}



function reduce_interrupt_coalescing() {
    local iface=$1
    echo "Tuning interrupt coalescing for $iface..."
    if ethtool -C "$iface" adaptive-rx on adaptive-tx on rx-usecs 50 tx-usecs 50 &>/dev/null; then
        echo "Interrupt coalescing tuned for $iface."
    else
        echo "Interrupt coalescing tuning failed for $iface."
    fi
}

function enable_flow_control() {
    local iface=$1
    echo "Enabling flow control for $iface..."
    if ethtool -A "$iface" rx on tx on &>/dev/null; then
        echo "Flow control enabled for $iface."
    else
        echo "Flow control not supported or failed for $iface."
    fi
}

function set_cpu_governor() {
    echo "Setting CPU governor to performance..."
    for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
        if echo performance > "$cpu"; then
            echo "CPU governor set to performance for $cpu."
        else
            echo "Failed to set CPU governor for $cpu."
        fi
    done
}

found=0
for iface in $(ip link show | grep "$interface_pattern" | awk -F': ' '{print $2}'); do
    if [[ " ${processed_interfaces[*]} " == *" $iface "* ]]; then
        continue
    fi

    processed_interfaces+=("$iface")
    found=1

    echo "Processing interface: $iface"
    if [ -e /sys/class/net/"$iface"/threaded ]; then
        echo "Enabling Threaded NAPI for $iface..."
        echo 1 > /sys/class/net/"$iface"/threaded || echo "Threaded NAPI not supported or failed for $iface."
    else
        echo "Threaded NAPI not supported or missing for $iface."
    fi

    enable_rss "$iface" "$max_queues"
done

if [[ $found -eq 0 ]]; then
    echo "No interfaces found matching pattern '$interface_pattern'."
fi

if [[ $enable_cpu_governor -eq 1 ]]; then
    set_cpu_governor
else
    echo "Skipping CPU governor configuration."
fi