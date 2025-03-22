#!/bin/bash
#
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


DEFAULT_NUM_PAIRS=1
DEFAULT_CPU=2           # CPU cores
DEFAULT_MEM_GB=2        # memory in Gb
DEFAULT_NUM_DPDK=1      # default number of nic for DPDK
DEFAULT_NUM_SRIOV_VF=1  # default number for nic for SRIOV kernel mode
DEFAULT_HUGEPAGES=2     # hugepages in Gi
DEFAULT_IMAGE="spyroot/dpdk-pktgen-k8s-cycling-bench-trex:latest-amd64"

# this a class we expect , match the name if you have something different.
DEFAULT_STORAGE_CLASS="fast-disks"
DEFAULT_STORAGE_SIZE="20"
DEFAULT_NETWORK_RESOURCE_TYPE="dpdk"
DEFAULT_POD_KUBECONFIG_PATH="/home/capv/.kube"

# this a name we expect on k8s side for each network type.
DPDK_RESOURCE_NAME="intel.com/dpdk"
SRIOV_RESOURCE_NAME="intel.com/sriov"

OPT_SAME_NODE="true"
OPT_DRY_RUN="false"

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

# Clean up existing tx* or rx* pods
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


echo "Creating target dir"
# Create a directory to store the generated Pod YAML files
mkdir -p pods

# ---------------------------
# Helper: usage
# ---------------------------
function display_help() {
    echo "Usage: $0 [options]"
    echo "  -s                  Deploy rx on the same node as tx"
    echo "  -i <image>          Container image for pods (default: $DEFAULT_IMAGE)"
    echo "  -n <num_pairs>      Number of tx-rx pairs (default: $DEFAULT_NUM_PAIRS)"
    echo "  -c <cpu_cores>      CPU request/limit per pod (default: $DEFAULT_CPU)"
    echo "  -m <mem_mib>        Memory request/limit per pod, in Gb (default: $DEFAULT_MEM_GB)"
    echo "  -d <dpdk_count>     DPDK VF resource per pod (default: $DEFAULT_NUM_DPDK)"
    echo "  -v <vf_count>       Kernel VF resource per pod (default: $DEFAULT_NUM_SRIOV_VF)"
    echo "  -g <huge_gib>       1Gi hugepages limit per pod (default: $DEFAULT_HUGEPAGES)"
    echo "  -y | --dry-run      Generate YAML files but do not apply them"
    echo ""
    echo "Example: $0 -n 1 -c 4 -m 8000 -d 2 -v 2 -g 2 -s"
    echo "         (Creates 1 pair: tx0 + rx0, each with 4 CPU, 8 GiB, etc., on the same node.)"
    echo ""
    echo "         $0 -n 1 --dry-run"
    echo "         (Generate the YAML but do not kubectl apply, so you can inspect it.)"
}

function validate_integer() {
    local re='^[0-9]+$'
    if ! [[ $1 =~ $re ]] ; then
        echo "Error: $1 must be a positive integer." >&2
        exit 1
    fi
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -s)
            OPT_SAME_NODE="true"
            shift
            ;;
        -i)
            CUSTOM_IMAGE="$2"
            shift 2
            ;;
        -n)
            validate_integer "$2"
            DEFAULT_NUM_PAIRS=$2
            shift 2
            ;;
        -c)
            validate_integer "$2"
            DEFAULT_CPU=$2
            shift 2
            ;;
        -m)
            validate_integer "$2"
            DEFAULT_MEM_GB=$2
            shift 2
            ;;
        -r)
            USER_NETWORK_RESOURCE_TYPE="$2"
            shift 2
            ;;
        -d)
            validate_integer "$2"
            DEFAULT_NUM_DPDK=$2
            shift 2
            ;;
        -v)
            validate_integer "$2"
            DEFAULT_NUM_SRIOV_VF=$2
            shift 2
            ;;
        -g)
            validate_integer "$2"
            DEFAULT_HUGEPAGES=$2
            shift 2
            ;;
        -y|--dry-run)
            OPT_DRY_RUN="true"
            shift
            ;;
        -h|--help)
            display_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            display_help
            exit 1
            ;;
    esac
done


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

if [ "$OPT_SAME_NODE" = "true" ]; then
    echo "Deploying all pods on the same node."
    node=$(kubectl get nodes --selector='!node-role.kubernetes.io/control-plane' --no-headers | awk 'NR==1{print $1}')
    tx_node="$node"
    rx_node="$node"
else
    tx_node=${nodes[0]}
    rx_node=${nodes[1]}
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

echo "Tx node: $tx_node"
echo "Rx node: $rx_node"
echo "-------------------------------------------------------"

# Take POD template and produce POD templates for all TXs, RXs.
MEMORY_REQUEST="${DEFAULT_MEM_GB}"
MEMORY_LIMIT="${DEFAULT_MEM_GB}"
CPU_REQUEST="$DEFAULT_CPU"
CPU_LIMIT="$DEFAULT_CPU"
HUGEPAGES_LIMIT="${DEFAULT_HUGEPAGES}"

for i in $(seq 0 $((DEFAULT_NUM_PAIRS - 1))); do

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
        echo "Applying $tx_name and $rx_name to cluster..."
        kubectl apply -f "pods/pod-$tx_name.yaml"
        kubectl apply -f "pods/pod-$rx_name.yaml"
    else
        echo "[DRY-RUN] Skipping apply for $tx_name and $rx_name."
    fi
done

echo "-------------------------------------------------------"
if [ "$OPT_DRY_RUN" = "true" ]; then
    echo "Dry-run mode: no pods were actually created."
    echo "Check 'pods/' folder to see the rendered YAML."
else
    echo "Done! Created $DEFAULT_NUM_PAIRS pairs of tx–rx pods."
fi
