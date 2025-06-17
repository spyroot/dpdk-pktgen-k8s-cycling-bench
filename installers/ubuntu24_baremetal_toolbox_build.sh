#!/bin/bash
# this will build AND install stress-ng, trafgen and DPDK etc, pkt gen on baremetal
# note you need pull latest driver update and install first
# it will install Mellanox , QAT , marvel all pull mode

set -e

PKTGEN_VERSION=pktgen-23.10.2
DPDK_VERSION=23.11

# for DPDK and deps for Melanox
echo "🔧 Installing DPDK dependencies..."
sudo apt-get install -y libarchive-dev infiniband-diags \
  ibverbs-utils libudev-dev doxygen python3-sphinx libnl-route-3-dev pandoc cython3 libpci-dev > /dev/null 2>&1

sudo apt install -y flex bison libnet-dev libnetfilter-conntrack-dev \
libnl-3-dev libsodium-dev liburcu-dev


echo "🔧 Building libcli..."
git clone https://github.com/dparrish/libcli.git /root/libcli > /dev/null 2>&1 && (
  cd /root/libcli
  make -j$(nproc) > /dev/null 2>&1
  make install > /dev/null 2>&1
)
rm -rf /root/libcli
echo "✅ libcli built and installed successfully."

echo "🔧 Building geoip..."
git clone https://github.com/maxmind/geoip-api-c.git /root/geoip > /dev/null 2>&1 && (
  cd /root/geoip
  ./bootstrap > /dev/null 2>&1
  ./configure > /dev/null 2>&1
  make -j$(nproc) > /dev/null 2>&1
  make install > /dev/null 2>&1
)
rm -rf /root/geoip
echo "✅ geoip built and installed successfully."

echo "🔧 Building netsniff-ng..."
git clone https://github.com/netsniff-ng/netsniff-ng.git /root/netsniff-ng > /dev/null 2>&1 && (
  cd /root/netsniff-ng
  ./configure > /dev/null 2>&1
  make -j$(nproc) > /dev/null 2>&1
  make install > /dev/null 2>&1
)
rm -rf /root/netsniff-ng
echo "✅ netsniff built and installed successfully."

echo "🔧 Building sysbench..."
git clone https://github.com/akopytov/sysbench.git /root/sysbench > /dev/null 2>&1 && (
  cd /root/sysbench
  ./autogen.sh > /dev/null 2>&1
  ./configure --without-mysql > /dev/null 2>&1
  make -j$(nproc) > /dev/null 2>&1
  make install > /dev/null 2>&1
)
rm -rf /root/sysbench
echo "✅ sysbench built and installed successfully."

echo "🔧 Building stress-ng..."
rm -rf /root/stress-ng
git clone https://github.com/ColinIanKing/stress-ng.git /root/stress-ng > /dev/null 2>&1 && (
  cd /root/stress-ng
  sed -i 's/\binit_mb_mgr_avx\b/init_mb_mgr_auto/' stress-ipsec-mb.c
  make -j$(nproc) > /dev/null 2>&1
  make install > /dev/null 2>&1
)
rm -rf /root/stress-ng
echo "✅ stress-ng built and installed successfully."

echo "🔧 Building libmd..."
git clone https://git.hadrons.org/git/libmd.git /root/libmd > /dev/null 2>&1 && (
  cd /root/libmd
  ./autogen > /dev/null 2>&1
  ./configure > /dev/null 2>&1
  make -j$(nproc) > /dev/null 2>&1
  make install > /dev/null 2>&1
)
rm -rf /root/libmd
echo "✅ libmd built and installed successfully."

echo "🔧 Building libbsd..."
git clone https://gitlab.freedesktop.org/libbsd/libbsd.git /root/libbsd > /dev/null 2>&1 && (
  cd /root/libbsd
  ./autogen > /dev/null 2>&1
  ./configure > /dev/null 2>&1
  make -j$(nproc) > /dev/null 2>&1
  make install > /dev/null 2>&1
)
rm -rf /root/libbsd
echo "✅ libbsd built and installed successfully."

echo "🔧 Building rdma-core..."
rm -rf /root/rdma-core
git clone https://github.com/linux-rdma/rdma-core.git /root/rdma-core > /dev/null 2>&1
mkdir -p /root/rdma-core/build
cd /root/rdma-core/build
cmake -DCMAKE_INSTALL_PREFIX=/usr -GNinja .. > /dev/null 2>&1
ninja -j"$(nproc)" > /dev/null 2>&1
sudo ninja install > /dev/null 2>&1
sudo ldconfig
echo "✅ rdma-core built and installed successfully."

echo "🔧 Building ndk-sw..."
cd /root/build
git clone https://github.com/CESNET/ndk-sw.git > /dev/null 2>&1
cd ndk-sw
sudo ./build.sh --bootstrap > /dev/null 2>&1
./build.sh --prepare > /dev/null 2>&1
./build.sh --make > /dev/null 2>&1
(cd drivers && ./configure > /dev/null 2>&1 && make -j"$(nproc)" > /dev/null 2>&1)
sudo ldconfig
echo "✅ ndk-sw built and installed successfully."

echo "🔧 Building libwd..."
cd /root/build && git clone https://gitee.com/src-openeuler/libwd.git > /dev/null 2>&1
cd libwd && tar xf libwd-2.6.0.tar.gz -C /root/build
cd /root/build/libwd-*
./autogen.sh > /dev/null 2>&1
./configure > /dev/null 2>&1
make -j"$(nproc)" > /dev/null 2>&1
sudo make install > /dev/null 2>&1
sudo ldconfig
echo "✅ libwd built and installed successfully."

echo "🔧 Installing Python pyelftools..."
sudo apt install -y python3-pyelftools > /dev/null 2>&1

mkdir -p /root/build
cd /root/build
wget http://fast.dpdk.org/rel/dpdk-${DPDK_VERSION}.tar.xz > /dev/null 2>&1
tar xf dpdk-${DPDK_VERSION}.tar.xz
cd dpdk-${DPDK_VERSION}
rm -rf build
meson -Dexamples=all build > /dev/null 2>&1
ninja -C build -j"$(nproc)" > /dev/null 2>&1
cd build
ninja install > /dev/null 2>&1
ldconfig
echo "✅ DPDK built and installed successfully."

echo "🔧 Building Pktgen-DPDK..."
git clone https://github.com/pktgen/Pktgen-DPDK.git /root/Pktgen-DPDK > /dev/null 2>&1 && (
  cd /root/Pktgen-DPDK
  git checkout ${PKTGEN_VERSION} > /dev/null 2>&1
  ./tools/pktgen-build.sh build > /dev/null 2>&1
  ninja -C /root/Pktgen-DPDK/Builddir install > /dev/null 2>&1
)
rm -rf /root/Pktgen-DPDK
echo "✅ PKT-GEN built and installed successfully."