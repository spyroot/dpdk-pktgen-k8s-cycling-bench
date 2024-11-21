#!/bin/bash
#
# This script automates network performance testing using iPerf3.
# It supports both server and client modes, facilitating tests across multiple interfaces.

# Key functionalities include:
# - Dynamically determining server IP addresses.
# - Managing iPerf3 server processes, including starting and restarting. min set of tools nc for control channel
# - Executing client tests for various packet sizes and modes (UDP/TCP, with/without zerocopy).
# - Logging activities and results for analysis.
# - all data serialized as json for later processing.

# Note iperf3 run The --one-off option causes the iPerf3 server to handle a single client
# connection and then terminate.
# This necessitates restarting the server before each test. To simplify the process, consider
# removing the --one-off option, allowing the server to handle multiple connections
# without restarting.
#
## autor Mus spyroot@gmail.com
#


declare -A SERVER_IPS=(
    ["eth0"]="100.96.5.146"
    ["net1"]="172.16.222.2"
    ["net2"]="192.168.27.150"
)

declare -A CLIENT_IPS=(
    ["eth0"]="100.96.6.90"
    ["net1"]="172.16.222.3"
    ["net2"]="192.168.27.147"
)

declare -A SERVER_TEST_PORTS=(
    ["eth0"]="5555"
    ["net1"]="6666"
    ["net2"]="7777"
)

#
PACKET_SIZES=(64 128 512 1500)
PARALLEL=1
DURATION=60

declare -A SERVER_PIDS

# Function start a iperf3 in server node and save server pid
# in SERVERS_PIDS
# Use a single control port for all interfaces
CONTROL_PORT=8080

# Define packet sizes and test parameters
PACKET_SIZES=(64 128 512 1500)
PARALLEL=1
DURATION=60
AFFINITY=10
# log file
LOG_FILE="iperf3_runner.log"

OUTPUT_DIR="/output"

IPERF_CLIENT_AFFINITY=""
AFFINITY_RT=""


function log_message() {
    local log_level=$1
    shift
    local log_message="$@"
    local timestamp=$(date +"%Y-%m-%d %H:%M:%S")
    echo "$timestamp [$log_level] $log_message" | tee -a "$LOG_FILE"
}

: > "$LOG_FILE"
# Function to check if iperf3 is installed; if not, attempt to install it
function check_and_install_iperf3() {
    if ! command -v iperf3 &> /dev/null; then
        log_message "INFO" "iperf3 not found. Attempting to install..."
        if [[ -f /etc/debian_version ]]; then
            sudo apt-get update && sudo apt-get install -y iperf3
        elif [[ -f /etc/redhat-release ]]; then
            sudo yum install -y iperf3
        else
            log_message "ERROR" "Unsupported OS. Please install iperf3 manually."
            exit 1
        fi
        if ! command -v iperf3 &> /dev/null; then
            log_message "ERROR" "iperf3 installation failed. Exiting."
            exit 1
        fi
        log_message "INFO" "iperf3 installed successfully."
    else
        log_message "INFO" "iperf3 is already installed."
    fi
}

check_and_install_iperf3

# Function to populate SERVER_IPS associative array
function populate_server_ips() {
    interfaces=$(ip -o -4 addr show | awk '{print $2}' | sort -u)
    for iface in $interfaces; do
        ip_address=$(ip -o -4 addr show "$iface" | awk '{print $4}' | cut -d'/' -f1)
        if [[ -n "$ip_address" ]]; then
            SERVER_IPS["$iface"]="$ip_address"
        fi
    done
}

declare -A SERVER_PIDS

# Function to start the iPerf3 server on a specific interface
# arg interface.
function start_server() {
    local iface=$1
    local server_ip=${SERVER_IPS[$iface]}
    local port=${SERVER_TEST_PORTS[$iface]}
    local log_file="iperf3_${iface}.log"

    if [[ -n "$AFFINITY_RT" ]]; then
        taskset_cmd="taskset -c $AFFINITY_RT"
    else
        taskset_cmd=""
    fi

    echo "Starting iPerf3 server on $server_ip:$port for interface $iface"
    $taskset_cmd iperf3 --bind "$server_ip" --server --daemon --port "$port" > "$log_file" 2>&1 &
    SERVER_PIDS[$iface]=$!

    if ! kill -0 ${SERVER_PIDS[$iface]} 2>/dev/null; then
      echo "Failed to start iPerf3 server on interface $iface"
      unset SERVER_PIDS[$iface]
    fi
}

# Function to restart or start the iPerf3 server on a
# specific interface. RESTART if iperf3 is running.
# if iperf3 server already gone. i.e one shoot server will exit
# in both case we start server.
function restart_server() {
    local iface=$1
    local pid=${SERVER_PIDS[$iface]}

    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
        echo "Stopping existing iPerf3 server on interface $iface (PID: $pid)"
        kill -TERM "$pid"
        sleep 1
        if kill -0 "$pid" 2>/dev/null; then
            echo "Process $pid did not terminate; forcing kill."
            kill -KILL "$pid"
        fi
    else
        echo "No running iPerf3 server found on interface $iface probably already gone."
    fi

    start_server "$iface"
    echo "iPerf3 server on interface $iface restarted."
}

# Function to start all iPerf3 servers and the control interface
function start_servers() {
    for iface in "${!SERVER_IPS[@]}"; do
        start_server "$iface"
    done
    control_interface &
    echo "All iPerf3 servers started."
}

# Function to handle control commands from clients
function control_interface() {
    while true; do
        command=$(nc -l -p "$CONTROL_PORT" -q 1)
        if [[ "$command" =~ ^RESTART\ (.+)$ ]]; then
            iface=${BASH_REMATCH[1]}
            if [[ -n "${SERVER_IPS[$iface]}" ]]; then
                echo "Received restart command for interface $iface"
                restart_server "$iface"
            else
                echo "Invalid interface: $iface"
            fi
        else
            echo "Invalid command: $command"
        fi
    done
}

function log_client_command() {
    local command="$1"
    echo "$(date +"%Y-%m-%d %H:%M:%S") [CLIENT COMMAND] $command" | tee -a "$LOG_FILE"
}
#
##
# Function to run client tests for each interface and packet size
function run_client_tests() {
    local interfaces=("$@")
    local mss_size="1480"

    if [[ -n "$AFFINITY_RT" ]]; then
        taskset_cmd="taskset -c $AFFINITY_RT"
    fi

    if [[ -n "$IPERF_CLIENT_AFFINITY" ]]; then
        iperf_affinity_opt="-A $IPERF_CLIENT_AFFINITY"
    fi

    for iface in "${interfaces[@]}"; do
        local client_ip=${CLIENT_IPS[$iface]}
        local server_ip=${SERVER_IPS[$iface]}
        local port=${SERVER_TEST_PORTS[$iface]}

        affinity_label=$( [ -n "$IPERF_CLIENT_AFFINITY" ] && echo "affinity_${IPERF_CLIENT_AFFINITY}" || echo "noaffinity" )
        parallel_label="parallel_${PARALLEL}"

        for pkt_size in "${PACKET_SIZES[@]}"; do
            # UDP Tests
            for zerocopy in "" "--zerocopy"; do
                zc_label=$( [ "$zerocopy" == "--zerocopy" ] && echo "zerocopy" || echo "nozerocopy" )
                if $console_mode; then
                    output_file="/dev/null"
                    json_flag=""
                else
                    output_file="$OUTPUT_DIR/udp_${pkt_size}_${iface}_${zc_label}_${affinity_label}_${parallel_label}.json"
                    json_flag="--json"
                fi
                echo "Running UDP test: $iface -> $server_ip:$port, Packet Size: $pkt_size, Zerocopy: $zc_label result file $output_file"

                client_command="iperf3 --parallel $PARALLEL --client $server_ip --length $pkt_size --bandwidth 0 $zerocopy --port $port --bind $client_ip %$iface -u $json_flag --time $DURATION $iperf_affinity_opt > $output_file"
                log_client_command "$client_command"
                eval "$client_command"

                echo "Sending restart command to server on $server_ip:$CONTROL_PORT"
                echo "RESTART $iface" | nc "$server_ip" "$CONTROL_PORT"
                sleep 1
            done

            # TCP Tests
            for zerocopy in "" "--zerocopy"; do
                zc_label=$( [ "$zerocopy" == "--zerocopy" ] && echo "zerocopy" || echo "nozerocopy" )
                if $console_mode; then
                    output_file="/dev/null"
                    json_flag=""
                else
                    output_file="$OUTPUT_DIR/tcp_${pkt_size}_${iface}_${zc_label}_${affinity_label}_${parallel_label}.json"
                    json_flag="--json"
                fi
                echo "Running TCP test: $iface -> $server_ip:$port, Packet Size: $pkt_size, Zerocopy: $zc_label result file $output_file"

                client_command="iperf3 --parallel $PARALLEL --client $server_ip --set-mss $mss_size --length $pkt_size --bandwidth 0 $zerocopy --port $port --bind $client_ip %$iface $json_flag --time $DURATION $iperf_affinity_opt > $output_file"
                log_client_command "$client_command"
                eval "$client_command"

                echo "Sending restart command to server on $server_ip:$CONTROL_PORT"
                echo "RESTART $iface" | nc "$server_ip" "$CONTROL_PORT"
                sleep 1
            done
        done
    done
    echo "All client tests completed. Results saved to JSON files."
}


#
## Function to run client tests for each interface and packet size
#function run_client_tests() {
#    local interfaces=("$@")
#    for iface in "${interfaces[@]}"; do
#        local client_ip=${CLIENT_IPS[$iface]}
#        local server_ip=${SERVER_IPS[$iface]}
#        local port=${SERVER_TEST_PORTS[$iface]}
#        local taskset_cmd=""
#        local iperf_affinity_opt=""
#
#        # Set taskset command if real-time affinity is specified
#        if [[ -n "$AFFINITY_RT" ]]; then
#            taskset_cmd="taskset -c $AFFINITY_RT"
#        fi
#
#        # Set iPerf3 client affinity option if specified
#        if [[ -n "$IPERF_CLIENT_AFFINITY" ]]; then
#            iperf_affinity_opt="-A $IPERF_CLIENT_AFFINITY"
#        fi
#
#        for pkt_size in "${PACKET_SIZES[@]}"; do
#            # Iterate over zerocopy options
#            for zerocopy in "" "--zerocopy"; do
#                zc_label=$( [ "$zerocopy" == "--zerocopy" ] && echo "zerocopy" || echo "nozerocopy" )
#                affinity_label=$( [ -n "$IPERF_CLIENT_AFFINITY" ] && echo "affinity_${IPERF_CLIENT_AFFINITY}" || echo "noaffinity" )
#                parallel_label="parallel_${PARALLEL}"
#
#                # UDP Test
#                output_file="$OUTPUT_DIR/udp_${pkt_size}_${iface}_${zc_label}_${affinity_label}_${parallel_label}.json"
#                echo "Running UDP test: $iface -> $server_ip:$port, Packet Size: $pkt_size, Zerocopy: $zc_label, Affinity: $affinity_label, Parallel: $parallel_label. Result file: $output_file"
#
#                client_udp_command="$taskset_cmd iperf3 --parallel $PARALLEL --client $server_ip --set-mss $pkt_size --bandwidth 0 $zerocopy --port $port --bind $client_ip %$iface -u --json --time $DURATION $iperf_affinity_opt > $output_file"
#                log_client_command "$client_udp_command"
#                eval "$client_command"
#
#                echo "Sending restart command to server on $server_ip:$CONTROL_PORT"
#                echo "RESTART $iface" | nc "$server_ip" "$CONTROL_PORT"
#                sleep 1
#
#                # TCP Test
#                output_file="$OUTPUT_DIR/tcp_${pkt_size}_${iface}_${zc_label}_${affinity_label}_${parallel_label}.json"
#                echo "Running TCP test: $iface -> $server_ip:$port, Packet Size: $pkt_size, Zerocopy: $zc_label, Affinity: $affinity_label, Parallel: $parallel_label. Result file: $output_file"
#
#                client_tcp_command="$taskset_cmd iperf3 --parallel $PARALLEL --client $server_ip --set-mss $pkt_size --bandwidth 0 $zerocopy --port $port --bind $client_ip %$iface --json --time $DURATION $iperf_affinity_opt > $output_file"
#                log_client_command "$client_tcp_command"
#                eval "$client_tcp_command"
#
#                echo "Sending restart command to server on $server_ip:$CONTROL_PORT"
#                echo "RESTART $iface" | nc "$server_ip" "$CONTROL_PORT"
#                sleep 1
#            done
#        done
#    done
#    echo "All client tests completed. Results saved to JSON files."
#}


# Function cleanup servers called before exit.
function cleanup() {
    echo "Cleaning up iPerf3 server processes..."
    for pid in "${SERVER_PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill -TERM "$pid"
            wait "$pid"
        fi
    done
    echo "Cleanup complete."
}

function display_usage() {
    echo "Usage: $0 {server|client} [options] [interfaces...]"
    echo
    echo "Modes:"
    echo "  server               Start the script in server mode."
    echo "  client               Start the script in client mode."
    echo
    echo "Options:"
    echo "  -p, --parallel       Number of parallel streams for iperf3 tests (default: 1)."
    echo "  --pkt-size           Packet size for tests (e.g., 64, 128, 512, 1500)."
    echo "  -t, --rt_affinity    Set CPU affinity for real-time (RT) cores (e.g., 2,3)."
    echo "  -a, --affinity       Set CPU affinity for iPerf3 client (e.g., 1)."
    echo
    echo "Interfaces:"
    echo "  Specify one or more network interfaces to test (e.g., eth0, net1, net2)."
    echo "  If no interfaces are specified, all available interfaces will be tested."
    echo
    echo "Examples:"
    echo "  $0 server"
    echo "  $0 client -p 5 eth0 net1"
    echo "  $0 client --pkt-size 128 -t 2,3 -a 1 eth0"
    echo
    echo "Note:"
    echo "  - The '-t|--rt_affinity' option sets the CPU cores for real-time processing. (for RT kernel)"
    echo "  - The '-a|--affinity' option sets the CPU core for the iPerf3 client process."
    exit 1
}


console_mode=false


while [[ "$#" -gt 0 ]]; do
    case $1 in
        server)
            mode="server"
            ;;
        client)
            mode="client"
            ;;
        -p|--parallel)
            PARALLEL="$2"
            shift
            ;;
        --pkt-size)
            PACKET_SIZES=("$2")
            shift
            ;;
        -t|--rt_affinity)
            AFFINITY_RT="$2"
            shift
            ;;
        -a|--affinity)
            IPERF_CLIENT_AFFINITY="$2"
            shift
            ;;
        --console)
            console_mode=true
            ;;
        *)
            interfaces+=("$1")
            ;;
    esac
    shift
done




if [ "$mode" == "server" ]; then
    populate_server_ips
    trap cleanup SIGINT SIGTERM
    for iface in "${!SERVER_IPS[@]}"; do
      echo "Interface: $iface, IP Address: ${SERVER_IPS[$iface]}"
    done
    start_servers
    wait
elif [ "$mode" == "client" ]; then
    if [ "${#PACKET_SIZES[@]}" -eq 0 ]; then
        PACKET_SIZES=(64 128 512 1500)
     fi

    if [ "${#interfaces[@]}" -eq 0 ]; then
        # No interfaces specified; test all
        interfaces=("${!CLIENT_IPS[@]}")
    fi

    run_client_tests "${interfaces[@]}"
else
    echo "Usage: $0 {server|client} [-p|--parallel <number>] [interfaces...]"
    exit 1
fi
