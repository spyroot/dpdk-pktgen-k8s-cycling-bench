import subprocess
import json
import re
import os
import argparse
import threading
from ipaddress import ip_address
from typing import List, Tuple
import time
from itertools import product
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt  # Importing matplotlib for plotting


# Existing LUA_UDP_TEMPLATE and other functions...

def parse_testpmd_log(log_lines):
    """
    Parse the testpmd log to extract statistics.
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


# Existing functions...

def collect_and_parse_stats(rx_pods: List[str], profile_name: str, output_dir: str = "results"):
    """
    Collect and parse statistics from RX pods.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(output_dir, exist_ok=True)

    for pod in rx_pods:
        print(f"\n📥 Pulling stats.log from {pod}...")
        local_log = f"{pod}_stats.log"
        try:
            subprocess.run(
                f"kubectl cp {pod}:/output/stats.log {local_log}",
                shell=True, check=True
            )
            print(f"✅ {local_log} copied.")

            with open(local_log, "r") as f:
                lines = f.readlines()

            stats = parse_testpmd_log(lines)

            print(f"\n📈 Stats for {pod}:")
            for key, arr in stats.items():
                print(f"{key}: mean={arr.mean():.2f}, min={arr.min()}, max={arr.max()}")

            base_name = profile_name.replace(".lua", "")
            out_file = f"{pod}_{base_name}_{timestamp}.npz"
            out_path = os.path.join(output_dir, out_file)

            np.savez(out_path, **stats)
            print(f"💾 Saved parsed stats to {out_path}")

            # Plot the statistics
            plot_stats(out_path)

        except Exception as e:
            print(f"❌ Failed for {pod}: {e}")


def plot_stats(npz_file: str):
    """
    Plot the statistics from the npz file.
    """
    data = np.load(npz_file)
    time_axis = np.arange(len(data['rx_pps']))

    plt.figure(figsize=(12, 8))

    plt.subplot(2, 1, 1)
    plt.plot(time_axis, data['rx_pps'], label='RX PPS', color='b')
    plt.plot(time_axis, data['tx_pps'], label='TX PPS', color='r')
    plt.xlabel('Time (s)')
    plt.ylabel('Packets Per Second')
    plt.title('Packets Per Second Over Time')
    plt.legend()
    plt.grid(True)

    plt.subplot(2, 1, 2)
    plt.plot(time_axis, data['rx_bytes'], label='RX Bytes', color='b')
    plt.plot(time_axis, data['tx_bytes'], label='TX Bytes', color='r')
    plt.xlabel('Time (s)')
    plt.ylabel('Bytes Per Second')
    plt.title('Bytes Per Second Over Time')
    plt.legend()
    plt.grid(True)

    plt.tight_layout()
    plt.show()


# Existing main functions...

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
    gen.add_argument("--base-src-port", default="1024", help="Base source
    ::contentReference[oaicite:0]
    {index = 0}

