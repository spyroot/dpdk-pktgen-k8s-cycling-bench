# Overview

This script is designed to automate the process of generating and running packet generation and 
reception tests in a Kubernetes environment using DPDK (Data Plane Development Kit). 

The script enables the creation of Lua flow profiles for Pktgen, manages packet generation traffic, 
collects performance statistics, and saves the results for further analysis.

Key Features:

- Profile Generation: Automatically generates packet flow profiles for different packet sizes, flow counts, and rates.
- Kubernetes Integration: Manages pods for packet generation (TX) and reception (RX) within a Kubernetes cluster.
- DPDK & Pktgen Support: Utilizes DPDK for high-performance packet processing and Pktgen for traffic generation.
- Stats Collection: Gathers detailed performance statistics like packet rate, byte count, and errors.
- Results Logging: Logs the collected statistics into .npz files for post-test analysis, and optionally uploads the results to Weights & Biases (W&B) for visualization.

## Installation Steps
To set up and run the packet generation and reception tests in your environment, follow the steps below:

pip install numpy wandb argparse
pip install matplotlib scipy numpy


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

When the create_pod_pairs.sh script is run, the socket memory for both TX and RX pods 
is dynamically configured based on the provided values.

The script generates the Pod YAML file with the specified memory values for each pod.
If no value is specified for socket memory, it will default to 2048MB for both TX and RX pods.

In the Packet Generator (packet_generator.py):

The start_generator command uses the --tx-socket-mem and --rx-socket-mem flags to pass the memory configuration to the running pods.
When the test starts, the TX and RX pods will use the configured memory settings, ensuring they have enough resources to handle high-performance packet processing.

Hence depend on topology you need make sure you have sufficient hugepages

(Note in packet generator that we describe later it  --tx-socket-mem 4096 --rx-socket-mem 4096 flags)
```bash
python packet_generator.py start_generator --profile flow_1flows_64B_100rate.lua --tx-socket-mem 4096 --rx-socket-mem 4096
```

In this example: 
 - Note it value per pod.   If you use 3 pod for TX 3 * 4096MB and for RX 3 * 4096MB
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

Prerequisites
Before running the script, ensure the following:

-- Kubernetes Cluster: A Kubernetes cluster is set up and you have access to it with the necessary privileges to create pods.
-- Kubeconfig: Ensure you have access to the Kubernetes cluster and the kubeconfig file is available at ~/.kube/config.
-- DPDK Device Plugin: Make sure the Kubernetes cluster has the DPDK device plugin installed for managing DPDK resources, and that the DPDK network resources are available on the nodes where you plan to deploy the pods.
-- SR-IOV or DPDK Resources: You should have DPDK VF resources or SR-IOV VF resources configured on your nodes (depending on your resource type). This is important to provide the necessary network interface for DPDK.
-- Pod Template: The pod-template.yaml file should be available in the same directory as this script. This file is used as a template for generating the individual tx and rx pods.

Container Image: Ensure the required container image is available in your registry. You can use the default image or specify your custom image with the -i option.

### Quick Start

Download the Script: Download the provided bash script, which will create tx and rx pods for DPDK tests.
Configure Your Cluster: Ensure that your Kubernetes cluster is ready with the necessary resources (DPDK or SR-IOV) available.
Prepare the Pod Template: Place the pod-template.yaml in the same directory as the script.
Run the Script: You can create tx and rx pod pairs using the following command:


```bash
./create_pods.sh -n <num_pairs> -c <cpu_cores> -m <mem_gb> -d <dpdk_count> -v <vf_count> -g <hugepages> -i <container_image> -s
```

Options:
-n <num_pairs>: The number of tx and rx pod pairs to create. Default is 3.
-c <cpu_cores>: Number of CPU cores to allocate for each pod. Default is 2.
-m <mem_gb>: Amount of memory to allocate for each pod (in GiB). Default is 2.
-d <dpdk_count>: Number of DPDK VF resources per pod. Default is 1.
-v <vf_count>: Number of SR-IOV VF resources per pod. Default is 1.
-g <hugepages>: Number of 1Gi hugepages to allocate per pod. Default is 2.
-i <container_image>: The container image for the pods. Default is spyroot/dpdk-pktgen-k8s-cycling-bench-trex:latest-amd64.
-s: Deploy tx and rx pods on the same node.
--dry-run: Generate YAML files without applying them to the cluster (useful for inspection).


Verify the Created Pods: Once the script has run, you can check the created pods using the following commands:

The pod creation script uses pod-template.yaml as a template for generating all the tx and rx pods.
Each pod is assigned one of two roles: either TX (transmit) or RX (receive).

```bash
kubectl get pods -l role=tx
kubectl get pods -l role=rx
```

Example Commands

### Example 1: Create 1 Pair of Pods on the Same Node with 4 CPU and 8Gi Memory. ( Check topologies below)

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
This is useful for inspection before applying them.

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
  - Check device plugin.

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


Deploy the Profile: After creating the pods, you can deploy the test profile using the command:

bash
Copy
python packet_generator.py start_generator --profile <profile_name> --duration <test_duration>

Replace <profile_name> with the appropriate Lua profile, and <test_duration> with the desired duration for the test in seconds.

### Running the Script

Once all dependencies are installed and the environment is set up,
you can run the script using the following commands:

python packet_generator.py generate_flow --rate 10,50,100 --pkt-size 64,512,1500 --flows 1,10000

 
## Topologies

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
