#!/usr/bin/env bash
# This script designed to pull all sonobuoy dependencies to local docker
# Optional re-point all image to customer aigrap server
# install aigrap server
# push to aigrap server

# Example of usage
#   --install-airgap will install harbor , disable ssl , set ip address based on default route
#   it resolve via ip route 0.0.0.0 take interface name and resolve IP and use in Harbor

# This script pulls all Sonobuoy dependencies to the local Docker instance.
# It can also:
#   - Re-point all images to a custom airgap registry.
#   - Install an airgap registry (Harbor).
#   - Push Sonobuoy images to an airgap registry.

# Usage:
#   --install-airgap  -> Installs Harbor, disables SSL, and sets its IP based on the default route.
#   --pull <server>   -> Pulls images, rewrites them for an airgap registry, and pushes them.
#   --push           -> Pushes all locally available Sonobuoy images to the airgap registry.


# Example of usage
#   --install-airgap will install harbor , disable ssl , set ip address based on default route
#   it resolves via ip route 0.0.0.0 take interface name and resolve IP and use in Harbor

# Author Mus @ broadcom

set -euo pipefail

# Harbor version
HARBOR_VERSION="v2.12.2"
HARBOR_URL="https://github.com/goharbor/harbor/releases/download/${HARBOR_VERSION}/harbor-online-installer-${HARBOR_VERSION}.tgz"
HARBOR_PROJECT="library"
KUBE_VERSION="v1.30.2"
KUBECONFIG_PATH="$HOME/.kube/config"

# Default airgap registry (set when --airgap <server> is used)
AIRGAP_SERVER=""
USE_AIRGAP_CONFIG=false

HARBOR_USER="${HARBOR_USER:-admin}"
HARBOR_PASSWORD="${HARBOR_PASSWORD:-Harbor12345}"

# Function to get the default network interface
function get_default_interface() {
    ip route | grep '^default' | awk '{print $5}' | head -n 1
}

function check_kubeconfig() {
    if [[ ! -f "$KUBECONFIG_PATH" ]]; then
        echo "❌ Error: Kubernetes config file not found at $KUBECONFIG_PATH!"
        echo "🔹 Please set the correct KUBECONFIG environment variable or ensure the file exists."
        exit 1
    fi
}

function get_sonobuoy_registries() {
    echo "==> Retrieving registry prefixes from Sonobuoy config..."
    sonobuoy gen default-image-config | awk -F': ' '{print $2}' | cut -d'/' -f1 | sort -u
}

# Function to get the IP address of the default interface
function get_default_ip() {
    local interface
    interface=$(get_default_interface)

    if [[ -z "$interface" ]]; then
        echo "❌ Error: Unable to determine the default network interface!"
        exit 1
    fi

    ip -4 addr show "$interface" | grep "inet " | awk '{print $2}' | cut -d'/' -f1
}

HARBOR_IP=$(get_default_ip)
HARBOR_REGISTRY="${HARBOR_IP}/${HARBOR_PROJECT}"

echo "==> 🚀 Using Harbor registry: ${HARBOR_REGISTRY}"

function harbor_login() {
    echo "🔑 Logging into Harbor using HTTP..."
    echo "${HARBOR_PASSWORD}" | docker login "http://${HARBOR_IP}" -u "${HARBOR_USER}" --password-stdin
}


function push_images_to_harbor() {
    echo "📦 Retrieving Sonobuoy image list..."

    # Ensure the command runs without errors
    SONOBUOY_IMAGES=$(sonobuoy images list --kubernetes-version $KUBE_VERSION 2>/dev/null | awk '{print $NF}')

    if [[ -z "$SONOBUOY_IMAGES" ]]; then
        echo "❌ Error: Could not retrieve Sonobuoy images!"
        exit 1
    fi

    echo "==> Found Sonobuoy images to push:"
    echo "$SONOBUOY_IMAGES"

    for IMAGE in ${SONOBUOY_IMAGES}; do
        if [[ -z "$(docker images -q "$IMAGE" 2>/dev/null)" ]]; then
            echo "⚠️ Skipping $IMAGE (Not found locally)"
            continue
        fi

        IMAGE_NAME=$(echo "$IMAGE" | cut -d'/' -f2- | cut -d':' -f1)
        IMAGE_TAG=$(echo "$IMAGE" | cut -d':' -f2)

        NEW_IMAGE="${HARBOR_IP}/${HARBOR_PROJECT}/${IMAGE_NAME}:${IMAGE_TAG}"

        echo "🔄 Retagging: ${IMAGE} -> ${NEW_IMAGE}"
        docker tag "${IMAGE}" "${NEW_IMAGE}"
        echo "📤 Pushing ${NEW_IMAGE} to Harbor..."
        docker push "${NEW_IMAGE}"
    done

    echo "✅ All available Sonobuoy images pushed to Harbor successfully!"
}

function usage() {
    echo -e "\n🔹 **Usage:**"
    echo -e "  $0 [OPTIONS]\n"
    echo "📌 Options:"
    echo "  --install-airgap       🏗️  Install Harbor for air-gapped environments."
    echo "  --pull <server>        📥  Pull Sonobuoy images and push them to an airgap registry."
    echo "  --push                 📤  Push Sonobuoy images to Harbor."
    echo "  --run [airgap_ip]      🚀  Run Sonobuoy, optionally using an airgap registry."
    echo "  --check <airgap_ip>    🔍  Verify required images exist in the airgap registry."
    echo "  -h, --help             ℹ️   Show this help message."

    echo -e "\n🔹 **Environment Variables:**"
    echo "  HARBOR_USER            Username for Harbor login (default: admin)"
    echo "  HARBOR_PASSWORD        Password for Harbor login (default: Harbor12345)"
    exit 1
}


function configure_docker_insecure_registry() {
    echo "🔍 Checking Docker insecure registry configuration..."

    # Check if the Harbor IP is already in Docker's insecure registries
    if docker info | grep -q "Insecure Registries:.*${HARBOR_IP}"; then
        echo "✅ Harbor IP ${HARBOR_IP} is already in Docker's insecure registries."
        return
    fi

    echo "⚠️ Harbor IP ${HARBOR_IP} is NOT in Docker's insecure registries. Adding it now..."
    sudo mkdir -p /etc/docker
    sudo tee /etc/docker/daemon.json > /dev/null <<EOF
{
  "insecure-registries": ["${HARBOR_IP}"]
}
EOF

    echo "==> Restarting Docker to apply changes..."
#    sudo systemctl restart docker
    echo "✅ Docker is now configured to allow insecure registry at ${HARBOR_IP}."
}


# Install Harbor for airgap
function install_harbor() {
    echo "📥 Downloading Harbor installer..."
    curl -L -o "harbor-installer.tgz" "${HARBOR_URL}"

    echo "📂 Extracting Harbor installer..."
    tar -xzf harbor-installer.tgz
    cd harbor || exit 1

    echo "🛠️  Generating default configuration..."
    cp harbor.yml.tmpl harbor.yml

    HARBOR_IP=$(get_default_ip)
    if [[ -z "$HARBOR_IP" ]]; then
        echo "❌ Error: Unable to determine IP address for the default network interface!"
        exit 1
    fi

    echo "🌐 Detected default network interface: $(get_default_interface)"
    echo "🔧 Setting Harbor hostname to: ${HARBOR_IP}"

    # we use IP that we resolved from ip route , etc and disable ssl
    sed -i "s/^hostname: .*/hostname: ${HARBOR_IP}/" harbor.yml

    sed -i "s/^  port: 443/#  port: 443/" harbor.yml  # Comment out HTTPS port
    sed -i "s|^  certificate:.*|#  certificate: /your/certificate/path|" harbor.yml
    sed -i "s|^  private_key:.*|#  private_key: /your/private/key/path|" harbor.yml
    sed -i "s/^https: .*/https: false/" harbor.yml
    sed -i "s/^  port: 80/  port: 80/" harbor.yml
    sed -i "s/^  enabled: true/  enabled: false/" harbor.yml

    echo "🚀 Running Harbor installation..."
    sudo ./install.sh

    echo "✅ Harbor installed successfully!"
    cd ..
}

# Pull Sonobuoy images and rewrite domains for airgap
function pull_images() {
    echo "📥 Generating modified default-image-config..."
    DEFAULT_CONFIG=$(sonobuoy gen default-image-config)

    MODIFIED_CONFIG=""
    while IFS= read -r line; do
        if [[ -n "$line" ]]; then
            # Extract domain (before first /)
            domain=$(echo "$line" | cut -d':' -f2 | cut -d'/' -f1)

            if [[ -n "$domain" ]]; then
                # Replace original domain with airgap registry
                replaced_line=$(echo "$line" | sed "s#$domain#$AIRGAP_SERVER#g")
                MODIFIED_CONFIG="$MODIFIED_CONFIG$replaced_line\n"
            else
                MODIFIED_CONFIG="$MODIFIED_CONFIG$line\n"
            fi
        else
            MODIFIED_CONFIG="$MODIFIED_CONFIG\n"
        fi
    done <<< "$DEFAULT_CONFIG"

    echo -e "$MODIFIED_CONFIG" > modified-image-config.yaml
    echo "==> Modified image configuration saved to modified-image-config.yaml"

    echo "==> Retrieving Sonobuoy images..."
    IMAGES=$(sonobuoy images download --kubernetes-version $KUBE_VERSION | tail -n 1)

    if [[ -z "${IMAGES}" ]]; then
        echo "Error: Could not retrieve images from Sonobuoy!"
        exit 1
    fi

    echo "==> Pulling Sonobuoy images..."
    for IMAGE in ${IMAGES}; do
        DOMAIN=$(echo "$IMAGE" | cut -d'/' -f1)
        NEW_IMAGE="${IMAGE/$DOMAIN/$AIRGAP_SERVER}"

        echo "==> Pulling ${IMAGE}..."
        docker pull "${IMAGE}"

        echo "==> Retagging ${IMAGE} -> ${NEW_IMAGE}"
        docker tag "${IMAGE}" "${NEW_IMAGE}"

        echo "==> Pushing ${NEW_IMAGE} to airgap server..."
        docker push "${NEW_IMAGE}"
    done

    echo "✅ Modified image configuration saved to modified-image-config.yaml"
}

function check_airgap_config() {
    if [[ "$USE_AIRGAP_CONFIG" == true && ! -f "modified-image-config.yaml" ]]; then
        echo "❌ Error: Airgap configuration file 'modified-image-config.yaml' is missing!"
        echo "🔹 Please run: ./t.sh --pull <airgap_registry> to generate it."
        exit 1
    fi
}

function check_airgap_images() {
    local AIRGAP_IP="$1"
    local HARBOR_USER="admin"
    local HARBOR_PASSWORD="Harbor12345"

    echo "🔍 Checking required images in airgap registry: $AIRGAP_IP"

    local images=(
        "library/conformance"
        "library/sonobuoy"
        "library/systemd-logs"
    )

    for image in "${images[@]}"; do
        echo "🔎 Checking ${AIRGAP_IP}/v2/${image}/tags/list..."

        RESPONSE=$(curl -s -u "${HARBOR_USER}:${HARBOR_PASSWORD}" \
            -H "Accept: application/json" \
            "http://${AIRGAP_IP}/v2/${image}/tags/list")

        if echo "$RESPONSE" | grep -q "errors"; then
            echo "❌ Error: Image '${image}' is missing in airgap registry!"
            echo "🔹 Please ensure you have pushed the required images using:"
            echo "   ./t.sh --pull $AIRGAP_IP"
            exit 1
        fi
    done

    echo "✅ All required images are available in $AIRGAP_IP"
}


function run_sonobuoy() {
    echo "🚀 Running Sonobuoy..."

    check_kubeconfig
    check_airgap_config

    if [[ "$USE_AIRGAP_CONFIG" == true ]]; then
        sonobuoy run --kubernetes-version $KUBE_VERSION  --kubeconfig="$KUBECONFIG_PATH" \
            --kube-conformance-image "${AIGRAP_SERVER}/library/conformance:v1.30.2" \
            --plugin-image systemd-logs:"${AIGRAP_SERVER}/library/systemd-logs:latest" \
            --e2e-repo-config modified-image-config.yaml \
            --mode non-disruptive-conformance \
            --image-pull-policy IfNotPresent
    else
        sonobuoy run --kubernetes-version $KUBE_VERSION --kubeconfig="$KUBECONFIG_PATH" \
            --mode non-disruptive-conformance \
            --kubernetes-version "$KUBE_VERSION"
    fi

    echo "✅ Sonobuoy started successfully."
}

if [[ $# -eq 0 ]]; then
    usage
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        --pull)
            if [[ $# -lt 2 ]]; then
                echo "Error: Missing registry argument for --airgap"
                usage
            fi
            AIRGAP_SERVER="$2"
            shift 2
            pull_images
            ;;
        --install-airgap)
            install_harbor
            exit 0
            ;;
        --push)
            configure_docker_insecure_registry
            harbor_login
            push_images_to_harbor
            exit 0
            ;;
          --check)
            if [[ $# -lt 2 ]]; then
                echo "❌ Error: Missing airgap IP for --check"
                usage
            fi
            AIRGAP_SERVER="$2"
            shift 2
            harbor_login
            check_airgap_images "$AIRGAP_SERVER"
            exit 0
            ;;
          --run)
            shift
            if [[ $# -gt 0 ]]; then
                AIRGAP_SERVER="$1"
                USE_AIRGAP_CONFIG=true
                generate_airgap_config
                shift
            fi
            run_sonobuoy
            exit 0 ;;

        -h|--help)
            usage
            ;;
        *)
             echo "❌ Error: Unknown option '$1'"; usage ;;
    esac
done

