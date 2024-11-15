# This script sample at 5 second (by default) interrupts
# and transpose view it useful to monitor which CPU core processing interrupts
# Use case if you do any irq affinity mapping.

#
# Author Mus spyroot@gmail.com
#
# python interrupt_sampler.py
# Sampling /proc/interrupts for 5 seconds...
#
# python i.py -c -i direct -t 2 -l 2.5
# Starting continuous sampling every 2 seconds...
#
#
# Filtered Interrupts:
# CPU20: 1903    0       0       0       0       0       0       0       0
#
# Filtered Interrupts:
# CPU20: 3806    0       0       0       0       0       0       0       0
#
# Filtered Interrupts:
# CPU20: 5709    0       0       0       0       0       0       0       0
#
# Filtered Interrupts:
# CPU20: 7612    0       0       0       0       0       0       0       0
# CPU22: 0       0       408     0       0       0       0       0       0
#
# Filtered Interrupts:
# CPU20: 9515    0       0       0       0       0       0       0       0
# CPU22: 0       0       510     0       0       0       0       0       0
#
# Filtered Interrupts:
# CPU20: 11418   0       0       0       0       0       0       0       0
# CPU22: 0       0       612     0       0       0       0       0       0
#
# Filtered Interrupts:
# CPU0: 336     0       0       0       0       0       0       0       0
# CPU20: 13321   0       0       0       0       0       0       0       0
# CPU22: 0       0       714     0       0       0       0       0       0
#
# Filtered Interrupts:
# CPU0: 384     0       0       0       0       0       0       0       0
# CPU20: 15224   0       0       0       0       0       0       0       0
# CPU22: 0       0       816     0       0       0       0       0       0

import time
import argparse
import math
from collections import defaultdict


def parse_interrupts(interface):
    """
    Parses /proc/interrupts and extracts data for the specified interface.
    :param interface: The interface name to filter (e.g., direct, eth0).
    :return: CPU headers and CPU interrupt data as a dictionary.
    """
    with open('/proc/interrupts', 'r') as f:
        data = f.readlines()

    direct_rows = [line for line in data if interface in line]

    cpu_header = data[0].split()
    cpu_count = len(cpu_header) - 1

    cpu_interrupts = {i: [0] * len(direct_rows) for i in range(cpu_count)}

    for row_index, row in enumerate(direct_rows):
        columns = row.split()
        irq_name = columns[0]

        for cpu_index in range(1, len(columns)):
            if cpu_index - 1 < cpu_count:
                try:
                    cpu_interrupts[cpu_index - 1][row_index] = int(columns[cpu_index])
                except ValueError:
                    cpu_interrupts[cpu_index - 1][row_index] = 0
                    print(f"Warning: Non-integer value for IRQ {irq_name}, CPU {cpu_index - 1}, using 0.")

    return cpu_header[1:], cpu_interrupts


def sample_interrupts(interface, period=5):
    """
    Samples /proc/interrupts once for the specified period.
    :param interface: The interface name to filter (e.g., direct, eth0).
    :param period: Sampling duration in seconds.
    """
    print(f"Sampling /proc/interrupts for {period} seconds...\n")
    time.sleep(period)
    cpu_names, cpu_interrupts = parse_interrupts(interface)
    display_interrupts(cpu_names, cpu_interrupts)


def continuous_sampling(interface, period=5, threshold=None):
    """
    Continuously samples /proc/interrupts at the specified interval
    and filters results based on a threshold.

    see display_interrupts

    :param interface: The interface name to filter (e.g., direct, eth0).
    :param period: Sampling interval in seconds.
    :param threshold: Logarithmic threshold for filtering minor interrupts.
    """
    print(f"Starting continuous sampling every {period} seconds...\n")
    cumulative_interrupts = defaultdict(lambda: [0] * len(parse_interrupts(interface)[1][0]))

    try:
        while True:
            time.sleep(period)
            _, cpu_interrupts = parse_interrupts(interface)

            for cpu_index in cpu_interrupts:
                for irq_index, value in enumerate(cpu_interrupts[cpu_index]):
                    cumulative_interrupts[cpu_index][irq_index] += value

            if threshold is not None:
                display_filtered_interrupts(cumulative_interrupts, threshold)
            else:
                display_interrupts(cpu_interrupts.keys(), cpu_interrupts)
    except KeyboardInterrupt:
        print("\nStopping continuous sampling...")


def display_interrupts(cpu_names, cpu_interrupts):
    """
    Displays interrupt data for all CPUs.

    :param cpu_names: List of CPU headers.
    :param cpu_interrupts: Dictionary of CPU interrupt data.
    """
    for cpu_index in range(len(cpu_interrupts)):
        print(f"CPU{cpu_index}: ", end='')
        for irq_index in range(len(cpu_interrupts[cpu_index])):
            print(f"{cpu_interrupts[cpu_index][irq_index]:<8}", end='')
        print()


def display_filtered_interrupts(cumulative_interrupts, threshold):
    """
    Displays interrupt data with filtering based on a logarithmic threshold.
    Rows with all values below the threshold are excluded.

    So value close in log scale are displayed value very far
    i.e 5 intrupts vs 5 000 000 ( we really don't care about 5)

    :param cumulative_interrupts: Cumulative interrupt data over time.
    :param threshold: Logarithmic threshold for filtering minor interrupts.
    """
    print("\nFiltered Interrupts:")
    for cpu_index in cumulative_interrupts:
        filtered_row = []
        significant_values = False

        for irq_index, value in enumerate(cumulative_interrupts[cpu_index]):
            if value > 0 and math.log10(value) >= threshold:
                filtered_row.append(f"{value:<8}")
                significant_values = True
            else:
                filtered_row.append("0       ")

        if significant_values:
            print(f"CPU{cpu_index}: ", end='')
            print(''.join(filtered_row))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monitor interrupts for a specific interface.")
    parser.add_argument('-i', '--interface', type=str, default='direct', help='Interface name (e.g., direct, eth0)')
    parser.add_argument('-t', '--time', type=int, default=5, help='Sampling period in seconds')
    parser.add_argument('-c', '--continuous', action='store_true', help='Enable continuous sampling mode')
    parser.add_argument('-l', '--log-threshold', type=float, default=None,
                        help='Log scale threshold for filtering interrupts')
    args = parser.parse_args()

    if args.continuous:
        continuous_sampling(interface=args.interface, period=args.time, threshold=args.log_threshold)
    else:
        sample_interrupts(interface=args.interface, period=args.time)
