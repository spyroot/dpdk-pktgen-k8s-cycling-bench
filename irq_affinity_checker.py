"""
------------
This Python script is designed to monitor IRQ (Interrupt Request) affinity mappings
for network-related interrupts in real-time.

It dynamically identifies IRQs associated with network interfaces and checks
if multiple IRQs are mapped to the same CPU core, potentially causing bottlenecks
or performance issues.

Example

python irq_affinity_checker.py -l

Detected Network Adapters and Associated IRQs:
Interface: eth0-rxtx-0, IRQ: 26
Interface: eth0-rxtx-1, IRQ: 27
Interface: eth0-rxtx-2, IRQ: 28
Interface: eth0-rxtx-3, IRQ: 29
Interface: eth0-rxtx-4, IRQ: 30
Interface: eth0-rxtx-5, IRQ: 31
Interface: eth0-rxtx-6, IRQ: 32
Interface: eth0-rxtx-7, IRQ: 33
Interface: eth0-event-8, IRQ: 34
Interface: direct-rxtx-0, IRQ: 35
Interface: direct-rxtx-1, IRQ: 36
Interface: direct-rxtx-2, IRQ: 37
Interface: direct-rxtx-3, IRQ: 38
Interface: direct-rxtx-4, IRQ: 39
Interface: direct-rxtx-5, IRQ: 40
Interface: direct-rxtx-6, IRQ: 41
Interface: direct-rxtx-7, IRQ: 42
Interface: direct-event-8, IRQ: 43
Interface: iavf-sriov_4-TxRx-0, IRQ: 48
Interface: iavf-sriov_4-TxRx-1, IRQ: 49
Interface: iavf-sriov_4-TxRx-2, IRQ: 50
Interface: iavf-sriov_4-TxRx-3, IRQ: 51
Interface: iavf-sriov_5-TxRx-0, IRQ: 53
Interface: iavf-sriov_5-TxRx-1, IRQ: 54
Interface: iavf-sriov_5-TxRx-2, IRQ: 55
Interface: iavf-sriov_5-TxRx-3, IRQ: 56
Interface: iavf-sriov_0-TxRx-0, IRQ: 58
Interface: iavf-sriov_0-TxRx-1, IRQ: 59
Interface: iavf-sriov_0-TxRx-2, IRQ: 60
Interface: iavf-sriov_0-TxRx-3, IRQ: 61
Interface: iavf-sriov_1-TxRx-0, IRQ: 63
Interface: iavf-sriov_1-TxRx-1, IRQ: 64
Interface: iavf-sriov_1-TxRx-2, IRQ: 65
Interface: iavf-sriov_1-TxRx-3, IRQ: 66
Interface: iavf-sriov_3-TxRx-0, IRQ: 68
Interface: iavf-sriov_3-TxRx-1, IRQ: 69
Interface: iavf-sriov_3-TxRx-2, IRQ: 70
Interface: iavf-sriov_3-TxRx-3, IRQ: 71
Interface: iavf-sriov_2-TxRx-0, IRQ: 73
Interface: iavf-sriov_2-TxRx-1, IRQ: 74
Interface: iavf-sriov_2-TxRx-2, IRQ: 75
Interface: iavf-sriov_2-TxRx-3, IRQ: 76
Monitoring IRQ affinity every 5 seconds...

Warning: CPU core 0 is assigned to multiple IRQs: 26, 27, 28, 29, 30, 31, 32, 33, 34, 48,
49, 50, 51, 53, 54, 55, 56, 58, 59, 60, 61, 63, 64, 65, 66, 68, 69, 70, 71, 73, 74, 75, 76
Warning: CPU core 20-27 is assigned to multiple IRQs: 35, 36, 37, 38, 39, 40, 41, 42, 43

Author Mus spyroot@gmail.com
"""
import time
import os
import argparse
from collections import defaultdict


def parse_affinity(irq):
    """ Reads the smp_affinity_list for a given IRQ and returns a list of CPUs assigned to it.
    :param irq:
    :return:
    """
    try:
        with open(f"/proc/irq/{irq}/smp_affinity_list", "r") as f:
            cpu_list = f.read().strip()
        return [cpu.strip() for cpu in cpu_list.split(",")]
    except FileNotFoundError:
        return []


def get_network_irqs():
    """
    :return:
    """
    network_interfaces = os.listdir("/sys/class/net")
    irqs = {}
    with open("/proc/interrupts", "r") as f:
        for line in f:
            columns = line.split()
            # Check if the last column partially matches any network interface
            if len(columns) > 1 and any(iface in columns[-1] for iface in network_interfaces):
                irq = columns[0].strip(":")
                irqs[irq] = columns[-1]
    return irqs


def detect_conflicts(irq_to_cpu_map):
    """ Detects and prints conflicts if multiple IRQs are mapped to the same CPU core.
    :param irq_to_cpu_map:
    :return:
    """
    cpu_to_irqs = defaultdict(list)

    for irq, cpus in irq_to_cpu_map.items():
        for cpu in cpus:
            cpu_to_irqs[cpu].append(irq)

    for cpu, irqs in cpu_to_irqs.items():
        if len(irqs) > 1:
            print(f"Warning: CPU core {cpu} is assigned to multiple IRQs: {', '.join(irqs)}")


def monitor_affinity(interval, duration=None):
    """ Monitors IRQ affinity mappings over time.
    :param interval:
    :param duration:
    :return:
    """
    print(f"Monitoring IRQ affinity every {interval} seconds...")

    start_time = time.time()
    while True:
        irq_to_cpu_map = {}
        network_irqs = get_network_irqs()

        if not network_irqs:
            print("No network-related IRQs found.")
            break

        for irq in network_irqs:
            cpus = parse_affinity(irq)
            irq_to_cpu_map[irq] = cpus

        detect_conflicts(irq_to_cpu_map)

        if duration and time.time() - start_time >= duration:
            print("Monitoring complete.")
            break

        time.sleep(interval)


def list_adapters_and_irqs():
    """ Prints a list of all network adapters and their associated IRQs.
    :return:
    """
    irqs = get_network_irqs()
    if irqs:
        print("\nDetected Network Adapters and Associated IRQs:")
        for irq, interface in irqs.items():
            print(f"Interface: {interface}, IRQ: {irq}")
    else:
        print("No network-related IRQs found.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monitor IRQ affinity conflicts in real-time.")
    parser.add_argument("-i",
                        "--interval",
                        type=int, default=5,
                        help="Sampling interval in seconds (default: 5)")
    parser.add_argument("-d", "--duration",
                        type=int, default=None,
                        help="Total duration to monitor in seconds (default: infinite)"
                        )
    parser.add_argument("-l", "--list",
                        action="store_true",
                        help="List all network adapters and associated IRQs on first run")
    args = parser.parse_args()

    if os.geteuid() != 0:
        print("This script must be run as root.")
        exit(1)

    if args.list:
        list_adapters_and_irqs()

    monitor_affinity(args.interval, args.duration)
