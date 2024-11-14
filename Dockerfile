# Author: Mustafa Byaramov
# Description: This Dockerfile builds an environment with tools like Pktgen-DPDK, Kubernetes, Helm,
# Sonobuoy, and other performance testing utilities.
# Version: 1.0
# docker build -t dpdk-pktgen-k8s-cycling-bench .
# docker run --privileged -it dpdk-pktgen-k8s-cycling-bench /bin/bash

# Testing Tools Included in This Dockerfile:
#
# 1. **Networking Tools**:
#    - **Netsniff-ng**: Network analyzer and packet capture.
#    - **Pktgen-DPDK**: High-performance packet generator for DPDK.
#    - **libnet**: Library for crafting network packets.
#
# 2. **System Benchmarking Tools**:
#    - **Sysbench**: CPU, memory, and I/O performance benchmarking.
#    - **Stress-ng**: Stress testing of system resources.
#    - **unixbench**: General system performance benchmarking.
#    - **fio**: Flexible I/O performance testing tool.
#    - **Intel MLC**: Memory latency and bandwidth testing.
#
# 3. **Security & Vulnerability Testing**:
#    - **Kube-bench**: Kubernetes best practices security check.
#    - **Trivy**: Container vulnerability scanning tool.
#    - **litmuschaos**: Chaos engineering tool for Kubernetes resilience testing.
#
# 4. **Kubernetes & Helm Tools**:
#    - **Helm**: Kubernetes package manager.
#    - **Sonobuoy**: Kubernetes cluster diagnostic and testing tool.
#    - **Kubernetes (kubemark)**: Tool to simulate large-scale Kubernetes clusters for performance testing.
#
# 5. **Development Tools**:
#    - **Vim**: Text editor with various plugins for development.
#    - **fzf**: Fuzzy finder to improve navigation in shell scripts.
#    - **YouCompleteMe**: Vim plugin for code completion.
#    - **yamlfmt**: YAML file formatting tool.
#    - **jq**: Command-line tool for processing JSON data.
#    - **yamllint**: YAML file linter.
#    - **gitlab_lint**: GitLab CI configuration linter.
#
# 6. **Miscellaneous**:
#    - **libcli**: Command-line interface library.
#    - **GeoIP**: Tool for geolocation testing of IP addresses.
#    - **Miniconda**: Lightweight Python environment management tool.
#


# DPKD Details for a build based on  spyroot/pktgen_toolbox_generic:latest
#
# Note all PMDs are enabeld. Including Crypto
#
  #
  ## =================
  ## Applications Enabled
  ## =================
  #
  ## apps:
  ## 	dumpcap, graph, pdump, proc-info, test-acl, test-bbdev, test-cmdline, test-compress-perf,
  ## 	test-crypto-perf, test-dma-perf, test-eventdev, test-fib, test-flow-perf, test-gpudev,
  ##   test-mldev, test-pipeline,
  ## 	test-pmd, test-regex, test-sad, test-security-perf, test,
  #
  ## Message:
  ## =================
  ## Libraries Enabled
  ## =================
  #
  ## libs:
  ## 	log, kvargs, telemetry, eal, ring, rcu, mempool, mbuf,
  ## 	net, meter, ethdev, pci, cmdline, metrics, hash, timer,
  ## 	acl, bbdev, bitratestats, bpf, cfgfile, compressdev, cryptodev, distributor,
  ## 	dmadev, efd, eventdev, dispatcher, gpudev, gro, gso, ip_frag,
  ## 	jobstats, latencystats, lpm, member, pcapng, power, rawdev, regexdev,
  ## 	mldev, rib, reorder, sched, security, stack, vhost, ipsec,
  ## 	pdcp, fib, port, pdump, table, pipeline, graph, node,
  #
  #
  ## Message:
  ## ===============
  ## Drivers Enabled
  ## ===============
  #
  ## common:
  ## 	cpt, dpaax, iavf, idpf, octeontx, cnxk, mlx5, nfp,
  ## 	qat, sfc_efx,
  ## bus:
  ## 	auxiliary, cdx, dpaa, fslmc, ifpga, pci, platform, vdev,
  ## 	vmbus,
  ## mempool:
  ## 	bucket, cnxk, dpaa, dpaa2, octeontx, ring, stack,
  ## dma:
  ## 	cnxk, dpaa, dpaa2, hisilicon, idxd, ioat, skeleton,
  ## net:
  ## 	af_packet, af_xdp, ark, atlantic, avp, axgbe, bnx2x, bnxt,
  ## 	bond, cnxk, cpfl, cxgbe, dpaa, dpaa2, e1000, ena,
  ## 	enetc, enetfec, enic, failsafe, fm10k, gve, hinic, hns3,
  ## 	i40e, iavf, ice, idpf, igc, ionic, ipn3ke, ixgbe,
  ## 	memif, mlx4, mlx5, netvsc, nfp, ngbe, null, octeontx,
  ## 	octeon_ep, pcap, pfe, qede, ring, sfc, softnic, tap,
  ## 	thunderx, txgbe, vdev_netvsc, vhost, virtio, vmxnet3,
  ## raw:
  ## 	cnxk_bphy, cnxk_gpio, dpaa2_cmdif, ifpga, ntb, skeleton,
  ## crypto:
  ## 	bcmfs, caam_jr, ccp, cnxk, dpaa_sec, dpaa2_sec, ipsec_mb, mlx5,
  ## 	nitrox, null, octeontx, openssl, scheduler, virtio,
  ## compress:
  ## 	isal, mlx5, octeontx, zlib,
  ## regex:
  ## 	mlx5, cn9k,
  ## ml:
  ## 	cnxk,
  ## vdpa:
  ## 	ifc, mlx5, nfp, sfc,
  ## event:
  ## 	cnxk, dlb2, dpaa, dpaa2, dsw, opdl, skeleton, sw,
  ## 	octeontx,
  ## baseband:
  ## 	acc, fpga_5gnr_fec, fpga_lte_fec, la12xx, null, turbo_sw,
  ## gpu:
  #
  #
  ## Message:
  ## =================
  ## Content Skipped
  ## =================
  #
  ## apps:
  #
  ## libs:
  #
  ## drivers:
  ## 	common/mvep:	missing dependency, "libmusdk"
  ## 	net/mana:	missing dependency, "mana"
  ## 	net/mvneta:	missing dependency, "libmusdk"
  ## 	net/mvpp2:	missing dependency, "libmusdk"
  ## 	net/nfb:	missing dependency, "libnfb"
  ## 	crypto/armv8:	missing dependency, "libAArch64crypto"
  ## 	crypto/mvsam:	missing dependency, "libmusdk"
  ## 	crypto/uadk:	missing dependency, "libwd"
  ## 	gpu/cuda:	missing dependency, "cuda.h"
  #
  ## docker buildx --build-arg MESON_ARGS="-Dplatform=native" -t my_image .
  ## docker buildx build --platform linux/amd64 MESON_ARGS="-Dplatform=native" -t cnfdemo.io/spyroot/dpdk_native_tester:latest .
  ## docker buildx build --platform linux/amd64 MESON_ARGS="-Dplatform=generic" -t cnfdemo.io/spyroot/dpdk_generic_tester:latest .

FROM spyroot/pktgen_toolbox_generic:latest
RUN yum update -y && \
    yum install -y gcc make git libpcap-devel

ENV GOMAXPROCS=$(nproc)
ENV GO111MODULE=on
ENV PKTGEN_VERSION=pktgen-23.10.0
ENV KUBERNETES_VERSION=v1.30.0
ENV RT_TESTS_VERSION=stable/v1.0
ENV HELM_VERSION=v3.10.0
ENV KUBE_BENCH_VERSION=0.9.1
ENV TRIVY_VERSION=0.57.0
ENV LITMUSCTL_VERSION=1.11.0

RUN git clone git://git.kernel.org/pub/scm/utils/rt-tests/rt-tests.git /root/rt-tests \
    && cd /root/rt-tests \
    && git checkout "${RT_TESTS_VERSION}" \
    && make all \
    && make install \
    && rm -rf /root/rt-tests

RUN git clone https://github.com/vmware-tanzu/sonobuoy.git /root/sonobuoy
WORKDIR /root/sonobuoy
RUN make build \
    && make golden \
    && make test \
    && cp /root/sonobuoy/sonobuoy /usr/local/bin/sonobuoy \
    && rm -rf /root/sonobuoy

RUN curl https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz -o helm-${HELM_VERSION}-linux-amd64.tar.gz \
    && tar -zxvf helm-${HELM_VERSION}-linux-amd64.tar.gz \
    && mv linux-amd64/helm /usr/local/bin/helm \
    && rm -rf linux-amd64

RUN curl -LO https://github.com/aquasecurity/kube-bench/releases/download/v${KUBE_BENCH_VERSION}/kube-bench_${KUBE_BENCH_VERSION}_linux_amd64.tar.gz \
    && tar -xzvf kube-bench_${KUBE_BENCH_VERSION}_linux_amd64.tar.gz \
    && mv kube-bench /usr/local/bin/ \
    && chmod +x /usr/local/bin/kube-bench \
    && rm -f kube-bench_${KUBE_BENCH_VERSION}_linux_amd64.tar.gz


RUN curl -LO https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz \
    && tar -xzvf trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz \
    && mv trivy /usr/local/bin/ \
    && chmod +x /usr/local/bin/trivy \
    && rm -f trivy_${TRIVY_VERSION}_Linux-64bit.tar.gz

RUN curl -LO https://github.com/litmuschaos/litmus/releases/download/v${LITMUSCTL_VERSION}/litmusctl-linux-amd64 \
    && mv litmusctl-linux-amd64 /usr/local/bin/litmusctl \
    && chmod +x /usr/local/bin/litmusctl \
    && rm -f litmusctl-linux-amd64

RUN git clone https://github.com/dparrish/libcli.git /root/libcli \
    && cd /root/libcli \
    && make -j$(nproc) \
    && make install \
    && rm -rf /root/libcli

RUN git clone https://github.com/maxmind/geoip-api-c.git /root/geoip \
    && cd /root/geoip \
    && ./bootstrap \
    && ./configure \
    && make -j$(nproc) \
    && make install \
    && rm -rf /root/geoip

ENV PKG_CONFIG_PATH=/usr/lib/pkgconfig:/usr/local/lib/pkgconfig:$PKG_CONFIG_PATH

RUN yum update -y && \
    yum install -y gcc make git libpcap-devel ncurses-devel

RUN ln -s /usr/lib/pkgconfig/ncursesw.pc /usr/lib/pkgconfig/ncurses.pc

RUN git clone https://github.com/netsniff-ng/netsniff-ng.git /root/netsniff-ng \
    && cd /root/netsniff-ng \
    && ./configure \
    && make -j$(nproc) \
    && make install \
    && rm -rf /root/netsniff-ng

RUN git clone https://github.com/akopytov/sysbench.git /root/sysbench \
    && cd /root/sysbench \
    && ./autogen.sh \
    && ./configure --without-mysql \
    && make -j$(nproc) \
    && make install \
    && rm -rf /root/sysbench

RUN git clone https://github.com/ColinIanKing/stress-ng.git /root/stress-ng \
    && cd /root/stress-ng \
    && make -j$(nproc) \
    && make install \
    && rm -rf /root/stress-ng

RUN pip install -U chaostoolkit chaostoolkit-kubernetes

RUN pip install kube-hunter
RUN yum install -y rsync

RUN git clone https://github.com/kubernetes/kubernetes.git /root/kubernetes \
    && cd /root/kubernetes \
    && git checkout ${KUBERNETES_VERSION} \
    && make -j$(nproc) WHAT=cmd/kubemark KUBE_BUILD_PLATFORMS=linux/amd64 \
    && cp /root/kubernetes/_output/local/bin/linux/amd64/kubemark /usr/local/bin/kubemark \
    && rm -rf /root/kubernetes

RUN git clone https://git.hadrons.org/git/libmd.git /root/libmd \
    && cd /root/libmd \
    && ./autogen \
    && ./configure \
    && make -j$(nproc) \
    && make install \
    && rm -rf /root/libmd

RUN git clone https://gitlab.freedesktop.org/libbsd/libbsd.git /root/libbsd \
    && cd /root/libbsd \
    && ./autogen \
    && ./configure \
    && make -j$(nproc) \
    && make install \
    && rm -rf /root/libbsd

RUN git clone https://github.com/pktgen/Pktgen-DPDK.git /root/Pktgen-DPDK \
    && cd /root/Pktgen-DPDK \
    && git checkout ${PKTGEN_VERSION} \
    && ./tools/pktgen-build.sh build \
    && ninja -C /root/Pktgen-DPDK/Builddir install \
    && rm -rf /root/Pktgen-DPDK

# this for a new instruction set TODO check what DPDK uses
RUN git clone https://github.com/netwide-assembler/nasm.git /root/nasm \
    && cd /root/nasm \
    && sh autogen.sh \
    && ./configure --prefix=/usr/local --bindir=/usr/local/bin --mandir=/usr/local/share/man \
    && make \
    && touch /root/nasm/nasm.1 /root/nasm/ndisasm.1 \
    && make install \
    && rm -rf /root/nasm

# in order to plot
RUN pip install matplotlib numpy

COPY stress-ng_cpu_bench.sh /
COPY sysbench_stress.sh /
COPY cyclictest_plot.sh /
COPY cyclictest_per_thread.py /

WORKDIR /root
