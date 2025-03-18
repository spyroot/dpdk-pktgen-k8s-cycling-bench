#!/bin/bash

# Default values
AIGRAP_SERVER=""
CPU=2
MEMORY=2
NUM_DPDK=2
NUM_VF=2
STORAGE_SIZE=50
KUBECONFIG_PATH=${KUBECONFIG:-"/home/capv/.kube"}
STORAGE_CLASS="local.storage"
POD_NAME="mus-toolkit"
IMAGE="dpdk-pktgen-k8s-cycling-bench-trex"

target_pod_name="server0"
client_pod_name="client0"

# Function to display usage information
function usage() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo "  -a | --airgap-server <url>     Specify the airgap server URL (default: none, uses standard image)"
    echo "  -c | --cpu <number>            Set the number of CPUs (default: $CPU)"
    echo "  -m | --memory <GB>             Set the memory size in GB (default: $MEMORY)"
    echo "  -d | --num-dpdk <number>       Set the number of DPDK devices (default: $NUM_DPDK)"
    echo "  -v | --num-vf <number>         Set the number of virtual functions (default: $NUM_VF)"
    echo "  -s | --storage-size <GB>       Set the storage size in GB (default: $STORAGE_SIZE)"
    echo "  -h | --help                    Display this help message"
    exit 1
}


# resolve
function resole_nodes() {
  local tx_node_name
  local rx_node_name
  local tx_node_addr
  local rx_node_addr
  local tx_pod_full_name
  local rx_pod_full_name

  # pod name
  tx_pod_full_name=$(kubectl get pods | grep "$target_pod_name" | awk '{print $1}')
  rx_pod_full_name=$(kubectl get pods | grep "$client_pod_name" | awk '{print $1}')

  # node name
  tx_node_name=$(kubectl get pod "$tx_pod_full_name" -o=jsonpath='{.spec.nodeName}')
  rx_node_name=$(kubectl get pod "$rx_pod_full_name" -o=jsonpath='{.spec.nodeName}')

  # node address
  tx_node_addr=$(kubectl get node "$tx_node_name" -o jsonpath='{.status.addresses[?(@.type=="InternalIP")].address}')
  rx_node_addr=$(kubectl get node "$rx_node_name" -o jsonpath='{.status.addresses[?(@.type=="InternalIP")].address}')

  echo "$tx_pod_full_name"
  echo "$rx_pod_full_name"
  echo "$tx_node_name"
  echo "$rx_node_name"
}


regenerate_monitor=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -a|--airgap-server)
            AIGRAP_SERVER="$2"
            shift 2
            ;;
        -c|--cpu)
            CPU="$2"
            shift 2
            ;;
        -m|--memory)
            MEMORY="$2"
            shift 2
            ;;
        -d|--num-dpdk)
            NUM_DPDK="$2"
            shift 2
            ;;
        -v|--num-vf)
            NUM_VF="$2"
            shift 2
            ;;
        -s|--storage-size)
            STORAGE_SIZE="$2"
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

# Determine the image path
if [ -n "$AIGRAP_SERVER" ]; then
  IMAGE_PATH="${AIGRAP_SERVER}/library/spyroot/${IMAGE}:latest"
else
  IMAGE_PATH="${IMAGE}"
fi

# Generate Kubernetes YAML deployment file
cat > k8s_deployment_spec.yaml <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: output.pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: ${STORAGE_SIZE}Gi
  storageClassName: ${STORAGE_CLASS}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${POD_NAME}
  labels:
    environment: dpdk.tester
    app: mus.toolkit
spec:
  replicas: 1
  selector:
    matchLabels:
      environment: dpdk.tester
      app: ${POD_NAME}
  template:
    metadata:
      labels:
        environment: dpdk.tester
        app: ${POD_NAME}
    spec:
      containers:
      - name: ${POD_NAME}
        command: ["/bin/bash", "-c", "PID=; trap 'kill \$PID' TERM INT; sleep infinity & PID=\$!; wait \$PID"]
        image: "${IMAGE_PATH}"
        securityContext:
          capabilities:
            add: ["IPC_LOCK", "NET_ADMIN", "SYS_TIME", "CAP_NET_RAW", "CAP_BPF", "CAP_SYS_ADMIN", "SYS_ADMIN"]
          privileged: true
        env:
          - name: PATH
            value: "/bin:/sbin:/usr/bin:/usr/sbin:/usr/bin:/usr/local/sbin:/usr/local/bin:\$PATH"
        volumeMounts:
        - name: sys
          mountPath: /sys
          readOnly: true
        - name: modules
          mountPath: /lib/modules
          readOnly: true
        - name: output
          mountPath: /output
        - name: kubeconfig
          mountPath: ${KUBECONFIG_PATH}
        resources:
          requests:
            memory: ${MEMORY}Gi
            cpu: "${CPU}"
            intel.com/dpdk: '${NUM_DPDK}'
            intel.com/kernel: '${NUM_VF}'
          limits:
            hugepages-1Gi: ${MEMORY}Gi
            cpu: "${CPU}"
            intel.com/dpdk: '${NUM_DPDK}'
            intel.com/kernel: '${NUM_VF}'
      volumes:
      - name: sys
        hostPath:
          path: /sys
      - name: modules
        hostPath:
          path: /lib/modules
      - name: output
        persistentVolumeClaim:
          claimName: output.pvc
      - name: kubeconfig
        hostPath:
          path: ${KUBECONFIG_PATH}
      nodeSelector:
        kubernetes.io/os: linux
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: sonobuoy-rolebinding
  namespace: default
subjects:
  - kind: ServiceAccount
    name: default
    namespace: default
roleRef:
  kind: Role
  name: admin
  apiGroup: rbac.authorization.k8s.io
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: sonobuoy-clusterrolebinding
subjects:
  - kind: ServiceAccount
    name: default
    namespace: default
roleRef:
  kind: ClusterRole
  name: cluster-admin
  apiGroup: rbac.authorization.k8s.io
EOF

echo "Kubernetes deployment YAML has been generated: k8s_deployment_spec.yaml"
echo "Using image: ${IMAGE_PATH}"
echo "CPU: ${CPU}, Memory: ${MEMORY}Gi, DPDK: ${NUM_DPDK}, VF: ${NUM_VF}, Storage: ${STORAGE_SIZE}Gi"
