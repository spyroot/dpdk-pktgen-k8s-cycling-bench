# Overview

This script is designed to automate the process of generating and running packet generation and 
reception tests in a Kubernetes environment using DPDK (Data Plane Development Kit). 

The system supports multiple configurations. As described in the Topology section, it allows you to 
run either a single or multiple pairs of TX and RX pods, either on the same node or spread 
across different nodes.

Additionally, the system enables the allocation of a subset of cores for the tests.
Please note that the minimum configuration per TX or RX pod is 2 cores. DPDK 
requires at least one core to be allocated as the master core for proper operation.

The system enables the creation of Lua flow profiles for Pktgen, manages packet generation traffic, 
collects performance statistics, and saves the results for further analysis.

Key Features:

- Profile Generation: Automatically generates packet flow profiles for different packet sizes, flow counts, and rates.
- Kubernetes Integration: Manages pods for packet generation (TX) and reception (RX) within a Kubernetes cluster.
- DPDK & Pktgen Support: Utilizes DPDK for high-performance packet processing and Pktgen for traffic generation.
- Stat Collection: Gathers detailed performance statistics like packet rate, byte count, and errors.
- Results Logging: Logs the collected statistics into .npz files for post-test analysis, and optionally uploads the 
- results to Weights & Biases (W&B) for visualization.

## Prerequisites

Before setting up and running the packet generation and reception tests, ensure the following prerequisites are met:

## Kubernetes Cluster
A working Kubernetes cluster is set up with admin access.
The cluster should have DPDK and SR-IOV (or Multus) 
configured to support the required network devices.

## DPDK Device Plugin:

Ensure that the DPDK device plugin is installed in the cluster to manage DPDK resources.

## Network Interface:

The nodes in your cluster must have network interfaces that support DPDK (Data Plane Development Kit).
Multus CNI (if deploying across multiple nodes):

If deploying pods on different nodes or using multiple network interfaces, ensure Multus CNI is 
installed for handling multi-network environments.

## Kubeconfig:

Make sure that kubectl is configured correctly to interact with your Kubernetes cluster. 
The kubeconfig file should be available at ~/.kube/config.

## Admin Access:

Ensure you have admin privileges on the Kubernetes cluster to create and manage resources.

## Hugepages and VFIO on Worker Node

The Hugepages and VFIO (Virtual Function I/O) must be enabled on the worker nodes where the 
DPDK workloads will run. 

 To check if Hugepages and VFIO are enabled:

 * The system should have hugepages enabled, with at least 2Gi of 1Gi Hugepages available.
 * You can verify this by checking the available Huge pages with the following command:

```bash
cat /proc/meminfo | grep HugePages
```

Ensure that the VFIO driver is loaded and that the network interfaces intended for DPDK are bound to VFIO. 
To check if VFIO is enabled, run:

```bash
lsmod | grep vfio
```

Make sure IOMMU enabled ( note this VM case IOMMU 0

```bash
dmesg | grep IOMMU
[    0.194602] DMAR: IOMMU enabled
[    0.365629] DMAR-IR: IOAPIC id 22 under DRHD base  0xfec10000 IOMMU 0
[    0.554670] DMAR: IOMMU batching disallowed due to virtualization
```

Ensure  hugepages mounted.

```bash
mount | grep hugetlbfs
hugetlbfs on /dev/hugepages type hugetlbfs (rw,relatime,pagesize=1024M)
```

Ensure that Hugepages are enabled in the kernel and the correct page size (e.g., 1GB ) is configured."

```bash
cat /proc/cmdline
BOOT_IMAGE=/boot/vmlinuz-6.1.90-1.ph5-rt root=PARTUUID=31cd07a8-a5bd-a255-9ea2-5cf4d847ee12  default_hugepagesz=1G hugepagesz=1G hugepages=16 intel_iommu=on iommu=pt intel_pstate=disable 
```

## Installation Steps
To set up and run the packet generation and reception tests in your environment, follow the steps below:
```bash
pip install numpy wandb argparse
pip install matplotlib scipy numpy
```

### Set Up Kubernetes Environment
Ensure that kubectl is configured correctly to interact with your cluster. You can verify the configuration by running:

```bash
kubectl cluster-info 
```

```bash
    Kubernetes control plane is running at https://10.100.63.10:6443
    CoreDNS is running at https://10.100.63.10:6443/api/v1/namespaces/kube-system/services/kube-dns:dns/proxy
```

## DPDK interface
   Verify DPDK Pod Configuration.

```bash
  dpdk-devbind --status
``` 

### Steps to Check if Static CPU Policy Manager is Enabled

Kubernetes uses a cpu-manager-policy configuration to define how CPU resources are assigned to pods. 
To check if the static CPU policy manager is enabled, run the following command on your Kubernetes node:

```bash
kubectl describe  nodes perf-perf-np01-njc2n-hznj4-4s6dv
```

You can see the CPU allocatable and CPU capacity sections, which tell you the total number of 
CPUs available on the node and how much is allocatable:

You can see the CPU allocatable and CPU capacity sections, which indicate the total number of CPUs available on the 
node and how many are allocatable for pod scheduling.

Additionally, check the hugepages section to see the amount and size of available hugepages 
(e.g., 1Gi or 2Mi). By default, systems typically reserve 2048 2Mi hugepages per socket and assume a 1Gi page size. 
You can adjust the number of hugepages during pod creation, but ensure the requested amount 
aligns with the node's available resources during traffic generation for optimal performance.

### How Hugepage set per pod

During Pod Creation:

- **create_pod_pairs.sh**
When the **create_pod_pairs.sh** script is run, the socket memory for both TX and RX pods 
is dynamically configured based on the provided values.  The script generates the Pod YAML file with the 
specified memory values for each pod. If no value is specified for socket memory, it will default to 2048MB 
for both TX and RX pods.


- **In the Packet Generator (packet_generator.py)**
The start_generator command uses the --tx-socket-mem and --rx-socket-mem flags to pass the memory configuration to the running pods.
When the test starts, the TX and RX pods will use the configured memory settings, ensuring they have enough resources to handle high-performance packet processing.

Hence, depending on topology, you need to make sure you have sufficient hugepages

(Note in packet generator that we describe later it  --tx-socket-mem 4096 --rx-socket-mem 4096 flags)
```bash
python packet_generator.py start_generator --profile flow_1flows_64B_100rate.lua --tx-socket-mem 4096 --rx-socket-mem 4096
```

In this example: 
 - Note its value per pod.   If you use pod 3 for TX 3 * 4096MB and for RX 3 * 4096MB
 - if you run all pods on same node TX 3 * 4096MB + for RX 3 * 4096MB 
 - TX Pod (Transmission): Allocates 4096MB of socket memory for TX operations.
 - RX Pod (Reception): Allocates 4096MB of socket memory for RX operations.

```bash
Capacity:
  cpu:                22
  ephemeral-storage:  517907788Ki
  hugepages-1Gi:      16Gi
  hugepages-2Mi:      0
  intel.com/direct:   0
  intel.com/dpdk:     6
  intel.com/sriov:    6
  memory:             65845504Ki
  pods:               110
Allocatable:
  cpu:                20
  ephemeral-storage:  477303816631
  hugepages-1Gi:      16Gi
  hugepages-2Mi:      0
  intel.com/direct:   0
  intel.com/dpdk:     6
  intel.com/sriov:    6
  memory:             46868736Ki
  pods:               110
```

## Kubernetes Pod Creation for DPDK Test

This guide helps you set up the necessary pods for running DPDK tests in a Kubernetes cluster. 
The provided script allows you to create multiple tx and rx pod pairs, either on the same node or on 
different nodes within the cluster.

## Prerequisites

Before running the script, ensure the following:

-- Kubernetes Cluster: A Kubernetes cluster is set up, and you have access to it with the necessary privileges to create pods.
-- Kubeconfig: Ensure you have access to the Kubernetes cluster and the kubeconfig file is available at ~/.kube/config.
-- DPDK Device Plugin: Make sure the Kubernetes cluster has the DPDK device plugin installed for managing DPDK resources, and that the DPDK network resources are available on the nodes where you plan to deploy the pods.
-- SR-IOV or DPDK Resources: You should have DPDK VF resources or SR-IOV VF resources configured on your nodes (depending on your resource type). This is important to provide the necessary network interface for DPDK.
-- Pod Template: The pod-template.yaml file should be available in the same directory as this script. This file is used as a template for generating the individual tx and rx pods.

Container Image: Ensure the required container image is available in your registry. You can use the default image or specify your custom image with the -i option.

## System Requirements

- Minimum CPU: 4 cores per node
- Minimum RAM: 16 GiB per node
- NIC: Intel X710/XL710/XXV710 or similar with SR-IOV and DPDK support
- Hugepage: At least 2Gi of 1Gi hugepages configured and mounted

```text
dpdk-k8s-bench/
├── create_pods.sh
├── run_experiments.sh
├── packet_generator.py
├── pod-template.yaml
├── flows/
├── results/
├── logs/
└── README.md

```

```text
results/
└── <exp_id>/
    ├── tx0-rx0/
    │   ├── <metadata>.npz
    │   ├── tx0_port_stats.csv
    │   ├── tx0_port_rate_stats.csv
    │   ├── rx0_stats.log
    │   └── rx0_warmup.log
```

### 📦 Results Directory Layout

Each experiment creates a unique ID folder inside `results/`. Within that folder, each TX/RX pod pair has its own subdirectory:


### 🧪 File Descriptions

- **`<metadata>.npz`**  
  A compressed NumPy archive that contains summary metrics and metadata for the test. It includes TX/RX packet rates, byte counts, and error statistics.

- **`tx0_port_stats.csv` / `tx1_port_stats.csv`**  
  Interface-level statistics from the TX side collected before and after the test. Includes total packets, bytes, and errors.

- **`tx0_port_rate_stats.csv` / `tx1_port_rate_stats.csv`**  
  TX-side per-sample packet rates recorded during the test. Useful for plotting real-time graphs.

- **`rx0_stats.log` / `rx1_stats.log`**  
  Output logs from `testpmd` running in RX pods. Contains RX packet counters, byte totals, drops, and error messages.

- **`rx0_warmup.log` / `rx1_warmup.log`**  
  Logs from the warmup phase before traffic generation. This is used to ensure MAC learning has taken place, especially in setups with L2 switching.

### Quick Start

- Download the Script: Download the provided bash script, which will create tx and rx pods for DPDK tests.
- Configure Your Cluster: Ensure that your Kubernetes cluster is ready with the necessary resources (DPDK or SR-IOV) available.
- Prepare the Pod Template: Place the pod-template.yaml in the same directory as the script.
- Run the Script: You can create tx and rx pod pairs using the following command:

```bash
./create_pods.sh -n <num_pairs> -c <cpu_cores> -m <mem_gb> -d <dpdk_count> -v <vf_count> -g <hugepages> -i <container_image> -s
```

Options:

```text
-n <num_pairs>: The number of tx and rx pod pairs to create. Default is 3.
-c <cpu_cores>: Number of CPU cores to allocate for each pod. Default is 2.
-m <mem_gb>: Amount of memory to allocate for each pod (in GiB). Default is 2.
-d <dpdk_count>: Number of DPDK VF resources per pod. Default is 1.
-v <vf_count>: Number of SR-IOV VF resources per pod. Default is 1.
-g <hugepages>: Number of 1Gi hugepages to allocate per pod. Default is 2.
-i <container_image>: The container image for the pods. Default is spyroot/dpdk-pktgen-k8s-cycling-bench-trex:latest-amd64.
-s: Deploy tx and rx pods on the same node.
--dry-run: Generate YAML files without applying them to the cluster (useful for inspection).
```


### Verify the Created Pods

Once the script has run, you can check the created pods using the following commands:
The pod creation script uses **pod-template.yaml** as a template for generating all the **txN** and **rxN** pods.
Each pod is assigned one of two roles: either TX (transmit) or RX (receive).

```bash
kubectl get pods -l role=tx
kubectl get pods -l role=rx
```

### 🔧 `create_pods.sh` — Pod Creation Script

This script is responsible for generating and deploying the Kubernetes pod specifications for 
both **TX (transmit)** and **RX (receive)** roles.

#### 📋 Responsibilities

- Reads and fills in a pod template (`pod-template.yaml`) with runtime values such as:
  - Pod name, node name
  - MAC and PCI mappings
  - CPU, memory, hugepages, NIC resources
- Supports **dry-run mode** (`--dry-run`) to validate pod specs without applying them.
- Assigns **pod affinity rules** to control whether pods are placed on the same or different nodes.
- Deploys **Persistent Volume Claims (PVC)** (e.g., `output-pvc`) if configured.
- Creates and labels pods with `role=tx` or `role=rx` for identification and selection.

#### 🛠️ Example Usage

```bash
# Create 2 TX/RX pairs on different nodes
./create_pods.sh -n 2 -c 4 -m 8 -d 2 -g 2 --no-same-node

# Dry-run to preview generated YAML without applying
./create_pods.sh -n 2 -c 4 -m 8 -g 2 --dry-run

# Use a custom image for pod deployment
./create_pods.sh -n 2 -i my-registry/my-image:latest
```
### 🚀 `run_experiments.sh` — Experiment Orchestration Script

This is the main entrypoint to run DPDK-based tests.

#### 📋 Responsibilities

- Validates system state and configuration.
- Automatically regenerates Lua profiles if needed.
- Ensures correct pod-node placement (same or different node).
- Checks for already completed tests and skips them.
- Backs up existing results.
- Run the test for each matched TX/RX pod pair using a selected Lua profile.

#### ✨ Key Features

- Supports profile filtering (`-f 64` to run only profiles containing "64").
- Supports **dry-run** mode by default (validates everything without execution).
- Auto-scans the `results/` directory for existing `.npz` files to avoid duplicate runs.
- Optionally saves or prints the current configuration (`--config`, `--config-file`).

#### 🛠️ Usage Example

```bash
# Dry run (default behavior)
./run_experiments.sh -n 2 --dry-run

# Run real experiments across different nodes
./run_experiments.sh -n 2 --run --no-same-node
```

## Example Commands

### Example 1: Create 1 Pair of Pods on the Same Node with 4 CPU and 8Gi Memory. (Check topologies below)

```bash
./create-pod-pairs.sh -n 1 -c 4 -m 8 -d 2 -v 2 -g 2 -s
```

This command will create 1 pair of tx and rx pods, each with 4 CPU cores, 8Gi memory, 
2 DPDK VF resources, 2 SR-IOV VF resources, and 2Gi of hugepages, all deployed on the same worker node.

#### Example 2: Dry-Run for 2 Pairs of Pods on Different Nodes

```text
./create-pod-pairs.sh -n 2 -c 4 -m 8 -d 2 -v 2 -g 2 --dry-run
```

#### Example 3: Dry-Run

```bash
./create-pod-pairs.sh -n 2 -c 4 -m 8 -d 2 -v 2 -g 2 --dry-run

```
This command generates the YAML files for 2 pairs of tx and rx pods but does not apply them to the Kubernetes cluster.
This is useful for inspections before applying them.

Example 3: Create Pods with a Custom Container Image

```bash
./create-pod-pairs.sh -n 3 -i my-custom-image:latest
```

This command will create 3 pairs of tx and rx pods using the my-custom-image:latest container image.
Note that entire system based on container that repo provide so please don't change that.


Pod Deployment Summary

Pod Naming:
- The tx pods are named **tx0, tx1, tx2**, etc.
- The rx pods are named **rx0, rx1, rx2**, etc.

Pod Labels:
The pods are labeled as **role=tx** for transmit pods and **role=rx** for receive pods.

Pod Template Variables:

The following variables will be dynamically replaced in the pod template:

- {{src-mac}}, {{dst-mac}}: MAC addresses for the tx and rx pods.
- {{src-pci}}, {{dst-pci}}: PCI addresses for the tx and rx pods.
- {{cpu-request}}, {{memory-request}}, etc.

### Troubleshooting

Pods Not Deploying:
  - Check that your nodes have sufficient DPDK/SR-IOV resources and that the correct device plugin is installed.
  - Use kubectl describe pod <pod_name> to inspect individual pod status.
  - Check the device plugin.

Dry-Run Issues:
  - If you're running in dry-run mode and the YAML files are not being generated as expected, 
  - check the output directory for the pods/ folder containing the YAML files.

### Verification

Check that pod running.

```bash
kubectl get pods
NAME                             READY   STATUS    RESTARTS        AGE
rx0                              1/1     Running   0               6d
tx0                              1/1     Running   0               6d
```


Note here.

 Limits:
      cpu:             2
      hugepages-1Gi:   2Gi
      intel.com/dpdk:  1
      memory:          2Gi
    Requests:
      cpu:             2
      hugepages-1Gi:   2Gi
      intel.com/dpdk:  1
      memory:          2Gi

```bash
kubectl describe pod rx0
Name:             rx0
Namespace:        default
Priority:         0
Service Account:  default
Node:             perf-perf-np01-njc2n-hznj4-4s6dv/10.100.63.191
Start Time:       Fri, 21 Mar 2025 05:17:53 +0400
Labels:           app=mus.toolkit
                  environment=dpdk.tester
Annotations:      k8s.v1.cni.cncf.io/network-status:
                    [{
                        "name": "antrea",
                        "interface": "eth0",
                        "ips": [
                            "100.96.2.13"
                        ],
                        "mac": "8a:10:34:59:c8:67",
                        "default": true,
                        "dns": {},
                        "gateway": [
                            "100.96.2.1"
                        ]
                    }]
                  pod-type: rx
Status:           Running
IP:               100.96.2.13
IPs:
  IP:  100.96.2.13
Containers:
  rx0:
    Container ID:  containerd://72ddffe19efc8bb2d5a6f275fde384b548c2f21b98807d3a4904f6f0de5ba120
    Image:         spyroot/dpdk-pktgen-k8s-cycling-bench-trex:latest-amd64
    Image ID:      docker.io/spyroot/dpdk-pktgen-k8s-cycling-bench-trex@sha256:ebf0d77b6ef1ffe71aa69f96487935e69ef449f47deff6aede7db62b1e9430e8
    Port:          <none>
    Host Port:     <none>
    Command:
      /bin/bash
      -c
      PID=; trap 'kill $PID' TERM INT; sleep infinity & PID=$!; wait $PID
    State:          Running
      Started:      Fri, 21 Mar 2025 05:17:54 +0400
    Ready:          True
    Restart Count:  0
    Limits:
      cpu:             2
      hugepages-1Gi:   2Gi
      intel.com/dpdk:  1
      memory:          2Gi
    Requests:
      cpu:             2
      hugepages-1Gi:   2Gi
      intel.com/dpdk:  1
      memory:          2Gi
    Environment:
      SRC_MAC:  00:50:56:AB:60:84
      DST_MAC:  00:50:56:AB:A2:EF
      SRC_PCI:  03:01.0
      DST_PCI:  03:00.0
      PATH:     /bin:/sbin:/usr/bin:/usr/sbin:/usr/bin:/usr/local/sbin:/usr/local/bin:$PATH
    Mounts:
      /dev/hugepages from hugepage (rw)
      /home/capv/.kube from kubeconfig (rw)
      /lib/modules from modules (ro)
      /output from output (rw)
      /sys from sys (ro)
      /var/run/secrets/kubernetes.io/serviceaccount from kube-api-access-jdl7l (ro)
Conditions:
  Type                        Status
  PodReadyToStartContainers   True
  Initialized                 True
  Ready                       True
  ContainersReady             True
  PodScheduled                True
Volumes:
  sys:
    Type:          HostPath (bare host directory volume)
    Path:          /sys
    HostPathType:
  modules:
    Type:          HostPath (bare host directory volume)
    Path:          /lib/modules
    HostPathType:
  output:
    Type:       PersistentVolumeClaim (a reference to a PersistentVolumeClaim in the same namespace)
    ClaimName:  output-pvc-rx0
    ReadOnly:   false
  hugepage:
    Type:          HostPath (bare host directory volume)
    Path:          /dev/hugepages
    HostPathType:
  kubeconfig:
    Type:          HostPath (bare host directory volume)
    Path:          /home/capv/.kube
    HostPathType:
  kube-api-access-jdl7l:
    Type:                    Projected (a volume that contains injected data from multiple sources)
    TokenExpirationSeconds:  3607
    ConfigMapName:           kube-root-ca.crt
    ConfigMapOptional:       <nil>
    DownwardAPI:             true
QoS Class:                   Guaranteed
Node-Selectors:              kubernetes.io/os=linux
Tolerations:                 node.kubernetes.io/not-ready:NoExecute op=Exists for 300s
                             node.kubernetes.io/unreachable:NoExecute op=Exists for 300s
Events:                      <none>
```



Replace <profile_name> with the appropriate Lua profile, and <test_duration> with the desired duration for the test in seconds.

## Running the Script (short version)

Once all dependencies are installed and the environment is set up,
you can run the script using the following commands:

```bash
python packet_generator.py generate_flow --rate 10,50,100 --pkt-size 64,512,1500 --flows 1,10000
```

In order to start generated profile

```bash
python packet_generator.py start_generator --profile <profile_name> --duration <test_duration>
```

## Detail view.

The system supports multiple configurations, and the profiles are always unidirectional. 
During the discovery phase, the system automatically identifies and matches the TX and RX pod pairs, 
NUMA topology, and corresponding DPDK interfaces, along with their MAC addresses.

```bash
python packet_generator.py generate_flow --rate 10,50,100 --pkt-size 64,512,1500 --flows 1,100
```
For each pair of TX and RX pods, profiles are generated and saved under each corresponding pair’s directory.

Example Directory Structure:

✗ tree
.
├── tx0-rx0
│   ├── profile_10000_flows_pkt_size_128B_100_rate_s.lua
│   ├── profile_10000_flows_pkt_size_128B_10_rate_s.lua
│   ├── profile_10000_flows_pkt_size_1500B_100_rate_s.lua
│   ├── profile_10000_flows_pkt_size_1500B_10_rate_s.lua
│   ├── profile_10000_flows_pkt_size_2000B_100_rate_s.lua
│   ├── profile_10000_flows_pkt_size_2000B_10_rate_s.lua
│   ├── profile_10000_flows_pkt_size_512B_100_rate_s.lua
│   ├── profile_10000_flows_pkt_size_512B_10_rate_s.lua
│   ├── profile_10000_flows_pkt_size_64B_100_rate_s.lua
│   ├── profile_10000_flows_pkt_size_64B_10_rate_s.lua
│   ├── profile_10000_flows_pkt_size_9000B_100_rate_s.lua
│   ├── profile_10000_flows_pkt_size_9000B_10_rate_s.lua
│   ├── profile_100_flows_pkt_size_128B_100_rate_s.lua
│   ├── profile_100_flows_pkt_size_128B_10_rate_s.lua
│   ├── profile_100_flows_pkt_size_1500B_100_rate_s.lua
│   ├── profile_100_flows_pkt_size_1500B_10_rate_s.lua
│   ├── profile_100_flows_pkt_size_2000B_100_rate_s.lua
│   ├── profile_100_flows_pkt_size_2000B_10_rate_s.lua
│   ├── profile_100_flows_pkt_size_512B_100_rate_s.lua
│   ├── profile_100_flows_pkt_size_512B_10_rate_s.lua
│   ├── profile_100_flows_pkt_size_64B_100_rate_s.lua
│   ├── profile_100_flows_pkt_size_64B_10_rate_s.lua
│   ├── profile_100_flows_pkt_size_9000B_100_rate_s.lua
│   ├── profile_100_flows_pkt_size_9000B_10_rate_s.lua
│   ├── profile_1_flows_pkt_size_128B_100_rate_s.lua
│   ├── profile_1_flows_pkt_size_128B_10_rate_s.lua
│   ├── profile_1_flows_pkt_size_1500B_100_rate_s.lua
│   ├── profile_1_flows_pkt_size_1500B_10_rate_s.lua
│   ├── profile_1_flows_pkt_size_2000B_100_rate_s.lua
│   ├── profile_1_flows_pkt_size_2000B_10_rate_s.lua
│   ├── profile_1_flows_pkt_size_512B_100_rate_s.lua
│   ├── profile_1_flows_pkt_size_512B_10_rate_s.lua
│   ├── profile_1_flows_pkt_size_64B_100_rate_s.lua
│   ├── profile_1_flows_pkt_size_64B_100_rate_s.lua.backup
│   ├── profile_1_flows_pkt_size_64B_10_rate_s.lua
│   ├── profile_1_flows_pkt_size_9000B_100_rate_s.lua
│   └── profile_1_flows_pkt_size_9000B_10_rate_s.lua

You can note that in each lua file we source mac and destination mac, during this phase we only populate 
require profiles.

if we run, we can see that all profiles post generation are automatically discovered, and we can consume any.
for packet generation.

## 🧩 Detailed Argument Descriptions


This script orchestrates full test runs. It auto-detects TX/RX pod pairs, manages Lua profiles,
avoids duplicate runs, and can resume from incomplete states.

| Argument               | Description                                                                                      |
|------------------------|--------------------------------------------------------------------------------------------------|
| `-n <num_pairs>`       | Number of TX/RX pod pairs to match. Defaults to all discovered pairs.                            |
| `--run`                | Run the experiments (otherwise defaults to dry-run/validation mode).                             |
| `--dry-run`            | Performs validation (pod presence, profiles, config) but does not run tests.                     |
| `--config`             | Prints current experiment configuration to terminal (useful for review/debug).                   |
| `--config-file <path>` | Saves the current test configuration to a file. Useful for logging or reuse.                     |
| `--no-same-node`       | Ensures TX and RX pods are deployed on different nodes. Default behavior places them apart.      |
| `-f <pattern>`         | Filters Lua profiles to run only those that match a pattern (e.g. `64`, `9000B`).                |
| `--scan-results`       | Lists which profiles have already completed and which are pending.                               |

---

### ✅ Resume Feature

This script **automatically resumes** from the last incomplete state by scanning:

- The `results/` directory  
- `.npz` files for integrity  
- Lua profile list to identify which tests are pending  

> 🧠 **Note**: No need to delete or move anything. If a profile already has a valid `.npz`, the script will **skip it** automatically.


```bash
python packet_generator.py start_generator --help
```

```bash
usage: packet_generator.py start_generator [-h] [--txd TXD] [--rxd RXD] [--warmup-duration WARMUP_DURATION] [--rx-socket-mem RX_SOCKET_MEM] [--tx-socket-mem TX_SOCKET_MEM]
                                           [--tx_num_core TX_NUM_CORE] [--rx_num_core RX_NUM_CORE] [--interactive INTERACTIVE] [--control-port CONTROL_PORT]
                                           [--sample-interval SAMPLE_INTERVAL] [--sample-count SAMPLE_COUNT] [--debug] [--skip-copy] [--skip-testpmd] [--duration DURATION] --profile
                                           <profile>

options:
  -h, --help            show this help message and exit
  --txd TXD             🚀 TX (Transmit) descriptor count
  --rxd RXD             📡 RX (Receive) descriptor count
  --warmup-duration WARMUP_DURATION
                        🧪 Warmup duration in seconds to trigger MAC learning (default: 2)
  --rx-socket-mem RX_SOCKET_MEM
                        📦 Socket memory for RX side testpmd (default: 2048)
  --tx-socket-mem TX_SOCKET_MEM
                        📦 Socket memory for TX side pktgen (default: 2048)
  --tx_num_core TX_NUM_CORE
                        🚀 Number of cores to use for generation. If not set, uses all available cores minus one for main.
  --rx_num_core RX_NUM_CORE
                        🧠 Number of cores to use at receiver side. If not set, uses all available cores minus one for main.
  --interactive INTERACTIVE
                        run pktgen interactively.
  --control-port CONTROL_PORT
                        🔌 Pktgen control port used for socat communication (default: 22022)
  --sample-interval SAMPLE_INTERVAL
                        📈 Interval (in seconds) between pktgen stat samples (default: 10s)
  --sample-count SAMPLE_COUNT
                        🔁 Number of samples to collect. If not set, will use duration/sample-interval
  --debug               🔍 Debug: Load and display contents of .npz results after test
  --skip-copy           ⏭️ Skip copying Lua profiles and Pktgen.lua into TX pods
  --skip-testpmd        ⏭️ Skip launching testpmd in RX pods
  --duration DURATION   ⏱ Duration in seconds to run pktgen before stopping testpmd
  --profile <profile>   📁 Available profiles: 🔹 collect.lua 🔹 profile_10000_flows_pkt_size_128B_100_rate_s.lua 🔹 profile_10000_flows_pkt_size_128B_10_rate_s.lua 🔹
                        profile_10000_flows_pkt_size_1500B_100_rate_s.lua 🔹 profile_10000_flows_pkt_size_1500B_10_rate_s.lua 🔹 profile_10000_flows_pkt_size_2000B_100_rate_s.lua 🔹
                        profile_10000_flows_pkt_size_2000B_10_rate_s.lua 🔹 profile_10000_flows_pkt_size_512B_100_rate_s.lua 🔹 profile_10000_flows_pkt_size_512B_10_rate_s.lua 🔹
                        profile_10000_flows_pkt_size_64B_100_rate_s.lua 🔹 profile_10000_flows_pkt_size_64B_10_rate_s.lua 🔹 profile_10000_flows_pkt_size_9000B_100_rate_s.lua 🔹
                        profile_10000_flows_pkt_size_9000B_10_rate_s.lua 🔹 profile_100_flows_pkt_size_128B_100_rate_s.lua 🔹 profile_100_flows_pkt_size_128B_10_rate_s.lua 🔹
                        profile_100_flows_pkt_size_1500B_100_rate_s.lua 🔹 profile_100_flows_pkt_size_1500B_10_rate_s.lua 🔹 profile_100_flows_pkt_size_2000B_100_rate_s.lua 🔹
                        profile_100_flows_pkt_size_2000B_10_rate_s.lua 🔹 profile_100_flows_pkt_size_512B_100_rate_s.lua 🔹 profile_100_flows_pkt_size_512B_10_rate_s.lua 🔹
                        profile_100_flows_pkt_size_64B_100_rate_s.lua 🔹 profile_100_flows_pkt_size_64B_10_rate_s.lua 🔹 profile_100_flows_pkt_size_9000B_100_rate_s.lua 🔹
                        profile_100_flows_pkt_size_9000B_10_rate_s.lua 🔹 profile_1_flows_pkt_size_128B_100_rate_s.lua 🔹 profile_1_flows_pkt_size_128B_10_rate_s.lua 🔹
                        profile_1_flows_pkt_size_1500B_100_rate_s.lua 🔹 profile_1_flows_pkt_size_1500B_10_rate_s.lua 🔹 profile_1_flows_pkt_size_2000B_100_rate_s.lua 🔹
                        profile_1_flows_pkt_size_2000B_10_rate_s.lua 🔹 profile_1_flows_pkt_size_512B_100_rate_s.lua 🔹 profile_1_flows_pkt_size_512B_10_rate_s.lua 🔹
                        profile_1_flows_pkt_size_64B_100_rate_s.lua 🔹 profile_1_flows_pkt_size_64B_10_rate_s.lua 🔹 profile_1_flows_pkt_size_9000B_100_rate_s.lua 🔹
```

 
## 🧮 How Socket Memory Is Calculated

DPDK requires memory to be allocated per NUMA socket in units called *socket memory*. This is essential for allocating hugepage-backed memory buffers that are used by DPDK for zero-copy packet processing.

### 🔢 Why 2048MB Is the Default

We use `2048` MB (2GiB) as the **default socket memory per pod** because:

- It's the **minimum safe amount** to support a small number of queues and descriptors.
- It ensures that Pktgen and TestPMD can **initialize without memory allocation failures**.
- It aligns with common **hugepage allocations** (e.g., 2 x 1GiB hugepages).
- It provides headroom for:
  - Packet buffers (`mbufs`)
  - Descriptor rings
  - Metadata structures

### 📐 How Total Socket Memory Is Calculated

When using the `--tx-socket-mem` and `--rx-socket-mem` flags, the script multiplies the provided 
amount by the number of pods:

```text
Total TX socket memory = TX_POD_COUNT × TX_SOCKET_MEM_MB
Total RX socket memory = RX_POD_COUNT × RX_SOCKET_MEM_MB
```

```bash
python packet_generator.py start_generator --tx-socket-mem 4096 --rx-socket-mem 4096
```
If you have 3 TX and 3 RX pods on the same node, the total memory required would be:

```text
TX: 3 × 4096MB = 12GiB
RX: 3 × 4096MB = 12GiB
Total = 24GiB of hugepage memory
```

Make sure your nodes have enough hugepages available (/proc/meminfo, mount, kubectl describe node) before assigning high values.
⚠️ Note: If hugepages are insufficient, DPDK apps may fail silently or throw ENOMEM errors during init.


#### 💡 Tip
If you assign more cores, queues, or larger packet buffers, increase socket memory accordingly. 
For large-scale tests or jumbo frames, 4GiB–8GiB per pod is common.


## Topologies

The system supports different topologies, with traffic always being unidirectional. For instance, you can create a 
single pair of pods on the same worker node or deploy multiple pod pairs on the same node. Alternatively, you 
can configure a topology where all TX pods are deployed on separate worker nodes.

In each case, multiple cores can be allocated per pod.  For example, you can test a single TX-RX pair with a 
single core or allocate multiple cores for both TX and RX. Similarly, you can create N TX pods, each with two 
or more cores, and do the same for RX pods.  Please note that the minimum configuration for a pod requires at 
least 2 cores, with one core designated as the master core.

EAL Flags, master core
[DPDK EAL Parameters Documentation](https://doc.dpdk.org/guides-19.02/linux_gsg/linux_eal_parameters.html)

```text
+-------------------+                +-------------------+
|      Worker 1     |                |      Worker 1     |
|                   |                |                   |
|  +-------------+  |                |  +-------------+  |
|  |   TX Pod 0  |  |  <->  +------+ |  |   RX Pod 0  |  |
|  |  (tx0)      |  |       | Switch |  |  (rx0)      |  |
|  +-------------+  |                |  +-------------+  |
|  +-------------+  |                |  +-------------+  |
|  |   TX Pod 1  |  |  <->  +------+ |  |   RX Pod 1  |  |
|  |  (tx1)      |  |       | Switch |  |  (rx1)      |  |
|  +-------------+  |                |  +-------------+  |
|  +-------------+  |                |  +-------------+  |
|  |   TX Pod N  |  |  <->  +------+ |  |   RX Pod N  |  |
|  |  (txN)      |  |       | Switch |  |    (rxN)    |  |
|  +-------------+  |                |  +-------------+  |
+-------------------+                +-------------------+


+-------------------+                +-------------------+
|      Worker A     |                |      Worker B     |
|                   |                |                   |
|  +-------------+  |                |  +-------------+  |
|  |   TX Pod 0  |  |  <->  +------+ |  |   RX Pod 0  |  |
|  |  (tx0)      |  |       | Switch |  |  (rx0)      |  |
|  +-------------+  |                |  +-------------+  |
|  +-------------+  |                |  +-------------+  |
|  |   TX Pod 1  |  |  <->  +------+ |  |   RX Pod 1  |  |
|  |  (tx1)      |  |       | Switch |  |  |  (rx1)   |  | 
|  +-------------+  |                |  +-------------+  |
+-------------------+                +-------------------+


+-------------------+                +-------------------+
|      Worker A     |                |      Worker B     |
|                   |                |                   |
|  +-------------+  |                |  +-------------+  |
|  |   TX Pod 0  |  |  <->  +------+ |  |   RX Pod 0  |  |
|  |  (tx0)      |  |       | Switch |  |  (rx0)      |  |
|  +-------------+  |                |  +-------------+  |
|  +-------------+  |                |  +-------------+  |
|  |   TX Pod 1  |  |  <->  +------+ |  |   RX Pod 1  |  |
|  |  (tx1)      |  |       | Switch |   |  (rx1)     |  |
|  +-------------+  |                |  +-------------+  |
|  +-------------+  |                |  +-------------+  |
|  |   TX Pod N  |  |  <->  +------+ |  |   RX Pod N  |  |
|  |  (txN)      |  |       | Switch |  |  |  (rxN)   |  |
|  +-------------+  |                |  +-------------+  |
+-------------------+                +-------------------+
```

### Appendix.

Default pod template, note persistent storage optional.
As part of k8s, there separate provisioner I use.
Check sub-dir provisioner for details.

```yaml
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: output-pvc-{{pod-name}}
  namespace: default
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: {{storage-size}}Gi
  storageClassName: {{storage-class}}
---
apiVersion: v1
kind: Pod
metadata:
  name: {{pod-name}}
  labels:
    environment: dpdk.tester
    app: mus.toolkit
  annotations:
    pod-type: "{{pod-role}}"
spec:
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
          - matchExpressions:
              - key: kubernetes.io/hostname
                operator: In
                values:
                  - {{node-name}}
  containers:
    - name: {{pod-name}}
      command: ["/bin/bash", "-c", "PID=; trap 'kill $PID' TERM INT; sleep infinity & PID=$!; wait $PID"]
      image: {{image}}
      imagePullPolicy: IfNotPresent
      securityContext:
        capabilities:
          add:
            - IPC_LOCK
            - CAP_SYS_NICE
            - SYS_NICE
            - NET_ADMIN
            - SYS_TIME
            - CAP_NET_RAW
            - CAP_BPF
            - CAP_SYS_ADMIN
            - SYS_ADMIN
        privileged: true
      env:
        - name: SRC_MAC
          value: "{{src-mac}}"
        - name: DST_MAC
          value: "{{dst-mac}}"
        - name: SRC_PCI
          value: "{{src-pci}}"
        - name: DST_PCI
          value: "{{dst-pci}}"
        - name: PATH
          value: "/bin:/sbin:/usr/bin:/usr/sbin:/usr/bin:/usr/local/sbin:/usr/local/bin:$PATH"
      volumeMounts:
        - name: sys
          mountPath: /sys
          readOnly: true
        - name: modules
          mountPath: /lib/modules
          readOnly: true
        - name: output
          mountPath: "/output"
        - name: kubeconfig
          mountPath: {{kubeconfig-path}}
        - name: hugepage
          mountPath: /dev/hugepages
      resources:
        requests:
          cpu: "{{cpu-request}}"
          memory: "{{memory-request}}Gi"
          {{resource-requests}}
        limits:
          cpu: "{{cpu-limit}}"
          memory: "{{memory-limit}}Gi"
          hugepages-1Gi: "{{hugepages-limit}}Gi"
          {{resource-limits}}
  volumes:
    - name: sys
      hostPath:
        path: /sys
    - name: modules
      hostPath:
        path: /lib/modules
    - name: output
      persistentVolumeClaim:
        claimName: output-pvc-{{pod-name}}
    - name: hugepage
      hostPath:
          path: /dev/hugepages
    - name: kubeconfig
      hostPath:
        path: {{kubeconfig-path}}
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

```