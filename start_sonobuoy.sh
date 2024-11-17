#!/bin/bash

# Check if an Airgap server address is provided
if [ -z "$1" ]; then
  echo "Usage: $0 <airgap_server_url>"
  exit 1
fi

AIGRAP_SERVER=$1
KUBECONFIG_PATH="${2:-/home/capv/.kube/config}"

# Generate the custom-repos.yaml file
echo "Generating custom-repos.yaml..."

cat > /root/custom-repos.yaml <<EOF
dockerLibraryRegistry: "${AIGRAP_SERVER}/library/sonobuoy"
e2eRegistry: "${AIGRAP_SERVER}/library/sonobuoy"
gcRegistry: "${AIGRAP_SERVER}/library/sonobuoy"
gcEtcdRegistry: "${AIGRAP_SERVER}/library"
privateRegistry: "${AIGRAP_SERVER}/library"
sampleRegistry: "${AIGRAP_SERVER}/library"
promoterE2eRegistry: "${AIGRAP_SERVER}/library/e2e-test-images"
buildImageRegistry: "${AIGRAP_SERVER}/library/build-image"
sigStorageRegistry: "${AIGRAP_SERVER}/library/sig-storage"
EOF

echo "custom-repos.yaml generated successfully."

echo "Running Sonobuoy..."

sonobuoy run --kubeconfig="$KUBECONFIG_PATH" \
  --sonobuoy-image "${AIGRAP_SERVER}/library/sonobuoy:latest" \
  --kube-conformance-image "${AIGRAP_SERVER}/library/conformance:v1.30.2" \
  --plugin-image systemd-logs:"${AIGRAP_SERVER}/library/sonobuoy/systemd-logs:latest" \
  --e2e-repo-config /root/custom-repos.yaml \
  --mode non-disruptive-conformance \
  --image-pull-policy IfNotPresent

echo "Sonobuoy started successfully."
