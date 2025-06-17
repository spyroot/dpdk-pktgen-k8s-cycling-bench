#!/bin/bash

# This script monitor discards
# Example: ./sriov_config.sh --pf vmnic3 --pattern "sriov_%d" --count 8
# Default values
# Author Mus

PF="vmnic6"
PATTERN="sriov_%d"
COUNT=6

# Usage function
usage() {
    echo "Usage: $0 [-p PF_NAME] [-t PATTERN] [-n COUNT]"
    echo "  -p, --pf         Physical Function interface (default: vmnic6)"
    echo "  -t, --pattern    Interface name pattern (default: sriov_%%d)"
    echo "  -n, --count      Number of interfaces to generate (default: 6)"
    exit 1
}

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -p|--pf)
            PF="$2"
            shift 2
            ;;
        -t|--pattern)
            PATTERN="$2"
            shift 2
            ;;
        -n|--count)
            COUNT="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown parameter: $1"
            usage
            ;;
    esac
done

for vf in $(seq 0 $((COUNT - 1))); do
    echo "VF ID: $vf"
    esxcli network sriovnic vf stats -n "$PF" -v "$vf" | grep -E "Discards|Errordrops" || echo "No discard or error stats for VF ID $vf"
done

# Generate interface list from pattern
interfaces=()
for ((i=1; i<=COUNT; i++)); do
    interfaces+=($(printf "$PATTERN" "$i"))
done

for iface in "${interfaces[@]}"; do
    echo "Applying settings to $iface"
    ethtool -C "$iface" adaptive-rx off adaptive-tx off rx-usecs 5 tx-usecs 5
done

for iface in "${interfaces[@]}"; do
    echo "Settings for $iface:"
    ethtool -c "$iface"
done

echo "Settings applied to all SR-IOV interfaces."
