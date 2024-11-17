DOCKER_LOCAL_VOL_IMAGE="gcr.io/k8s-staging-sig-storage/local-volume-node-cleanup:canary"
DOCKER_LOLCA_VOL_PROVISIONER="registry.k8s.io/sig-storage/local-volume-provisioner:v2.7.0"

AIRGAP_SERVER="192.168.41.5:8043"
REMOTE_DIR="/photon-reps/images"
REMOTE_AIRGAP="192.168.41.5"
REMOTE_USERNAME="admin"

TRAMPOLINE_IP="10.204.11.145"
TRAMPOLINE_USERNAME="vm-mustafa"

AIRGAP_USERNAME="your_airgap_username"
AIRGAP_PASSWORD="your_airgap_password"

docker pull --platform linux/amd64 ${DOCKER_LOCAL_VOL_IMAGE}
docker pull --platform linux/amd64 ${DOCKER_LOLCA_VOL_PROVISIONER}

docker save --output /tmp/local-volume-node-cleanup.tar ${DOCKER_LOCAL_VOL_IMAGE}
docker save --output /tmp/local-volume-provisioner.tar ${DOCKER_LOCAL_VOL_PROVISIONER}

gzip /tmp/local-volume-node-cleanup.tar
gzip /tmp/local-volume-provisioner.tar

scp -J ${TRAMPOLINE_USERNAME}@${TRAMPOLINE_IP} /tmp/local-volume-node-cleanup.tar.gz ${REMOTE_USERNAME}@${REMOTE_AIRGAP}:${REMOTE_DIR}
scp -J ${TRAMPOLINE_USERNAME}@${TRAMPOLINE_IP} /tmp/local-volume-provisioner.tar.gz ${REMOTE_USERNAME}@${REMOTE_AIRGAP}:${REMOTE_DIR}

ssh -J ${TRAMPOLINE_USERNAME}@${TRAMPOLINE_IP} ${REMOTE_USERNAME}@${REMOTE_AIRGAP} <<EOF
  sudo docker login ${AIRGAP_SERVER} -u ${AIRGAP_USERNAME} -p ${AIRGAP_PASSWORD}
  sudo docker tag ${DOCKER_LOCAL_VOL_IMAGE} ${AIRGAP_SERVER}/library/local-volume-node-cleanup:canary
  sudo docker tag ${DOCKER_LOCAL_VOL_PROVISIONER} ${AIRGAP_SERVER}/library/local-volume-provisioner:v2.7.0
EOF


ssh -J ${TRAMPOLINE_USERNAME}@${TRAMPOLINE_IP} ${REMOTE_USERNAME}@${REMOTE_AIRGAP} <<EOF
  sudo docker push ${AIRGAP_SERVER}/library/local-volume-node-cleanup:canary
  sudo docker push ${AIRGAP_SERVER}/library/local-volume-provisioner:v2.7.0
EOF
