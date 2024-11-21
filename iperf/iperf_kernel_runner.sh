#!/bin/bash
#!/bin/bash
# Author: Mus spyroot@gmail.com
#
# This script automates network performance testing using iperf3 under various
# Linux kernel scheduler policies (SCHED_RR, SCHED_FIFO, SCHED_OTHER, etc.).
# It can operate in two modes: server and client. The script also supports
# single-core and multi-core configurations for testing scenarios.
#
# Key Features:
# 1. Scheduler Policy Adjustment: Modify the scheduling policy of processes
#    using `chrt` (e.g., SCHED_RR, SCHED_FIFO).
# 2. Core Affinity: Use `taskset` to pin server and client processes to specific CPU cores.
# 3. Single-Core Mode: All server/client processes run on the same core.
# 4. Multi-Core Mode: Server/client processes are evenly distributed across multiple cores.
# 5. Interface and IP Validation: Ensures the provided network interface and IP address are correct.
# 6. Dynamic Parameter Adjustment: Allows configuration of parallel streams, packet size,
#    timeout, and more via command-line arguments.
#
# Example Usage:
# - Start 4 servers in multi-core mode:
#   ./script.sh server -n 4
#
# - Start 4 clients in single-core mode:
#   ./script.sh client -n 4 --single-core
#
# - Specify custom packet size and timeout for clients:
#   ./script.sh client -n 4 --pkt-size 128 --timeout 300
#
# - Change scheduler policy to SCHED_RR:
#   ./script.sh client -n 4 -r
#
# Environment Variables:
# - SERVER_IP: IP address for the server (default: 172.16.222.158)
# - CLIENT_IP: IP address for the client (default: 172.16.222.124)


# Scheduler and core options
shed="-f"  # Default scheduler policy is FIFO
core_num_start=4  # Starting core number for assignment
core_increment=1  # Increment core number for each process
start_port=5551
single_core_mode=false

# Default values for parallel, packet size, and timeout, interface we bind
PARALLEL="1"
PKT_LEN="64"
TIMEOUT="600"
PRIORITY="99"
INTERFACE="net1"


# IP and port configuration (read from ENV or default values)
# you can pass from kubectl so you can direct via kubectl exec --
server_ip="${SERVER_IP:-172.16.222.158}"
client_ip="${CLIENT_IP:-172.16.222.124}"

# Function to log messages
function log_message() {
    echo "$(date +"%Y-%m-%d %H:%M:%S") $1"
}

# Function to get the last physical core
function get_last_core() {
    numactl -s | grep physcpubind | awk '{print $NF}'
}

function get_interface_ip() {
    local iface=$1
    ip -o -4 addr show "$iface" | awk '{print $4}' | cut -d'/' -f1
}

# Function to validate the interface and IP
function validate_interface_and_ip() {
    local iface=$1
    local expected_ip=$2
    local actual_ip

    if ! ip link show "$iface" &>/dev/null; then
        log_message "ERROR: Interface $iface does not exist."
        exit 1
    fi

    actual_ip=$(get_interface_ip "$iface")
    if [[ -z "$actual_ip" ]]; then
        log_message "ERROR: No IP address assigned to interface $iface."
        exit 1
    fi

    if [[ "$VALIDATE_IP" == true && "$actual_ip" != "$expected_ip" ]]; then
        log_message "ERROR: IP address mismatch on $iface. Expected: $expected_ip, Found: $actual_ip"
        exit 1
    fi

    log_message "Validation successful: Interface $iface has IP $actual_ip."
}


# Parse command-line arguments
mode=""
num_processes=1
while [[ "$#" -gt 0 ]]; do
    case $1 in
        server)
            mode="server"
            ;;
        client)
            mode="client"
            ;;
        -n|--number)
            num_processes="$2"
            shift
            ;;
         --interface)
            INTERFACE="$2"
            shift
            ;;
        --no-validate)
            VALIDATE_IP=false
            ;;
        --single-core)
            single_core_mode=true
            ;;
        -b|--batch)
            shed="-b"
            ;;
        -d|--deadline)
            shed="-d"
            ;;
        -f|--fifo)
            shed="-f"
            ;;
        -i|--idle)
            shed="-i"
            ;;
        -o|--other)
            shed="-o"
            ;;
        -r|--rr)
            shed="-r"
            ;;
        --parallel)
            PARALLEL="$2"
            shift
            ;;
        --pkt-size)
            PKT_LEN="$2"
            shift
            ;;
        --timeout)
            TIMEOUT="$2"
            shift
            ;;
        *)
            echo "Invalid argument: $1"
            exit 1
            ;;
    esac
    shift
done

if [[ -z "$mode" ]]; then
    echo "Usage: $0 {server|client} -n <number_of_processes> [--single-core] [--parallel <streams>] [--pkt-size <size>] [--timeout <seconds>] [-b|-d|-f|-i|-o|-r]"
    exit 1
fi

if [[ "$mode" == "server" ]]; then
    validate_interface_and_ip "$INTERFACE" "$server_ip"
elif [[ "$mode" == "client" ]]; then
    validate_interface_and_ip "$INTERFACE" "$client_ip"
fi

# Determine core assignment
if $single_core_mode; then
    core_num=$(get_last_core)
    log_message "Single-core mode enabled. Using core $core_num for all processes."
else
    log_message "Multi-core mode enabled. Starting from core $core_num_start."
fi

# Start server processes
if [[ "$mode" == "server" ]]; then
    log_message "Starting $num_processes iperf3 servers..."
    for ((i = 0; i < num_processes; i++)); do
        if $single_core_mode; then
            port=$((start_port + i))
            log_message "Starting server on port $port, core $core_num"
            chrt $shed $PRIORITY taskset -a -c "$core_num" iperf3 --server --bind $server_ip --one-off --daemon --port $port
        else
            core_num=$((core_num_start + i * core_increment))
            port=$((start_port + i))
            log_message "Starting server on port $port, core $core_num"
            chrt $shed $PRIORITY taskset -a -c $core_num iperf3 --server --bind $server_ip --one-off --daemon --port $port
        fi
    done
    log_message "All servers started."
fi

# Start client processes
if [[ "$mode" == "client" ]]; then
    log_message "Starting $num_processes iperf3 clients..."
    for ((i = 0; i < num_processes; i++)); do
        if $single_core_mode; then
            port=$((start_port + i))
            log_message "Starting client on port $port, core $core_num"
            chrt $shed $PRIORITY taskset -a -c $core_num iperf3 --client "$server_ip" --bind "$client_ip" --udp --zerocopy --bandwidth 0 --time $TIMEOUT --parallel "$PARALLEL" --length "$PKT_LEN" --port $port > log_$port 2>&1 &
        else
            core_num=$((core_num_start + i * core_increment))
            port=$((start_port + i))
            log_message "Starting client on port $port, core $core_num"
            chrt $shed $PRIORITY taskset -a -c $core_num iperf3 --client "$server_ip" --bind "$client_ip" --udp --zerocopy --bandwidth 0 --time $TIMEOUT --parallel "$PARALLEL" --length "$PKT_LEN" --port $port > log_$port 2>&1 &
        fi
    done
    log_message "All clients started."
fi

# Stop all iperf3 processes if needed
function stop_all() {
    log_message "Stopping all iperf3 processes..."
    ps aux | grep iperf3 | grep -v grep | awk '{print $2}' | xargs kill -9
    log_message "All iperf3 processes stopped."
}
