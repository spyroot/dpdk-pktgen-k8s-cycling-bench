#!/bin/bash
#
# DPDK Packet Generator Kubernetes Benchmark

# This script creates multiple pairs of "tx" and "rx" pods.

# It can create N where N is 1, 2, 3.. N act as TX POD i.e transmit in unidirectional sense.
# It can create N pods in M worker node where M is 1, 2.. M,  where M = 1 all on same worker node.

# -n <num_pairs> : Number of pairs (default: 3).
# -s            : Deploy both on the same node.
# -c <int>      : CPU (request/limit).
# -m <int>      : Memory (MiB, request/limit).
# -d <int>      : DPDK device resource count.
# -v <int>      : Kernel (VF) resource count.
# -g <int>      : Hugepages (1Gi) limit.
# -i <image>    : Container image.
# -y | --dry-run: Generate YAML but do not apply to the cluster.
#
# After creation, you'll have:
#   tx0, rx0
#   tx1, rx1
#   tx2, rx2
# ... up to -n pairs.
#
# The pods have labels role=tx or role=rx so you can select them with:
#   kubectl get pods -l role=tx
#   kubectl get pods -l role=rx
#
# In order avoid any promiscuous mode we want TX use actual mac addr as source and it should be destine to RX actual mac
# Hence we first build a array of all mac and all PCI device.
#
# Note that device plugin will pass allocate PCI address,  so code bellow will pass to TX SRC_MAC , and DST_MAC
# and RX pod will get inverse of that.  Same logic for PCI ADDRESS.
#
#  This a values in template script will replace with actual values.
#
#        - name: SRC_MAC
#          value: "{{src-mac}}"
#        - name: DST_MAC
#          value: "{{dst-mac}}"
#        - name: SRC_PCI
#          value: "{{src-pci}}"
#        - name: DST_PCI
#          value: "{{dst-pci}}"
#
# Author: Mus
# mbayramov@vmware.com

set -euo pipefail

KUBECONFIG_FILE="$HOME/.kube/config"
POD_TEMPLATE="pod-template.yaml"

MAC_ADDRESSES=(
    "00:50:56:AB:A2:EF" # Port 0
    "00:50:56:AB:60:84" # Port 1
    "00:50:56:AB:BB:C2" # Port 2
    "00:50:56:AB:A9:B8" # Port 3
    "00:50:56:AB:2D:CE" # Port 4
    "00:50:56:AB:25:6A" # Port 5
)

PCI_ADDRESSES=(
    "03:00.0" # Port 0
    "03:01.0" # Port 1
    "03:02.0" # Port 2
    "03:03.0" # Port 3
    "03:04.0" # Port 4
    "03:05.0" # Port 5
)

if [ "${#MAC_ADDRESSES[@]}" -ne "${#PCI_ADDRESSES[@]}" ]; then
  echo "❌ Number of MAC addresses and PCI addresses must match."
  echo "   ➤ MACs: ${#MAC_ADDRESSES[@]}"
  echo "   ➤ PCI:  ${#PCI_ADDRESSES[@]}"
  exit 1
fi



DEFAULT_NUM_PAIRS=1
DEFAULT_CPU=2           # CPU cores
DEFAULT_MEM_GB=2        # memory in Gb
DEFAULT_NUM_DPDK=1      # default number of nic for DPDK
DEFAULT_NUM_SRIOV_VF=1  # default number for nic for SRIOV kernel mode
DEFAULT_HUGEPAGES=$(( DEFAULT_CPU - 1 ))
DEFAULT_IMAGE="spyroot/dpdk-pktgen-k8s-cycling-bench-trex:latest-amd64"

# this a class we expect , match the name if you have something different.
DEFAULT_STORAGE_CLASS="fast-disks"
DEFAULT_STORAGE_SIZE="20"
DEFAULT_NETWORK_RESOURCE_TYPE="dpdk"
DEFAULT_POD_KUBECONFIG_PATH="/home/capv/.kube"

# this a name we expect on k8s side for each network type.
DPDK_RESOURCE_NAME="intel.com/dpdk"
SRIOV_RESOURCE_NAME="intel.com/sriov"

OPT_SAME_NODE="false"
OPT_DRY_RUN="false"
USER_SET_HUGEPAGES="false"

if ! command -v kubectl >/dev/null 2>&1; then
    echo "❌ 'kubectl' not found. Please ensure it's installed and in your PATH."
    exit 1
fi

if (( DEFAULT_MEM_GB <= 0 )); then
    echo "❌ Memory per pod must be greater than 0 GiB."
    exit 1
fi

if [ ! -f ".yamllint" ]; then
  echo "⚙️  Generating default .yamllint config..."
  cat <<EOF > .yamllint
extends: default
rules:
  line-length:
    max: 120
    level: warning
  document-start: disable
  indentation:
    spaces: 2
EOF
fi


function get_k8s_resource_name() {
    local resource_key="$1"
    case "$resource_key" in
        "dpdk")
            echo "intel.com/dpdk"
            ;;
        "sriov")
            echo "intel.com/sriov"
            ;;
        *)
            echo "Unsupported resource type: $resource_key" >&2
            return 1
            ;;
    esac
}

if [ ! -f "$KUBECONFIG_FILE" ]; then
    echo "kubeconfig file not found at $HOME/.kube/config."
    exit 1
fi

export KUBECONFIG="$KUBECONFIG_FILE"

if ! kubectl cluster-info >/dev/null 2>&1; then
    echo "❌ Unable to connect to Kubernetes cluster. Check your kubeconfig and cluster status."
    exit 1
fi


# ---------------------------
# Helper: usage
# ---------------------------
function display_help() {
    echo -e "🧪 \033[1mDPDK Kubernetes Pod Generator\033[0m"
    echo ""
    echo "This script generates and optionally deploys TX–RX pod pairs using DPDK or SR-IOV NICs."
    echo ""
    echo "🛠️  Usage:"
    echo "  ./create_pods.sh [options]"
    echo ""
    echo "📦 Options:"
    echo "  -n | --pairs <num>       🔁 Number of TX–RX pairs to create (default: $DEFAULT_NUM_PAIRS)"
    echo "  -s | --same-node         📍 Place TX and RX pods on the same worker node"
    echo "  -c | --cpu <int>         🧠 CPU cores per pod (default: $DEFAULT_CPU)"
    echo "  -m | --memory <int>      💾 Memory in GiB per pod (default: $DEFAULT_MEM_GB)"
    echo "  -d | --dpdk <int>        🚀 DPDK NIC resource count (default: $DEFAULT_NUM_DPDK)"
    echo "  -v | --vf <int>          🧩 SR-IOV VF count (default: $DEFAULT_NUM_SRIOV_VF)"
    echo "  -g | --hugepages <int>   🧱 Hugepages in GiB (default: $DEFAULT_HUGEPAGES)"
    echo "  -i | --image <image>     📦 Docker image to use (default: $DEFAULT_IMAGE)"
    echo "  -r | --resource <type>   🌐 Resource type to use: 'dpdk' or 'sriov'"
    echo "  -y | --dry-run           📝 Generate YAML only, do not deploy pods"
    echo "  -h | --help              📖 Show this help message"
    echo ""
    echo "📌 Notes:"
    echo "  - Pods are labeled with role=tx or role=rx."
    echo "  - You can filter with:"
    echo "      ▸ kubectl get pods -l role=tx"
    echo "      ▸ kubectl get pods -l role=rx"
    echo ""
    echo "🚀 Examples:"
    echo "  ▸ 🔁 Same k8s worker node (TX and RX on the same worker node):"
    echo "      ./create_pods.sh -n 2 -c 4 -m 8 -d 2 -g 2 -s"
    echo ""
    echo "  ▸ 🔀 Different k8s worker nodes (TX and RX on separate nodes):"
    echo "      ./create_pods.sh -n 2 -c 4 -m 8 -d 2 -g 2"
    echo ""
    echo "  ▸ 📝 Dry-Run Only (generate YAML, do not apply):"
    echo "      ./create_pods.sh -n 2 --dry-run"
    echo ""
    echo "  ▸ Generate pod YAML only, without applying to the cluster:"
    echo "      ./create_pods.sh -n 2 --dry-run"
    echo ""
    echo "💡 Make sure the device plugin is running and your nodes have the correct resource labels."
}


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
        -i|--image)
            CUSTOM_IMAGE="$2"
            shift 2
            ;;
        -n|--pairs)
            validate_integer "$2"
            DEFAULT_NUM_PAIRS=$2
            shift 2
            ;;
        -c|--cpu)
            validate_integer "$2"
            DEFAULT_CPU=$2
            shift 2
            ;;
        -m|--memory)
            validate_integer "$2"
            DEFAULT_MEM_GB=$2
            shift 2
            ;;
        -d|--dpdk)
            validate_integer "$2"
            DEFAULT_NUM_DPDK=$2
            shift 2
            ;;
        -v|--vf)
            validate_integer "$2"
            DEFAULT_NUM_SRIOV_VF=$2
            shift 2
            ;;
        -g|--hugepages)
            validate_integer "$2"
            DEFAULT_HUGEPAGES=$2
            USER_SET_HUGEPAGES="true"
            shift 2
            ;;
        -y|--dry-run)
            OPT_DRY_RUN="true"
            shift
            ;;
        -r|--resource)
            USER_NETWORK_RESOURCE_TYPE="$2"
            shift 2
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


# clean up existing tx* or rx* pods
PODS=$(kubectl get pods -o=name | grep -E 'tx|rx' || true)
if [ -n "$PODS" ]; then
  echo "Deleting matching pods: $PODS"
  echo "$PODS" | xargs kubectl delete --ignore-not-found
else
  echo "No pods match tx or rx."
fi

PVC_NAMES=$(kubectl get pvc -o=name | grep -E 'output-pvc-.*' || true)
if [ -n "$PVC_NAMES" ]; then
  echo "Deleting matching PVCs: $PVC_NAMES"
  echo "$PVC_NAMES" | xargs kubectl delete --ignore-not-found
else
  echo "No PVCs found for tx or rx pods."
fi


# Clean up existing tx* or rx* pods
PODS=$(kubectl get pods -o=name | grep -E 'tx|rx' || true)
if [ -n "$PODS" ]; then
  echo "Deleting matching pods: $PODS"
  echo "$PODS" | xargs kubectl delete --ignore-not-found
else
  echo "No pods match tx or rx."
fi

# Clean up matching PVCs
PVC_NAMES=$(kubectl get pvc -o=name | grep -E 'output-pvc-.*' || true)
if [ -n "$PVC_NAMES" ]; then
  echo "Deleting matching PVCs: $PVC_NAMES"
  echo "$PVC_NAMES" | xargs kubectl delete --ignore-not-found
else
  echo "No PVCs found for tx or rx pods."
fi

# ✅ Clean up and recreate pods folder
echo "🧹 Cleaning up 'pods/' folder..."
rm -rf pods
mkdir -p pods

function validate_network_resource() {
    local resource_name="$1"
    local required_count="$2"
    local node="$3"

    local resource_full_name
    if [ "$resource_name" = "dpdk" ]; then
        resource_full_name="intel.com/dpdk"
    elif [ "$resource_name" = "sriov" ]; then
        resource_full_name="intel.com/sriov"
    else
        echo "Error: Unsupported resource type '$resource_name'. Supported types are: dpdk, sriov"
        exit 1
    fi

    local allocatable_resources
    allocatable_resources=$(kubectl describe node "$node" | grep -A 10 "Allocatable:" | grep "$resource_full_name" || true)

    if [ -n "$allocatable_resources" ]; then
        # Extract the number of available units for the resource
        local available_units
        available_units=$(echo "$allocatable_resources" | awk '{print $2}')
        echo "  $resource_full_name available: $available_units units on node $node"

        # Check if the available units meet or exceed the required count
        # this a check in case available advertised is < 0 then what we need.
        # i.e since we pin pod to a node we need make sure node can
        # actually provide what we need.
        if [ "$available_units" -ge "$required_count" ]; then
            echo "  Sufficient $resource_name resources available on node $node."
        else
            echo "  WARNING: Insufficient $resource_name resources on node $node. Required: $required_count, Available: $available_units."
        fi
    else
        echo "  WARNING: $resource_full_name not found in allocatable resources for node $node."
    fi
}

# If user specified a custom image
if [ -n "${CUSTOM_IMAGE:-}" ]; then
    DEFAULT_IMAGE="$CUSTOM_IMAGE"
fi

NETWORK_RESOURCE_TYPE="${USER_NETWORK_RESOURCE_TYPE:-$DEFAULT_NETWORK_RESOURCE_TYPE}"

DPDK_REQUEST="${DPDK_REQUEST:-$DEFAULT_NUM_DPDK}"
DPDK_LIMIT="${DPDK_LIMIT:-$DEFAULT_NUM_DPDK}"
KERNEL_REQUEST="${KERNEL_REQUEST:-$DEFAULT_NUM_SRIOV_VF}"
KERNEL_LIMIT="${KERNEL_LIMIT:-$DEFAULT_NUM_SRIOV_VF}"

if [ "$NETWORK_RESOURCE_TYPE" = "dpdk" ]; then
    resource_requests="$DPDK_RESOURCE_NAME: \"$DPDK_REQUEST\""
    resource_limits="$DPDK_RESOURCE_NAME: \"$DPDK_LIMIT\""
elif [ "$NETWORK_RESOURCE_TYPE" = "sriov" ]; then
    resource_requests="$SRIOV_RESOURCE_NAME: \"$KERNEL_REQUEST\""
    resource_limits="$SRIOV_RESOURCE_NAME: \"$KERNEL_LIMIT\""
else
    echo "Error: Unsupported resource type '$NETWORK_RESOURCE_TYPE'. Supported types are: dpdk, sriov"
    exit 1
fi

echo "Pod Configuration:"
echo "  Number of Pairs:        $DEFAULT_NUM_PAIRS"
echo "  CPU per Pod:            $DEFAULT_CPU"
echo "  Memory per Pod (Gb):    $DEFAULT_MEM_GB"
echo "  DPDK per Pod:           $DEFAULT_NUM_DPDK"
echo "  VF per Pod:             $DEFAULT_NUM_SRIOV_VF"
echo "  1Gi HugePages per Pod:  $DEFAULT_HUGEPAGES"
echo "  Image:                  $DEFAULT_IMAGE"
echo "  Same Node (tx+rx):      $OPT_SAME_NODE"
echo "  Dry-Run Only?:          $OPT_DRY_RUN"

unset nodes
declare -a nodes
if [ "$OPT_SAME_NODE" = "false" ]; then
    while IFS= read -r line; do
        nodes+=("$line")
    done < <(kubectl get nodes --selector='!node-role.kubernetes.io/control-plane' --no-headers | awk '{print $1}')
    if [[ ${#nodes[@]} -lt 2 ]]; then
        echo "Only one worker node found or none. Forcing same-node deployment."
        OPT_SAME_NODE="true"
    fi
fi

#
#if [ "$OPT_SAME_NODE" = "true" ]; then
#    node=$(kubectl get nodes --selector='!node-role.kubernetes.io/control-plane' --no-headers | awk 'NR==1{print $1}')
#    tx_node="$node"
#    rx_node="$node"
#else
#    # Rotate nodes for tx/rx placement
#    tx_node="${nodes[$((i % ${#nodes[@]}))]}"
#    rx_node="${nodes[$(((i + 1) % ${#nodes[@]}))]}"
#fi


#if [ "$NETWORK_RESOURCE_TYPE" = "dpdk" ]; then
#    validate_network_resource "$NETWORK_RESOURCE_TYPE" "$DPDK_REQUEST" "$tx_node"
#    validate_network_resource "$NETWORK_RESOURCE_TYPE" "$DPDK_REQUEST" "$rx_node"
#elif [ "$NETWORK_RESOURCE_TYPE" = "sriov" ]; then
#    validate_network_resource "$NETWORK_RESOURCE_TYPE" "$KERNEL_REQUEST" "$tx_node"
#    validate_network_resource "$NETWORK_RESOURCE_TYPE" "$KERNEL_REQUEST" "$rx_node"
#else
#    echo "Error: Unsupported resource type '$NETWORK_RESOURCE_TYPE'. Supported types are: dpdk, sriov"
#    exit 1
#fi
#
#echo "Tx node: $tx_node"
#echo "Rx node: $rx_node"
#echo "-------------------------------------------------------"

# a check if num pairs > then what we have in CaaS
MAX_PAIRS=$((${#MAC_ADDRESSES[@]} / 2))
if [ "$DEFAULT_NUM_PAIRS" -gt "$MAX_PAIRS" ]; then
      echo "   ➤ You requested: $DEFAULT_NUM_PAIRS pairs"
      echo "   ➤ You provided:  ${#MAC_ADDRESSES[@]} MACs and ${#PCI_ADDRESSES[@]} PCI addresses"
      echo "   💡 Hint: Add ${DEFAULT_NUM_PAIRS}*2 MAC and PCI entries to support $DEFAULT_NUM_PAIRS pairs"
    exit 1
fi

if (( ${#MAC_ADDRESSES[@]} % 2 != 0 )) || (( ${#PCI_ADDRESSES[@]} % 2 != 0 )); then
    echo "⚠️ Warning: MAC or PCI address arrays contain an odd number of entries. Pairs will be truncated."
fi

if [ ! -f "$POD_TEMPLATE" ]; then
    echo "❌ Template file $POD_TEMPLATE not found."
    exit 1
fi

# take POD template and produce POD templates for all TXs, RXs.
MEMORY_REQUEST="${DEFAULT_MEM_GB}"
MEMORY_LIMIT="${DEFAULT_MEM_GB}"
CPU_REQUEST="$DEFAULT_CPU"
CPU_LIMIT="$DEFAULT_CPU"
HUGEPAGES_LIMIT="${DEFAULT_HUGEPAGES}"

if (( DEFAULT_CPU % 2 == 0 )); then
    echo "❌ CPU core count must be an odd number (e.g., 3, 5, 7)."
    echo "   1 main core + even number of worker cores is required for TX/RX split."
    exit 1
fi

if [ "$USER_SET_HUGEPAGES" = "true" ] && (( DEFAULT_HUGEPAGES > (DEFAULT_CPU - 1) )); then
    echo "ℹ️  Note: You requested more hugepages than TX/RX cores."
    echo "    Typically, only packet-processing cores need 1Gi each."
fi

# we auto-adjust hugepages if not set i.e. 1G per TX/RX core
if [ "$USER_SET_HUGEPAGES" = "false" ]; then
    if (( DEFAULT_CPU > 1 )); then
        DEFAULT_HUGEPAGES=$(( DEFAULT_CPU - 1 ))
    else
        DEFAULT_HUGEPAGES=1
    fi
    echo "📐 Auto-adjusted hugepages: ${DEFAULT_HUGEPAGES}Gi (1Gi per TX/RX core)"
else
    EXPECTED_HUGEPAGES=$(( DEFAULT_CPU - 1 ))
    if (( DEFAULT_HUGEPAGES < EXPECTED_HUGEPAGES )); then
        echo "⚠️  Warning: You specified fewer hugepages (${DEFAULT_HUGEPAGES}) than TX/RX cores (${EXPECTED_HUGEPAGES})."
        echo "    This may lead to allocation failures or degraded performance."
    fi
fi

if [ "$OPT_SAME_NODE" = "true" ]; then
    echo "🔁 Topology Mode: Single Worker Node (TX and RX on same node)"
else
    echo "🔀 Topology Mode: Multi-Worker Node (TX and RX on different nodes)"
    echo "   🧠 Nodes used: ${nodes[*]}"
fi

for i in $(seq 0 $((DEFAULT_NUM_PAIRS - 1))); do

    if [ "$OPT_SAME_NODE" = "true" ]; then
        node=$(kubectl get nodes --selector='!node-role.kubernetes.io/control-plane' --no-headers | awk 'NR==1{print $1}')
        tx_node="$node"
        rx_node="$node"
    else
        tx_node="${nodes[$((2 * i % ${#nodes[@]}))]}"
        rx_node="${nodes[$(((2 * i + 1) % ${#nodes[@]}))]}"
    fi

    if [ "$tx_node" = "$rx_node" ]; then
        echo "🔁 Topology Mode: Single Worker Node (TX and RX on same node)"
    else
        echo "🔀 Topology Mode: Multi-Worker Node (TX and RX on different nodes)"
    fi


    if [ "$NETWORK_RESOURCE_TYPE" = "dpdk" ]; then
        validate_network_resource "$NETWORK_RESOURCE_TYPE" "$DPDK_REQUEST" "$tx_node"
        validate_network_resource "$NETWORK_RESOURCE_TYPE" "$DPDK_REQUEST" "$rx_node"
    elif [ "$NETWORK_RESOURCE_TYPE" = "sriov" ]; then
        validate_network_resource "$NETWORK_RESOURCE_TYPE" "$KERNEL_REQUEST" "$tx_node"
        validate_network_resource "$NETWORK_RESOURCE_TYPE" "$KERNEL_REQUEST" "$rx_node"
    else
        echo "Error: Unsupported resource type '$NETWORK_RESOURCE_TYPE'. Supported types are: dpdk, sriov"
        exit 1
    fi

    tx_name="tx$i"
    rx_name="rx$i"

    SRC_MAC_TX=${MAC_ADDRESSES[$((i * 2))]}
    DST_MAC_TX=${MAC_ADDRESSES[$((i * 2 + 1))]}
    SRC_PCI_TX=${PCI_ADDRESSES[$((i * 2))]}
    DST_PCI_TX=${PCI_ADDRESSES[$((i * 2 + 1))]}

    SRC_MAC_RX=${MAC_ADDRESSES[$((i * 2 + 1))]}
    DST_MAC_RX=${MAC_ADDRESSES[$((i * 2))]}
    SRC_PCI_RX=${PCI_ADDRESSES[$((i * 2 + 1))]}
    DST_PCI_RX=${PCI_ADDRESSES[$((i * 2))]}


    sed -e "s|{{pod-name}}|$tx_name|g" \
        -e "s|{{pod-role}}|tx|g" \
        -e "s|{{node-name}}|$tx_node|g" \
        -e "s|{{cpu-request}}|$CPU_REQUEST|g" \
        -e "s|{{cpu-limit}}|$CPU_LIMIT|g" \
        -e "s|{{memory-request}}|$MEMORY_REQUEST|g" \
        -e "s|{{memory-limit}}|$MEMORY_LIMIT|g" \
        -e "s|{{resource-requests}}|$resource_requests|g" \
        -e "s|{{resource-limits}}|$resource_limits|g" \
        -e "s|{{hugepages-limit}}|$HUGEPAGES_LIMIT|g" \
        -e "s|{{src-mac}}|$SRC_MAC_TX|g" \
        -e "s|{{dst-mac}}|$DST_MAC_TX|g" \
        -e "s|{{src-pci}}|$SRC_PCI_TX|g" \
        -e "s|{{dst-pci}}|$DST_PCI_TX|g" \
        -e "s|{{image}}|$DEFAULT_IMAGE|g" \
        -e "s|{{storage-class}}|$DEFAULT_STORAGE_CLASS|g" \
        -e "s|{{storage-size}}|$DEFAULT_STORAGE_SIZE|g" \
        -e "s|{{kubeconfig-path}}|$DEFAULT_POD_KUBECONFIG_PATH|g" \
        "$POD_TEMPLATE" \
        > "pods/pod-$tx_name.yaml"

    sed -e "s|{{pod-name}}|$rx_name|g" \
        -e "s|{{pod-role}}|rx|g" \
        -e "s|{{node-name}}|$rx_node|g" \
        -e "s|{{cpu-request}}|$CPU_REQUEST|g" \
        -e "s|{{cpu-limit}}|$CPU_LIMIT|g" \
        -e "s|{{memory-request}}|$MEMORY_REQUEST|g" \
        -e "s|{{memory-limit}}|$MEMORY_LIMIT|g" \
        -e "s|{{hugepages-limit}}|$HUGEPAGES_LIMIT|g" \
        -e "s|{{resource-requests}}|$resource_requests|g" \
        -e "s|{{resource-limits}}|$resource_limits|g" \
        -e "s|{{src-mac}}|$SRC_MAC_RX|g" \
        -e "s|{{dst-mac}}|$DST_MAC_RX|g" \
        -e "s|{{src-pci}}|$SRC_PCI_RX|g" \
        -e "s|{{dst-pci}}|$DST_PCI_RX|g" \
        -e "s|{{image}}|$DEFAULT_IMAGE|g" \
        -e "s|{{storage-class}}|$DEFAULT_STORAGE_CLASS|g" \
        -e "s|{{storage-size}}|$DEFAULT_STORAGE_SIZE|g" \
        -e "s|{{kubeconfig-path}}|$DEFAULT_POD_KUBECONFIG_PATH|g" \
        "$POD_TEMPLATE" \
        > "pods/pod-$rx_name.yaml"

    echo "Generated POD spec YAML for $tx_name (TX) and $rx_name (RX)."

    if [ "$OPT_DRY_RUN" = "false" ]; then
        echo "🚀 Applying $tx_name and $rx_name to the cluster..."
        kubectl apply -f "pods/pod-$tx_name.yaml" &
        kubectl apply -f "pods/pod-$rx_name.yaml" &
        wait
        echo "✅ Successfully applied $tx_name and $rx_name"
    else
      echo "📝 [DRY-RUN] Skipping apply for $tx_name and $rx_name."
    fi
done

echo "-------------------------------------------------------"

if [ "$OPT_DRY_RUN" = "true" ]; then

    echo "🧪 Validating generated YAMLs..."
    for file in pods/pod-*.yaml; do
        if kubectl apply --dry-run=client -f "$file" >/dev/null 2>&1; then
            echo "✅ $file: valid"
        else
            echo "❌ $file: failed validation"
        fi
    done

    # Optional YAML linting pass
    if command -v yamllint >/dev/null 2>&1; then
        echo "🧪 Running yamllint on generated YAMLs..."
        for file in pods/pod-*.yaml; do
            echo "📄 Linting $file"
            yamllint "$file" || echo "⚠️  Lint warning(s) in $file"
        done
    else
        echo "⚠️  'yamllint' not installed. Skipping YAML linting."
    fi

    echo "Dry-run mode: no pods were actually created."
    echo "Check 'pods/' folder to see the rendered YAML."
else
    echo "✅ Done! Created $DEFAULT_NUM_PAIRS pairs of tx–rx pods."
fi
