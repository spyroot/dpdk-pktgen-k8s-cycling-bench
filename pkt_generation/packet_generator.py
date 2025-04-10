"""
This script suite is designed to test DPDK (Data Plane Development Kit) performance in Kubernetes (k8s)
across a variety of configurations and scenarios.

Basic Scenario:
------------------

The most basic one two pod on same worker node.  On act as TX and another as RX and we want to test many
variation in terms packet size , number flow.

More sophisticated if same worker node host N pod let say it 8 pod,  and we form 1:1 8 pair.
tx0 - rx0
tx1 - rx1
so on...

And alternative configuration where we have two node and each node host N pod , it could since pair
TX0 - RX0 where TX0 on Node Alice and RX on Node BOB
or N pods
where TX0,TX1 . son on


The simplest test setup involves two pods scheduled on the same Kubernetes worker node:
- One pod acts as the **transmitter (TX)**.
- The other pod acts as the **receiver (RX)**.

In this setup, we aim to evaluate how DPDK performs under varying:
- Packet sizes (e.g., 64, 128, 512, 1500, 2000, 9000 bytes)
- Flow counts (e.g., 1, 100, 10000 concurrent flows)
- Transmission rates (percentage of line rate, e.g., 10%, 50%, 100%)

Intermediate Scenario:
-------------------------
A more advanced configuration tests **multiple TX-RX pairs** on the same node.
For example, if a node hosts 8 pods, we can form 8 pairs like:
    tx0 <-> rx0
    tx1 <-> rx1
    ...
    tx7 <-> rx7

This tests NUMA locality, inter-pod scheduling, and CPU/PCIe balancing on the same host.

 Cross-Node Scenario:
------------------------
For even more realistic network tests, we scale out across two or more worker nodes:

Case A: **Symmetric 1:1 pairings**
- Pods are distributed across nodes, e.g.:
    - `tx0` runs on Node A (Alice)
    - `rx0` runs on Node B (Bob)

Case B: **Asymmetric distribution**
- All TX pods run on Node A
- All RX pods run on Node B
- This simulates real-world ingress/egress load imbalance

Flow Profile Generation:
---------------------------
Flows are dynamically generated using customizable templates via `generate_flow`:

Each flow profile is:

- Automatically named and saved under `flows/txN-rxN/`
- Describes a Lua-based configuration for Pktgen to simulate UDP traffic

The user can define:
- `--rate`: Transmission rate (in %)
- `--pkt-size`: Packet size (bytes)
- `--flows`: Number of flows
- `--flow-mode`: Determines which parameters are incremented per flow:
    - `s`    → Increment source IP only
    - `sd`   → Increment source + destination IPs
    - `sp`   → Increment source IP + source port
    - `dp`   → Increment source IP + destination port
    - `spd`  → Increment source IP + port + destination IP
    - `sdpd` → Increment source IP + port, destination IP + port

Each combination of rate, packet size, flow count, and mode generates a unique Lua profile, e.g.:
    `flow_10000flows_1500B_100rate_sdpd.lua`

These profiles can be copied and used inside TX_x pods to run Pktgen automatically.

Execution Workflow:
----------------------
1. Run `generate_flow` to create profiles:
    $ python packet_generator.py generate_flow --rate 10,50,100 --pkt-size 64,512 --flows 100,10000

2. Then run `start_generator` to deploy the test:
    $ python packet_generator.py start_generator --profile flow_10000flows_1500B_100rate.lua

This will:
- Copy Lua profiles to TX pods
- Launch `testpmd` in RX pods (in `rxonly` mode)
- Launch `pktgen` in TX pods using the profile
- Use NUMA-aware CPU pinning for optimal performance

Test results are saved to `/output/stats.log` in each RX pod for post-analysis.

Autor mus

"""
import argparse
import hashlib
import json
import logging
import os
import shutil
import sys
import re
import subprocess
import tarfile
import time
from datetime import datetime
from ipaddress import ip_address
from itertools import product
from typing import List, Optional, Union
from typing import Tuple, Dict
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import wandb

# logging.basicConfig(
#     filename='pktgen.log',
#     level=logging.INFO,
#     format='%(asctime)s - %(levelname)s - %(message)s'
# )

logger = logging.getLogger(__name__)

# this out template
LUA_UDP_TEMPLATE = """\
package.path = package.path ..";?.lua;test/?.lua;app/?.lua;"
require "Pktgen"

local pauseTime		= 1000;

local function setup_range_flow()

    pktgen.clear("all");
    pktgen.cls();
    pktgen.reset("all");
    
    pktgen.stop(0);
    pktgen.set("all", "rate", {rate});
    pktgen.mac_from_arp("on");
    pktgen.ping4("all");
    pktgen.prime("all");
    pktgen.screen("on");
    
    print("**** Execute Range test ********")
    
    pktgen.page("range")
    
    pktgen.range.dst_mac("0", "start", "{dst_mac}")
    pktgen.range.src_mac("0", "start", "{src_mac}")
    pktgen.delay(1000);

    pktgen.range.dst_ip("0", "start", "{dst_ip}")
    pktgen.range.dst_ip("0", "inc", "{dst_ip_inc}")
    pktgen.range.dst_ip("0", "min", "{dst_ip}")
    pktgen.range.dst_ip("0", "max", "{dst_max_ip}")
    pktgen.delay(1000);

    pktgen.range.src_ip("0", "start", "{src_ip}")
    pktgen.range.src_ip("0", "inc", "{src_ip_inc}")
    pktgen.range.src_ip("0", "min", "{src_ip}")
    pktgen.range.src_ip("0", "max", "{src_max_ip}")
    
    pktgen.set_proto("0", "udp")
    pktgen.delay(1000);
    
    pktgen.range.dst_port("0", "start", {dst_port})
    pktgen.range.dst_port("0", "inc", {dst_port_inc})
    pktgen.range.dst_port("0", "min", {dst_port})
    pktgen.range.dst_port("0", "max", {dst_port_max})
    pktgen.delay(1000);

    pktgen.range.src_port("0", "start", {src_port})
    pktgen.range.src_port("0", "inc", {src_port_inc})
    pktgen.range.src_port("0", "min", {src_port})
    pktgen.range.src_port("0", "max", {src_port_max})
    
    pktgen.range.pkt_size("0", "start", {pkt_size})
    pktgen.range.pkt_size("0", "inc", 0)
    pktgen.range.pkt_size("0", "min", {pkt_size})
    pktgen.range.pkt_size("0", "max", {pkt_size})
    
    pktgen.set_range("0", "on");
    pktgen.set("0", "count", 0);
    pktgen.page("stats");
    pktgen.delay(1000);

end

local function start()
    pktgen.start(0);
    print("####### test started  #######")
end

function main()
	setup_range_flow();
	start();
end

main();
"""

# unused for now,
# modification required.
# A) in pod template we attac h 2 port vs 1
# B) in cmd we need accept type of test
# C) we need resolve both PCI addr and pass ( i.e. same semantic as per pair unidirectional )
# D) we switch to this template
# E) We add type of test loop convergence.
#
# Note the same test technically we can do with two pod on two different worker
# if we loopback pkt back.
LUA_UDP_CONVERGENCE_TEMPLATE = """\
package.path = package.path ..";?.lua;test/?.lua;app/?.lua;../?.lua"
require "Pktgen";

local pkt_sizes		= { 64, 128, 256, 512, 1024, 1280, 1518, 2000, 9000 };

local duration         = {duration};
local confirmDuration  = {confirm_duration};
local pauseTime        = {pause_time};

local sendport         = "{send_port}";
local recvport         = "{recv_port}";

local dstip		= "90.90.90.90";
local srcip		= "1.1.1.1";
local netmask		= "/24";

local initialRate      = {initial_rate};

local src_mac          = "{src_mac}";
local dst_mac          = "{dst_mac}";

local function setupTraffic()
    pktgen.set_mac(sendport, "src", src_mac);
    pktgen.set_mac(recvport, "dst", dst_mac);
	pktgen.set_ipaddr(sendport, "dst", dstip);
	pktgen.set_ipaddr(sendport, "src", srcip..netmask);
	pktgen.set_ipaddr(recvport, "dst", srcip);
	pktgen.set_ipaddr(recvport, "src", dstip..netmask);
	pktgen.set_proto(sendport..","..recvport, "udp");
	pktgen.set(sendport, "count", 0);
end

local function runTrial(pkt_size, rate, duration, count)

	local num_tx, num_rx, num_dropped;
	pktgen.clr();
	pktgen.set(sendport, "rate", rate);
	pktgen.set(sendport, "size", pkt_size);

	pktgen.start(sendport);
	file:write("Running trial " .. count .. ". % Rate: " .. rate .. ". Packet Size: " .. pkt_size .. ". Duration (mS):" .. duration .. "\n");
	pktgen.delay(duration);
	pktgen.stop(sendport);
	pktgen.delay(pauseTime);
	statTx = pktgen.portStats(sendport, "port")[tonumber(sendport)];
	statRx = pktgen.portStats(recvport, "port")[tonumber(recvport)];
	num_tx = statTx.opackets;
	num_rx = statRx.ipackets;
	num_dropped = num_tx - num_rx;

	file:write("Tx: " .. num_tx .. ". Rx: " .. num_rx .. ". Dropped: " .. num_dropped .. "\n");
	pktgen.delay(pauseTime);
	return num_dropped;
end

local function runThroughputTest(pkt_size)
	local num_dropped, max_rate, min_rate, trial_rate;

	max_rate = 100;
	min_rate = 1;
	trial_rate = initialRate;
	for count=1, 10, 1
	do
		num_dropped = runTrial(pkt_size, trial_rate, duration, count);
		if num_dropped == 0
		then
			min_rate = trial_rate;
		else
			max_rate = trial_rate;
		end
		trial_rate = min_rate + ((max_rate - min_rate)/2);
	end

	trial_rate = min_rate;
	num_dropped = runTrial(pkt_size, trial_rate, confirmDuration, "Confirmation");
	if num_dropped == 0
	then
		file:write("Max rate for packet size "  .. pkt_size .. "B is: " .. trial_rate .. "\n\n");
	else
		file:write("Max rate of " .. trial_rate .. "% could not be confirmed for 60 seconds as required by rfc2544." .. "\n\n");
	end
end

function main()
	file = io.open("convergence_test.txt", "w");
	setupTraffic();
	for _,size in pairs(pkt_sizes)
	do
		runThroughputTest(size);
	end
	file:close();
end

main();
"""


def parse_testpmd_log(log_lines):
    """
    :param log_lines:
    :return:
    """
    rx_pps_list = []
    tx_pps_list = []

    rx_bytes_list = []
    tx_bytes_list = []

    rx_packets_list = []
    tx_packets_list = []

    rx_missed_list = []
    rx_nombuf_list = []
    rx_err_list = []

    for line in log_lines:
        # RX and TX pps
        if "Rx-pps:" in line:
            match = re.search(r"Rx-pps:\s+(\d+)", line)
            if match:
                rx_pps_list.append(int(match.group(1)))
        elif "Tx-pps:" in line:
            match = re.search(r"Tx-pps:\s+(\d+)", line)
            if match:
                tx_pps_list.append(int(match.group(1)))

        # RX-bytes and TX-bytes
        elif "RX-bytes:" in line:
            match = re.search(r"RX-bytes:\s+(\d+)", line)
            if match:
                rx_bytes_list.append(int(match.group(1)))
        elif "TX-bytes:" in line:
            match = re.search(r"TX-bytes:\s+(\d+)", line)
            if match:
                tx_bytes_list.append(int(match.group(1)))

        # RX and TX packets
        elif "RX-packets:" in line:
            match = re.search(r"RX-packets:\s+(\d+)", line)
            if match:
                rx_packets_list.append(int(match.group(1)))
        elif "TX-packets:" in line:
            match = re.search(r"TX-packets:\s+(\d+)", line)
            if match:
                tx_packets_list.append(int(match.group(1)))

        # RX-missed
        elif "RX-missed:" in line:
            match = re.search(r"RX-missed:\s+(\d+)", line)
            if match:
                rx_missed_list.append(int(match.group(1)))

        # RX-nombuf
        elif "RX-nombuf:" in line:
            match = re.search(r"RX-nombuf:\s+(\d+)", line)
            if match:
                rx_nombuf_list.append(int(match.group(1)))

        # RX-errors
        elif "RX-errors:" in line:
            match = re.search(r"RX-errors:\s+(\d+)", line)
            if match:
                rx_err_list.append(int(match.group(1)))

    # Normalize error/missed/nombuf lengths
    max_len = max(len(rx_pps_list), len(rx_err_list), len(rx_missed_list), len(rx_nombuf_list))
    rx_err_list += [0] * (max_len - len(rx_err_list))
    rx_missed_list += [0] * (max_len - len(rx_missed_list))
    rx_nombuf_list += [0] * (max_len - len(rx_nombuf_list))

    return {
        "rx_pps": np.array(rx_pps_list),
        "tx_pps": np.array(tx_pps_list),
        "rx_bytes": np.array(rx_bytes_list),
        "tx_bytes": np.array(tx_bytes_list),
        "rx_packets": np.array(rx_packets_list),
        "tx_packets": np.array(tx_packets_list),
        "rx_errors": np.array(rx_err_list),
        "rx_missed": np.array(rx_missed_list),
        "rx_nombuf": np.array(rx_nombuf_list),
    }


def safe_print(*_args, sep=" ", end="\n", **kwargs):
    joined_string = sep.join([str(arg) for arg in _args])
    print(joined_string + end, sep=sep, end="", **kwargs)


def get_increments_from_mode(
        mode: str, num_flows: int
):
    """
    :param mode:
    :param num_flows:
    :return:
    """
    ip_inc = "0.0.0.1" if 's' in mode or 'd' in mode else "0.0.0.0"
    increments = {
        "src_ip_inc": ip_inc if 's' in mode else "0.0.0.0",
        "dst_ip_inc": ip_inc if 'd' in mode else "0.0.0.0",
        "src_port_inc": 1 if 'P' in mode or 'S' in mode else 0,
        "dst_port_inc": 1 if 'P' in mode or 'D' in mode else 0,
    }
    return increments


def get_pods(
) -> Tuple[List[str], List[str]]:
    """
    Fetch all pods and return txN and rxN separately.
    Tuple is pair txN t rxN,  where txN is a list of pod names.
    :return: Tuple[List[str], List[str]]: tx_pods and rx_pods
    :raise RuntimeError: if kubectl fails or no tx/rx pods are found
    """
    cmd = "kubectl get pods -o json"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"❌ Failed to get pods: {result.stderr.strip()}")

    try:
        pod_data = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError("❌ Failed to parse pod data from kubectl output.")

    tx_pods = []
    rx_pods = []

    for pod in pod_data["items"]:
        pod_name = pod["metadata"]["name"]
        if pod_name.startswith("tx"):
            tx_pods.append(pod_name)
        elif pod_name.startswith("rx"):
            rx_pods.append(pod_name)

    if not tx_pods:
        raise RuntimeError("❌ No TX pods found (expected pod names like 'tx0', 'tx1', ...)")
    if not rx_pods:
        raise RuntimeError("❌ No RX pods found (expected pod names like 'rx0', 'rx1', ...)")

    tx_pods.sort()
    rx_pods.sort()

    return tx_pods, rx_pods


def get_mac_address(
        pod_name: str
) -> str:
    """Extract MAC address from dpdk-testpmd inside a pod with env var.

    Note we always mask EAL via -a hence TX or RX pod see a single DPDK port.
    All profile use VF's mac address that eliminates -P (promiscuous mode)

    :param pod_name: tx0, tx1, rx0 etc. pod name
    :return: return DPDK interface mac
    """
    check_cmd = f"kubectl exec {pod_name} -- pgrep -f dpdk-testpmd"
    result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)

    if result.returncode == 0:
        raise RuntimeError(f"❌ testpmd is already running in pod {pod_name}. Cannot retrieve MAC address.")

    shell_cmd = "dpdk-testpmd -a \\$PCIDEVICE_INTEL_COM_DPDK --"
    full_cmd = f"kubectl exec {pod_name} -- sh -c \"{shell_cmd}\""
    result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    full_output = result.stdout + result.stderr
    match = re.search(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", full_output)
    return match.group(0) if match else None


def get_numa_cores(
        pod_name: str
) -> Union[str, None]:
    """Extract NUMA core bindings from numactl -s

    We figure out how many core to use on TX or RX side from a numa topology.

    i.e.

    - if pod created with a 2 CPU , it singles core test, thus,
    we always need 1 core fas master core. (read dpdk doc)

    - if pod crate with 5 core  one for master 2 TX 2 for RX

    :param pod_name:  tx0, tx1, rx0 etc. pod name
    :return:
    """
    cmd = f"kubectl exec {pod_name} -- numactl -s"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    for line in result.stdout.splitlines():
        if "physcpubind:" in line:
            return line.split("physcpubind:")[1].strip()
    return None


def collect_pods_related(
        tx_pods: List[str],
        rx_pods: List[str],
        collect_macs: bool = True
) -> Tuple[List[str], List[str], List[str], List[str], List[str], List[str]]:
    """
    From each TX and RX pod collect MAC address and NUMA core list concurrently.

    :param tx_pods: list of TX pods
    :param rx_pods: list of RX pods
    :param collect_macs: whether to collect MAC addresses
    :return: tx_macs, rx_macs, tx_numa, rx_numa, tx_nodes, rx_nodes
    """
    cmd = "kubectl get pods -o json"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    pod_data = json.loads(result.stdout)
    pod_to_node = {
        item["metadata"]["name"]: item["spec"]["nodeName"]
        for item in pod_data["items"]
    }

    def collect_info(pod: str):
        """thread callback"""
        mac_ = get_mac_address(pod).strip() if collect_macs else ""
        _n = get_numa_cores(pod)
        if _n is None:
            raise RuntimeError("failed acquire numa information.")
        numa_ = get_numa_cores(pod).strip()
        node_ = pod_to_node.get(pod, "unknown")
        return pod, mac_, numa_, node_

    all_pods = tx_pods + rx_pods
    results = {}

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(collect_info, pod): pod for pod in all_pods}
        for future in futures:
            pod, mac, numa, node = future.result()
            results[pod] = {"mac": mac, "numa": numa, "node": node}

    # Split back to TX and RX groups
    tx_macs, rx_macs = [], []
    tx_numa, rx_numa = [], []
    tx_nodes, rx_nodes = [], []

    for pod in tx_pods:
        info = results[pod]
        if collect_macs:
            tx_macs.append(info["mac"])
        tx_numa.append(info["numa"])
        tx_nodes.append(info["node"])

    for pod in rx_pods:
        info = results[pod]
        if collect_macs:
            rx_macs.append(info["mac"])
        rx_numa.append(info["numa"])
        rx_nodes.append(info["node"])

    if collect_macs:
        logger.info("\n🧾 TX Pods MAC Addresses & NUMA Cores:")
        for i, pod in enumerate(tx_pods):
            logger.info(f"{pod}: MAC={tx_macs[i]}, NUMA={tx_numa[i]}")

        logger.info("\n🧾 RX Pods MAC Addresses & NUMA Cores:")
        for i, pod in enumerate(rx_pods):
            logger.info(f"{pod}: MAC={rx_macs[i]}, NUMA={rx_numa[i]}")

    return tx_macs, rx_macs, tx_numa, rx_numa, tx_nodes, rx_nodes


def parse_pktgen_port_rate_csv(
        file_path: str
) -> Tuple[Dict[str, np.ndarray], Dict[str, int]]:
    """
    Parses the port_rate_stats.csv collected from Pktgen TX_N pod using plain string ops.
    Returns both metrics and a metadata map indicating column positions.

    :param file_path: path to the CSV file
    :return: Tuple of (metrics dictionary, metadata dictionary)
    """
    metrics = {
        "mbits_tx": [],
        "pkts_tx": [],
        "obytes": [],
        "opackets": [],
        "imissed": [],
        "oerrors": [],
        "rx_nombuf": [],
        "pkts_rx": [],
        "mbits_rx": [],
        "ipackets": [],
        "ibytes": [],
        "ierrors": []
    }

    metadata = {}

    with open(file_path, "r") as f:
        for line_num, line in enumerate(f):
            parts = line.strip().split(",")
            values = parts[1:]
            for idx, kv in enumerate(values):
                if '=' in kv:
                    key, val = kv.split('=')
                    if key in metrics:
                        if line_num == 0:
                            metadata[key] = idx
                        try:
                            metrics[key].append(int(val))
                        except ValueError:
                            metrics[key].append(0)

    return {k: np.array(v) for k, v in metrics.items()}, metadata


def parse_pktgen_port_stats_csv(
        file_path: str
) -> Tuple[Dict[str, np.ndarray], Dict[str, int]]:
    """
    Parses the port_stats.csv collected from Pktgen TX_N pod.
    Returns both metrics and a metadata map indicating column positions.

    :param file_path: path to the CSV file
    :return: Tuple of (metrics dictionary, metadata dictionary)
    """
    base_keys = [
        "rx_nombuf",
        "opackets",
        "imissed",
        "ierrors",
        "ibytes",
        "oerrors",
        "obytes",
        "ipackets"
    ]

    # we add port prefix, so we can merge rate and port stats to single numpy view
    metrics = {f"port_{k}": [] for k in base_keys}
    metadata = {}

    with open(file_path, "r") as f:
        for line_num, line in enumerate(f):
            parts = line.strip().split(",")
            values = parts[1:]  # Skip timestamp
            for idx, kv in enumerate(values):
                if '=' in kv:
                    key, val = kv.split('=')
                    port_key = f"port_{key}"
                    if port_key in metrics:
                        if line_num == 0:
                            metadata[port_key] = idx
                        try:
                            metrics[port_key].append(int(val))
                        except ValueError:
                            metrics[port_key].append(0)

    return {k: np.array(v) for k, v in metrics.items()}, metadata


def copy_flows_to_pod_pair(
        tx: str,
        rx: str
) -> None:
    """ Copy
    :param tx:
    :param rx:
    :return:
    """
    flow_dir = f"flows/{tx}-{rx}"
    if not os.path.exists(flow_dir):
        logger.info(f"⚠️ Warning: Flow directory {flow_dir} does not exist.")
        return

    tar_path = f"/tmp/{tx}-{rx}.tar"
    with tarfile.open(tar_path, "w") as tar:
        for file in os.listdir(flow_dir):
            if file.endswith(".lua"):
                full_path = os.path.join(flow_dir, file)
                tar.add(full_path, arcname=file)

        tar.add("sample.lua", arcname="sample_pktgen.lua")

    logger.info(f"📦 Copying {tar_path} to pod {tx}")
    subprocess.run(f"kubectl cp {tar_path} {tx}:/tmp/", shell=True, check=True)

    logger.info(f"📂 Extracting files inside {tx}")
    try:
        result = subprocess.run(
            f"kubectl exec {tx} -- sh -c 'tar -xf /tmp/{tx}-{rx}.tar -C / > /dev/null 2>&1'",
            shell=True,
            check=True
        )
        logger.info(f"✅ Extraction completed in pod {tx} (exit code: {result.returncode})")
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Failed to extract tar in pod {tx}: {e}")

    os.remove(tar_path)


def copy_flows_to_pods(tx_pods: List[str], rx_pods: List[str]) -> None:
    """Copy all .lua files from flow directories to corresponding TX pods in one go

    :param tx_pods: a list of tx pods
    :param rx_pods: a list of rx pods
    :return:
    """
    if not tx_pods or not rx_pods:
        raise ValueError("❌ TX or RX pods list is empty.")

    if len(tx_pods) != len(rx_pods):
        raise ValueError(
            f"❌ TX and RX pod count mismatch: "
            f"{len(tx_pods)} != {len(rx_pods)}")

    for pod in tx_pods + rx_pods:
        if pod is None or not isinstance(pod, str):
            raise TypeError(f"❌ Invalid pod name: {pod}")

    with ThreadPoolExecutor(max_workers=len(tx_pods)) as pool:
        pool.map(lambda pair: copy_flows_to_pod_pair(*pair), zip(tx_pods, rx_pods))


def load_metadata_file(path: str) -> Dict[str, str]:
    """
    Loads metadata.txt from given path and returns a dictionary of key-value pairs.
    Lines starting with '#' are ignored.
    """
    metadata = {}
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                metadata[key.strip()] = value.strip()
    return metadata


def write_pair_metadata(
        path: str,
        tx_pod: str,
        rx_pod: str,
        tx_mac: str,
        rx_mac: str,
        tx_numa: str,
        rx_numa: str,
        tx_node: str,
        rx_node: str,
        expid: str,
        timestamp: str,
        cmd: argparse.Namespace,
):
    """
    Write metadata.txt for a TX-RX pair into the given path.
    """
    os.makedirs(path, exist_ok=True)
    metadata_path = os.path.join(path, "metadata.txt")

    with open(metadata_path, "w") as f:
        f.write(f"# Experiment Metadata\n")
        f.write(f"expid={expid}\n")
        f.write(f"timestamp={timestamp}\n")
        f.write(f"profile={cmd.profile}\n\n")

        f.write(f"# Pod and Node Information\n")
        f.write(f"tx_pod={tx_pod}\n")
        f.write(f"rx_pod={rx_pod}\n")
        f.write(f"tx_node={tx_node}\n")
        f.write(f"rx_node={rx_node}\n")
        f.write(f"tx_mac={tx_mac}\n")
        f.write(f"rx_mac={rx_mac}\n")
        f.write(f"tx_numa={tx_numa}\n")
        f.write(f"rx_numa={rx_numa}\n\n")

        f.write(f"# Generator Configuration\n")
        for key, value in vars(cmd).items():
            f.write(f"{key}={value}\n")

    logger.info(f"📝 Metadata saved to {metadata_path}")


def move_pktgen_profiles(
        tx_pods: List[str]
) -> None:
    """
    Copy Pktgen.lua inside each TX pod from
    /root/Pktgen-DPDK/ to /usr/local/bin/.
    :param tx_pods:
    :return:
    """
    for tx in tx_pods:
        logger.info(f"📦 Copying Pktgen.lua")
        cmd = f"kubectl exec {tx} -- cp /root/Pktgen-DPDK/Pktgen.lua /usr/local/bin/"
        result = subprocess.run(cmd, shell=True)
        if result.returncode == 0:
            logger.info(f"✅ [OK] {tx}: Copied successfully.")
        else:
            logger.info(f"❌ [ERROR] {tx}: Failed to copy.")


def main_generate(
        cmd: argparse.Namespace
) -> None:
    """

    :param cmd:
    :return:
    """
    tx_pods, rx_pods = get_pods()
    tx_macs, rx_macs, tx_numa, rx_numa, tx_nodes, rx_nodes = collect_pods_related(tx_pods, rx_pods)
    os.makedirs("flows", exist_ok=True)

    flow_counts = parse_int_list(cmd.flows)
    rates = parse_int_list(cmd.rate)
    pkt_sizes = parse_int_list(cmd.pkt_size)

    for rate in rates:
        if not (1 <= rate <= 100):
            logger.info(f"❌ Invalid rate: {rate}. Rate must be between 1 and 100 (inclusive).")
            exit(1)

    for size in pkt_sizes:
        if not (64 <= size <= 9000):
            logger.info(f"❌ Invalid packet size: {size}. Must be between 64 and 9000.")
            exit(1)

    for t, r, tx_mac, rx_mac, tx_numa, rx_numa in zip(tx_pods, rx_pods, tx_macs, rx_macs, tx_numa, rx_numa):
        flow_dir = f"flows/{t}-{r}"
        os.makedirs(flow_dir, exist_ok=True)
        logger.info(f"📂 Generating flows in {flow_dir}")

        for flow, rate, size in product(flow_counts, rates, pkt_sizes):
            render_paired_lua_profile(
                src_mac=tx_mac,
                dst_mac=rx_mac,
                base_src_ip=cmd.base_src_ip,
                base_dst_ip=cmd.base_dst_ip,
                base_src_port=cmd.base_src_port,
                base_dst_port=cmd.base_dst_port,
                rate=rate,
                pkt_size=size,
                num_flows=flow,
                flow_mode=cmd.flow_mode,
                output_dir=flow_dir
            )


def warmup_mac_learning(
        pod: str,
        tx_mac: str,
        cores_str: str,
        warmup_duration: int,
        socket_mem: str
) -> None:
    """Warmup RX side to facilitate mac learning prior a run.

    :param pod: RX pode.
    :param tx_mac:  RX mac address.  This mac address is a destination mac from RX view point.
    :param cores_str:  RX cores number.
    :param warmup_duration:  Duration of warmup in seconds.
    :param socket_mem:
    :return:
    """
    logger.info(f"📡 [Warmup] Sending from {pod} to {tx_mac} to trigger MAC learning")

    warmup_cmd = (
        f"timeout {warmup_duration}s dpdk-testpmd -l {cores_str} -n 4 --socket-mem {socket_mem} "
        f"--proc-type auto --file-prefix warmup_{pod} "
        f"-a $PCIDEVICE_INTEL_COM_DPDK "
        f"-- --forward-mode=txonly --eth-peer=0,{tx_mac} --auto-start --stats-period 1 > /output/warmup.log 2>&1"
    )
    kubectl_cmd = f"kubectl exec {pod} -- sh -c '{warmup_cmd}'"
    result = subprocess.run(kubectl_cmd, capture_output=True, shell=True)
    if result.returncode == 124:
        logger.info(f"📡 [Warmup Done].")


def timeout_handler(exit_code):
    """
    EXIT status:
          124  if COMMAND times out, and --preserve-status is not specified
          125  if the timeout command itself fails
          126  if COMMAND is found but cannot be invoked
          127  if COMMAND cannot be found
          137  if COMMAND (or timeout itself) is sent the KILL (9) signal (128+9)

  -    the exit status of COMMAND otherwise

    :param exit_code:
    :return:
    """


def start_dpdk_testpmd(
        rx_pods: List[str],
        rx_numa: List[str],
        tx_macs: List[str],
        cmd: argparse.Namespace
) -> List[Tuple[str, str, str]]:
    """
        Starts DPDK testpmd in rxonly mode on each RX pod using NUMA-aware CPU pinning.

    For each RX pod:
        - Selects a master core and RX worker cores
        - Sends a warm-up flow to facilitate  MAC address learning
        - Launches testpmd in background with specified core list
        - Verifies that testpmd is running and logging

    By default, we use all core or clamp from value from args.

    :param rx_pods: List of RX pod names (e.g., ["rx0", "rx1"])
    :param rx_numa:  Corresponding list of core strings from `numactl -s` (e.g., ["0 1 2 3", "4 5 6 7"])
    :param tx_macs: MAC addresses from TX pods to use for warmup
    :param cmd:
    :return:   List[Tuple[str, str, str]]:
            A list of tuples, one per RX pod:
              - main_core (str): The master core ID
              - rx_core_str (str): Comma-separated RX cores used
              - all_core_str (str): Comma-separated full core list (main + RX)

    :raise   RuntimeError: If any pod has insufficient cores based on CLI configuration.
    """

    if not (len(rx_pods) == len(rx_numa) == len(tx_macs)):
        raise ValueError("Input lists (rx_pods, rx_numa, tx_macs) must have the same length.")

    rx_core_list = []

    for index, pod in enumerate(rx_pods):
        numa_cores = rx_numa[index].strip().split()
        available_cores = len(numa_cores)

        if available_cores < 2:
            logger.info(f"[⚠️ WARNING] Pod {pod} has only {available_cores} cores; expected at least 2.")
            continue

        # numa_cores = rx_numa[index].strip().split()
        # required = cmd.rx_num_core + 1
        # if len(numa_cores) < required:
        #     raise RuntimeError(
        #         f"❌ {pod} has only {len(numa_cores)} cores; need at least {required} for proper NUMA pinning.")

        if cmd.rx_num_core is None:
            usable_cores = available_cores - 1  # reserve one for master
        else:
            required = cmd.rx_num_core + 1
            if available_cores < required:
                raise RuntimeError(
                    f"❌ {pod} has only {available_cores} cores; need at least {required} for proper pinning.")
            usable_cores = cmd.rx_num_core

        # Now select the cores
        main_core = numa_cores[0]
        rx_cores = numa_cores[1:1 + usable_cores]  # use next N cores
        rx_core_str = ",".join(rx_cores)
        all_core_str = ",".join([main_core] + rx_cores)

        kill_cmd = f"kubectl exec {pod} -- pkill -f dpdk-testpmd"
        subprocess.run(kill_cmd, shell=True)

        # warm up.
        warmup_mac_learning(
            pod=pod,
            tx_mac=tx_macs[index],
            cores_str=all_core_str,
            warmup_duration=cmd.warmup_duration,
            socket_mem=cmd.rx_socket_mem
        )

        # we give kernel/DPDK time to release resources after warmup
        time.sleep(1)
        # duration = max(int(cmd.duration) - 2, 5)

        expected_samples = cmd.duration // cmd.sample_interval
        buffer_per_sample = 2
        total_buffer = expected_samples * buffer_per_sample
        timeout_duration = cmd.duration + total_buffer + 60

        testpmd_cmd = (
            f"timeout {timeout_duration} dpdk-testpmd --main-lcore {main_core} -l {all_core_str} -n 4 "
            f"--socket-mem {cmd.rx_socket_mem} "
            f"--proc-type auto --file-prefix testpmd_rx "
            f"-a $PCIDEVICE_INTEL_COM_DPDK "
            f"-- --forward-mode=rxonly --auto-start --stats-period 1 > /output/stats.log 2>&1 &"
        )

        kubectl_cmd = f"kubectl exec {pod} -- sh -c '{testpmd_cmd}'"
        logger.info(f"🚀 [INFO] Starting testpmd on {pod} → main_core={main_core}, rx_cores={rx_cores}")

        subprocess.run(kubectl_cmd, shell=True)
        time.sleep(2)

        proc_running = subprocess.run(
            f"kubectl exec {pod} -- pgrep dpdk-testpmd",
            shell=True,
            capture_output=True
        ).returncode == 0

        log_ok = subprocess.run(
            f"kubectl exec {pod} -- sh -c 'test -s /output/stats.log && echo OK || echo FAIL'",
            shell=True,
            capture_output=True,
            text=True
        ).stdout.strip() == "OK"

        if proc_running and log_ok:
            logger.info(f"[✅] {pod}: dpdk-testpmd is running and logging.")
        else:
            logger.info(f"[❌] {pod}: dpdk-testpmd may have failed.")

        rx_core_list.append((main_core, rx_core_str, all_core_str))

    return rx_core_list


def generate_sampling_lua_script(
        filepath: str = "sample.lua",
        pkt_file: str = '/tmp/pkt_stats.csv',
        rate_file: str = '/tmp/port_rate_stats.csv',
        port_file: str = '/tmp/port_stats.csv',
):
    """This function generate lua script that we use to sample stats.

    :param filepath:  a path where save (locally before we copy to each pod)
    :param pkt_file:  this is a pkt stats location insider a pod
    :param rate_file: this is a pkt rate stats file location insider a pod
    :param port_file: this is a port  stats file location insider a pod
    :return:
    """
    lua_script = (
        "local ts = os.date('!%Y-%m-%dT%H:%M:%S'); "

        "local rate = pktgen.portStats(0, 'rate'); "
        f"if rate and rate[0] then "
        f"local f1 = io.open('{rate_file}', 'a'); "
        "local str = ts .. ','; "
        "for k,v in pairs(rate[0]) do str = str .. k .. '=' .. tostring(v) .. ',' end; "
        "f1:write(str:sub(1, -2), '\\n'); f1:close(); end; "

        "local pkt = pktgen.pktStats(0)[0]; "
        f"if pkt then "
        f"local f2 = io.open('{pkt_file}', 'a'); "
        "local str = ts .. ','; "
        "for k,v in pairs(pkt) do str = str .. k .. '=' .. tostring(v) .. ',' end; "
        "f2:write(str:sub(1, -2), '\\n'); f2:close(); end; "

        "local port = pktgen.portStats(0, 'port'); "
        f"if port and port[0] then "
        f"local f3 = io.open('{port_file}', 'a'); "
        "local str = ts .. ','; "
        "for k,v in pairs(port[0]) do str = str .. k .. '=' .. tostring(v) .. ',' end; "
        "f3:write(str:sub(1, -2), '\\n'); f3:close(); end; "
    )

    with open("sample.lua", "w") as f:
        f.write(lua_script)


def sample_pktgen_stats_via_socat(
        pod: str,
        cmd: argparse.Namespace,
        pkt_file: str = '/tmp/pkt_stats.csv',
        rate_file: str = '/tmp/port_rate_stats.csv',
        port_file: str = '/tmp/port_stats.csv',
        port: str = '22022'):
    """Sample stats from pktgen using socat as control channel
    and store them in a file."""

    lua_script = (
        "local ts = os.date('!%Y-%m-%dT%H:%M:%S'); "

        "local rate = pktgen.portStats(0, 'rate'); "
        f"if rate and rate[0] then "
        f"local f1 = io.open('{rate_file}', 'a'); "
        "local str = ts .. ','; "
        "for k,v in pairs(rate[0]) do str = str .. k .. '=' .. tostring(v) .. ',' end; "
        "f1:write(str:sub(1, -2), '\\n'); f1:close(); end; "

        "local pkt = pktgen.pktStats(0)[0]; "
        f"if pkt then "
        f"local f2 = io.open('{pkt_file}', 'a'); "
        "local str = ts .. ','; "
        "for k,v in pairs(pkt) do str = str .. k .. '=' .. tostring(v) .. ',' end; "
        "f2:write(str:sub(1, -2), '\\n'); f2:close(); end; "

        "local port = pktgen.portStats(0, 'port'); "
        f"if port and port[0] then "
        f"local f3 = io.open('{port_file}', 'a'); "
        "local str = ts .. ','; "
        "for k,v in pairs(port[0]) do str = str .. k .. '=' .. tostring(v) .. ',' end; "
        "f3:write(str:sub(1, -2), '\\n'); f3:close(); end; "
    )

    # socat_cmd = f"echo \"{lua_script}\" | socat - TCP4:localhost:{port}"
    socat_cmd = f"cat /sample_pktgen.lua | socat - TCP4:localhost:{port}"

    kubectl_cmd = [
        "kubectl", "exec", pod, "--",
        "sh", "-c", socat_cmd
    ]
    result = subprocess.run(kubectl_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = result.stderr.lower()
        if "connection refused" in stderr:
            logger.error(f"❌ [ERROR] Sampling failed on {pod}: connection refused.")
        else:
            logger.error(f"❌ [ERROR] Sampling failed on {pod}: {result.stderr.strip()}")
        return False

    logger.info(f"[✅ {pod}] Updated stats sample complete for pod {pod}.")
    return True


def read_pktgen_stats(
        pod: str,
        file_name: str = '/tmp/port_rate_stats.csv'
):
    """Read the collected stats from the file and print them.
    :param pod:
    :param file_name:
    :return:
    """
    """Read the collected stats from the file and print them."""
    logger.info(f"[🧪] Reading stats from {file_name} on pod {pod}")
    # Read the stats file
    read_cmd = [
        "kubectl", "exec", "-it", pod, "--",
        "cat", file_name
    ]
    result = subprocess.run(read_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode == 0:
        logger.info(f"[🧪] Stats from pod {pod}:")
        logger.info(result.stdout.decode())
    else:
        logger.info(f"[ERROR] Failed to read stats from pod {pod}: {result.stderr.decode()}")


def validate_and_cleanup_lua(
        pod: str,
        profile: str
) -> bool:
    lua_script_path = f"/{profile}"
    check_cmd = f"kubectl exec -it {pod} -- sh -c 'test -s {lua_script_path}'"
    if subprocess.run(check_cmd, shell=True).returncode != 0:
        logger.error(f"❌ [ERROR] Lua script {lua_script_path} missing or empty in {pod}")
        return False

    cleanup_cmd = f"kubectl exec {pod} -- sh -c 'rm -f /tmp/*.csv'"
    subprocess.run(cleanup_cmd, shell=True)
    return True


def launch_pktgen(
        pod: str,
        main_core: str,
        tx_cores: str,
        rx_cores: str,
        all_cores: str,
        cmd: argparse.Namespace,
        session_name: str
):
    """
    Launches pktgen in a Kubernetes pod, either interactively or via tmux session.

    :param pod: Kubernetes TX pod name
    :param main_core: main lcore for pktgen. ( main core is separate core for stats)
    :param tx_cores: TX core range ( a core set for transmit)
    :param rx_cores: RX core range ( a core set for rx processing)
    :param all_cores: All cores used for DPDK
    :param cmd: Argument namespace with flags
    :param session_name:

    :return: subprocess.Popen handle
    """
    lua_script_path = f"/{cmd.profile}"

    expected_samples = cmd.duration // cmd.sample_interval
    buffer_per_sample = 2
    total_buffer = expected_samples * buffer_per_sample
    timeout_duration = cmd.duration + total_buffer + 24

    # base_pktgen_cmd = (
    #     f"cd /usr/local/bin; timeout {timeout_duration} pktgen --no-telemetry -l "
    #     f"{all_cores} -n 4 --socket-mem {cmd.tx_socket_mem} --main-lcore {main_core} "
    #     f"--proc-type auto --file-prefix pg "
    #     f"-a $PCIDEVICE_INTEL_COM_DPDK "
    #     f"-- -G --txd={cmd.txd} --rxd={cmd.rxd} "
    #     f"-f {lua_script_path} -m [{tx_cores}:{rx_cores}].0"
    # )

    pktgen_cmd = (
        f"cd /usr/local/bin; timeout {timeout_duration} pktgen --no-telemetry -l "
        f"{all_cores} -n 4 --socket-mem {cmd.tx_socket_mem} --main-lcore {main_core} "
        f"--proc-type auto --file-prefix pg "
        f"-a $PCIDEVICE_INTEL_COM_DPDK "
        f"-- -G --txd={cmd.txd} --rxd={cmd.rxd} "
        f"-f {lua_script_path} -m [{tx_cores}:{rx_cores}].0"
    )

    kubectl_cmd = f"kubectl exec -it {pod} -- sh -c '{pktgen_cmd}'"
    window_name = pod
    subprocess.run(
        ["tmux", "send-keys", "-t", f"{session_name}:{window_name}", kubectl_cmd, "Enter"])

    # if getattr(cmd, "use_tmux", False):
    #     pktgen_cmd = f"tmux new-session -d -s pktgen '{base_pktgen_cmd}'"
    # else:
    #     pktgen_cmd = base_pktgen_cmd

    logger.debug(f"pktgen command for {pod}: {pktgen_cmd}")
    logger.info(f"[✅] Launching Pktgen on {pod} using profile: {cmd.profile}")


def kill_tmux_session(
        session_name: str
):
    """Kill a tmux session if it exists."""
    if tmux_session_exists(session_name):
        logger.info(f"[💀] Killing existing tmux session: {session_name}")
        subprocess.run(["tmux", "kill-session", "-t", session_name], check=True)


def tmux_session_exists(
        session_name: str
) -> bool:
    """
    :param session_name:
    :return:
    """
    result = subprocess.run(
        ["tmux", "has-session", "-t", session_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    return result.returncode == 0


def ensure_tmux_window_ready(
        session: str,
        window: str,
        timeout: int = 3
):
    """

    :param session:
    :param window:
    :param timeout:
    :return:
    """
    for _ in range(timeout * 10):
        result = subprocess.run(
            ["tmux", "list-windows", "-t", session],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if window in result.stdout:
            return
        time.sleep(0.1)
    raise RuntimeError(f"❌ Timed out waiting for window '{window}' in session '{session}'")


def prepare_tmux_session(
        session_name: str,
        window_names: List[str]
):
    """Kill old tmux session where session_name is run nane , and start N window in tmux for each run.
    :param session_name:
    :param window_names:
    :return:
    """
    kill_tmux_session(session_name)

    logger.info(f"[🧰] Creating tmux session: {session_name}")
    subprocess.run(
        ["tmux", "new-session", "-d", "-s", session_name, "-n", "bootstrap", "bash"],
        check=True
    )

    for win in window_names:
        logger.info(f"[🧰] Creating window: {win} in session: {session_name}")
        subprocess.run(["tmux", "new-window", "-t", session_name, "-n", win], check=True)
        ensure_tmux_window_ready(session_name, win)


def create_tmux_session(
        session_name,
        window_names,
        commands
):
    """
    Creates a tmux session with multiple windows and panes,
    running specified commands.

    :param session_name:
    :param window_names:
    :param commands:
    :return:
    """
    subprocess.run(["tmux", "new-session", "-d", "-s", session_name])

    for window_name, window_commands in zip(window_names, commands):
        subprocess.run(["tmux", "new-window", "-t", session_name, "-n", window_name])
        for i, command in enumerate(window_commands):
            if i > 0:
                subprocess.run(["tmux", "split-window", "-v", "-t", f"{session_name}:{window_name}"])
            subprocess.run(["tmux", "send-keys", "-t", f"{session_name}:{window_name}.{i}", command, "Enter"])

    subprocess.run(["tmux", "attach", "-t", session_name])


def start_pktgen_on_tx_pods(
        tx_pods: List[str],
        tx_numa: List[str],
        cmd: argparse.Namespace
) -> List[Tuple[str, str, str]]:
    """
    Start pktgen inside each TX pod using the specified profile in interactive mode.

    The logic for starting pktgen is as follows:

    1. Start pktgen with the -f flag, where the argument is a Lua script file (i.e., profile).
    2. The Lua script will start the pktgen tester without blocking the execution.
    3. We use Kubernetes (K8s) to sample data from pktgen via the socket interface during the specified duration.
    4. We collect stats over a few intervals for the duration.
    5. After the duration completes, we gracefully stop the pktgen traffic by sending the stop command to the port.
    6. A timeout (`cmd.duration + X`) is used to ensure pktgen is killed sometime in the future, so it is
    terminated correctly.

    :param tx_pods: A list of TX pod names from which to start pktgen.
    :param tx_numa: A list of core assignments from NUMA nodes that the given TX pods can provide.
    :param cmd: Command arguments for packet generation.
    :return: A list of tuples, each tuple being (main_core, tx_core_str, all_core_str).
    """

    if not (len(tx_pods) == len(tx_numa)):
        raise ValueError("Mismatch between number of TX pods and TX NUMA core entries")

    session_name = f"pktgen_{cmd.profile.split('.')[0]}"
    prepare_tmux_session(session_name, tx_pods)

    def run_for_pod(
            i: int,
            pod: str,
            numa_str: str
    ) -> Union[Tuple[str, str, str], None]:
        """
        :param i: 
        :param pod: 
        :param numa_str: 
        :return: 
        """
        numa_cores = tx_numa[i].strip().split()
        # for single core test, we need 2 core one for --master to collect stats.
        if len(numa_cores) < 2:
            logger.info(f"[WARNING] Pod {pod} does not have enough NUMA cores.")
            return None

        # Single core test: If only two cores are available, use them for TX and RX
        main_core = numa_cores[0]
        usable_cores = numa_cores[1:]

        if len(numa_cores) == 2:
            tx_cores = rx_cores = numa_cores[1]
        else:
            total_cores = len(numa_cores)
            txrx_cores = (total_cores - 1) // 2
            if txrx_cores % 2 != 0:
                txrx_cores -= 1

            # it should be sorted, but we handle a case if it not.
            tx_cores = sorted([numa_cores[i + 1] for i in range(txrx_cores)])
            rx_cores = sorted([numa_cores[txrx_cores + 1 + i] for i in range(txrx_cores)])

            tx_core_range = f"{tx_cores[0]}-{tx_cores[-1]}" if len(tx_cores) > 1 else f"{tx_cores[0]}"
            rx_core_range = f"{rx_cores[0]}-{rx_cores[-1]}" if len(rx_cores) > 1 else f"{rx_cores[0]}"
            tx_cores = tx_core_range
            rx_cores = rx_core_range

        all_core_str = ",".join([main_core] + usable_cores)

        if not validate_and_cleanup_lua(pod, cmd.profile):
            return None

        try:
            launch_pktgen(pod, main_core, tx_cores, rx_cores, all_core_str, cmd, session_name)
        except Exception as e:
            logger.error(f"[❌] Failed to launch pktgen in {pod}: {e}")
            return None

        sample_interval = cmd.sample_interval
        sample_count = cmd.sample_count or int(cmd.duration / sample_interval)

        logger.info(f"[{pod}] Sampling stats from pktgen")

        for j in range(sample_count):
            time.sleep(sample_interval)
            success = sample_pktgen_stats_via_socat(pod, cmd, port=cmd.control_port)
            if not success:
                logger.info(f"⚠️ Sampling failed at iteration {j}, pktgen may have terminated.")
                break

        # collect last sample
        sample_pktgen_stats_via_socat(pod, cmd, port=cmd.control_port)
        send_pktgen_stop(pod, cmd.control_port)
        sample_pktgen_stats_via_socat(pod, cmd, port=cmd.control_port)

        if cmd.debug:
            read_pktgen_stats(pod)

        logger.info(f"[✅] Finished pktgen setup for {pod}. Returning core assignment.")
        return main_core, tx_cores, all_core_str

    args_list = [(i, pod, numa) for i, (pod, numa) in enumerate(zip(tx_pods, tx_numa))]
    logger.info(f"[🚀] TX pod worklist: {args_list}")

    with ThreadPoolExecutor(max_workers=len(tx_pods)) as pool:
        results = list(pool.map(lambda a: run_for_pod(*a), args_list))

    logger.info(f"[🔍] Results returned from threads:")
    for idx, result in enumerate(results):
        logger.info(f"  → {tx_pods[idx]}: {result}")

    tx_core_list = [r for r in results if r is not None]

    logger.info(f"[📌] Final tx_core_list: {tx_core_list}")
    if len(tx_core_list) != len(tx_pods):
        logger.info(f"⚠️  Warning: Only {len(tx_core_list)} TX pods "
                    f"successfully launched pktgen out of {len(tx_pods)}")

    return tx_core_list


def stop_testpmd_on_rx_pods(
        rx_pods: List[str]
) -> None:
    """Gracefully stop dpdk-testpmd on RX pods."""
    for pod in rx_pods:
        subprocess.run(f"kubectl exec {pod} -- pkill -SIGINT dpdk-testpmd", shell=True)
        logger.info(f"🛑 Stopped testpmd on {pod}")


def build_stats_filename(
        pod_name: str,
        tx_cores: str,
        rx_cores: str,
        profile_name: str,
        timestamp: str,
        role: str = "rx",
        suffix: str = "spec",
        extension: str = "npz",
        expid: str = ""
) -> str:
    """ Returns a  file name for TX/RX stats results.
    :param pod_name:  Name of pod.
    :param tx_cores:  Number of TX/RX cores.
    :param rx_cores:  Number of RX/TX cores.
    :param profile_name:  Name of profile.
    :param timestamp:  a timestamp.
    :param role:     The role of the pod.
    :param suffix:  The suffix of the stats file.
    :param extension:  The extension of the stats file.
    :param expid:  The experiment id
    :return:
    """
    base_name = profile_name.replace(".lua", "")
    expid_prefix = f"{expid}_" if expid else ""
    return (f"{expid_prefix}{pod_name}_{role}_"
            f"txcores_{tx_cores}_"
            f"rxcores_{rx_cores}_"
            f"{suffix}_{base_name}_"
            f"{timestamp}."
            f"{extension}")


def collect_and_parse_rx_stats(
        rx_pods: List[str],
        tx_cores: str,
        rx_cores: str,
        profile_name: str,
        timestamp: str,
        expid: str,
        output_dir: str = "results",
        sample_from: str = "/output/stats.log"
):
    """  Collect stats from dpdk-testpmd from RX pods.


    :param rx_pods:  a RX pod name.
    :param tx_cores: list of core that used for generation
    :param rx_cores:  list of core that used at receiver.
    :param profile_name: a profile name.
    :param expid:
    :param timestamp:
    :param output_dir: where to save data.
    :param sample_from:
    :return:
    """

    warmup_log_path = "/output/warmup.log"
    os.makedirs(output_dir, exist_ok=True)

    for pod_name in rx_pods:
        logger.info(f"\n📥 Pulling stats.log from {pod_name}...")

        local_log = os.path.join(output_dir, f"{pod_name}_stats.log")
        local_warmup_log = os.path.join(output_dir, f"{pod_name}_warmup.log")

        # copy warm log
        try:
            subprocess.run(
                f"kubectl cp {pod_name}:{warmup_log_path} {local_warmup_log}",
                shell=True, check=True
            )
            logger.info(f"📄 Warmup log saved as {local_warmup_log}")
        except subprocess.CalledProcessError:
            logger.info(f"⚠️  No warmup log found for {pod_name}")

        # copy stats log i.e RX stats
        try:
            subprocess.run(
                f"kubectl cp {pod_name}:{sample_from} {local_log}",
                shell=True, check=True
            )

            logger.info(f"✅ {local_log} copied.")

            with open(local_log, "r") as f:
                lines = f.readlines()

            stats = parse_testpmd_log(lines)
            logger.info(f"\n📈 Stats for {pod_name}:")

            for key, arr in stats.items():
                logger.info(f"{key}: mean={arr.mean():.2f}, min={arr.min()}, max={arr.max()}")

            out_file = build_stats_filename(
                pod_name=pod_name,
                tx_cores=tx_cores,
                rx_cores=rx_cores,
                profile_name=profile_name.replace(".lua", ""),
                timestamp=timestamp,
                role="rx",
                expid=expid
            )
            out_path = os.path.join(output_dir, out_file)

            np.savez(out_path, **stats)
            logger.info(f"💾 Saved parsed stats to {out_path}")

        except Exception as e:
            logger.info(f"❌ Failed for {pod_name}: {e}")


def collect_and_parse_tx_stats(
        tx_pods: List[str],
        tx_cores: str,
        rx_cores: str,
        profile_name: str,
        timestamp: str,
        expid: str,
        output_dir: str = "results",
) -> None:
    """
    Collect stats from TX port, we pool rate and port state
    port_rate_stats.csv on each TX pod is port state, paired with rate that store
    a rate.

    :param tx_pods: List of TX pod names.
    :param tx_cores: list of tx core, it used to write metadata in filename
    :param rx_cores: list of rx core, it used to write metadata in filename
    :param timestamp: timestamp
    :param expid: experiment id
    :param profile_name: Profile name used in this test.
    :param output_dir: Where to save results.
    """
    os.makedirs(output_dir, exist_ok=True)

    for pod_name in tx_pods:

        rate_file = os.path.join(output_dir, f"{pod_name}_port_rate_stats.csv")
        port_file = os.path.join(output_dir, f"{pod_name}_port_stats.csv")

        logger.info(f"\n📥 Pulling TX stats from {pod_name}...")

        try:
            subprocess.run(
                f"kubectl cp {pod_name}:/tmp/port_rate_stats.csv {rate_file}",
                shell=True, check=True
            )
            subprocess.run(
                f"kubectl cp {pod_name}:/tmp/port_stats.csv {port_file}",
                shell=True, check=True
            )

            rate_stats, _ = parse_pktgen_port_rate_csv(rate_file)
            port_stats, _ = parse_pktgen_port_stats_csv(port_file)

            logger.info(f"✅ {rate_file} and {port_file} copied.")
            combined_stats = {**rate_stats, **port_stats}

            logger.info(f"\n📊 TX Stats Summary for {pod_name}:")
            for key, arr in combined_stats.items():
                logger.info(f"{key}: mean={arr.mean():.2f}, min={arr.min()}, max={arr.max()}")

            out_file = build_stats_filename(
                pod_name=pod_name,
                tx_cores=tx_cores,
                rx_cores=rx_cores,
                profile_name=profile_name.replace(".lua", ""),
                timestamp=timestamp,
                role="tx",
                expid=expid
            )
            out_path = os.path.join(output_dir, out_file)

            np.savez(out_path, **combined_stats)
            logger.info(f"💾 Saved TX stats to {out_path}")

        except Exception as e:
            logger.info(f"❌ Failed to collect TX stats for {pod_name}: {e}")


def generate_experiment_id(
        profile_name,
        tx_cores,
        rx_cores,
        timestamp
):
    base_str = f"{profile_name}_{tx_cores}_{rx_cores}_{timestamp}"
    return hashlib.md5(base_str.encode()).hexdigest()[:8]  # short ID


def debug_dump_npz_results(
        result_dir: str = "results"
) -> None:
    """
    If debug flag is set, this prints all .npz files found in the result directory.

    :param result_dir:
    :return:
    """
    from glob import glob
    logger.info("\n🧪 DEBUG: Dumping parsed .npz result files:")
    for npz_file in sorted(glob(os.path.join(result_dir, "*.npz"))):
        logger.info(f"\n📂 {npz_file}")
        try:
            data = np.load(npz_file)
            for key in data:
                arr = data[key]
                logger.info(f"🔹 {key}: shape={arr.shape}, "
                            f"mean={arr.mean():.2f}, "
                            f"min={arr.min()}, "
                            f"max={arr.max()}")
        except Exception as e:
            logger.info(f"❌ Failed to read {npz_file}: {e}")


def send_pktgen_stop(
        pod: str,
        control_port: str,
        timeout: int = 5
) -> bool:
    """stop pktgen via socket interface, i.e. Send 'pktgen.stop(0)' to pktgen via socat.
    :param pod: a tx pod
    :param control_port: tcp port that pktgen listen
    :param timeout: timeout for tcp connection
    :return:
    """
    lua_stop_cmd = f"echo 'pktgen.stop(0)' | socat - TCP4:localhost:{control_port}"
    kubectl_cmd = f"kubectl exec {pod} -- sh -c \"{lua_stop_cmd}\""

    logger.info(f"🛑 Sending stop command to Pktgen on pod {pod} (port {control_port})")
    try:
        result = subprocess.run(
            kubectl_cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout
        )

        if result.returncode == 0:
            logger.info(f"✅ pktgen.stop(0) sent successfully to {pod}")
            return True
        else:
            logger.info(f"⚠️ [WARNING] Failed to send stop to {pod} (exit={result.returncode})")
            logger.info(result.stderr.decode())
            return False

    except subprocess.TimeoutExpired:
        logger.info(f"⏱️ Timeout while sending pktgen.stop(0) to {pod}")
        return False


def main_start_generator(
        cmd: argparse.Namespace
) -> None:
    """ Starts dpdk_testpmd on RX pods and pktgen on TX pods unless skipped via flags.
    :param cmd: args
    :return: Nothing
    """
    tx_pods, rx_pods = get_pods()
    tx_macs, rx_macs, tx_numa, rx_numa, tx_nodes, rx_nodes = collect_pods_related(tx_pods, rx_pods)

    # we always should have valid pairs. if we don't something is wrong here.
    if len(tx_pods) != len(rx_pods):
        raise RuntimeError(f"❌ Pod count mismatch: "
                           f"{len(tx_pods)} TX pods vs {len(rx_pods)} RX pods")

    if len(tx_macs) != len(tx_pods):
        raise RuntimeError(f"❌ TX MAC count mismatch:"
                           f" {len(tx_macs)} MACs for {len(tx_pods)} TX pods")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    expid = hashlib.md5(f"{cmd.profile}_{timestamp}".encode()).hexdigest()[:8]
    base_output_dir = os.path.join("results", f"{expid}")

    logger.info(f"📁 Results will be saved in: {base_output_dir}")

    generate_sampling_lua_script()

    if not cmd.skip_copy:
        copy_flows_to_pods(tx_pods, rx_pods)
    else:
        logger.info("⏭️  Skipping Lua profile copy step (--skip-copy)")

    rx_core_list = []
    if not cmd.skip_testpmd:
        rx_core_list = start_dpdk_testpmd(rx_pods, rx_numa, tx_macs, cmd)
    else:
        logger.info("⏭️  Skipping testpmd launch on RX pods (--skip-testpmd)")

    move_pktgen_profiles(tx_pods)
    tx_core_list = start_pktgen_on_tx_pods(tx_pods, tx_numa, cmd)
    # we sleep a bit, to let all pkt receive.
    time.sleep(60)
    stop_testpmd_on_rx_pods(rx_pods)

    logger.info("✅ Test run complete. Collecting stats...")

    # if any pod failed we will not have same pairs.
    # TOOD add logic to handle only successfully pairs
    if len(tx_core_list) != len(tx_pods):
        logger.info(f"⚠️  Warning: Only {len(tx_core_list)} "
                    f"TX pods successfully launched pktgen out of {len(tx_pods)}")
    if len(rx_core_list) != len(rx_pods):
        logger.info(f"⚠️  Warning: Only {len(rx_core_list)} "
                    f"RX pods successfully launched testpmd out of {len(rx_pods)}")

    for i, (tx_pod, rx_pod) in enumerate(zip(tx_pods, rx_pods)):
        # // trade block or sub-process
        # // we can serialize pktgen output to rest like interface
        # //
        tx_main, tx_cores, tx_all = tx_core_list[i]
        rx_main, rx_cores, rx_all = rx_core_list[i]

        pair_dir = os.path.join(base_output_dir, f"{tx_pod}-{rx_pod}", args.profile.split(".")[0])
        logger.info(f"📁 Results will be saved in: {pair_dir}")
        os.makedirs(pair_dir, exist_ok=True)

        write_pair_metadata(
            path=pair_dir,
            tx_pod=tx_pod,
            rx_pod=rx_pod,
            tx_mac=tx_macs[i],
            rx_mac=rx_macs[i],
            tx_numa=tx_numa[i],
            rx_numa=rx_numa[i],
            tx_node=tx_nodes[i],
            rx_node=rx_nodes[i],
            expid=expid,
            timestamp=timestamp,
            cmd=cmd
        )

        collect_and_parse_tx_stats(
            [tx_pod],
            tx_cores=tx_cores,
            rx_cores=rx_cores,
            timestamp=timestamp,
            expid=expid,
            profile_name=cmd.profile,
            output_dir=pair_dir
        )

        collect_and_parse_rx_stats(
            [rx_pod],
            tx_cores=tx_cores,
            rx_cores=rx_cores,
            timestamp=timestamp,
            expid=expid,
            profile_name=cmd.profile,
            output_dir=pair_dir
        )

        if cmd.debug:
            debug_dump_npz_results(pair_dir)

    logger.info("📁 All results saved in 'results/' directory.")


def parse_int_list(csv: str) -> List[int]:
    return [int(v.strip()) for v in csv.split(",") if v.strip()]


def render_converge_lua_profile(
        duration: int,
        confirm_duration: int,
        pause_time: int,
        send_port: str,
        recv_port: str,
        src_ip: str,
        dst_ip: str,
        netmask: str,
        initial_rate: int,
        src_mac: str,
        dst_mac: str
) -> str:
    """
    Generate a Lua script for pkt convergence testing using the given parameters.
    :return: A formatted Lua script as a string.
    """
    return LUA_UDP_CONVERGENCE_TEMPLATE.format(
        duration=duration,
        confirm_duration=confirm_duration,
        pause_time=pause_time,
        send_port=send_port,
        recv_port=recv_port,
        src_ip=src_ip,
        dst_ip=dst_ip,
        netmask=netmask,
        initial_rate=initial_rate,
        src_mac=src_mac,
        dst_mac=dst_mac
    )


def render_paired_lua_profile(
        src_mac: str,
        dst_mac: str,
        base_src_ip: str,
        base_dst_ip: str,
        base_src_port: str,
        base_dst_port: str,
        rate: int,
        pkt_size: int,
        num_flows: int,
        flow_mode: str,
        output_dir: str
) -> None:
    """
    Renders lua profiles, we take template and replace value based
    on what we need. Specifically that focus on range capability with increment on
    pktgen side.

    :param src_mac: a src mac that we resolve via kubectl from pod.
    :param dst_mac: a dst mac that we resolve via kubectl from pod.
    :param base_src_ip: base ip address of source pod.
    :param base_dst_ip: base ip address of destination pod.
    :param base_src_port: base port of source pod.
    :param base_dst_port: base port of destination pod.
    :param rate: rate of lua profile generation ( percentage from port speeed) - it rate cmd in pktgen
    :param pkt_size: pkt size that we set via pktgen pkt size cmd.
    :param num_flows: number of flows we want to generate.
    :param flow_mode: flow mode.
    :param output_dir: where to save data.
    :return:
    """
    os.makedirs(output_dir, exist_ok=True)
    base_src = ip_address(base_src_ip)
    base_dst = ip_address(base_dst_ip)
    src_port = int(base_src_port)
    dst_port = int(base_dst_port)

    #  max values for ranges in IP space
    src_max_ip = str(base_src + num_flows - 1) if "s" in flow_mode else str(base_src)
    dst_max_ip = str(base_dst + num_flows - 1) if "d" in flow_mode else str(base_dst)

    src_port_max = src_port + num_flows - 1 if "S" in flow_mode else src_port
    dst_port_max = dst_port + num_flows - 1 if "D" in flow_mode else dst_port

    ip_inc = "0.0.0.1"
    src_ip_inc = ip_inc if "s" in flow_mode else "0.0.0.0"
    dst_ip_inc = ip_inc if "d" in flow_mode else "0.0.0.0"
    src_port_inc = 1 if "S" in flow_mode else 0
    dst_port_inc = 1 if "D" in flow_mode else 0

    filename = f"profile_{num_flows}_flows_pkt_size_{pkt_size}B_{rate}_rate_{flow_mode}.lua"
    output_file = os.path.join(output_dir, filename)

    with open(output_file, "w") as f:
        f.write(LUA_UDP_TEMPLATE.format(
            rate=rate,
            dst_mac=dst_mac,
            src_mac=src_mac,

            dst_ip=str(base_dst),
            dst_ip_inc=dst_ip_inc,
            dst_max_ip=dst_max_ip,

            src_ip=str(base_src),
            src_ip_inc=src_ip_inc,
            src_max_ip=src_max_ip,

            dst_port=dst_port,
            dst_port_inc=dst_port_inc,
            dst_port_max=dst_port_max,

            src_port=src_port,
            src_port_inc=src_port_inc,
            src_port_max=src_port_max,

            pkt_size=pkt_size
        ))
    logger.info(f"[✔] Generated: {output_file}")


def upload_npz_to_wandb(
        result_dir="results",
        expid=None
):
    """
    Uploads all .npz files in the result directory to Weights & Biases (wandb).
    :param result_dir: Directory containing result files.
    :param expid: Optional experiment ID for grouping TX/RX results.
    """
    run_name = f"pktgen_run_{expid}" if expid else f"pktgen_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    wandb.init(project="dpdk-benchmarks", name=run_name)

    for file in os.listdir(result_dir):
        if file.endswith(".npz"):
            file_path = os.path.join(result_dir, file)
            logger.info(f"📤 Uploading {file} to wandb...")
            wandb.save(file_path)

    wandb.finish()


def main(cmd: argparse.Namespace) -> None:
    """ main block
    :param cmd:
    :return:
    """
    tx_pods, rx_pods = get_pods()
    tx_macs, rx_macs, tx_numa, rx_numa, tx_nodes, rx_nodes = collect_pods_related(tx_pods, rx_pods)
    os.makedirs("flows", exist_ok=True)

    flow_counts = parse_int_list(cmd.flows)
    rates = parse_int_list(cmd.rate)
    pkt_sizes = parse_int_list(cmd.pkt_size)

    for t, r, tx_mac, rx_mac, tx_numa, rx_numa in zip(
            tx_pods, rx_pods, tx_macs, rx_macs, tx_numa, rx_numa):
        d = f"flows/{t}-{r}"
        logger.info(t, r, tx_mac, rx_mac, tx_numa, rx_numa)
        os.makedirs(d, exist_ok=True)
        for num_flows, rate, pkt_size in product(flow_counts, rates, pkt_sizes):
            render_paired_lua_profile(
                src_mac=tx_mac,
                dst_mac=rx_mac,
                base_src_ip=cmd.base_src_ip,
                base_dst_ip=cmd.base_dst_ip,
                base_src_port=cmd.base_src_port,
                base_dst_port=cmd.base_dst_port,
                rate=rate,
                pkt_size=pkt_size,
                num_flows=num_flows,
                flow_mode=cmd.flow_mode,
                output_dir=d
            )


def discover_available_profiles(
) -> List[str]:
    """Scan 'flows' directory and return a list of available profile i.e. Lua files.
    that we push to TX pod.
    :return:  a list of profile, where profile is seperated lua file.
    """
    profiles = set()
    if not os.path.exists("flows"):
        return []

    for pod_dir in os.listdir("flows"):
        pod_path = os.path.join("flows", pod_dir)
        if os.path.isdir(pod_path):
            for file in os.listdir(pod_path):
                if file.endswith(".lua"):
                    profiles.add(file)
    return sorted(profiles)


def upload_npz_to_wandb(result_dir="results", expid=None):
    """
    Uploads and logs contents of .npz files from result_dir to wandb for visualization.
    """
    import glob

    npz_files = glob.glob(os.path.join(result_dir, "*.npz"))
    if expid:
        npz_files = [f for f in npz_files if expid in os.path.basename(f)]

    if not npz_files:
        logger.info(f"⚠️ No .npz files found for expid={expid} in {result_dir}")
        return

    run_name = f"pktgen_run_{expid}" if expid else f"pktgen_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    wandb.init(project="dpdk-benchmarks", name=run_name)

    for file in npz_files:
        logger.info(f"📤 Logging metrics from: {file}")
        data = np.load(file)

        # Convert to series-style logging
        length = len(next(iter(data.values())))
        for i in range(length):
            log_dict = {"step": i}
            for key in data:
                log_dict[key] = data[key][i].item() if isinstance(data[key][i], np.generic) else data[key][i]
            wandb.log(log_dict)

    wandb.finish()


def is_power_of_two(n): return n > 0 and (n & (n - 1)) == 0


def setup_logging(
        log_level: str,
        log_output: str = "console",
        log_file: str = "benchmark.log"
):
    """

    :param log_level:
    :param log_output:
    :param log_file:
    :return:
    """
    handlers = []

    console_formatter = logging.Formatter("%(message)s")
    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"
    )

    if log_output in ("console", "both"):
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(console_formatter)
        handlers.append(console_handler)

    if log_output in ("file", "both"):
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(file_formatter)
        handlers.append(file_handler)

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        handlers=handlers
    )


def clean_up(cmd: argparse.Namespace):
    """This routine cleanup on interrupts  (KeyboardInterrupt) etc
     - Kill tmux session
    - Stop testpmd on RX pods
    - Kill pktgen in TX pods
    :param cmd:
    :return:
    """

    tx_pods, rx_pods = get_pods()

    try:
        stop_testpmd_on_rx_pods(rx_pods)
        logger.info("🧼 Stopped testpmd on all RX pods")
    except Exception as e:
        logger.error(f"❌ Failed to stop testpmd: {e}")

    try:
        for pod in tx_pods:
            subprocess.run(
                ["kubectl", "exec", pod, "--", "pkill", "-9", "pktgen"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        logger.info("🧯 Force-killed pktgen in TX pods")

        # delete stale files inside each tx pod
        for pod in tx_pods:
            subprocess.run(
                ["kubectl", "exec", pod, "--", "rm", "-f", "/tmp/*.csv", "/sample_pktgen.lua"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        logger.info("🗑️  Removed temporary CSV and Lua files from TX pods")


    except Exception as e:
        logger.error(f"❌ Failed to kill pktgen in TX pods: {e}")

    logger.warning("🧹 Starting cleanup...")
    session = f"pktgen_{cmd.profile.split('.')[0]}"
    try:
        kill_tmux_session(session)
        logger.info(f"🧹 Killed tmux session: {session}")
    except Exception as e:
        logger.error(f"❌ Failed to kill tmux session: {e}")


if __name__ == '__main__':


    if not shutil.which("kubectl"):
        raise RuntimeError("❌ 'kubectl' is not found in PATH. Please install or configure it properly.")

    parser = argparse.ArgumentParser(
        description="""🧪 DPDK Lua Flow Generator & Test Driver

    This tool helps generate Pktgen Lua profiles and start test traffic in a Kubernetes environment using DPDK.

    🛠 Usage Modes:
       ▸ generate_flow   - Generates target test profile for pktgen based on flow, size, and rate combinations
       ▸ start_generator - Launches pktgen on TX pods and testpmd on RX pods using a selected profile

    🔰 Example Usage:

       🔹 Generate multiple profiles:
          $ python packet_generator.py generate_flow --rate 10,50,100 --pkt-size 64,512,1500 --flows 1,100

       🔹 Start with a selected profile:
          $ python packet_generator.py start_generator --profile flow_1flows_64B_100rate.lua

    💡 Notes:
       - You must run `generate_flow` first to create profiles in the ./flows/ directory.
       - Profiles are matched by filename, e.g. flow_1flows_64B_100rate.lua
    """,
        formatter_class=argparse.RawTextHelpFormatter
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    gen = subparsers.add_parser("generate_flow", help="🛠 Generate Pktgen Lua flows")
    gen.add_argument("--base-src-ip", default="192.168.1.1", help="Base source IP")
    gen.add_argument("--base-dst-ip", default="192.168.2.1", help="Base destination IP")
    gen.add_argument("--base-src-port", default="1024", help="Base source port")
    gen.add_argument("--base-dst-port", default="1024", help="Base destination port")
    gen.add_argument("--flows", type=str, default="1",
                     help="Comma-separated flow counts (e.g., 1,100,10000)")
    gen.add_argument("--rate", type=str, default="10",
                     help="Comma-separated rates (e.g., 10,50,100)")
    gen.add_argument("--pkt-size", type=str, default="64",
                     help="Comma-separated packet sizes (e.g., 64,128,512,1500,2000,9000)")
    gen.add_argument(
        "--flow-mode",
        type=str,
        default="s",
        choices=["s", "sd", "sp", "dp", "spd", "sdpp", "sdpd"],
        help=(
            "Flow generation mode (default: s)\n"
            "  s    - Increment Source IP only\n"
            "  sd   - Increment Source and Destination IPs\n"
            "  sp   - Increment Source IP + Source Port\n"
            "  dp   - Increment Source IP + Destination Port\n"
            "  spd  - Source IP + Port + Destination IP\n"
            "  sdpd - Source IP + Port, Destination IP + Port"
        )
    )

    start = subparsers.add_parser("start_generator", help="🚀 Start pktgen & testpmd using selected profile")
    start.add_argument("--txd", type=int, default=2048, help="🚀 TX (Transmit) descriptor count")
    start.add_argument("--rxd", type=int, default=2048, help="📡 RX (Receive) descriptor count")

    start.add_argument(
        "--warmup-duration", type=int, default=4,
        help="🧪 Warmup duration in seconds to trigger MAC learning (default: 2)"
    )

    start.add_argument(
        "--rx-socket-mem", type=str, default="2048",
        help="📦 Socket memory for RX side testpmd (default: 2048)"
    )

    start.add_argument(
        "--tx-socket-mem", type=str, default="2048",
        help="📦 Socket memory for TX side pktgen (default: 2048)"
    )

    start.add_argument("--tx_num_core", type=int, default=None,
                       help="🚀 Number of cores to use for generation. "
                            "If not set, uses all available cores minus one for main.")

    start.add_argument("--rx_num_core", type=int, default=None,
                       help="🧠 Number of cores to use at receiver side. "
                            "If not set, uses all available cores minus one for main.")

    start.add_argument("--interactive", default=False, action="store_true",
                       help="Run pktgen with -it (interactive mode)")

    start.add_argument("--use-tmux", default=False, action="store_true",
                       help="Run pktgen inside tmux session")

    start.add_argument("--control-port", type=str, default="22022",
                       help="🔌 Pktgen control port used for socat communication (default: 22022)")
    start.add_argument("--sample-interval", type=int, default=10,
                       help="📈 Interval (in seconds) between pktgen stat samples (default: 10s)")
    start.add_argument("--sample-count", type=int, default=None,
                       help="🔁 Number of samples to collect. "
                            "If not set, will use duration/sample-interval")
    start.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level (default: INFO)"
    )

    start.add_argument(
        "--log-output",
        choices=["console", "file", "both"],
        default="console",
        help="Where to log: 'console', 'file', or 'both' (default: console)"
    )
    start.add_argument(
        "--log-file",
        default="benchmark.log",
        help="Log file name if using file or both (default: benchmark.log)"
    )

    start.add_argument(
        "--debug", action="store_true",
        help="🔍 Debug: Load and display contents of .npz results after test"
    )
    start.add_argument(
        "--skip-copy", action="store_true",
        help="⏭️  Skip copying Lua profiles and Pktgen.lua into TX pods"
    )
    start.add_argument(
        "--skip-testpmd", action="store_true",
        help="⏭️  Skip launching testpmd in RX pods"
    )
    start.add_argument(
        "--duration", type=int, default=60,
        help="⏱ Duration in seconds to run pktgen before stopping testpmd"
    )

    # Discover available profiles
    available_profiles = discover_available_profiles()
    profile_help = (
        "📁 Available profiles:\n" +
        "\n".join(f"  🔹 {p}" for p in available_profiles)
        if available_profiles else
        "⚠️  No profiles found. Please run `generate_flow` first."
    )

    start.add_argument(
        "--profile", type=str, required=True, metavar="<profile>", help=profile_help
    )

    upload = subparsers.add_parser("upload_wandb", help="📤 Upload existing results to Weights & Biases")
    upload.add_argument("--expid", type=str, required=False, help="Experiment ID used in filenames")
    upload.add_argument("--result-dir", type=str, default="results", help="Directory containing .npz results")

    args = parser.parse_args()

    log_level = getattr(args, "log_level", "INFO")
    log_output = getattr(args, "log_output", "console")
    log_file = getattr(args, "log_file", "benchmark.log")

    setup_logging(args.log_level, args.log_output, args.log_file)

    if args.command == "start_generator":
        if args.profile not in available_profiles:
            print(f"\n❌ Invalid profile: {args.profile}")
            print("📂 Run with `--help` to see available profiles.")
            exit(1)

    if args.command == "generate_flow":
        main_generate(args)
    elif args.command == "start_generator":
        if not (1024 <= int(args.control_port) <= 65535):
            raise ValueError(f"❌ Control port {args.control_port} is out of valid range.")
        if args.tx_num_core is not None and args.tx_num_core < 1:
            raise ValueError("❌ --tx_num_core must be >= 1 if specified.")
        if args.rx_num_core is not None and args.rx_num_core < 1:
            raise ValueError("❌ --rx_num_core must be >= 1 if specified.")
        if args.sample_interval < 1:
            raise ValueError("❌ --sample-interval must be >= 1 second.")
        if args.duration <= 0:
            raise ValueError("❌ --duration must be > 0.")
        if args.sample_interval >= args.duration:
            raise ValueError("❌ --sample-interval must be less than --duration.")
        if not is_power_of_two(args.txd):
            raise ValueError("❌ --txd must be a power of 2.")
        if not is_power_of_two(args.rxd):
            raise ValueError("❌ --rxd must be a power of 2.")
        try:
            main_start_generator(args)
        except KeyboardInterrupt:
            logger.warning("🛑 KeyboardInterrupt received! Attempting cleanup...")
            session = f"pktgen_{args.profile.split('.')[0]}"
            try:
                session = f"pktgen_{args.profile.split('.')[0]}"
                kill_tmux_session(session)
                logger.info(f"🧹 Killed tmux session: {session}")
            except Exception as e:
                logger.error(f"❌ Failed to kill tmux session: {e}")

    elif args.command == "upload_wandb":
        upload_npz_to_wandb(result_dir=args.result_dir, expid=args.expid)
