"""

This script monitor pps per each queue.
It support vmxnet3 and intel card, stats taken directly from ethtool

=== TX, RX PPS Rates, and Drops for Interface: sriov_1 (NIC Type: sriov) ===

Queue      TX PPS               RX PPS               Drops PPS
======================================================================
0          0                    0                    0
1          0                    0                    0
2          0                    0                    0
3          0                    0                    0
4          0                    0                    0
5          0                    0                    0
6          0                    0                    0
7          0                    0                    0
8          0                    0                    0
9          0                    0                    0
10         0                    0                    0
11         0                    0                    0
12         0                    0                    0
13         0                    0                    0
14         0                    0                    0
15         0                    0                    0

Author mus spyroot@gmail.com
"""
import os
import time
import re
from collections import defaultdict
from typing import Dict, Tuple, DefaultDict
import argparse


def parse_vmxnet3_stats(
        output: str
) -> Tuple[DefaultDict[int, int], DefaultDict[int, int], DefaultDict[int, int]]:
    """Parses ethtool -S output for vmxnet3 NICs.
    :param output:
    :return:
    """
    tx_stats = defaultdict(int)
    rx_stats = defaultdict(int)
    drops_stats = defaultdict(int)
    current_queue = None

    for line in output.splitlines():
        line = line.strip()
        if line.startswith("Tx Queue#:"):
            current_queue = int(re.search(r"Tx Queue#: (\d+)", line).group(1))
        elif current_queue is not None and "ucast pkts tx" in line:
            tx_stats[current_queue] = int(line.split(":")[1].strip())
        elif line.startswith("Rx Queue#:"):
            current_queue = int(re.search(r"Rx Queue#: (\d+)", line).group(1))
        elif current_queue is not None and "ucast pkts rx" in line:
            rx_stats[current_queue] = int(line.split(":")[1].strip())
        elif "drv dropped tx total" in line:
            drops_stats[current_queue] = int(line.split(":")[1].strip())
        elif "drv dropped rx total" in line:
            queue = current_queue if current_queue is not None else 0
            drops_stats[queue] += int(line.split(":")[1].strip())
        elif "pkts tx discard" in line:
            queue = current_queue if current_queue is not None else 0
            drops_stats[queue] += int(line.split(":")[1].strip())

    return tx_stats, rx_stats, drops_stats


def parse_sriov_stats(
        output: str
) -> Tuple[DefaultDict[int, int], DefaultDict[int, int], DefaultDict[int, int]]:
    """Parses ethtool -S output for SR-IOV NICs.
    :param output:
    :return:
    """
    tx_stats = defaultdict(int)
    rx_stats = defaultdict(int)
    drops_stats = defaultdict(int)
    for line in output.splitlines():
        line = line.strip()
        tx_match = re.match(r"tx-(\d+)\.packets:\s*(\d+)", line)
        rx_match = re.match(r"rx-(\d+)\.packets:\s*(\d+)", line)
        drop_match = re.match(r"rx-(\d+)\.disc:\s*(\d+)", line)  # Adjust for drop field
        if tx_match:
            queue = int(tx_match.group(1))
            tx_stats[queue] = int(tx_match.group(2))
        elif rx_match:
            queue = int(rx_match.group(1))
            rx_stats[queue] = int(rx_match.group(2))
        elif drop_match:
            queue = int(drop_match.group(1))
            drops_stats[queue] = int(drop_match.group(2))
    return tx_stats, rx_stats, drops_stats


def detect_nic_type(
        output: str
) -> str:
    """Detects the NIC type based on the ethtool output.
    :param output:
    :return:
    """
    if "Tx Queue#:" in output:
        return "vmxnet3"
    elif re.search(r"tx-\d+\.packets:", output):
        return "sriov"
    return "unknown"


def calculate_pps_rate(
        prev_stats: DefaultDict[int, int], current_stats: DefaultDict[int, int], interval: float
) -> Dict[int, float]:
    """Calculates the PPS rate by comparing current and previous statistics.
    :param prev_stats:
    :param current_stats:
    :param interval:
    :return:
    """
    pps_rate = {}
    for queue in set(prev_stats.keys()).union(current_stats.keys()):
        prev_value = prev_stats.get(queue, 0)
        current_value = current_stats.get(queue, 0)
        pps_rate[queue] = (current_value - prev_value) / interval
    return pps_rate


def display_pps(
        tx_pps: Dict[int, float],
        rx_pps: Dict[int, float],
        drop_pps: Dict[int, float],
        interface: str,
        nic_type: str
) -> None:
    """Displays the PPS rates for TX, RX, and Drops in a refreshing format.
    :param tx_pps:
    :param rx_pps:
    :param drop_pps:
    :param interface:
    :param nic_type:
    :return:
    """
    os.system('clear')
    print(f"=== TX, RX PPS Rates, and Drops for Interface: {interface} (NIC Type: {nic_type}) ===\n")
    print("{:<10} {:<20} {:<20} {:<20}".format("Queue", "TX PPS", "RX PPS", "Drops PPS"))
    print("=" * 70)
    for queue in sorted(set(tx_pps.keys()).union(rx_pps.keys(), drop_pps.keys())):
        tx_rate = tx_pps.get(queue, 0)
        rx_rate = rx_pps.get(queue, 0)
        drop_rate = drop_pps.get(queue, 0)
        print("{:<10} {:<20} {:<20} {:<20}".format(queue, round(tx_rate), round(rx_rate), round(drop_rate)))


def main() -> None:
    """ Main function. """
    parser = argparse.ArgumentParser(description="Monitor TX, RX PPS, and Drops for a given interface.")
    parser.add_argument(
        "-i", "--interface",
        default="direct",
        help="The network interface to monitor (default: direct)"
    )
    parser.add_argument(
        "-t", "--interval",
        type=float,
        default=1.0,
        help="Sampling interval in seconds (default: 1.0)"
    )
    args = parser.parse_args()
    interface = args.interface
    interval = args.interval

    prev_tx_stats, prev_rx_stats, prev_drops_stats = defaultdict(int), defaultdict(int), defaultdict(int)

    while True:
        try:
            # Run the `ethtool -S` command for the specified interface
            result = os.popen(f'ethtool -S {interface}').read()
            if not result:
                raise ValueError(
                    f"Failed to fetch stats. Ensure `ethtool -S {interface}` works and the interface exists.")

            # Detect the NIC type and parse the stats accordingly
            nic_type = detect_nic_type(result)
            if nic_type == "vmxnet3":
                current_tx_stats, current_rx_stats, current_drops_stats = parse_vmxnet3_stats(result)
            elif nic_type == "sriov":
                current_tx_stats, current_rx_stats, current_drops_stats = parse_sriov_stats(result)
            else:
                raise ValueError("Unknown NIC type. Unable to parse the statistics.")

            tx_pps = calculate_pps_rate(prev_tx_stats, current_tx_stats, interval)
            rx_pps = calculate_pps_rate(prev_rx_stats, current_rx_stats, interval)
            drop_pps = calculate_pps_rate(prev_drops_stats, current_drops_stats, interval)

            display_pps(tx_pps, rx_pps, drop_pps, interface, nic_type)
            prev_tx_stats, prev_rx_stats, prev_drops_stats = current_tx_stats, current_rx_stats, current_drops_stats

            time.sleep(interval)
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")
            break


if __name__ == "__main__":
    main()
