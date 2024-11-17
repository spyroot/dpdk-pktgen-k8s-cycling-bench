#!/bin/bash

if [ -z "$1" ]; then
  echo "Usage: $0 <airgap_server_url>"
  exit 1
fi

AIGRAP_SERVER=$1
KUBECONFIG_PATH=${KUBECONFIG:-"/home/capv/.kube"}
STORAGE_CLASS="local_storage"
CPU="2"
MEMORY="2"
NUM_DPDK=2
NUM_VF=2
STORAGE_SIZE=50
POD_NAME="mus_toolking"

cat > k8s_deployment_spec.yaml <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: output-pvc
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
    environment: dpdk-tester
    app: mus-toolkit
spec:
  replicas: 1
  selector:
    matchLabels:
      environment: dpdk-tester
      app: ${POD_NAME}
  template:
    metadata:
      labels:
        environment: dpdk-tester
        app: ${POD_NAME}
    spec:
      containers:
      - name: ${POD_NAME}
        command: ["/bin/bash", "-c", "PID=; trap 'kill \$PID' TERM INT; sleep infinity & PID=\$!; wait \$PID"]
        image: "${AIGRAP_SERVER}/library/spyroot/dpdk-pktgen-k8s-cycling-bench:latest"
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
          claimName: output-pvc
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

echo "Simplified Kubernetes YAML spec has been generated in k8s_deployment_spec.yaml."
