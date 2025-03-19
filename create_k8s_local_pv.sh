#!/bin/bash
# Local PV generator  Utility.
#
# It create bunch of local pv based.
#
# it expect symmetrical struct ona ll worker node
# i.e two worker node same disk.

# Example new  disk.
# fdisk create portion
# sudo fdisk /dev/sdb
# sudo mkfs.ext4 /dev/sdb1

# mount use blkid to get PARTUUID
# PARTUUID=793c8730-1681-47cb-9074-9969bd0602ea	/mnt/local-storage	ext4	defaults,noatime,data=writeback	1	2

# mount
# sudo mkdir -p /mnt/local-storage/pvc1
# sudo mkdir -p /mnt/local-storage/pvc2
# sudo mkdir -p /mnt/local-storage/pvcN
#
# Mus spyroot@gmail.com

STORAGE_CLASS="fast-disks"
CAPACITY="50Gi"
ACCESS_MODES="ReadWriteOnce"
VOLUME_MODE="Filesystem"
RECLAIM_POLICY="Delete"
BASE_PATH="/mnt/local-storage"
NUM_PVS=6


function create_storage_class() {
  if ! kubectl get storageclass "$STORAGE_CLASS" &>/dev/null; then
    echo "Creating StorageClass '$STORAGE_CLASS'..."
    cat <<EOF | kubectl apply -f -
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: $STORAGE_CLASS
  annotations:
    storageclass.kubernetes.io/is-default-class: "true"
provisioner: kubernetes.io/no-provisioner
volumeBindingMode: WaitForFirstConsumer
reclaimPolicy: $RECLAIM_POLICY
allowVolumeExpansion: false
EOF
    echo "StorageClass '$STORAGE_CLASS' created."
  else
    echo "StorageClass '$STORAGE_CLASS' already exists. Skipping creation."
  fi
}


NODES=$(kubectl get nodes --selector='!node-role.kubernetes.io/control-plane,!node-role.kubernetes.io/master' -o jsonpath='{.items[*].metadata.name}')

for NODE in $NODES; do
  for i in $(seq 1 $NUM_PVS); do
    PV_NAME="local-pv-${NODE}-${i}"
    LOCAL_PATH="${BASE_PATH}/pv${i}"

    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: PersistentVolume
metadata:
  name: $PV_NAME
spec:
  capacity:
    storage: $CAPACITY
  accessModes:
    - $ACCESS_MODES
  persistentVolumeReclaimPolicy: $RECLAIM_POLICY
  storageClassName: $STORAGE_CLASS
  volumeMode: $VOLUME_MODE
  local:
    path: $LOCAL_PATH
  nodeAffinity:
    required:
      nodeSelectorTerms:
        - matchExpressions:
            - key: kubernetes.io/hostname
              operator: In
              values:
                - $NODE
EOF

  done
done

