#!/bin/bash
#
# IRQ Affinity Tunner Utility
# Supports both ladder (per-queue) and pool (all IRQs share CPUs) modes
#
# Author: Mus
#
# Usage:
#   ./irq_tunner.sh --mode ladder -i direct --cpus 0,1,2,3
#   ./irq_manager.sh --mode pool -i direct --cpu-range 20-27 [-p]
#
# ./irq_tunner.sh --mode pool --interface direct --cpu-range 20-27 -p
# ./irq_tunner.sh --mode pool --interface direct --cpu-range 20-27

# Note I did test on single NUMA so I need test on dual numa as well
#

# Default values

mode=""
interface=""
cpu_list=()
cpu_range=""
offset=0
print_flag=0


# Function to display usage
function usage() {
    echo "Usage: $0 --mode <ladder|pool> -i <iface> [options]"
    echo "Options:"
    echo "  --mode, -m <ladder|pool>      Specify mode of operation:"
    echo "                                ladder: Assign CPUs per IRQ queue in a round-robin manner."
    echo "                                pool: Assign a range of CPUs to all IRQs."
    echo "  --interface, -i <iface>       Specify network interface (e.g., eth0)"
    echo "  --cpus, -l <cpu_list>         Comma-separated list of CPUs for ladder mode (e.g., 0,1,2,3)"
    echo "  --cpu-range, -c <cpu_range>   Range of CPUs for pool mode (e.g., 20-27)"
    echo "  --offset, -o <offset>         Starting CPU offset for ladder mode (default: 0)"
    echo "  -p, --print                   Print current IRQ affinity values after setting them"
    echo "  -h, --help                    Display this help message"
    exit 1
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode|-m)
            mode=$2
            shift 2
            ;;
        --interface|-i)
            interface=$2
            shift 2
            ;;
        --cpus|-l)
            IFS=',' read -r -a cpu_list <<< "$2"
            shift 2
            ;;
        --cpu-range|-c)
            cpu_range=$2
            shift 2
            ;;
        --offset|-o)
            offset=$2
            shift 2
            ;;
        -p|--print)
            print_flag=1
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

if [[ -z "$mode" || -z "$interface" ]]; then
    echo "Error: Mode and interface are required."
    usage
fi

if [[ "$mode" == "ladder" && ${#cpu_list[@]} -eq 0 ]]; then
    echo "Error: --cpus is required for ladder mode."
    usage
fi

if [[ "$mode" == "pool" && -z "$cpu_range" ]]; then
    echo "Error: --cpu-range is required for pool mode."
    usage
fi

# Function to build IRQ map for a given interface
function build_irq_map() {
    local interface=$1
    local cpu_range=$2

    declare -A irq_map
    while IFS= read -r line; do
        irq=$(echo "$line" | awk '{print $1}' | tr -d ':')
        irq_name=$(echo "$line" | awk '{print $NF}')

        if [[ "$irq_name" == *"$interface"* ]]; then
            irq_map[$irq]="$cpu_range"
        fi
    done < /proc/interrupts
    declare -p irq_map
}

# Function to set IRQ affinity
function set_irq_affinity() {
    local -n irq_map_ref=$1
    for irq in "${!irq_map_ref[@]}"; do
        echo "Setting IRQ $irq to CPU cores ${irq_map_ref[$irq]}"
        echo "${irq_map_ref[$irq]}" > /proc/irq/$irq/smp_affinity_list || echo "Failed to set IRQ $irq"
    done
}

# Function to print current IRQ affinity
function print_irq_affinity() {
    local -n irq_map_ref=$1
    echo "Current IRQ affinity values:"
    for irq in "${!irq_map_ref[@]}"; do
        echo -n "IRQ $irq: "
        cat /proc/irq/$irq/smp_affinity_list || echo "Unable to read IRQ $irq affinity"
    done
}

# Ladder mode: Distribute IRQs across CPUs
function ladder_mode() {
    local iface=$1
    local -n cpus=$2
    local offset=$3

    # Extract IRQs for the specified interface
    irqs=($(grep "$iface" /proc/interrupts | awk '{print $1}' | tr -d ':'))
    if [[ ${#irqs[@]} -eq 0 ]]; then
        echo "No IRQs found for interface $iface."
        exit 1
    fi

    echo "Distributing IRQs for $iface across CPUs: ${cpus[*]} (Offset: $offset)"

    local cpu_index=$offset
    for irq in "${irqs[@]}"; do
        cpu=${cpus[$((cpu_index % ${#cpus[@]}))]}
        echo "Setting IRQ $irq to CPU $cpu"
        echo "$cpu" > /proc/irq/$irq/smp_affinity_list || echo "Failed to set IRQ $irq"
        ((cpu_index++))
    done
}

# Pool mode: Assign a CPU range to all IRQs
function pool_mode() {
    local iface=$1
    local cpu_range=$2

    eval "$(build_irq_map "$iface" "$cpu_range")"
    set_irq_affinity irq_map
}

if [[ "$mode" == "ladder" ]]; then
    ladder_mode "$interface" cpu_list "$offset"
elif [[ "$mode" == "pool" ]]; then
    pool_mode "$interface" "$cpu_range"
else
    echo "Invalid mode: $mode. Use ladder or pool."
    usage
fi

if [[ $print_flag -eq 1 ]]; then
    irqs=($(grep "$interface" /proc/interrupts | awk '{print $1}' | tr -d ':'))
    if [[ ${#irqs[@]} -eq 0 ]]; then
        echo "No IRQs found for interface $interface."
        exit 1
    fi
    declare -A irq_map
    for irq in "${irqs[@]}"; do
        irq_map[$irq]=$(cat /proc/irq/"$irq"/smp_affinity_list)
    done
    print_irq_affinity irq_map
fi

