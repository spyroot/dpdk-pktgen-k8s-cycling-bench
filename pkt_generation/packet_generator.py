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
where TX0,TX1 .. son on


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
import subprocess
import json
import os
import argparse
from ipaddress import ip_address
from typing import List, Tuple
import time
from itertools import product
import re
import numpy as np
from datetime import datetime

# this out template
LUA_UDP_TEMPLATE = """\
package.path = package.path ..";?.lua;test/?.lua;app/?.lua;"
require "Pktgen"

pktgen.set("all", "rate", {rate});
pktgen.mac_from_arp("on");
pktgen.ping4("all");
pktgen.prime("all");
pktgen.screen("on");

print("**** Execute Range test ********")

pktgen.page("range")

pktgen.range.dst_mac("0", "start", "{dst_mac}")
pktgen.range.src_mac("0", "start", "{src_mac}")

pktgen.range.dst_ip("0", "start", "{dst_ip}")
pktgen.range.dst_ip("0", "inc", "{dst_ip_inc}")
pktgen.range.dst_ip("0", "min", "{dst_ip}")
pktgen.range.dst_ip("0", "max", "{dst_max_ip}")

pktgen.range.src_ip("0", "start", "{src_ip}")
pktgen.range.src_ip("0", "inc", "{src_ip_inc}")
pktgen.range.src_ip("0", "min", "{src_ip}")
pktgen.range.src_ip("0", "max", "{src_max_ip}")

pktgen.set_proto("0", "udp")

pktgen.range.dst_port("0", "start", {dst_port})
pktgen.range.dst_port("0", "inc", {dst_port_inc})
pktgen.range.dst_port("0", "min", {dst_port})
pktgen.range.dst_port("0", "max", {dst_port_max})

pktgen.range.src_port("0", "start", {src_port})
pktgen.range.src_port("0", "inc", {src_port_inc})
pktgen.range.src_port("0", "min", {src_port})
pktgen.range.src_port("0", "max", {src_port_max})

pktgen.range.pkt_size("0", "start", {pkt_size})
pktgen.range.pkt_size("0", "inc", 0)
pktgen.range.pkt_size("0", "min", {pkt_size})
pktgen.range.pkt_size("0", "max", {pkt_size})

pktgen.set_range("0", "on")
pktgen.start(0)
"""


def parse_testpmd_log(log_lines):
    """
    :param log_lines:
    :return:
    """
    rx_pps_list = []
    rx_bytes_list = []
    tx_pps_list = []
    tx_bytes_list = []
    rx_err_list = []

    for line in log_lines:
        if "Rx-pps:" in line:
            match = re.search(r"Rx-pps:\s+(\d+)\s+Rx-bps:\s+(\d+)", line)
            if match:
                rx_pps, rx_bps = match.groups()
                rx_pps_list.append(int(rx_pps))
                rx_bytes_list.append(int(rx_bps) // 8)  # Convert bps to Bytes/sec
        elif "Tx-pps:" in line:
            match = re.search(r"Tx-pps:\s+(\d+)\s+Tx-bps:\s+(\d+)", line)
            if match:
                tx_pps, tx_bps = match.groups()
                tx_pps_list.append(int(tx_pps))
                tx_bytes_list.append(int(tx_bps) // 8)
        elif "RX-errors:" in line:
            match = re.search(r"RX-errors:\s+(\d+)", line)
            if match:
                rx_err_list.append(int(match.group(1)))

    # Normalize error list if shorter
    max_len = max(len(rx_pps_list), len(rx_err_list))
    rx_err_list += [0] * (max_len - len(rx_err_list))

    return {
        "rx_pps": np.array(rx_pps_list),
        "rx_bytes": np.array(rx_bytes_list),
        "tx_pps": np.array(tx_pps_list),
        "tx_bytes": np.array(tx_bytes_list),
        "rx_errors": np.array(rx_err_list)
    }


def get_increments_from_mode(
        mode: str, num_flows: int
):
    """

    :param mode:
    :param num_flows:
    :return:
    """
    ip_inc = "0.0.0.1" if 's' in mode or 'd' in mode else "0.0.0.0"
    port_inc = 1 if 'p' in mode else 0

    increments = {
        "src_ip_inc": ip_inc if 's' in mode else "0.0.0.0",
        "dst_ip_inc": ip_inc if 'd' in mode else "0.0.0.0",
        "src_port_inc": 1 if 'P' in mode or 'S' in mode else 0,
        "dst_port_inc": 1 if 'P' in mode or 'D' in mode else 0,
    }
    return increments


def get_pods(
) -> Tuple[List[str], List[str]]:
    """Fetch all pods and return txN and rxN separately.
    Tuple is pair txN t rxN,  where txN is a list of pod names.
    :return:
    """
    cmd = "kubectl get pods -o json"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    pod_data = json.loads(result.stdout)

    tx_pods = []
    rx_pods = []

    for pod in pod_data["items"]:
        pod_name = pod["metadata"]["name"]
        if pod_name.startswith("tx"):
            tx_pods.append(pod_name)
        elif pod_name.startswith("rx"):
            rx_pods.append(pod_name)

    tx_pods.sort()
    rx_pods.sort()
    return tx_pods, rx_pods


def get_mac_address(pod_name: str) -> str:
    """Extract MAC address from dpdk-testpmd inside a pod with env var
    ."""
    shell_cmd = "dpdk-testpmd -a \\$PCIDEVICE_INTEL_COM_DPDK --"
    full_cmd = f"kubectl exec {pod_name} -- sh -c \"{shell_cmd}\""
    result = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
    full_output = result.stdout + result.stderr
    match = re.search(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", full_output)
    return match.group(0) if match else None


def get_numa_cores(pod_name: str) -> str:
    """Extract NUMA core bindings from numactl -s."""
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
) -> Tuple[List[str], List[str], List[str], List[str]]:
    """From each TX and RX pod collect port mac address and list of cores.

    :param tx_pods:
    :param rx_pods:
    :param collect_macs:
    :return:
    """
    tx_macs = []
    rx_macs = []
    tx_numa = []
    rx_numa = []

    for pod in tx_pods:
        print(f"📡 Collecting info for TX pod: {pod}")
        if collect_macs:
            tx_macs.append(get_mac_address(pod).strip())
        tx_numa.append(get_numa_cores(pod).strip())

    for pod in rx_pods:
        print(f"📡 Collecting info for RX pod: {pod}")
        if collect_macs:
            rx_macs.append(get_mac_address(pod).strip())
        rx_numa.append(get_numa_cores(pod).strip())

    if collect_macs:
        print("\n🧾 TX Pods MAC Addresses & NUMA Cores:")
        for i, pod in enumerate(tx_pods):
            print(f"{pod}: MAC={tx_macs[i]}, NUMA={tx_numa[i]}")

        print("\n🧾 RX Pods MAC Addresses & NUMA Cores:")
        for i, pod in enumerate(rx_pods):
            print(f"{pod}: MAC={rx_macs[i]}, NUMA={rx_numa[i]}")

    return tx_macs, rx_macs, tx_numa, rx_numa


def main(cmd: argparse.Namespace) -> None:
    """

    :param cmd:
    :return:
    """
    tx_pods, rx_pods = get_pods()
    tx_macs, rx_macs, tx_numa, rx_numa = collect_pods_related(tx_pods, rx_pods)
    os.makedirs("flows", exist_ok=True)

    flow_counts = parse_int_list(cmd.flows)
    rates = parse_int_list(cmd.rate)
    pkt_sizes = parse_int_list(cmd.pkt_size)

    for t, r, tx_mac, rx_mac, tx_numa, rx_numa in zip(tx_pods, rx_pods, tx_macs, rx_macs, tx_numa, rx_numa):
        d = f"flows/{t}-{r}"
        print(t, r, tx_mac, rx_mac, tx_numa, rx_numa)
        os.makedirs(d, exist_ok=True)
        for num_flows, rate, pkt_size in product(flow_counts, rates, pkt_sizes):
            generate_lua_scripts(
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


def copy_flows_to_pods(
        tx_pods: List[str],
        rx_pods: List[str]) -> None:
    """Copy generated Lua flows into each TX pod based on flow directory names."""
    for tx, rx in zip(tx_pods, rx_pods):
        flow_dir = f"flows/{tx}-{rx}"
        if os.path.exists(flow_dir):
            for file in os.listdir(flow_dir):
                src_path = os.path.join(flow_dir, file)
                dst_path = f"{tx}:/"
                print(f"📤 Copying {src_path} to {dst_path}")
                subprocess.run(f"kubectl cp {src_path} {dst_path}", shell=True, check=True)
        else:
            print(f"Warning: Flow directory {flow_dir} does not exist.")


def move_pktgen_lua_inside_pods(
        tx_pods: List[str]
) -> None:
    """Copy Pktgen.lua inside each TX pod from
    /root/Pktgen-DPDK/ to /usr/local/bin/."""

    for tx in tx_pods:
        print(f"📦 Copying Pktgen.lua")
        cmd = f"kubectl exec {tx} -- cp /root/Pktgen-DPDK/Pktgen.lua /usr/local/bin/"
        result = subprocess.run(cmd, shell=True)
        if result.returncode == 0:
            print(f"✅ [OK] {tx}: Copied successfully.")
        else:
            print(f"❌ [ERROR] {tx}: Failed to copy.")


def main_generate(
        cmd: argparse.Namespace
) -> None:
    """

    :param cmd:
    :return:
    """
    tx_pods, rx_pods = get_pods()
    tx_macs, rx_macs, tx_numa, rx_numa = collect_pods_related(tx_pods, rx_pods)
    os.makedirs("flows", exist_ok=True)

    flow_counts = parse_int_list(cmd.flows)
    rates = parse_int_list(cmd.rate)
    pkt_sizes = parse_int_list(cmd.pkt_size)

    for rate in rates:
        if not (1 <= rate <= 100):
            print(f"❌ Invalid rate: {rate}. Rate must be between 1 and 100 (inclusive).")
            exit(1)

    for size in pkt_sizes:
        if not (64 <= size <= 9000):
            print(f"❌ Invalid packet size: {size}. Must be between 64 and 9000.")
            exit(1)

    for t, r, tx_mac, rx_mac, tx_numa, rx_numa in zip(tx_pods, rx_pods, tx_macs, rx_macs, tx_numa, rx_numa):
        flow_dir = f"flows/{t}-{r}"
        os.makedirs(flow_dir, exist_ok=True)
        print(f"📂 Generating flows in {flow_dir}")

        for flow, rate, size in product(flow_counts, rates, pkt_sizes):
            generate_lua_scripts(
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


def start_testpmd_on_rx_pods(
        rx_pods: List[str],
        rx_numa: List[str],
        cmd: argparse.Namespace
) -> str:
    """Start dpdk-testpmd on RX pods in rxonly mode, using all available NUMA cores."""

    for index, pod in enumerate(rx_pods):
        numa_cores = rx_numa[index].strip().split()
        if len(numa_cores) < 2:
            print(f"[WARNING] Pod {pod} does not have enough NUMA cores.")
            continue

        cores_str = ",".join(numa_cores)

        kill_cmd = f"kubectl exec {pod} -- pkill -f dpdk-testpmd"
        subprocess.run(kill_cmd, shell=True)

        duration = max(int(cmd.duration) - 2, 5)  # ensure at least 5s run
        testpmd_cmd = (
            f"timeout {duration} dpdk-testpmd -l {cores_str} -n 4 --socket-mem 2048 "
            f"--proc-type auto --file-prefix testpmd_rx "
            f"-a $PCIDEVICE_INTEL_COM_DPDK "
            f"-- --forward-mode=rxonly --auto-start --stats-period 1 > /output/stats.log 2>&1 &"
        )

        kubectl_cmd = f"kubectl exec {pod} -- sh -c '{testpmd_cmd}'"
        print(f"🚀 [INFO] Starting testpmd on {pod} with cores: {cores_str}")
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
            print(f"[✅] {pod}: dpdk-testpmd is running and logging.")
        else:
            print(f"[❌] {pod}: dpdk-testpmd may have failed.")

        return cores_str


def start_pktgen_on_tx_pods(
        tx_pods: List[str],
        tx_numa: List[str],
        cmd: argparse.Namespace
) -> str:
    """Start pktgen inside each TX pod using the specified profile in interactive mode.
    :param tx_pods:  a tx pod name from which to start pktgen
    :param tx_numa: a list of core from numa node that given tx pods can provide.
    :param cmd: args for generation.
    :return: number of core used for generation.
    """
    for i, pod in enumerate(tx_pods):
        numa_cores = tx_numa[i].strip().split()
        if len(numa_cores) < 2:
            print(f"[WARNING] Pod {pod} does not have enough NUMA cores.")
            continue

        # Use core 0 and 1 if available, or fallback to first two
        core_list = ",".join(numa_cores[:2])
        main_core = numa_cores[1]
        lua_script_path = f"/{cmd.profile}"

        pktgen_cmd = (
            f"cd /usr/local/bin; timeout {cmd.duration} pktgen --no-telemetry -l "
            f"{core_list} -n 4 --socket-mem {cmd.socket_mem} "
            f"--proc-type auto --file-prefix pg "
            f"-a $PCIDEVICE_INTEL_COM_DPDK "
            f"-- -T --txd={cmd.txd} --rxd={cmd.rxd} "
            f"-f {lua_script_path} -m [{main_core}:{main_core}].0"
        )

        kubectl_cmd = [
            "kubectl", "exec", "-it", pod, "--",
            "sh", "-c", pktgen_cmd
        ]

        print(kubectl_cmd)
        print(f"[🧪] Launching interactive Pktgen on {pod} with profile: {cmd.profile}")
        subprocess.run(kubectl_cmd)

        return core_list


def stop_testpmd_on_rx_pods(rx_pods: List[str]) -> None:
    """Gracefully stop dpdk-testpmd on RX pods."""
    for pod in rx_pods:
        subprocess.run(f"kubectl exec {pod} -- pkill -SIGINT dpdk-testpmd", shell=True)
        print(f"🛑 Stopped testpmd on {pod}")


def collect_and_parse_stats(
        rx_pods: List[str],
        tx_cores: str,
        rx_cores: str,
        profile_name: str,
        output_dir: str = "results",
        sample_from: str = "/output/stats.log"
):
    """  Collect stats from dpdk-testpmd from RX pods.
    :param rx_pods:  a RX pod name
    :param tx_cores: list of core that used for generation
    :param rx_cores:  list of core that used at receiver.
    :param profile_name: a profile name.
    :param output_dir: where to save data.
    :param sample_from:
    :return:
    """

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(output_dir, exist_ok=True)

    for pod_name in rx_pods:
        print(f"\n📥 Pulling stats.log from {pod_name}...")
        local_log = f"{pod_name}_stats.log"
        try:
            subprocess.run(
                f"kubectl cp {pod_name}:{sample_from} {local_log}",
                shell=True, check=True
            )

            print(f"✅ {local_log} copied.")

            with open(local_log, "r") as f:
                lines = f.readlines()

            stats = parse_testpmd_log(lines)

            print(f"\n📈 Stats for {pod_name}:")
            for key, arr in stats.items():
                print(f"{key}: mean={arr.mean():.2f}, min={arr.min()}, max={arr.max()}")

            base_name = profile_name.replace(".lua", "")
            out_file = f"{pod_name}_tx_cores{tx_cores}_rx_cores_{rx_cores}_{base_name}_{timestamp}.npz"
            out_path = os.path.join(output_dir, out_file)

            np.savez(out_path, **stats)
            print(f"💾 Saved parsed stats to {out_path}")

        except Exception as e:
            print(f"❌ Failed for {pod_name}: {e}")


def main_start_generator(
        cmd: argparse.Namespace
) -> None:
    """
    Starts testpmd on RX pods and pktgen on TX pods unless skipped via flags.
    """
    tx_pods, rx_pods = get_pods()
    tx_macs, rx_macs, tx_numa, rx_numa = collect_pods_related(
        tx_pods, rx_pods, collect_macs=False
    )

    if not cmd.skip_copy:
        copy_flows_to_pods(tx_pods, rx_pods)
    else:
        print("⏭️  Skipping Lua profile copy step (--skip-copy)")

    rx_cores = ""
    if not cmd.skip_testpmd:
        rx_cores = start_testpmd_on_rx_pods(rx_pods, rx_numa, cmd)
    else:
        print("⏭️  Skipping testpmd launch on RX pods (--skip-testpmd)")

    move_pktgen_lua_inside_pods(tx_pods)
    tx_cores = start_pktgen_on_tx_pods(tx_pods, tx_numa, cmd)
    stop_testpmd_on_rx_pods(rx_pods)

    print("✅ Test run complete. Collecting stats...")

    collect_and_parse_stats(
        rx_pods,
        tx_cores,
        rx_cores,
        profile_name=cmd.profile,
        output_dir="results"
    )

    print("📁 All results saved in 'results/' directory.")


def parse_int_list(csv: str) -> List[int]:
    return [int(v.strip()) for v in csv.split(",") if v.strip()]


def generate_lua_scripts(
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

    # Build descriptive filename
    filename = f"flow_{num_flows}flows_{pkt_size}B_{rate}rate_{flow_mode}.lua"
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
    print(f"[✔] Generated: {output_file}")


def discover_available_profiles() -> List[str]:
    """Scan 'flows' directory and return a list of available profile Lua files."""
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


if __name__ == '__main__':

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

    # 🚀 start_generator subcommand
    start = subparsers.add_parser("start_generator", help="🚀 Start pktgen & testpmd using selected profile")
    start.add_argument("--txd", type=int, default=2048, help="🚀 TX (Transmit) descriptor count")
    start.add_argument("--rxd", type=int, default=2048, help="📡 RX (Receive) descriptor count")
    start.add_argument("--socket-mem", type=str, default="2048",
                       help="🧠 Socket memory size (e.g., '2048' or '1024,1024')")
    start.add_argument("--tx_num_core", type=int, default=2,
                       help="🚀 number of core to use for generation. "
                            "(note if it should match the number of CPUs on a POD")
    start.add_argument("--rx_num_core", type=int, default=2,
                       help="🧠 number of core to use at receiver side.")

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

    args = parser.parse_args()
    if args.command == "start_generator":
        if args.profile not in available_profiles:
            print(f"\n❌ Invalid profile: {args.profile}")
            print("📂 Run with `--help` to see available profiles.")
            exit(1)

    if args.command == "generate_flow":
        main_generate(args)
    elif args.command == "start_generator":
        main_start_generator(args)
