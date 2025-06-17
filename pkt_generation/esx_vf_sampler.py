# This script sample stats from PF and report for active VF.
# Tested on ESXi 8.0.x
#
# Author Mus
# spyroot@gmail.com

import subprocess
import re
import time
import os
import argparse
from typing import Tuple, Dict

SAMPLE_INTERVAL = 1
AVERAGE_OVER = 5
WARN_THRESHOLD_TX_PPS = 38_000_000


def clear_terminal():
    os.system("clear" if os.name == "posix" else "cls")


def get_pf_stats(nic_name: str) -> Dict[str, int]:
    """
    Collects stats for the physical NIC.
    Returns: dict with rx_pkts, tx_pkts, rx_errors, tx_errors, rx_drops, tx_drops
    """
    try:
        output = subprocess.check_output(
            ["esxcli", "network", "nic", "stats", "get", "-n", nic_name],
            text=True
        )
        stats = {
            "rx_pkts": int(re.search(r"Packets received:\s+(\d+)", output).group(1)) if re.search(r"Packets received:\s+(\d+)", output) else 0,
            "tx_pkts": int(re.search(r"Packets sent:\s+(\d+)", output).group(1)) if re.search(r"Packets sent:\s+(\d+)", output) else 0,
            "rx_drops": int(re.search(r"Receive packets dropped:\s+(\d+)", output).group(1)) if re.search(r"Receive packets dropped:\s+(\d+)", output) else 0,
            "tx_drops": int(re.search(r"Transmit packets dropped:\s+(\d+)", output).group(1)) if re.search(r"Transmit packets dropped:\s+(\d+)", output) else 0,
            "rx_errors": int(re.search(r"Total receive errors:\s+(\d+)", output).group(1)) if re.search(r"Total receive errors:\s+(\d+)", output) else 0,
            "tx_errors": int(re.search(r"Total transmit errors:\s+(\d+)", output).group(1)) if re.search(r"Total transmit errors:\s+(\d+)", output) else 0,
        }
        return stats
    except subprocess.CalledProcessError:
        return {"rx_pkts": 0, "tx_pkts": 0, "rx_drops": 0, "tx_drops": 0, "rx_errors": 0, "tx_errors": 0}


def get_active_vfs(nic_name: str):
    """Fetch list of active VF IDs for a given NIC."""
    try:
        output = subprocess.check_output(
            ["esxcli", "network", "sriovnic", "vf", "list", "-n", nic_name],
            text=True
        )
        vfs = []
        for line in output.splitlines():
            match = re.match(r"\s*(\d+)\s+true", line)
            if match:
                vfs.append(int(match.group(1)))
        return vfs
    except subprocess.CalledProcessError as e:
        print(f"❌ Error fetching VF list: {e}")
        return []


def get_vf_stats(
        nic_name: str,
        vf_id: int
) -> Dict[str, int]:
    """
    Returns VF stats as a dictionary: RX/TX unicast pkts, RX errordrops, TX discards, and TX errors.
    """
    try:
        output = subprocess.check_output(
            ["esxcli", "network", "sriovnic", "vf", "stats", "-n", nic_name, "-v", str(vf_id)],
            text=True
        )
        stats = {
            "rx_pkts": int(re.search(r"Rx Unicast Pkt:\s+(\d+)", output).group(1))
            if re.search(r"Rx Unicast Pkt:\s+(\d+)", output) else 0,

            "tx_pkts": int(re.search(r"Tx Unicast Pkt:\s+(\d+)", output).group(1))
            if re.search(r"Tx Unicast Pkt:\s+(\d+)", output) else 0,

            "rx_errors": int(re.search(r"Rx Errordrops:\s+(\d+)", output).group(1))
            if re.search(r"Rx Errordrops:\s+(\d+)", output) else 0,

            "tx_discards": int(re.search(r"Tx Discards:\s+(\d+)", output).group(1))
            if re.search(r"Tx Discards:\s+(\d+)", output) else 0,

            "tx_errors": int(re.search(r"Tx Errors:\s+(\d+)", output).group(1))
            if re.search(r"Tx Errors:\s+(\d+)", output) else 0,
        }
        return stats
    except subprocess.CalledProcessError:
        return {"rx_pkts": 0, "tx_pkts": 0, "rx_errors": 0, "tx_discards": 0, "tx_errors": 0}


def get_active_vfs(nic_name: str):
    """Fetch list of active VF IDs for a given NIC."""
    try:
        output = subprocess.check_output(
            ["esxcli", "network", "sriovnic", "vf", "list", "-n", nic_name],
            text=True
        )
        vfs = []
        for line in output.splitlines():
            match = re.match(r"\s*(\d+)\s+true", line)
            if match:
                vfs.append(int(match.group(1)))
        return vfs
    except subprocess.CalledProcessError as e:
        print(f"❌ Error fetching VF list: {e}")
        return []


def main():
    parser = argparse.ArgumentParser(description="📊 Live SR-IOV VF Stats Monitor for ESXi")
    parser.add_argument("-n", "--nic", default="vmnic3", help="NIC name (default: vmnic3)")
    args = parser.parse_args()

    nic = args.nic
    active_vfs = get_active_vfs(nic)
    if not active_vfs:
        print(f"❌ No active VFs found on {nic}.")
        return

    # Prime with first sample
    prev_vf_stats = {vf_id: get_vf_stats(nic, vf_id) for vf_id in active_vfs}
    prev_pf_stats = get_pf_stats(nic)
    time.sleep(SAMPLE_INTERVAL)

    while True:
        start = time.time()
        current_stats = {vf_id: get_vf_stats(nic, vf_id) for vf_id in active_vfs}
        curr_pf_stats = get_pf_stats(nic)
        elapsed = time.time() - start

        clear_terminal()
        print(f"📡 Live VF Stats on {nic} (avg over {SAMPLE_INTERVAL}s)\n")
        print(f"{'VF':<5} {'RX_PPS':>10} {'TX_PPS':>10} {'RX_ERR/s':>10} {'TX_DROP/s':>12} {'TX_ERR/s':>10}")
        print("-" * 66)

        for vf_id in active_vfs:
            prev = prev_vf_stats[vf_id]
            curr = current_stats[vf_id]

            rx_pps = int((curr["rx_pkts"] - prev["rx_pkts"]) / elapsed)
            tx_pps = int((curr["tx_pkts"] - prev["tx_pkts"]) / elapsed)
            rx_err = int((curr["rx_errors"] - prev["rx_errors"]) / elapsed)
            tx_drop = int((curr["tx_discards"] - prev["tx_discards"]) / elapsed)
            tx_err = int((curr["tx_errors"] - prev["tx_errors"]) / elapsed)

            print(f"{vf_id:<5} {rx_pps:>10,} {tx_pps:>10,} {rx_err:>10,} {tx_drop:>12,} {tx_err:>10,}")

        print("\n🌐 PF (Physical Function) Stats:\n")
        print(f"{'TYPE':<10} {'PPS':>12} {'ERROR/s':>12} {'DROP/s':>12}")
        print("-" * 50)

        rx_pps = int((curr_pf_stats["rx_pkts"] - prev_pf_stats["rx_pkts"]) / elapsed)
        tx_pps = int((curr_pf_stats["tx_pkts"] - prev_pf_stats["tx_pkts"]) / elapsed)
        rx_err = int((curr_pf_stats["rx_errors"] - prev_pf_stats["rx_errors"]) / elapsed)
        tx_err = int((curr_pf_stats["tx_errors"] - prev_pf_stats["tx_errors"]) / elapsed)
        rx_drop = int((curr_pf_stats["rx_drops"] - prev_pf_stats["rx_drops"]) / elapsed)
        tx_drop = int((curr_pf_stats["tx_drops"] - prev_pf_stats["tx_drops"]) / elapsed)

        print(f"{'RX':<10} {rx_pps:>12,} {rx_err:>12,} {rx_drop:>12,}")
        print(f"{'TX':<10} {tx_pps:>12,} {tx_err:>12,} {tx_drop:>12,}")

        # update
        prev_vf_stats = current_stats
        prev_pf_stats = curr_pf_stats
        time.sleep(SAMPLE_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Stopped.")


