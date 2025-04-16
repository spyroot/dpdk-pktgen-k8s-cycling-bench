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
import glob
import hashlib
import json
import logging
import os
import shutil
import sys
import re
import subprocess
import tarfile
import threading
import time
from datetime import datetime
from ipaddress import ip_address
from itertools import product
from shlex import shlex
from typing import List, Optional, Union
from typing import Tuple, Dict
from concurrent.futures import ThreadPoolExecutor
import csv

import numpy as np
import wandb
import shlex

import paramiko
from threading import Lock


class SSHConnectionManager:
    def __init__(self, username: str, password: str):

        self.username = username
        self.password = password
        self.connections = {}
        self.lock = Lock()
        self.closed = False

    def get_connection(
            self, host: str
    ) -> paramiko.SSHClient:
        """

        :param host:
        :return:
        """
        with self.lock:
            client = self.connections.get(host)
            if client:
                transport = client.get_transport()
                if transport and transport.is_active():
                    return client
                else:
                    # 🔄 reconnect if transport dead
                    try:
                        client.close()
                    except Exception:
                        pass
                    del self.connections[host]

            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(hostname=host, username=self.username, password=self.password,
                           look_for_keys=False, allow_agent=False)
            client.get_transport().set_keepalive(30)
            self.connections[host] = client
            return client

    def close_all(self):
        with self.lock:
            for client in self.connections.values():
                client.close()
            self.connections.clear()
            self.closed = True
            print("🧹 SSH connections closed.")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close_all()


logger = logging.getLogger(__name__)

# this base lua for range flow template
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

LUA_UDP_LATENCY_TEMPLATE_CONVERGENCE = """\
package.path = package.path ..";?.lua;test/?.lua;app/?.lua;"
require "Pktgen"

local pkt_sizes = {{pkt_sizes}};
local duration = {duration};
local confirmDuration = {confirm_duration};
local pauseTime = {pause_time};

local sendport = "0";
local recvport = "1";

local dstip = "{dst_ip}";
local srcip = "{src_ip}";
local netmask = "{netmask}";
local initialRate = {initial_rate};

local function setup(rate, pktsize)
    pktgen.dst_mac("0", "start", "{dst_mac_port0}")
    pktgen.src_mac("0", "start", "{src_mac_port0}")

    pktgen.dst_mac("1", "start", "{dst_mac_port1}")
    pktgen.src_mac("1", "start", "{src_mac_port1}")

    pktgen.set_ipaddr(sendport, "dst", dstip)
    pktgen.set_ipaddr(sendport, "src", srcip..netmask)

    pktgen.set_ipaddr(recvport, "dst", srcip)
    pktgen.set_ipaddr(recvport, "src", dstip..netmask)

    pktgen.set_proto(sendport..","..recvport, "udp")

    pktgen.set(sendport, "count", 0)
    pktgen.set(sendport, "rate", rate)
    pktgen.set(sendport, "size", pktsize)

    pktgen.latency(sendport, "enable")
    pktgen.latency(sendport, "rate", 1000)
    pktgen.latency(sendport, "entropy", 12)

    pktgen.latency(recvport, "enable")
    pktgen.latency(recvport, "rate", 10000)
    pktgen.latency(recvport, "entropy", 8)
end

local function runTrial(pkt_size, rate, duration, count)
    pktgen.clr()
    pktgen.set(sendport, "rate", rate)
    pktgen.set(sendport, "size", pkt_size)

    pktgen.start(sendport)
    pktgen.delay(duration)
    pktgen.stop(sendport)

    pktgen.delay(pauseTime)
end

local function run(pkt_size)

    local max_rate = 100
    local min_rate = 1
    local trial_rate = initialRate
    local num_dropped

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
	
    trial_rate = min_rate
    runTrial(pkt_size, trial_rate, confirmDuration, 0)
end

function main()

    pkt_size=pkt_sizes[1]
    setup(initialRate, pkt_size)
    run(pkt_size)
end

main()
"""

LUA_UDP_LATENCY_TEMPLATE_FIXED = """\
package.path = package.path ..";?.lua;test/?.lua;app/?.lua;"
require "Pktgen"

local pkt_sizes = {{pkt_sizes}};
local duration = {duration};
local confirmDuration = {confirm_duration};
local pauseTime = {pause_time};

local sendport = "0";
local recvport = "1";

local dstip = "{dst_ip}";
local srcip = "{src_ip}";
local netmask = "{netmask}";
local initialRate = {initial_rate};

local function setup(rate, pktsize)
    pktgen.dst_mac("0", "start", "{dst_mac_port0}")
    pktgen.src_mac("0", "start", "{src_mac_port0}")

    pktgen.dst_mac("1", "start", "{dst_mac_port1}")
    pktgen.src_mac("1", "start", "{src_mac_port1}")

    pktgen.set_ipaddr(sendport, "dst", dstip)
    pktgen.set_ipaddr(sendport, "src", srcip..netmask)

    pktgen.set_ipaddr(recvport, "dst", srcip)
    pktgen.set_ipaddr(recvport, "src", dstip..netmask)

    pktgen.set_proto(sendport..","..recvport, "udp")

    pktgen.set(sendport, "count", 0)
    pktgen.set(sendport, "rate", rate)
    pktgen.set(sendport, "size", pktsize)

    pktgen.latency(sendport, "enable")
    pktgen.latency(sendport, "rate", 1000)
    pktgen.latency(sendport, "entropy", 12)

    pktgen.latency(recvport, "enable")
    pktgen.latency(recvport, "rate", 10000)
    pktgen.latency(recvport, "entropy", 8)
end

local function runTrial(pkt_size, rate, duration, count)

    pktgen.clr()
    pktgen.set(sendport, "rate", rate)
    pktgen.set(sendport, "size", pkt_size)

    pktgen.start(sendport)
    pktgen.delay(duration)
    pktgen.stop(sendport)

    pktgen.delay(pauseTime)
end


function main()
    pkt_size = pkt_sizes[1]
    setup(initialRate, pkt_size)
    runTrial(pkt_size, initialRate, confirmDuration, 0)
end

main()
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


def discover_experiments(root_dir="results"):
    """Return a list of (exp_id, tx_file_path) tuples for sorting and processing."""
    experiments = []
    for dirpath, _, filenames in os.walk(root_dir):
        for fname in filenames:
            if fname.endswith(".npz") and "_tx_" in fname or "_rx_":
                match = re.match(r"^([a-f0-9]{8})_", fname)
                if match:
                    exp_id_ = match.group(1)
                    full_path = os.path.join(dirpath, fname)
                    experiments.append((exp_id_, full_path))
    return experiments


def sanity_check(
        exp_dirs_by_id: Dict[str, List[str]]
) -> Dict[str, bool]:
    """
    Validates the integrity and completeness of experiment result directories.

    For each experiment ID, the function checks:
    - That the number of result directories (TX/RX pod pairs) is equal to the maximum found across all experiments.
    - That each result directory contains all expected files:
        - One TX .npz result file (filename includes "_tx_")
        - One RX .npz result file (filename includes "_rx_")
        - metadata.txt
        - RX stats log (e.g., "rx0_stats.log")
        - RX warmup log (e.g., "rx0_warmup.log")
        - TX port rate stats CSV (e.g., "tx0_port_rate_stats.csv")
        - TX port stats CSV (e.g., "tx0_port_stats.csv")

    If any directory under an experiment is incomplete or missing, that entire experiment is marked as invalid.
}
    """
    sanity_results = {}

    # each profile under experiment must have same number of pair
    max_len = max(len(v) for v in exp_dirs_by_id.values())
    for exp_id, exp_dir in exp_dirs_by_id.items():
        if len(exp_dir) < max_len:
            sanity_results[exp_id] = False
            continue

        exp_results = {}
        for r_dir in exp_dir:
            try:
                filenames = os.listdir(r_dir)
                required_files = {
                    "tx_npz": False,
                    "rx_npz": False,
                    "metadata": False,
                    "rx_stats": False,
                    "rx_warmup": False,
                    "tx_rate_stats": False,
                    "tx_port_stats": False,
                }

                for f in filenames:
                    if f.endswith(".npz") and "_tx_" in f:
                        required_files["tx_npz"] = True
                    elif f.endswith(".npz") and "_rx_" in f:
                        required_files["rx_npz"] = True
                    elif f == "metadata.txt":
                        required_files["metadata"] = True
                    elif f.startswith("rx") and f.endswith("_stats.log"):
                        required_files["rx_stats"] = True
                    elif f.startswith("rx") and f.endswith("_warmup.log"):
                        required_files["rx_warmup"] = True
                    elif f.startswith("tx") and f.endswith("_port_rate_stats.csv"):
                        required_files["tx_rate_stats"] = True
                    elif f.startswith("tx") and f.endswith("_port_stats.csv"):
                        required_files["tx_port_stats"] = True

                exp_results[r_dir] = all(required_files.values())

            except FileNotFoundError:
                exp_results[r_dir] = False

        sanity_results[exp_id] = all(exp_results.values())

    return sanity_results


def parse_testpmd_log(
        log_lines: List[str]
) -> Dict[str, np.ndarray]:
    """
    Parses DPDK testpmd log output and extracts RX/TX statistics.

        Notes:
        - If error/missed/nombuf stats are fewer than PPS entries, they're zero-padded.
        - All numeric values are cast to integers.

    :param log_lines:
    :return: Dict[str, np.ndarray]: A dictionary with the following keys:
            - "rx_pps": RX packets per second
            - "tx_pps": TX packets per second
            - "rx_bytes": RX total bytes
            - "tx_bytes": TX total bytes
            - "rx_packets": RX packet count
            - "tx_packets": TX packet count
            - "rx_errors": RX error count (filled with 0s if missing)
            - "rx_missed": RX missed packet count (filled with 0s if missing)
            - "rx_nombuf": RX no-buffer count (filled with 0s if missing)
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
            if match and match.group(1).isdigit():
                rx_pps_list.append(int(match.group(1)))
        elif "Tx-pps:" in line:
            match = re.search(r"Tx-pps:\s+(\d+)", line)
            if match and match.group(1).isdigit():
                tx_pps_list.append(int(match.group(1)))

        # RX-bytes and TX-bytes
        elif "RX-bytes:" in line:
            match = re.search(r"RX-bytes:\s+(\d+)", line)
            if match and match.group(1).isdigit():
                rx_bytes_list.append(int(match.group(1)))
        elif "TX-bytes:" in line:
            match = re.search(r"TX-bytes:\s+(\d+)", line)
            if match and match.group(1).isdigit():
                tx_bytes_list.append(int(match.group(1)))

        # RX and TX packets
        elif "RX-packets:" in line:
            match = re.search(r"RX-packets:\s+(\d+)", line)
            if match and match.group(1).isdigit():
                rx_packets_list.append(int(match.group(1)))
        elif "TX-packets:" in line:
            match = re.search(r"TX-packets:\s+(\d+)", line)
            if match and match.group(1).isdigit():
                tx_packets_list.append(int(match.group(1)))

        # RX-missed
        elif "RX-missed:" in line:
            match = re.search(r"RX-missed:\s+(\d+)", line)
            if match and match.group(1).isdigit():
                rx_missed_list.append(int(match.group(1)))

        # RX-nombuf
        elif "RX-nombuf:" in line:
            match = re.search(r"RX-nombuf:\s+(\d+)", line)
            if match and match.group(1).isdigit():
                rx_nombuf_list.append(int(match.group(1)))

        # RX-errors
        elif "RX-errors:" in line:
            match = re.search(r"RX-errors:\s+(\d+)", line)
            if match and match.group(1).isdigit():
                rx_err_list.append(int(match.group(1)))

    # normalize error/missed/nombuf lengths
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
    Determine which packet fields should be incremented based on flow generation mode.

    Flow mode characters:
        - 's': increment source IP
        - 'd': increment destination IP
        - 'S': increment source port
        - 'D': increment destination port
        - 'P': increment both source and destination ports

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


def get_pci_port_map(
        pod_name: str,
        is_all_dev: bool = False
) -> Dict[str, int]:
    """
    Map PCI address to DPDK port ID inside a pod using dpdk-testpmd output.

    :param pod_name:
    :param is_all_dev:
    :return:
    """
    if not is_all_dev:
        pci_env_cmd = f"kubectl exec {pod_name} -- sh -c 'echo $PCIDEVICE_INTEL_COM_DPDK'"
        pci_result = subprocess.run(pci_env_cmd, shell=True, capture_output=True, text=True)
        pci_addr = pci_result.stdout.strip()

        if not pci_addr:
            print(f"❌ Could not resolve PCI address inside {pod_name}")
            return {}

        print(f"🔍 [{pod_name}] PCI address: {pci_addr}")
        testpmd_cmd = f"kubectl exec {pod_name} -- dpdk-testpmd -a {pci_addr} -- --disable-device-start"
    else:
        print(f"🔍 [{pod_name}] Probing all PCI devices")
        testpmd_cmd = f"kubectl exec {pod_name} -- dpdk-testpmd -- --disable-device-start"

    result = subprocess.run(testpmd_cmd, shell=True, capture_output=True, text=True)
    output = result.stdout + result.stderr

    pci_to_port = {}
    port_id = 0

    for line in output.splitlines():
        match = re.search(r"device:\s+([0-9a-fA-F:.]+)", line)
        if match:
            pci = match.group(1)
            pci_to_port[pci] = port_id
            port_id += 1

    if not pci_to_port:
        print(f"⚠️ No PCI→port ID mapping found in {pod_name}")
    return pci_to_port


def is_testpmd_running(pod_name: str) -> bool:
    """
    Check if dpdk-testpmd is currently running inside the given pod.

    :param pod_name: Name of the pod (e.g., 'tx0', 'rx1')
    :return: True if testpmd is running, False otherwise
    """
    check_cmd = f"kubectl exec {pod_name} -- pgrep -f dpdk-testpmd"
    result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
    return result.returncode == 0


def get_mac_address(
        pod_name: str,
        is_retry: bool = True
) -> str:
    """Extract MAC address from dpdk-testpmd inside a pod with env var.

    Note we always mask EAL via -a hence TX or RX pod see a single DPDK port.
    All profile use VF's mac address that eliminates -P (promiscuous mode)

    :param is_retry:
    :param pod_name: tx0, tx1, rx0 etc. pod name
    :return: return DPDK interface mac
    """

    if is_retry:
        max_retries = 3
        retry_delay = 1

        for attempt in range(1, max_retries + 1):
            if not is_testpmd_running(pod_name):
                break
            print(f"⚠️ testpmd still running in {pod_name}, retrying ({attempt}/{max_retries})...")
            time.sleep(retry_delay)
        else:
            raise RuntimeError(f"❌ testpmd is still running in pod {pod_name} after {max_retries} retries.")
    else:
        if is_testpmd_running(pod_name):
            raise RuntimeError(f"❌ testpmd is already running in pod {pod_name}. Cannot retrieve MAC address.")

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


def check_npz_validity(
        npz_file_path: str,
        min_samples: int = 1) -> (bool, str):
    """
    Validate the contents of a .npz file for a DPDK experiment result.

    This function determines whether the given .npz file is from a TX or RX pod
    (based on filename), then validates the presence and basic structure of expected
    keys for each type.

    For RX files:
      - Must contain keys: rx_pps, tx_pps, rx_bytes, rx_packets
      - rx_pps must not be None and must have at least `min_samples` elements

    For TX files:
      - Must contain keys: pkts_tx, obytes, opackets, port_obytes
      - Each key must exist, not be None, and (if it's a NumPy array) contain
        at least `min_samples` elements

    :param npz_file_path:
    :param min_samples:
    :return:
    """
    try:
        data = np.load(npz_file_path)
        keys = set(data.files)

        is_rx = "_rx_" in npz_file_path
        is_tx = "_tx_" in npz_file_path

        if not (is_rx or is_tx):
            return False, "Cannot determine TX or RX file type"

        if is_rx:
            required_rx_keys = ["rx_pps", "tx_pps", "rx_bytes", "rx_packets"]
            for key in required_rx_keys:
                if key not in keys:
                    return False, f"Missing key: {key}"
                if key == "rx_pps" and data[key] is None:
                    return False, "rx_pps is None"
                if key == "rx_pps" and len(data[key]) < min_samples:
                    return False, f"Too few samples: {len(data[key])} < {min_samples}"

        if is_tx:
            required_tx_keys = ["pkts_tx", "obytes", "opackets", "port_obytes"]
            for key in required_tx_keys:
                if key not in keys:
                    return False, f"Missing key: {key}"
                if data[key] is None:
                    return False, f"{key} is None"
                if isinstance(data[key], np.ndarray) and len(data[key]) < min_samples:
                    return False, f"Too few samples: {len(data[key])} < {min_samples}"

        return True, f"Valid ({len(data[list(data.keys())[0]])} samples)"

    except Exception as e:
        return False, f"Error reading npz: {e}"



def has_profile_run(
        profile: str
) -> bool:
    expected_base = profile.replace(".lua", "")
    for exp_dir in glob.glob("results/*"):
        if not os.path.isdir(exp_dir):
            continue
        tx_npz = glob.glob(os.path.join(exp_dir, f"*tx*{expected_base}*.npz"))
        rx_npz = glob.glob(os.path.join(exp_dir, f"*rx*{expected_base}*.npz"))
        meta = os.path.join(exp_dir, "metadata.txt")

        if tx_npz and rx_npz and os.path.isfile(meta):
            return True
    return False


def run_ssh_command_persistent(
        manager: SSHConnectionManager,
        host: str,
        command: List[str]
) -> str:
    try:
        ssh_client = manager.get_connection(host)
        stdin, stdout, stderr = ssh_client.exec_command(" ".join(command))
        output = stdout.read().decode()

        exit_status = stdout.channel.recv_exit_status()
        error = stderr.read().decode()

        if exit_status != 0:
            raise RuntimeError(f"SSH command failed: {command}\nExit code: {exit_status}\nStderr: {error}")

        return output.strip()
    except Exception as e:
        print(f"❌ SSH command failed on {host}: {e}")
        return ""


def run_ssh_command(
        esxi_host,
        command,
        password="VMware1!"
):
    """
    Executes a remote SSH command on an ESXi host using `sshpass`.

    :param esxi_host: IP or hostname of the ESXi host
    :param command: Command and arguments to run (as list)
    :param password: SSH password (default is 'VMware1!')
    :return: Output of the command as a string
    """
    remote_cmd_str = " ".join(shlex.quote(arg) for arg in command)
    ssh_cmd = [
        "sshpass", "-p", password,
        "ssh", "-tt",
        "-o", "StrictHostKeyChecking=no",
        f"root@{esxi_host}",
        remote_cmd_str
    ]

    try:
        output = subprocess.check_output(ssh_cmd, text=True, stderr=subprocess.DEVNULL)
        return output
    except subprocess.CalledProcessError as e:
        print(f"❌ SSH command failed on {esxi_host}: {e}")
        return ""


def get_vf_stats(
        ssh_mgr: SSHConnectionManager,
        esxi_host: str,
        nic_name: str,
        vf_id: int
) -> Dict[str, int]:
    """
    Retrieves statistics for a specific VF on a NIC from an ESXi host.

    :param ssh_mgr:
    :param esxi_host: IP or hostname of the ESXi host
    :param nic_name: Name of the NIC
    :param vf_id: Virtual Function ID
    :return: Dictionary of stat name → value
    """
    try:
        output = run_ssh_command_persistent(
            ssh_mgr,
            esxi_host,
            ["esxcli", "network", "sriovnic", "vf", "stats", "-n", nic_name, "-v", str(vf_id)],
        )
        stats: Dict[str, int] = {}
        for line in output.splitlines():
            match = re.match(r"(.+?):\s+(\d+)", line.strip())
            if match:
                key = match.group(1).strip().replace(" ", "_").lower()
                stats[key] = int(match.group(2))
        logger.info("")
        return stats
    except Exception as e:
        print(f"❌ Error fetching stats for VF {vf_id} on {nic_name}@{esxi_host}: {e}")
        return {}


def monitor_vf_stats_remote(
        ssh_mgr: SSHConnectionManager,
        esxi_host: str,
        nic_name: str,
        interval: int,
        duration: int,
        output_dir: str = "results",
) -> None:
    """
    Monitors VF stats for all active VFs on an ESXi host NIC
    and writes to a CSV file.

    :param esxi_host: ESXi hostname or IP
    :param nic_name: NIC interface (e.g., vmnic3)
    :param interval: Sampling interval in seconds
    :param duration: Total monitoring duration in seconds
    :param output_dir: Directory to save CSV output
    :param ssh_mgr:
    """

    logger.info(
        f"🟢 Started ESXi monitor thread for host {esxi_host}, "
        f"NIC {nic_name}, interval {interval}s, duration {duration}s")

    if not esxi_host or not nic_name:
        raise ValueError("❌ Invalid ESXi host or NIC name provided.")

    if interval <= 0 or duration <= 0:
        raise ValueError("❌ Sampling interval and duration must be positive integers.")

    logger.info(f"🚀 Starting VF sampling thread on {esxi_host}:{nic_name} "
                f"every {interval}s for {duration}s")

    vfs = get_active_vfs(ssh_mgr, esxi_host, nic_name)
    if not vfs:
        logger.warning(f"⚠️ No active VFs found on {esxi_host} for {nic_name}")
        return
    logger.info(f"🔍 Found {len(vfs)} active VFs on {esxi_host} ({nic_name})")

    os.makedirs(output_dir, exist_ok=True)
    csv_file = os.path.join(output_dir, f"{esxi_host.replace('.', '_')}_{nic_name}_vf_stats.csv")

    with open(csv_file, "w", newline="") as f:
        writer: Optional[csv.DictWriter] = None
        start_time = time.time()
        while time.time() - start_time < duration:
            timestamp = datetime.utcnow().isoformat()
            for vf in vfs:
                stats = get_vf_stats(ssh_mgr, esxi_host, nic_name, vf)
                if stats:
                    stats["timestamp"] = timestamp
                    stats["vf_id"] = vf
                    stats["nic_name"] = nic_name
                    stats["esxi_host"] = esxi_host

                    if writer is None:
                        fieldnames = list(stats.keys())
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()

                    writer.writerow(stats)
                    f.flush()
            time.sleep(interval)


def collect_cmdline_from_nodes(
        pods: List[str],
        nodes: List[str],
        output_dir: str
) -> Dict[str, str]:
    """
    Collects /proc/cmdline from one pod per unique node.

    :param pods: List of pods (one per node is enough)
    :param nodes: Corresponding node names
    :param output_dir: Directory to store cmdline outputs
    :return: Dictionary of node name -> cmdline string
    """
    seen_nodes = set()
    cmdlines = {}

    for pod, node in zip(pods, nodes):
        if node in seen_nodes:
            continue
        seen_nodes.add(node)

        try:
            result = subprocess.run(
                ["kubectl", "exec", pod, "--", "cat", "/proc/cmdline"],
                capture_output=True, text=True, check=True
            )
            cmdline_output = result.stdout.strip()
            cmdlines[node] = cmdline_output

            file_path = os.path.join(output_dir, f"{node}_cmdline.txt")
            with open(file_path, "w") as f:
                f.write(cmdline_output + "\n")

            logger.info(f"📝 Collected /proc/cmdline from node {node} (via pod {pod})")

        except subprocess.CalledProcessError as e:
            logger.warning(f"⚠️ Failed to collect /proc/cmdline from {node} via {pod}: {e}")

    return cmdlines


def start_esxi_collector(
        ssh_mgr: SSHConnectionManager,
        tx_nodes: List[str],
        rx_nodes: List[str],
        esxi_map: Dict[str, str],
        cmd: argparse.Namespace,
        base_output_dir: str
) -> List[threading.Thread]:
    """
    Start background threads to collect VF stats from ESXi hosts.

    For each unique ESXi host across all TX and RX Kubernetes nodes:

    - If the node has a label 'node.cluster.x-k8s.io/esxi-host', it's mapped to the corresponding ESXi IP/hostname.
    - A separate VF stats sampling thread is launched per unique ESXi host (even if multiple worker nodes reside on the same host).
    - Output CSV files are saved under the profile directory of each pod pair (e.g., results/<expid>/tx0-rx0/<profile>/).

    ⚠If any node is missing the ESXi host label, that node is skipped with a warning.

    :param ssh_mgr:
    :param tx_nodes: List of TX node names (e.g., ['worker-1'])
    :param rx_nodes: List of RX node names (e.g., ['worker-2'])
    :param esxi_map: Dictionary mapping node name → ESXi hostname/IP from K8s node label
    :param cmd: Parsed command-line arguments from argparse
    :param base_output_dir: Root directory where result folders exist
    :return: List of running background threads for VF stats monitoring
    """

    logger.info(f"🔍 Invoking start_esxi_collector... {esxi_map}")

    esxi_seen = set()
    esxi_nic_map = {}

    profile_subdir = os.path.join(base_output_dir, "esxi_stats", cmd.profile.split(".")[0])
    os.makedirs(profile_subdir, exist_ok=True)

    for node in set(tx_nodes + rx_nodes):
        esxi_host = esxi_map.get(node)
        if not esxi_host:
            logger.warning(f"⚠️ Node '{node}' is missing ESXi label. Skipping VF sampling for this node.")
            continue

        if esxi_host in esxi_seen:
            continue

        esxi_seen.add(esxi_host)
        esxi_nic_map[(esxi_host, profile_subdir)] = cmd.nic_name

    if not esxi_nic_map:
        logger.warning("⚠️ No ESXi hosts detected from node labels. VF stats collection will be skipped.")
        return []

    logger.info("🔗 ESXi Host to NIC Mapping:")
    for (host, path), nic in esxi_nic_map.items():
        logger.info(f"  • {host} → {nic} → {path}")

    monitor_threads = []

    for (esxi_host, output_dir), nic_name in esxi_nic_map.items():
        logger.info(f"📄 VF stats for {esxi_host} ({nic_name}) will be saved to: {output_dir}")
        monitor_thread = threading.Thread(
            target=monitor_vf_stats_remote,
            args=(ssh_mgr, esxi_host, nic_name, getattr(cmd, "sample_interval", 10),
                  getattr(cmd, "duration", 60) + 30, output_dir),
            daemon=True
        )
        monitor_thread.start()
        monitor_threads.append(monitor_thread)

    logger.info(f"📡 Started VF stats monitoring for ESXi hosts: "
                f"{[host for (host, _) in esxi_nic_map.keys()]}")

    # 🚨 Threads will run with ssh_mgr active until main joins
    time.sleep(2)

    logger.info(f"📡 Started VF stats monitoring for ESXi hosts: "
                f"{[host for (host, _) in esxi_nic_map.keys()]}")

    time.sleep(2)
    return monitor_threads


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

    if result.returncode == 127 or "not found" in result.stderr.lower():
        raise RuntimeError(
            f"❌ 'numactl' is not installed in pod {pod_name}. "
            f"Please install it in your container image (e.g., via 'tdnf install -y numactl')."
        )

    if result.returncode != 0:
        raise RuntimeError(
            f"❌ Failed to run `numactl -s` in pod {pod_name}. "
            f"Make sure 'numactl' is installed in the container. "
            f"Error: {result.stderr.strip()}"
        )

    for line in result.stdout.splitlines():
        if "physcpubind:" in line:
            return line.split("physcpubind:")[1].strip()

    raise RuntimeError(
        f"❌ Could not find 'physcpubind' in numactl output for pod {pod_name}.\n"
        f"Output:\n{result.stdout}"
    )


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
        tx_esxi: str = None,
        rx_esxi: str = None,
        tx_cmdline: str = None,
        rx_cmdline: str = None,
):
    """    Write metadata.txt for a TX-RX pair into the given path.

    :param path:
    :param tx_pod:
    :param rx_pod:
    :param tx_mac:
    :param rx_mac:
    :param tx_numa:
    :param rx_numa:
    :param tx_node:
    :param rx_node:
    :param expid:
    :param timestamp:
    :param cmd:
    :param tx_esxi:
    :param rx_esxi:
    :param tx_cmdline:
    :param rx_cmdline:
    :return:
    """

    os.makedirs(path, exist_ok=True)
    metadata_path = os.path.join(path, "metadata.txt")

    with open(metadata_path, "w") as f:
        f.write(f"# Experiment Metadata\n")
        f.write(f"expid={expid}\n")
        f.write(f"timestamp={timestamp}\n")
        f.write(f"profile={cmd.profile}\n\n")

        if tx_esxi:
            f.write(f"tx_esxi={tx_esxi}\n")
        if rx_esxi:
            f.write(f"rx_esxi={rx_esxi}\n")

        f.write(f"# Pod and Node Information\n")
        f.write(f"tx_pod={tx_pod}\n")
        f.write(f"rx_pod={rx_pod}\n")
        f.write(f"tx_node={tx_node}\n")
        f.write(f"rx_node={rx_node}\n")
        f.write(f"tx_mac={tx_mac}\n")
        f.write(f"rx_mac={rx_mac}\n")
        f.write(f"tx_numa={tx_numa}\n")
        f.write(f"rx_numa={rx_numa}\n\n")

        if tx_cmdline:
            f.write(f"tx_cmdline={tx_cmdline}\n")
        if rx_cmdline:
            f.write(f"rx_cmdline={rx_cmdline}\n")

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

    if cmd.gen_mode == "paired":
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
    elif cmd.gen_mode == "latency":
        for t, r, tx_mac, rx_mac in zip(tx_pods, rx_pods, tx_macs, rx_macs):
            flow_dir = f"flows/{t}-{r}"
            os.makedirs(flow_dir, exist_ok=True)
            logger.info(f"📡 Generating latency flows in {flow_dir}")

            for rate, size in product(rates, pkt_sizes):
                render_latency_lua_profile(
                    src_mac_port=tx_mac,
                    dst_mac_port=rx_mac,
                    base_src_ip=cmd.base_src_ip,
                    base_dst_ip=cmd.base_dst_ip,
                    pkt_sizes=[size],
                    duration=10000,
                    confirm_duration=60000,
                    pause_time=1000,
                    initial_rate=rate,
                    netmask="/24",
                    output_dir=flow_dir,
                    convergence=False
                )
    elif cmd.gen_mode == "converge":
        for t, r, tx_mac, rx_mac in zip(tx_pods, rx_pods, tx_macs, rx_macs):
            flow_dir = f"flows/{t}-{r}"
            os.makedirs(flow_dir, exist_ok=True)
            logger.info(f"📡 Generating latency flows in {flow_dir}")

            for rate, size in product(rates, pkt_sizes):
                render_latency_lua_profile(
                    src_mac_port=tx_mac,
                    dst_mac_port=rx_mac,
                    base_src_ip=cmd.base_src_ip,
                    base_dst_ip=cmd.base_dst_ip,
                    pkt_sizes=[size],
                    duration=10000,
                    confirm_duration=60000,
                    pause_time=1000,
                    initial_rate=rate,
                    netmask="/24",
                    output_dir=flow_dir,
                    convergence=False
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
        f"-- --forward-mode=txonly --eth-peer=0,{tx_mac} "
        f"--auto-start --stats-period 1 > /output/warmup.log 2>&1"
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

    TBD.
    :param exit_code:
    :return:
    """
    pass


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
            f"--proc-type auto --file-prefix testpmd_rx_{pod} "
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

    # lua_script = (
    #     "local ts = os.date('!%Y-%m-%dT%H:%M:%S'); "
    #
    #     "local rate = pktgen.portStats(0, 'rate'); "
    #     f"if rate and rate[0] then "
    #     f"local f1 = io.open('{rate_file}', 'a'); "
    #     "local str = ts .. ','; "
    #     "for k,v in pairs(rate[0]) do str = str .. k .. '=' .. tostring(v) .. ',' end; "
    #     "f1:write(str:sub(1, -2), '\\n'); f1:close(); end; "
    #
    #     "local pkt = pktgen.pktStats(0)[0]; "
    #     f"if pkt then "
    #     f"local f2 = io.open('{pkt_file}', 'a'); "
    #     "local str = ts .. ','; "
    #     "for k,v in pairs(pkt) do str = str .. k .. '=' .. tostring(v) .. ',' end; "
    #     "f2:write(str:sub(1, -2), '\\n'); f2:close(); end; "
    #
    #     "local port = pktgen.portStats(0, 'port'); "
    #     f"if port and port[0] then "
    #     f"local f3 = io.open('{port_file}', 'a'); "
    #     "local str = ts .. ','; "
    #     "for k,v in pairs(port[0]) do str = str .. k .. '=' .. tostring(v) .. ',' end; "
    #     "f3:write(str:sub(1, -2), '\\n'); f3:close(); end; "
    # )

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
        session_name: str,
        port_to_core: str,
):
    """
    Launches pktgen in a Kubernetes pod, either interactively or via tmux session.

    :param port_to_core:
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

    # if cmd.latency_mode:
    #     assert len(core_list) >= 5,
    #     main_core = core_list[0]
    #     tx_cores_port0 = core_list[1]
    #     rx_cores_port0 = core_list[2]
    #     tx_cores_port1 = core_list[3]
    #     rx_cores_port1 = core_list[4]
    #
    #     port_mappings = (
    #         f"-m [{tx_cores_port0}:{rx_cores_port0}].0 "
    #         f"-m [{tx_cores_port1}:{rx_cores_port1}].1"
    #     )

    pktgen_cmd = (
        f"cd /usr/local/bin; timeout {timeout_duration} pktgen --no-telemetry -l "
        f"{all_cores} -n 4 --socket-mem {cmd.tx_socket_mem} --main-lcore {main_core} "
        f"--proc-type auto --file-prefix pg_{pod} "
        f"-a $PCIDEVICE_INTEL_COM_DPDK "
        f"-- -G --txd={cmd.txd} --rxd={cmd.rxd} "
        f"-f {lua_script_path} {port_to_core}"
    )
    #
    # -m[{tx_cores}:{rx_cores}]
    # .0

    kubectl_cmd = f"kubectl exec -it {pod} -- sh -c '{pktgen_cmd}'"
    window_name = pod
    subprocess.run(
        ["tmux", "send-keys", "-t", f"{session_name}:{window_name}", kubectl_cmd, "Enter"])

    if cmd.debug:
        logger.debug(f"[{pod}] 🔧 Full pktgen command:\n{pktgen_cmd}")
        logger.debug(f"[{pod}] 🔧 Full kubectl exec command:\n{kubectl_cmd}")

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
        t_sessesion: str,
        window: str,
        timeout: int = 3
):
    """

    :param t_sessesion:
    :param window:
    :param timeout:
    :return:
    """
    for _ in range(timeout * 10):
        result = subprocess.run(
            ["tmux", "list-windows", "-t", t_sessesion],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if window in result.stdout:
            return
        time.sleep(0.1)
    raise RuntimeError(f"❌ Timed out waiting for window '{window}' in session '{t_sessesion}'")


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
        total_usable = len(usable_cores)

        ports_needed = 2 if cmd.latency else 1
        cores_per_port = 2  # 1 TX + 1 RX per port
        min_required = ports_needed * cores_per_port

        if total_usable < min_required:
            logger.warning(
                f"[⚠️] Not enough cores for pod {pod} in {'latency' if cmd.latency else 'regular'} mode. "
                f"Required: {min_required}, Available: {total_usable}")
            return None

        # single core per pod
        if len(numa_cores) == 2:
            tx_cores = rx_cores = numa_cores[1]
        else:
            # n cores ( latency (2 port) or pps test with (1 port per pod)
            total_cores = len(numa_cores)
            txrx_cores = (total_cores - 1) // 2
            if txrx_cores % 2 != 0:
                txrx_cores -= 1

            # it should be sorted, but we handle a case if it not.
            tx_cores = sorted([numa_cores[i + 1] for i in range(txrx_cores)])
            rx_cores = sorted([numa_cores[txrx_cores + 1 + i] for i in range(txrx_cores)])

            if cmd.latency:

                # it should be sorted, but we handle a case if it not.
                tx_cores = sorted([numa_cores[i + 1] for i in range(txrx_cores)])
                rx_cores = sorted([numa_cores[txrx_cores + 1 + i] for i in range(txrx_cores)])

                # for latency we split all TX / 2 since we need to port
                # and RX / 2
                half = len(tx_cores) // 2
                tx0 = tx_cores[:half]
                rx0 = rx_cores[:half]
                tx1 = tx_cores[half:]
                rx1 = rx_cores[half:]

                port_to_core = (
                    f"-m [{','.join(tx0)}:{','.join(rx0)}].0 "
                    f"-m [{','.join(tx1)}:{','.join(rx1)}].1"
                )

            else:

                tx_core_range = f"{tx_cores[0]}-{tx_cores[-1]}" if len(tx_cores) > 1 else f"{tx_cores[0]}"
                rx_core_range = f"{rx_cores[0]}-{rx_cores[-1]}" if len(rx_cores) > 1 else f"{rx_cores[0]}"
                tx_cores = tx_core_range
                rx_cores = rx_core_range
                port_to_core = f"-m [{tx_cores}:{rx_cores}].0"

        all_core_str = ",".join([main_core] + usable_cores)

        if not validate_and_cleanup_lua(pod, cmd.profile):
            return None

        try:
            launch_pktgen(
                pod,
                main_core,
                tx_cores,
                rx_cores,
                all_core_str,
                cmd,
                session_name,
                port_to_core
            )
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


def pod_to_esxi_host_mapping() -> Dict[str, str]:
    """
    Retrieve a mapping of Kubernetes worker node names to
    their corresponding ESXi host IPs or names.

    This function inspects the node labels  `node.cluster.x-k8s.io/esxi-host`
    to determine the ESXi host each worker node is running on.

    (This only ESXi specific , on baremetal no op)

    Returns:
        dict: A dictionary where the keys are Kubernetes node names, and the values are the associated
        ESXi host IPs or hostnames.
              Example:
              {
                  "node-1": "10.192.18.5",
                  "node-2": "10.192.18.9"
              }

    :return: Dict[str, str]: A dictionary where the keys are Kubernetes node names,
             and the values are the associated
    """
    result = subprocess.run(
        ["kubectl", "get", "nodes", "-o", "json"],
        capture_output=True,
        text=True
    )
    nodes = json.loads(result.stdout)
    esxi_map = {}
    for node in nodes["items"]:
        node_name = node.get("metadata", {}).get("name")
        labels = node.get("metadata", {}).get("labels", {})
        esxi_host = labels.get("node.cluster.x-k8s.io/esxi-host")

        if node_name and esxi_host:
            esxi_map[node_name] = esxi_host
        elif node_name:
            logger.debug(f"🔍 Node '{node_name}' has no ESXi label — skipping.")

    return esxi_map


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


def get_active_vfs(
        ssh_mgr: SSHConnectionManager,
        esxi_host,
        nic_name
):
    """Fetch list of active VF IDs for a given NIC."""
    try:
        output = run_ssh_command_persistent(ssh_mgr, esxi_host, [
            "esxcli", "network", "sriovnic", "vf", "list", "-n", nic_name])
        vfs = []
        for line in output.splitlines():
            match = re.match(r"\s*(\d+)\s+true", line)
            if match:
                vfs.append(int(match.group(1)))
        return vfs
    except Exception as e:
        print(f"❌ Error fetching VF list from {esxi_host}: {e}")
        return []


def get_unicast_pkt_counts(nic_name, vf_id):
    """Returns RX and TX unicast packet counts for a VF as a tuple."""
    try:
        output = subprocess.check_output(
            ["esxcli", "network", "sriovnic", "vf", "stats", "-n", nic_name, "-v", str(vf_id)],
            text=True
        )
        rx_match = re.search(r"Rx Unicast Pkt:\s+(\d+)", output)
        tx_match = re.search(r"Tx Unicast Pkt:\s+(\d+)", output)
        rx = int(rx_match.group(1)) if rx_match else 0
        tx = int(tx_match.group(1)) if tx_match else 0
        return rx, tx
    except subprocess.CalledProcessError:
        return 0, 0


def main_start_generator(
        cmd: argparse.Namespace
) -> List[threading.Thread]:
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

    esxi_map = pod_to_esxi_host_mapping()
    if not esxi_map:
        raise RuntimeError("❌ No ESXi mapping found. Check node labels or node selector.")

    ssh_mgr = SSHConnectionManager(cmd.default_username, cmd.default_password)
    vf_monitor_threads = start_esxi_collector(
        ssh_mgr, tx_nodes, rx_nodes, esxi_map, cmd, base_output_dir)

    if not cmd.skip_copy:
        copy_flows_to_pods(tx_pods, rx_pods)
    else:
        logger.info("⏭️  Skipping Lua profile copy step (--skip-copy)")

    rx_core_list = []
    if not cmd.skip_testpmd:
        rx_core_list = start_dpdk_testpmd(rx_pods, rx_numa, tx_macs, cmd)
    else:
        logger.info("⏭️  Skipping testpmd launch on RX pods (--skip-testpmd)")

    cmdlines = collect_cmdline_from_nodes(tx_pods + rx_pods, tx_nodes + rx_nodes, base_output_dir)

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

        tx_main, tx_cores, tx_all = tx_core_list[i]
        rx_main, rx_cores, rx_all = rx_core_list[i]

        pair_dir = os.path.join(base_output_dir, f"{tx_pod}-{rx_pod}", args.profile.split(".")[0])
        logger.info(f"📁 Results will be saved in: {pair_dir}")
        os.makedirs(pair_dir, exist_ok=True)

        tx_esxi = esxi_map.get(tx_nodes[i])
        rx_esxi = esxi_map.get(rx_nodes[i])

        tx_cmdline = cmdlines.get(tx_nodes[i])
        rx_cmdline = cmdlines.get(rx_nodes[i])

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
            cmd=cmd,
            tx_esxi=tx_esxi,
            rx_esxi=rx_esxi,
            tx_cmdline=tx_cmdline,
            rx_cmdline=rx_cmdline

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

    for t_ in vf_monitor_threads:
        t_.join()

    logger.info("✅ VF sampling threads completed.")
    logger.info("📁 All results saved in 'results/' directory.")

    session_name = f"pktgen_{cmd.profile.split('.')[0]}"
    try:
        kill_tmux_session(session_name)
        logger.info(f"🧹 Cleaned up tmux session: {session_name}")
    except Exception as e:
        logger.error(f"❌ Failed to kill tmux session: {e}")

    if ssh_mgr is not None:
        ssh_mgr.close_all()

    return vf_monitor_threads


def parse_int_list(csv_str: str) -> List[int]:
    """Parse command  seperated list of values , note this for arg parser no spaces. """
    return [int(v.strip()) for v in csv_str.split(",") if v.strip()]


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


#
def render_latency_lua_profile(
        src_mac_port: str,
        dst_mac_port: str,
        base_src_ip: str,
        base_dst_ip: str,
        pkt_sizes: list,
        duration: int = 10000,
        confirm_duration: int = 60000,
        pause_time: int = 1000,
        initial_rate: int = 50,
        netmask: str = "/24",
        output_dir: str = "flows",
        convergence: bool = True
) -> str:
    """
    Render a Lua profile for fixed or convergence-based latency tests.

    :param src_mac_port: Source MAC used on port 0
    :param dst_mac_port: Destination MAC used on port 0
    :param base_src_ip: Base source IP
    :param base_dst_ip: Base destination IP
    :param pkt_sizes: List of packet sizes (only the first one is used)
    :param duration: Trial duration in milliseconds
    :param confirm_duration: Final trial confirmation duration
    :param pause_time: Delay between trials
    :param initial_rate: Starting rate for convergence
    :param netmask: Subnet mask string (e.g., /24)
    :param output_dir: Directory to store Lua script
    :param convergence: Whether to use convergence-based search
    :return: Path to the generated Lua script
    """
    os.makedirs(output_dir, exist_ok=True)

    mode = "converge" if convergence else "fixed"
    pkt_size = pkt_sizes[0]
    filename = f"profile_latency_{mode}_pkt_size_{pkt_size}_{initial_rate}rate.lua"
    output_path = os.path.join(output_dir, filename)

    lua_template = LUA_UDP_LATENCY_TEMPLATE_CONVERGENCE if convergence else LUA_UDP_LATENCY_TEMPLATE_FIXED

    lua_script = lua_template.format(
        pkt_sizes=", ".join(str(s) for s in pkt_sizes),
        duration=duration,
        confirm_duration=confirm_duration,
        pause_time=pause_time,
        dst_ip=base_dst_ip,
        src_ip=base_src_ip,
        netmask=netmask,
        initial_rate=initial_rate,
        dst_mac_port0=src_mac_port,
        src_mac_port0=dst_mac_port,
        dst_mac_port1=dst_mac_port,
        src_mac_port1=src_mac_port,
    )

    with open(output_path, "w") as f:
        f.write(lua_script)

    logger.info(f"[✔] Generated latency profile: {output_path}")
    return output_path


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
) -> None:
    """Setup logging facility.

    :param log_level: Logging level (e.g., "DEBUG", "INFO", "WARNING", "ERROR").
                      If invalid or not recognized, defaults to "INFO".
    :param log_output: Where to send the logs. Options:
                          - "console": output logs to standard output.
                          - "file": write logs to the specified file.
                          - "both": output to both console and file.
    :param log_file: File path to write logs if `log_output` includes "file" or "both".
    :return: Npme
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
    """This routine cleanup on interrupts  (KeyboardInterrupt) etc.
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
    except Exception as err:
        logger.error(f"❌ Failed to stop testpmd: {err}")

    try:
        for pod in tx_pods:
            subprocess.run(
                ["kubectl", "exec", pod, "--", "pkill", "-9", "pktgen"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        logger.info("🧯 Force-killed pktgen in TX pods")

        # we delete all stale files inside each tx pod
        for pod in tx_pods:
            subprocess.run(
                ["kubectl", "exec", pod, "--", "rm", "-f", "/tmp/*.csv", "/sample_pktgen.lua"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        logger.info("🗑️  Removed temporary CSV and Lua files from TX pods")

    except Exception as err:
        logger.error(f"❌ Failed to kill pktgen in TX pods: {err}")

    logger.warning("🧹 Starting cleanup...")
    session_ = f"pktgen_{cmd.profile.split('.')[0]}"
    try:
        kill_tmux_session(session_)
        logger.info(f"🧹 Killed tmux session: {session_}")
    except Exception as err:
        logger.error(f"❌ Failed to kill tmux session: {err}")


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

    parser.add_argument(
        "--debug", action="store_true",
        help="🔍 Debug: Load and display contents of .npz results after test"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    gen = subparsers.add_parser("generate_flow", aliases=["gen"], help="🛠 Generate Pktgen Lua flows")
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

    gen.add_argument(
        "--gen-mode",
        type=str,
        default="paired",
        choices=["paired", "converge", "latency"],
        help="🧬 Profile generation mode:\n"
             "  paired   - Per TX-RX pod pair (default)\n"
             "  converge     - All profiles in a flat directory\n"
             "  latency  - Generate latency profiles"
    )

    gen.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level (default: INFO)"
    )

    gen.add_argument(
        "--log-output",
        choices=["console", "file", "both"],
        default="console",
        help="Where to log: 'console', 'file', or 'both' (default: console)"
    )

    gen.add_argument(
        "--log-file",
        default="benchmark.log",
        help="Log file name if using file or both (default: benchmark.log)"
    )

    start = subparsers.add_parser("start_generator",
                                  aliases=["start"],
                                  help="🚀 Start pktgen & testpmd using selected profile")
    start.add_argument(
        "--latency", action="store_true",
        help="🧪 Run latency (convergence) test instead of PPS test. "
             "Uses convergence Lua template with binary rate search."
    )

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

    start.add_argument(
        "--nic-name", type=str, default="vmnic3",
        help="🖧 NIC name on ESXi host to monitor VF stats (default: vmnic3)"
    )

    start.add_argument(
        "--default-username", type=str, default="root",
        help="🔐 Default SSH username for ESXi hosts (default: root)"
    )
    start.add_argument(
        "--default-password", type=str, default="VMware1!",
        help="🔐 Default SSH password for ESXi hosts (default: VMware1!)"
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

    # sub-parse to validate experiment
    validate = subparsers.add_parser("validate_npz", help="🔍 Validate a .npz result file")
    validate.add_argument(
        "--file", type=str, required=True, help="Path to .npz result file to validate"
    )
    validate.add_argument(
        "--min-samples", type=int, default=5, help="Minimum valid sample count (default: 5)"
    )

    # TODO move out to global
    validate.add_argument(
        "--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    )
    validate.add_argument(
        "--log-output", default="console", choices=["console", "file", "both"]
    )
    validate.add_argument(
        "--log-file", default="benchmark.log"
    )

    sanity = subparsers.add_parser("sanity", help="🔍 Sanity check all results.")
    # TODO move out to global

    sanity.add_argument(
        "--min-samples", type=int, default=5, help="Minimum valid sample count (default: 5)"
    )

    sanity.add_argument("--purge", action="store_true", help="Purge invalid experiment result directories")

    sanity.add_argument(
        "--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    )
    sanity.add_argument(
        "--log-output", default="console", choices=["console", "file", "both"]
    )
    sanity.add_argument(
        "--log-file", default="benchmark.log"
    )

    args = parser.parse_args()

    if getattr(args, "debug", False):
        setup_logging("DEBUG", getattr(args, "log_output", "console"), getattr(args, "log_file", "benchmark.log"))
        logger.debug("🧪 Debug mode enabled")
        logger.debug(f"Parsed arguments: {vars(args)}")
    else:
        setup_logging(getattr(args, "log_level", "INFO"),
                      getattr(args, "log_output", "console"),
                      getattr(args, "log_file", "benchmark.log"))

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

        vf_monitor_threads = None
        try:
            vf_monitor_threads = main_start_generator(args)
        except KeyboardInterrupt:
            logger.warning("🛑 KeyboardInterrupt received! Attempting cleanup...")
            session = f"pktgen_{args.profile.split('.')[0]}"
            try:
                session = f"pktgen_{args.profile.split('.')[0]}"
                kill_tmux_session(session)
                logger.info(f"🧹 Killed tmux session: {session}")
            except Exception as e_:
                logger.error(f"❌ Failed to kill tmux session: {e_}")

            if vf_monitor_threads:
                for t in vf_monitor_threads:
                    t.join()

            sys.exit(130)

    elif args.command == "upload_wandb":
        upload_npz_to_wandb(result_dir=args.result_dir, expid=args.expid)
    elif args.command == "validate_npz":
        is_valid, message = check_npz_validity(args.file, args.min_samples)
        print(f"{'✅' if is_valid else '❌'} {args.file} → {message}")
        sys.exit(0 if is_valid else 1)
    elif args.command == "sanity":

        discovered = discover_experiments()
        grouped = {}
        base_dirs = {}

        for exp_id, file_path in discovered:
            grouped.setdefault(exp_id, []).append(file_path)
            base_dirs.setdefault(exp_id, []).append(os.path.abspath(os.path.dirname(file_path)))

        invalid_experiments = {}

        sanity_result = sanity_check(base_dirs)
        for exp_id, valid in sanity_result.items():
            print(f"{exp_id}: {'✅' if valid else '❌'}")
            if not valid:
                invalid_experiments[exp_id] = base_dirs.get(exp_id, [])

        print("\nRunning npz checks for valid experiments:")
        for exp_id, dirs in base_dirs.items():
            if not sanity_result.get(exp_id, False):
                continue
            for result_dir in dirs:
                for f in os.listdir(result_dir):
                    if f.endswith(".npz"):
                        full_path = os.path.join(result_dir, f)
                        is_valid, message = check_npz_validity(full_path, min_samples=args.min_samples)
                        print(f"{'✅' if is_valid else '❌'} {full_path} → {message}")
                        if not is_valid:
                            invalid_experiments.setdefault(exp_id, []).append(result_dir)

        if args.purge:
            print("\n🧹 Purging invalid result directories:")
            seen_dirs = set()
            results_root = os.path.abspath("results")
            for exp_id, paths in invalid_experiments.items():
                for path in paths:
                    abs_path = os.path.abspath(path)
                    if abs_path not in seen_dirs:
                        seen_dirs.add(abs_path)
                        if abs_path.startswith(results_root) and os.path.isdir(abs_path):
                            print(f"🗑 Removing {abs_path}")
                            shutil.rmtree(abs_path, ignore_errors=True)
                        else:
                            print(f"⚠️ Skipping suspicious path: {abs_path}")
