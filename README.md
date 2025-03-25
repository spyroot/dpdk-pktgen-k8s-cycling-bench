# dpdk-pktgen-k8s-cycling-bench


This repository contains a Dockerfile for building an environment tailored for high-performance packet generation and benchmarking, utilizing **DPDK**, **Pktgen**, and **Kubernetes**. 
It includes tools for system stress testing, network analysis, vulnerability scanning, and Kubernetes diagnostics. 

## Key Features:
- **DPDK & Pktgen**: High-performance packet generation and processing with DPDK and Pktgen.
- **Kubernetes Benchmarking**: Tools for testing and simulating Kubernetes clusters with tools like `kubemark` and `sonobuoy`.
- **Networking Tools**: Includes `netsniff-ng`, `libnet`, and other utilities for network analysis and packet capture.
- **Security Tools**: Includes `kube-bench` for Kubernetes best practices security checks and `trivy` for container vulnerability scanning.
- **Performance Benchmarking**: System benchmarking tools like `sysbench`, `stress-ng`, `unixbench`, and more for CPU, memory, and network stress testing.
- **Development & Miscellaneous Tools**: Includes `vim`, `fzf`, `jq`, `yamlfmt`, and other utilities to aid in Kubernetes and containerized environment development.

## Installation:
To build the Docker image:
```bash
docker build -t dpdk-pktgen-k8s-cycling-bench .
```


## Repo structure

- **opt**: Scripts and tools related to node optimization.
- **opt**: Scripts and tools related to traffic generation.

