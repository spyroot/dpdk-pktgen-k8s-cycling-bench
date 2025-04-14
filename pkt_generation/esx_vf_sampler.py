import subprocess
import re
import time
import os
import argparse

SAMPLE_INTERVAL = 1
AVERAGE_OVER = 5
WARN_THRESHOLD_TX_PPS = 38_000_000


def clear_terminal():
    os.system("clear" if os.name == "posix" else "cls")



def get_active_vfs2(nic_name):
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


def main():
    parser = argparse.ArgumentParser(description="Live SR-IOV VF PPS monitor for ESXi")
    parser.add_argument("-n", "--nic", default="vmnic3", help="NIC name (default: vmnic3)")
    args = parser.parse_args()

    nic = args.nic
    active_vfs = get_active_vfs(nic)
    if not active_vfs:
        print(f"No active VFs found on {nic}.")
        return

    # Prime with first sample
    prev_counts = {vf_id: get_unicast_pkt_counts(nic, vf_id) for vf_id in active_vfs}
    time.sleep(SAMPLE_INTERVAL)

    while True:
        start = time.time()
        current_counts = {vf_id: get_unicast_pkt_counts(nic, vf_id) for vf_id in active_vfs}
        elapsed = time.time() - start

        clear_terminal()
        print(f"📡 Live VF PPS on {nic} (avg over {SAMPLE_INTERVAL}s)\n")
        print(f"{'VF':<5} {'RX_PPS':>12} {'TX_PPS':>12}")
        print("-" * 32)

        for vf_id in active_vfs:
            rx1, tx1 = prev_counts[vf_id]
            rx2, tx2 = current_counts[vf_id]
            rx_pps = int((rx2 - rx1) / elapsed)
            tx_pps = int((tx2 - tx1) / elapsed)
            print(f"{vf_id:<5} {rx_pps:>12,} {tx_pps:>12,}")

        prev_counts = current_counts
        time.sleep(SAMPLE_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Stopped.")
