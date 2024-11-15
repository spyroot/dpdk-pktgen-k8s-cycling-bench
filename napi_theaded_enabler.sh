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
done

if [[ $found -eq 0 ]]; then
    echo "No interfaces found matching pattern '$interface_pattern'."
fi
