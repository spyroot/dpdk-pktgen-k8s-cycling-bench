#!/bin/bash
#
# DPDK Packet Generator Kubernetes Benchmark
#
# This script launches network performance experiments using paired "tx" and "rx" Kubernetes pods.
# It supports generating YAML manifests, validating resource specs, checking pod readiness,
# ensuring proper NUMA/node placement, and running the actual traffic generator (Pktgen).
#
# 🧪 Purpose:
#   - Automate the setup and execution of DPDK/SR-IOV-based experiments across Kubernetes pods.
#   - Optionally perform a dry-run to validate config without deploying.
#
# 🧵 Features:
#   - Generate and deploy N TX–RX pod pairs.
#   - Run traffic tests using pre-generated Lua profiles.
#   - Print pod–node mappings and verify affinity constraints (e.g., same/different node).
#   - Validate pod resource specs (CPU, memory, NICs, hugepages).
#
#  if you want run with default settings ./run_experiments.sh --no-same-node --run
#
#
# 🛠️ Usage:
#
#   ./run_experiment.sh [options]
#
# 📦 Options:
#   -n | --pairs <num>        🔁 Number of TX–RX pod pairs (default: 2)
#   -s | --same-node          📍 Place TX and RX pods on the same node (default: true)
#   -c | --cpu <int>          🧠 CPU cores per pod (default: 2)
#   -m | --memory <int>       💾 Memory in GiB per pod (default: 2)
#   -d | --dpdk <int>         🚀 DPDK NIC resource count per pod (default: 1)
#   -v | --vf <int>           🧩 SR-IOV VF count per pod (default: 1)
#   -g | --hugepages <int>    🧱 Hugepages in GiB per pod (default: CPU - 1)
#   -i | --image <image>      📦 Docker image to use (default: spyroot/dpdk-pktgen-...)
#   -r | --resource <type>    🌐 Resource type to use: 'dpdk' or 'sriov'
#   -y | --dry-run            📝 Only validate setup and generate YAML (no pod deployment)
#   --config                  📋 Print current configuration and exit
#   --config-file <file>      📋 Save configuration to the specified file
#   -h | --help               📖 Show this help message
#
# 📄 Notes:
#   - Pods are labeled with role=tx and role=rx for easy filtering:
#       ▸ kubectl get pods -l role=tx
#       ▸ kubectl get pods -l role=rx
#   - Profiles (*.lua) are read from the 'flows/' directory.
#
# 🧪 Example:
#   ./run_experiment.sh -n 2 -c 4 -m 8 -d 2 -g 2 -s
#   ./run_experiment.sh -n 4 --dry-run
#   ./run_experiment.sh --config
#
# Author: Mus
set -euo pipefail
WAIT_TIMEOUT="120"   # default wait timeout (seconds)
DURATION="120"      # default duration to run a test.
FLOWS="1,100,10000" # default number of flow generate
PKT_SIZES="64,512,1500,2000,9000" # default packet sizes tool will generate
RATE="100" # default rate for each flow
# default number of paris of txN - rxN (mapping 1:1,  profile also 1:1)
# default numer of cores.

# is kernel interrupt mode vf test
IS_SRIOV_VF="0"
# is dpdk pool mode vf test.
IS_DPDK_VF="1"

# if all pods should share same node or not
OPT_SAME_NODE="true"
# by default run dry run is true , we do all check but do not schedule a test.
OPT_DRY_RUN="true"

# by default we always do for two pair same node.
DEFAULT_NUM_PAIRS=2

# filter profile that we want run
PROFILE_FILTER=""

# this a name we expect on k8s side for each network type.
DPDK_RESOURCE_NAME="intel.com/dpdk"
SRIOV_RESOURCE_NAME="intel.com/sriov"

DEFAULT_CPU=5           # CPU cores
DEFAULT_MEM_GB=8        # memory in Gb
DEFAULT_NUM_DPDK=1      # default number of nic for DPDK
DEFAULT_NUM_SRIOV_VF=0  # default number for nic for SRIOV kernel mode
DEFAULT_HUGEPAGES=$(( DEFAULT_CPU - 1 ))
DEFAULT_IMAGE="spyroot/dpdk-pktgen-k8s-cycling-bench-trex:latest-amd64"
FORCE_REDEPLOY="false"

SCAN_ONLY=false

function display_help() {
    echo -e "🧪 \033[1mDPDK Kubernetes Experiment Runner\033[0m"
    echo ""
    echo "This script validates and runs DPDK/SR-IOV-based performance tests using paired TX–RX Kubernetes pods."
    echo "Note: By default, this script runs in dry-run mode."
    echo ""
    echo "🛠️  Usage:"
    echo "  ./run_experiments.sh [options]"
    echo ""
    echo "📦 Options:"
    echo "  -n | --pairs <num>             🔁 Number of TX–RX pod pairs (default: $DEFAULT_NUM_PAIRS)"
    echo "  -s | --same-node               📍 Place TX and RX pods on the same node (default: true)"
    echo "      --no-same-node             🚀 Force TX and RX pods onto different nodes"
    echo "  -c | --cpu <int>               🧠 CPU cores per pod (default: $DEFAULT_CPU)"
    echo "  -m | --memory <int>            💾 Memory in GiB per pod (default: $DEFAULT_MEM_GB)"
    echo "  -d | --dpdk <int>              🚀 DPDK NIC resource count per pod (default: $DEFAULT_NUM_DPDK)"
    echo "  -v | --vf <int>                🧩 SR-IOV VF count per pod (default: $DEFAULT_NUM_SRIOV_VF)"
    echo "  -g | --hugepages <int>         🧱 Hugepages in GiB per pod (default: CPU - 1)"
    echo "  -f | --filter-profile <str>    🔍 Run only profiles matching the string (e.g., '64')"
    echo "  -i | --image <image>           📦 Docker image to use (default: $DEFAULT_IMAGE)"
    echo "  -r | --resource <type>         🌐 Resource type: 'dpdk' or 'sriov'"
    echo "  -y | --dry-run [true|false]    📝 Whether to run in dry-run mode (default: true)"
    echo "      --new                      ♻️  Regenerate flow profiles and re-deploy pods"
    echo "      --run                      🚀 Shortcut for --dry-run false"
    echo "      --config                   📋 Print current configuration and exit"
    echo "      --config-file <file>       📋 Save current configuration to specified file"
    echo "      --scan-results             📊 Scan and report which profiles have already been completed"
    echo "  -h | --help                    📖 Show this help message"
    echo ""
    echo "📌 Notes:"
    echo "  - Pods are labeled with role=tx or role=rx for selection:"
    echo "      ▸ kubectl get pods -l role=tx"
    echo "      ▸ kubectl get pods -l role=rx"
    echo "  - All Lua flow profiles are stored in the 'flows/' directory."
    echo "  - Results are saved in the 'results/' directory. Completed profiles are automatically skipped."
    echo ""
    echo "🔄 Default Behavior:"
    echo "  - Automatically skips profiles that already have a result file (.npz) in the results directory."
    echo "  - Use --scan-results to view which profiles are done vs pending."
    echo ""
    echo "🚀 Examples:"
    echo "  ▸ Validate setup only (dry-run mode):"
    echo "      ./run_experiments.sh -n 2 --dry-run"
    echo ""
    echo "  ▸ Change number of pair, num nodes and deploy new pods: "
    echo "      ./run_experiments.sh -n 2 --no-same-node --run --new"
    echo ""
    echo "  ▸ Run tests using DPDK on the different node with default test profile:"
    echo "      ./run_experiments.sh --no-same-node --run"
    echo ""
    echo "  ▸ Run tests across nodes:"
    echo "      ./run_experiments.sh -n 2 -c 4 -m 8 -g 1 --no-same-node --run"
    echo ""
    echo "  ▸ Run only profiles containing '64' that are not yet complete:"
    echo "      ./run_experiments.sh -f 64 --run"
    echo ""
    echo "  ▸ Show scan results (without running tests):"
    echo "      ./run_experiments.sh --scan-results"
    echo ""
    echo "  ▸ Save config to file:"
    echo "      ./run_experiments.sh --config-file config.txt"
    echo ""
    echo "💡 Ensure the device plugin is deployed and your nodes are labeled with available resources."
}

if [[ $# -ge 1 && ( "$1" == "--help" || "$1" == "-h" ) ]]; then
    display_help
    exit 0
fi

# hold all profiles , that we generated prior or new.
if [ ! -d "flows" ]; then
    echo "⚠️  'flows/' directory not found — regenerating profiles..."

    has_pods=$(kubectl get pods --no-headers | grep -E '^tx[0-9]+|^rx[0-9]+' || true)
    if [[ -n "$has_pods" ]]; then
        echo "📦 TX/RX pods detected — regenerating and syncing Lua profiles only."
        python packet_generator.py generate_flow --flows "$FLOWS" --pkt-size "$PKT_SIZES" --rate "$RATE"
    else
        echo "❌ No TX/RX pods detected and 'flows/' directory is missing."
        echo "   Please create pods or restore the 'flows/' directory."
        exit 1
    fi
fi

# this function wait for pod ready state.
function wait_for_all_pods_ready() {

    local all_ready=true
    echo "⏳ Waiting for all TX and RX pods to become Ready (timeout: ${WAIT_TIMEOUT}s)..."

    for pod in "${tx_pods[@]}"; do
        echo "   ⏳ Waiting for pod $pod..."
        if ! kubectl wait --for=condition=Ready pod "$pod" --timeout="${WAIT_TIMEOUT}s"; then
            echo "❌ Pod $pod did not become Ready"
            all_ready=false
        fi
    done

    for pod in "${rx_pods[@]}"; do
        echo "   ⏳ Waiting for pod $pod..."
        if ! kubectl wait --for=condition=Ready pod "$pod" --timeout="${WAIT_TIMEOUT}s"; then
            echo "❌ Pod $pod did not become Ready"
            all_ready=false
        fi
    done

    if [ "$all_ready" != true ]; then
        echo "❌ One or more pods failed to become Ready. Exiting."
        exit 1
    fi

    echo "✅ All TX and RX pods are now Ready!"
    echo ""
    echo "📡 RX pods:"
    kubectl get pods -l role=rx -o wide
    echo ""
    echo "📡 TX pods:"
    kubectl get pods -l role=tx -o wide
    echo ""
}


# scale for all profiles.
profiles=($(find flows/ -type f -name "*.lua" -exec basename {} \; | sort -u))

if ! kubectl cluster-info >/dev/null 2>&1; then
    echo "❌ Unable to connect to Kubernetes cluster. Check your kubeconfig and cluster status."
    exit 1
fi

rx_pods=()
while IFS= read -r pod; do
  rx_pods+=("$pod")
done < <(kubectl get pods -o jsonpath='{.items[*].metadata.name}' 2>/dev/null | tr ' ' '\n' | grep '^rx[0-9]\+' || true)
echo "✅ rx_pods populated: ${#rx_pods[@]} found"

tx_pods=()
while IFS= read -r pod; do
  tx_pods+=("$pod")
done < <(kubectl get pods -o jsonpath='{.items[*].metadata.name}' 2>/dev/null | tr ' ' '\n' | grep '^tx[0-9]\+' || true)
echo "✅ tx_pods populated: ${#tx_pods[@]} found"


# if no pods either in tx and rx create and generate profile
if [ ${#rx_pods[@]} -eq 0 ] || [ ${#tx_pods[@]} -eq 0 ]; then
    echo "📦 No TX or RX pods found — creating pods via create_pods.sh..."

    CREATE_CMD="./create_pods.sh"
    CREATE_CMD+=" -n $DEFAULT_NUM_PAIRS"
    CREATE_CMD+=" -c $DEFAULT_CPU"
    CREATE_CMD+=" -m $DEFAULT_MEM_GB"
    CREATE_CMD+=" -d $DEFAULT_NUM_DPDK"
    CREATE_CMD+=" -v $DEFAULT_NUM_SRIOV_VF"
    CREATE_CMD+=" -g $DEFAULT_HUGEPAGES"

    [[ "$OPT_SAME_NODE" == "true" ]] && CREATE_CMD+=" --same-node"
    [[ -n "${CUSTOM_IMAGE:-}" ]] && CREATE_CMD+=" --image $CUSTOM_IMAGE"

    echo "🚧 Running: $CREATE_CMD"
    eval "$CREATE_CMD"

    # re-populate rx_pods/tx_pods after creation
    rx_pods=($(kubectl get pods -o jsonpath='{.items[*].metadata.name}' | tr ' ' '\n' | grep '^rx[0-9]\+'))
    tx_pods=($(kubectl get pods -o jsonpath='{.items[*].metadata.name}' | tr ' ' '\n' | grep '^tx[0-9]\+'))

    if [ ${#rx_pods[@]} -eq 0 ] || [ ${#tx_pods[@]} -eq 0 ]; then
        echo "❌ Pod creation failed — no TX/RX pods detected."
        exit 1
    fi

    wait_for_all_pods_ready
    echo "✅ Created ${#tx_pods[@]} TX pods and ${#rx_pods[@]} RX pods"
fi

if ! command -v jq >/dev/null 2>&1; then
    echo "❌ 'jq' is required but not found. Please install jq to proceed."
    exit 1
fi

for tool in kubectl jq; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "❌ '$tool' is required but not found. Please install it to continue."
        exit 1
    fi
done


# function validate integer
function validate_integer() {
    local re='^[0-9]+$'
    if ! [[ $1 =~ $re ]] ; then
        echo "Error: $1 must be a positive integer." >&2
        exit 1
    fi
}

while [[ $# -gt 0 ]]; do
    if [[ "$1" == *=* ]]; then
        echo "❌ Unsupported argument format: $1"
        echo "   Please use space-separated options like '-c 2', not '--cpu=2'"
        exit 1
    fi

    case "$1" in
        -s|--same-node)
            OPT_SAME_NODE="true"
            shift
            ;;
        --no-same-node)
          OPT_SAME_NODE="false"
          shift
          ;;
        -n|--pairs)
            validate_integer "$2"
            DEFAULT_NUM_PAIRS="$2"
            shift 2
            ;;
        --duration)
            validate_integer "$2"
            DURATION="$2"
            shift 2
            ;;
        --wait-timeout)
            validate_integer "$2"
            WAIT_TIMEOUT="$2"
            shift 2
            ;;
        -i|--image)
           if [[ -z "$2" || "$2" == "-"* ]]; then
              echo "❌ Invalid Docker image: '$2'"
              echo "   Provide a valid image name after -i or --image (e.g., spyroot/dpdk:latest)"
              exit 1
          fi
          CUSTOM_IMAGE="$2"
          shift 2
          ;;
        -c|--cpu)
            validate_integer "$2"
            DEFAULT_CPU="$2"
            shift 2
            ;;
        -m|--memory)
            validate_integer "$2"
            DEFAULT_MEM_GB="$2"
            shift 2
            ;;
        -d|--dpdk)
            validate_integer "$2"
            DEFAULT_NUM_DPDK="$2"
            shift 2
            ;;
        -v|--vf)
            validate_integer "$2"
            DEFAULT_NUM_SRIOV_VF="$2"
            shift 2
            ;;
        -g|--hugepages)
            validate_integer "$2"
            DEFAULT_HUGEPAGES="$2"
            USER_SET_HUGEPAGES="true"
            shift 2
            ;;
        -f | --filter-profile)
          PROFILE_FILTER="$2"
          shift 2
          ;;
         --new)
        FORCE_REDEPLOY="true"
        shift
        ;;
        -r|--resource)
          case "$2" in
              dpdk)
                  IS_DPDK_VF="1"
                  IS_SRIOV_VF="0"
                  ;;
              sriov)
                  IS_DPDK_VF="0"
                  IS_SRIOV_VF="1"
                  ;;
              *)
                  echo "❌ Invalid resource type: $2. Must be 'dpdk' or 'sriov'."
                  exit 1
                  ;;
          esac
          shift 2
          ;;
        --dry-run)
          if [[ $# -lt 2 ]]; then
              echo "❌ Missing value for --dry-run: must be 'true' or 'false'"
              exit 1
          fi
          case "$2" in
              true|false)
                  OPT_DRY_RUN="$2"
                  ;;
              *)
                  echo "❌ Invalid value for --dry-run: must be 'true' or 'false'"
                  exit 1
                  ;;
          esac
          shift 2
          ;;
        --run|--no-dry-run)
            OPT_DRY_RUN="false"
            shift
            ;;
        --config)
            PRINT_CONFIG="true"
            CONFIG_OUTPUT_FILE=""
            shift
            ;;
        --config-file)
            PRINT_CONFIG="true"
            CONFIG_OUTPUT_FILE="$2"
            shift 2
            ;;
        --scan-results)
              SCAN_ONLY=true
              shift
            ;;
        -h|--help)
            display_help
            exit 0
            ;;
        *)
            echo "❌ Unknown option: $1"
            display_help
            exit 1
            ;;
    esac
done


if [[ "$FORCE_REDEPLOY" == "true" ]]; then
    echo "♻️  --new flag detected — regenerating profiles and re-creating TX/RX pods"

    # Clean up existing pods (optional — or rely on create_pods.sh to overwrite)
    kubectl delete pods -l role=tx --ignore-not-found
    kubectl delete pods -l role=rx --ignore-not-found

    # Regenerate profiles
    python packet_generator.py generate_flow --flows "$FLOWS" --pkt-size "$PKT_SIZES" --rate "$RATE"

    # Recreate pods
    CREATE_CMD="./create_pods.sh"
    CREATE_CMD+=" -n $DEFAULT_NUM_PAIRS"
    CREATE_CMD+=" -c $DEFAULT_CPU"
    CREATE_CMD+=" -m $DEFAULT_MEM_GB"
    CREATE_CMD+=" -d $DEFAULT_NUM_DPDK"
    CREATE_CMD+=" -v $DEFAULT_NUM_SRIOV_VF"
    CREATE_CMD+=" -g $DEFAULT_HUGEPAGES"
    [[ "$OPT_SAME_NODE" == "true" ]] && CREATE_CMD+=" --same-node"
    [[ -n "${CUSTOM_IMAGE:-}" ]] && CREATE_CMD+=" --image $CUSTOM_IMAGE"

    echo "🚧 Running: $CREATE_CMD"
    eval "$CREATE_CMD"

    # Refresh pod lists
    rx_pods=($(kubectl get pods -o jsonpath='{.items[*].metadata.name}' | tr ' ' '\n' | grep '^rx[0-9]\+'))
    tx_pods=($(kubectl get pods -o jsonpath='{.items[*].metadata.name}' | tr ' ' '\n' | grep '^tx[0-9]\+'))

    wait_for_all_pods_ready
fi

# function check if results contain results for a particular profile
function has_profile_run() {
    local profile="$1"
    local exp_dirs=(results/*)
    for dir in "${exp_dirs[@]}"; do
        if [ -d "$dir" ]; then
            if find "$dir" -type f -name "*${profile%.lua}*.npz" | grep -q .; then
                return 0
            fi
        fi
    done
    return 1
}

#
function report_profiles_status() {
    echo "📊 Profile Scan Report"
    echo "-----------------------"
    local total=${#profiles[@]}
    local run=0
    local not_run=0
    for profile in "${profiles[@]}"; do
        if has_profile_run "$profile"; then
            echo "✅ $profile"
            ((run++))
        else
            echo "❌ $profile"
            ((not_run++))
        fi
    done
    echo ""
    echo "📈 Summary: $run/$total completed, $not_run pending"
}


if [[ "${PRINT_CONFIG:-false}" == "true" ]]; then
    print_config
    exit 0
fi

if [[ "$SCAN_ONLY" == "true" ]]; then
    report_profiles_status
    exit 0
fi

function check_profiles_in_pods() {
    local pod_list_name=$1
    local profile_list_name=$2

    local missing=false

    # Get values of arrays by name
    local pod_list=()
    eval "pod_list=(\"\${${pod_list_name}[@]}\")"

    local profile_list=()
    eval "profile_list=(\"\${${profile_list_name}[@]}\")"

    for pod in "${pod_list[@]}"; do
        echo "🔍 Checking profiles in pod: $pod"

        pod_profiles=()

        while IFS= read -r line; do
            pod_profiles+=("$line")
        done < <(kubectl exec "$pod" -- sh -c 'ls /profile_*.lua 2>/dev/null' || true)


        echo "📦 Discovered profiles in $pod:"
        if [ "${#pod_profiles[@]:-0}" -gt 0 ]; then
            for p in "${pod_profiles[@]}"; do
                echo "   ✔️ $p"
            done
        else
            echo "   ⚠️ No profiles found"
        fi

        pod_profiles_basename=()
        if [ "${#pod_profiles[@]}" -gt 0 ]; then
            for f in "${pod_profiles[@]}"; do
                pod_profiles_basename+=("$(basename "$f")")
            done
        fi

        for expected in "${profile_list[@]}"; do
            found=false
            if [ "${#pod_profiles_basename[@]}" -gt 0 ]; then
                for f in "${pod_profiles_basename[@]}"; do
                    if [ "$f" == "$expected" ]; then
                        found=true
                        break
                    fi
                done
            fi
            if [ "$found" = false ]; then
                echo "❌ Missing $expected in $pod"
                missing=true
                break
            fi
        done

        if $missing; then
            break
        fi
    done

    if $missing; then
        return 1
    else
        return 0
    fi
}

# function check all resource

function check_pod_spec_resources() {
    local pod=$1

    echo "🔍 Validating resources for pod: $pod"

    local limits
    limits=$(kubectl get pod "$pod" -o json | jq '.spec.containers[0].resources.limits')

    local requests
    requests=$(kubectl get pod "$pod" -o json | jq '.spec.containers[0].resources.requests')
    local required_keys

    local required_keys=("cpu" "memory" "hugepages-1Gi" "$DPDK_RESOURCE_NAME" "$SRIOV_RESOURCE_NAME")
    local missing=false

    [[ "$IS_DPDK_VF" == "1" ]] && required_keys+=("$DPDK_RESOURCE_NAME")
    [[ "$IS_SRIOV_VF" == "1" ]] && required_keys+=("$SRIOV_RESOURCE_NAME")

    for key in "${required_keys[@]}"; do
        # try to extract the value directly
        val_limit=$(echo "$limits" | jq -er ".\"$key\"" 2>/dev/null || echo "")
        val_request=$(echo "$requests" | jq -er ".\"$key\"" 2>/dev/null || echo "")

        if [[ -z "$val_limit" || -z "$val_request" ]]; then
            echo "❌ Missing $key in pod $pod (limit: ${val_limit:-not set}, request: ${val_request:-not set})"
            missing=true
        else
            echo "   ✔️ $key → limit=$val_limit, request=$val_request"
        fi
    done

    if $missing; then
        return 1
    else
        echo "✅ Pod $pod spec is valid"
        return 0
    fi
}

# function check that all txN and rxN placed.
function check_pod_node_placement() {
    local -a tx_nodes=()
    local -a rx_nodes=()

    for pod in "${tx_pods[@]}"; do
        node=$(kubectl get pod "$pod" -o jsonpath='{.spec.nodeName}')
        tx_nodes+=("$node")
    done

    for pod in "${rx_pods[@]}"; do
        node=$(kubectl get pod "$pod" -o jsonpath='{.spec.nodeName}')
        rx_nodes+=("$node")
    done

    # Remove duplicates
    unique_tx_nodes=($(echo "${tx_nodes[@]}" | tr ' ' '\n' | sort -u))
    unique_rx_nodes=($(echo "${rx_nodes[@]}" | tr ' ' '\n' | sort -u))

    if [[ "$OPT_SAME_NODE" == "true" ]]; then

        combined_nodes=("${unique_tx_nodes[@]}" "${unique_rx_nodes[@]}")
        unique_combined=($(echo "${combined_nodes[@]}" | tr ' ' '\n' | sort -u))

        if [[ ${#unique_combined[@]} -ne 1 ]]; then
            echo "❌ Expected all pods to run on the same node, but found multiple:"
            printf "   TX nodes: %s\n" "${unique_tx_nodes[@]}"
            printf "   RX nodes: %s\n" "${unique_rx_nodes[@]}"
            return 1
        else
            echo "✅ All TX and RX pods are on the same node: ${unique_combined[0]}"
        fi
    else
        if [[ ${#unique_tx_nodes[@]} -ne 1 || ${#unique_rx_nodes[@]} -ne 1 ]]; then
            echo "❌ Expected TX and RX pods each on a single node, but found:"
            printf "   TX nodes: %s\n" "${unique_tx_nodes[@]}"
            printf "   RX nodes: %s\n" "${unique_rx_nodes[@]}"
            return 1
        fi

        if [[ "${unique_tx_nodes[0]}" == "${unique_rx_nodes[0]}" ]]; then
            echo "❌ TX and RX pods are on the same node: ${unique_tx_nodes[0]}"
            echo "   When --same-node is disabled, they must be on different nodes."
            return 1
        fi

        echo "✅ TX and RX pods are placed on different nodes:"
        echo "   TX node: ${unique_tx_nodes[0]}"
        echo "   RX node: ${unique_rx_nodes[0]}"
    fi

    return 0
}

# Maps all pod names to their assigned nodes
function build_pod_node_mapping() {

    echo "🔎 Mapping pod names to their Kubernetes nodes..."

    local all_pods=("${tx_pods[@]}" "${rx_pods[@]}")
    pod_names=()
    pod_nodes=()

    for pod in "${all_pods[@]}"; do
        node=$(kubectl get pod "$pod" -o jsonpath='{.spec.nodeName}')
        pod_names+=("$pod")
        pod_nodes+=("$node")
    done
}

# function nice printer for all pairs.
function print_pair_node_map_for_profile() {
    local profile="$1"
    echo ""
    echo "📡 Test will start on all pairs with profile: $profile"
    for i in $(seq 0 $((DEFAULT_NUM_PAIRS - 1))); do
        local rx_pod="rx${i}"
        local tx_pod="tx${i}"
        local rx_node=$(kubectl get pod "$rx_pod" -o jsonpath='{.spec.nodeName}')
        local tx_node=$(kubectl get pod "$tx_pod" -o jsonpath='{.spec.nodeName}')

        echo "pair $rx_pod-$tx_pod nodes:"
        echo "   └── RX node: $rx_node"
        echo "   └── TX node: $tx_node"
    done
    echo ""
}


function print_config() {
    local output="${CONFIG_OUTPUT_FILE:-/dev/stdout}"
    {
        echo "📋 Effective configuration:"
        echo "• Pairs:           $DEFAULT_NUM_PAIRS"
        echo "• CPU:             $DEFAULT_CPU"
        echo "• Memory:          ${DEFAULT_MEM_GB}Gi"
        echo "• Hugepages:       ${DEFAULT_HUGEPAGES}Gi"
        echo "• DPDK NICs:       $DEFAULT_NUM_DPDK"
        echo "• SR-IOV VFs:      $DEFAULT_NUM_SRIOV_VF"
        echo "• Image:           ${CUSTOM_IMAGE:-$DEFAULT_IMAGE}"
        echo "• Duration:        ${DURATION}s"
        echo "• Timeout:         ${WAIT_TIMEOUT}s"
        echo "• Same Node:       $OPT_SAME_NODE"
        echo "• Resource Type:   $( [[ $IS_DPDK_VF == "1" ]] && echo "DPDK" || ([[ $IS_SRIOV_VF == "1" ]] && echo "SR-IOV" || echo "Unspecified") )"
        echo "• Dry Run:         $OPT_DRY_RUN"
        echo "• Profiles:"
        for profile in "${profiles[@]}"; do
            echo "   └── $profile"
        done
    } > "$output"
}

# interrupt handler
function cleanup_on_interrupt() {
    echo ""
    echo "🛑 KeyboardInterrupt received! Attempting cleanup..."

    running_sessions=$(tmux ls 2>/dev/null | grep "pktgen_" | awk -F: '{print $1}')
    for sess in $running_sessions; do
        tmux kill-session -t "$sess"
        echo "🧹 Killed tmux session: $sess"
    done

    echo "❌ Experiment interrupted."
    exit 1
}

echo "• Command Line:    $0 $*"

# note by default IS_DPDK_VF is true
if [[ "$IS_DPDK_VF" != "1" && "$IS_SRIOV_VF" != "1" ]]; then
    echo "⚠️  Resource type is unspecified. Use --resource dpdk or --resource sriov"
    exit 1
fi

# it should either pool mode or interrupt mode but not both
if [[ "$IS_DPDK_VF" == "1" && "$IS_SRIOV_VF" == "1" ]]; then
    echo "⚠️ Warning: Both DPDK and SR-IOV resources are specified. Only one should be active per pod."
    exit 1
fi

echo "📦 Discovered profiles:"
for profile in "${profiles[@]}"; do
    echo "   └── $profile"
done

echo "📡 RX pods:"
for pod in "${rx_pods[@]}"; do
    echo "   📥 $pod"
done

echo "📡 TX pods:"
for pod in "${tx_pods[@]}"; do
    echo "   📤 $pod"
done

# number of existing pair must match
if [ "${#rx_pods[@]}" -ne "$DEFAULT_NUM_PAIRS" ] || [ "${#tx_pods[@]}" -ne "$DEFAULT_NUM_PAIRS" ]; then
    echo "❌ Expected $DEFAULT_NUM_PAIRS TX-RX pairs"
    echo "   Found: ${#tx_pods[@]} TX pods, ${#rx_pods[@]} RX pods"
    echo "💡 Please create the correct number of pods or update the --pairs flag"
    exit 1
fi

# we check all pod specs
for pod in "${rx_pods[@]}" "${tx_pods[@]}"; do
    if ! check_pod_spec_resources "$pod"; then
        echo "⚠️ Pod $pod failed spec validation — trigger redeploy?"
    fi
done



# check all profiles present
if ! check_profiles_in_pods tx_pods profiles; then
    echo "⚙️ Generating profiles (some missing in TX pods)..."
    python packet_generator.py generate_flow --flows "$FLOWS" --pkt-size "$PKT_SIZES" --rate "$RATE"
else
    echo "✅ All profiles are present in TX pods"
fi


RECREATED=false
# Recreate pods if placement is invalid
if ! check_pod_node_placement; then
    echo "⚠️ Pod node placement does not meet expected topology"

    CREATE_CMD="./create_pods.sh"
    CREATE_CMD+=" -n \"$DEFAULT_NUM_PAIRS\""
    CREATE_CMD+=" -c \"$DEFAULT_CPU\""
    CREATE_CMD+=" -m \"$DEFAULT_MEM_GB\""
    CREATE_CMD+=" -d \"$DEFAULT_NUM_DPDK\""
    CREATE_CMD+=" -v \"$DEFAULT_NUM_SRIOV_VF\""
    CREATE_CMD+=" -g \"$DEFAULT_HUGEPAGES\""

    [[ "$OPT_SAME_NODE" == "true" ]] && CREATE_CMD+=" --same-node"
    # if we need overwrite image location
    [[ -n "${CUSTOM_IMAGE:-}" ]] && CREATE_CMD+=" --image \"$CUSTOM_IMAGE\""

    echo "🚧 Recreating pods due to invalid node placement..."
    eval "$CREATE_CMD"
    RECREATED=true
fi

# now we wait for all pods.
wait_for_all_pods_ready

# re-check only if user expects TX and RX to be on different nodes
if [[ "$OPT_SAME_NODE" == "false" ]]; then
    if ! check_pod_node_placement; then
        echo "❌ Pods were recreated but still failed topology validation (e.g., same node placement when --no-same-node was set)"
        echo "   💡 Please ensure node selector and affinity rules in the pod template support cross-node scheduling."
        exit 1
    fi
fi


# if we re-create any pods we regenerate profiles.
if [[ "$RECREATED" == "true" ]] || ! check_profiles_in_pods tx_pods profiles; then
    echo "⚙️ Syncing all Lua profiles to TX pods..."
    python packet_generator.py generate_flow --flows "$FLOWS" --pkt-size "$PKT_SIZES" --rate "$RATE"
else
    echo "✅ All profiles are present in TX pods"
fi

# build pod to node
build_pod_node_mapping

completed=0
for profile in "${profiles[@]}"; do
    if has_profile_run "$profile"; then
        ((completed++))
    fi
done

# If all are complete, back up results (only if NOT in dry-run)
if [ "$completed" -eq "${#profiles[@]}" ]; then
    if [[ "$OPT_DRY_RUN" == "true" ]]; then
        echo "✅ All profiles completed. Dry-run mode is active — skipping results backup."
        exit 0
    fi

    echo "✅ All profiles completed. Backing up results..."
    mkdir -p results_backups
    BACKUP_DIR="results_backups/results_$(date +%Y%m%d_%H%M%S)"
    mv results "$BACKUP_DIR"
    echo "📦 Results moved to: $BACKUP_DIR"
    exit 0
fi

# in case we want filter ( i.e use sub-set of tests based on pkt size )
filtered_profiles=("${profiles[@]}")

if [[ -n "$PROFILE_FILTER" ]]; then
    filtered_profiles=()
    for p in "${profiles[@]}"; do
        if [[ "$p" == *"$PROFILE_FILTER"* ]]; then
            filtered_profiles+=("$p")
        fi
    done

    if [[ ${#filtered_profiles[@]} -eq 0 ]]; then
        echo "❌ No profiles match filter: $PROFILE_FILTER"
        echo "📂 Available profiles:"
        printf "   - %s\n" "${profiles[@]}"
        exit 1
    fi
fi

trap cleanup_on_interrupt INT

# for each profile we run a test, in dry run we just print
# (note that profile still pushed prior.
for profile in "${filtered_profiles[@]}"; do

    if has_profile_run "$profile"; then
        echo "⏭️ Skipping $profile — result already exists"
        continue
    fi

    print_pair_node_map_for_profile "$profile"

    if [[ "$OPT_DRY_RUN" == "true" ]]; then
        echo "📝 Dry-run enabled — skipping execution for: $profile"
    else
        echo "🚀 Starting test for profile: $profile"
        python packet_generator.py start_generator --profile "$profile" --duration "$DURATION"
#        pid=$!
#        echo "PID"
#        echo $pid
#
#        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
#            wait "$pid"
#            ret=$?
#        else
#            echo "❌ Failed to start packet_generator.py or it exited too quickly."
#            ret=1
#        fi

        ret=$?
        # handle Ctrl+C or manual interruption
        if [[ $ret -eq 130 ]]; then
          echo "🛑 KeyboardInterrupt detected. Stopping experiment..."
          break
        fi

        echo "✅ Completed test for profile: $profile"
        fi
    echo "-----------------------------------"
    sleep 5
done

