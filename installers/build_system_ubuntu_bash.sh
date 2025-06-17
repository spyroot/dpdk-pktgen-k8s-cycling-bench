#!/bin/bash
set -e

echo "Supported AVX"

lscpu | grep -o 'avx[^ ]*'

echo "🔐 Checking and installing Intel GPG key..."
GPG_FILE="/etc/apt/trusted.gpg.d/intel.gpg"
KEY_ID="BAC6F0C353D04109"

if ! gpg --list-keys "$KEY_ID" &>/dev/null; then
    echo "📥 Importing Intel GPG key..."
    gpg --keyserver keyserver.ubuntu.com --recv-keys "$KEY_ID"
    gpg --export "$KEY_ID" | sudo gpg --dearmor -o "$GPG_FILE"
else
    echo "✅ Intel GPG key already exists."
fi

echo "📜 Checking Intel APT source list..."
INTEL_LIST="/etc/apt/sources.list.d/intel-oneapi.list"
INTEL_REPO="deb https://apt.repos.intel.com/oneapi all main"

if ! grep -Fxq "$INTEL_REPO" "$INTEL_LIST" 2>/dev/null; then
    echo "📥 Adding Intel repository to APT sources."
    echo "$INTEL_REPO" | sudo tee "$INTEL_LIST"
else
    echo "✅ Intel repository already present."
fi

echo "🔧 Updating system..."
sudo apt-get update -y
sudo apt-get upgrade -y

echo "📦 Installing core build tools and compilers..."
sudo apt-get install -y \
    build-essential \
    gcc \
    g++ \
    clang \
    llvm \
    cmake \
    make \
    meson \
    ninja-build \
    git \
    curl \
    wget \
    unzip \
    python3 \
    python3-pip \
    python3-venv \
    golang-go \
    pkg-config \
    libtool \
    valgrind \
    autoconf \
    automake \
    nasm \
    cpuid

echo "📚 Installing C/C++ libraries and headers..."
sudo apt-get install -y \
    libnuma-dev \
    libpcap-dev \
    libelf-dev \
    libfdt-dev \
    libssl-dev \
    zlib1g-dev \
    libibverbs-dev \
    rdma-core \
    libibverbs-dev \
    libibverbs-dev \
    libmlx5-1 \
    libmnl-dev \
    libjansson-dev \
    libnl-3-dev \
    libnl-route-3-dev \
    libconfig-dev \
    libcap-dev \
    libhugetlbfs-dev \
    libdpdk-dev

echo "🧠 Installing DPDK dependencies..."
sudo apt-get install -y \
    linux-headers-$(uname -r) \
    linux-image-$(uname -r) \
    linux-modules-extra-$(uname -r) \
    linux-tools-common \
    linux-tools-generic \
    linux-tools-$(uname -r)

echo "🧱 Setting up hugepages..."
echo "vm.nr_hugepages=1024" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p

sudo apt-get install -y \
  intel-oneapi-compiler-dpcpp-cpp \
  intel-oneapi-runtime-compilers \
  intel-oneapi-compiler-fortran \
  intel-oneapi-runtime-compilers


#echo "🔬 Installing Intel oneAPI compiler (ICX)..."
#ARCH=$(uname -m)
#if [[ "$ARCH" == "x86_64" ]]; then
#    wget https://registrationcenter-download.intel.com/akdlm/IRC_NAS/tec/19104/l_dpcpp-cpp-compiler_p_2024.0.0.49575_offline.sh -O intel_icx.sh
#    chmod +x intel_icx.sh
#    sudo ./intel_icx.sh -a --silent --eula accept
#    echo '✅ Intel compiler installed. You may need to source the env from /opt/intel/oneapi/setvars.sh'
#else
#    echo "⚠️ Skipping Intel compiler: unsupported architecture ($ARCH)"
#fi

echo "🧪 Optional tools (for debugging, benchmarking)..."
sudo apt-get install -y \
    linuxptp \
    ethtool \
    tcpdump \
    iproute2 \
    sysstat \
    net-tools \
    lsof \
    htop \
    numactl

echo "✅ All tools and dependencies installed for DPDK development."

echo "🛡️ Installing Intel IPSec Multi-Buffer Library (intel-ipsec-mb)..."

IPSEC_DIR="/opt/intel-ipsec-mb"
if [ ! -d "$IPSEC_DIR" ]; then
    sudo git clone https://github.com/intel/intel-ipsec-mb.git "$IPSEC_DIR"
    cd "$IPSEC_DIR"
    sudo make -j"$(nproc)"
    sudo make install
    sudo ldconfig
    echo "✅ Intel IPSec MB installed successfully."
else
    echo "ℹ️ Intel IPSec MB already cloned at $IPSEC_DIR — skipping rebuild."
fi
