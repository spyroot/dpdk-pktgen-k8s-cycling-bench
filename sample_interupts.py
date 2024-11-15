# This script sample at 5 second (by default) interupts
# and transpose view

#
# it useful to monitor which CPU core proccessing intrupts
# Use case if you do any irq affinity mapping.

#
# python interupt_sampler.py
# Sampling /proc/interrupts for 5 seconds...
#
# CPU0: 48      0       9       0       0       0       0       0       0
# CPU1: 0       0       0       0       0       0       0       0       0
# CPU2: 0       0       0       0       0       0       0       0       0
# CPU3: 0       0       0       0       0       0       3       0       0
# CPU4: 0       0       0       0       0       0       0       0       0
# CPU5: 0       0       0       0       0       0       0       0       0
# CPU6: 0       0       0       0       0       0       0       0       0
# CPU7: 0       0       0       0       0       0       0       0       0
# CPU8: 0       0       0       0       0       0       0       0       0
# CPU9: 0       0       0       0       0       0       0       0       0
# CPU10: 0       0       0       0       0       0       0       0       0
# CPU11: 0       0       0       0       0       0       0       0       0
# CPU12: 0       0       5       0       0       0       0       0       0
# CPU13: 0       0       0       1       0       0       0       0       0
# CPU14: 0       0       0       0       0       0       0       0       0
# CPU15: 0       0       0       0       0       0       0       0       0
# CPU16: 0       0       0       0       0       0       0       0       0
# CPU17: 0       0       0       0       0       0       0       0       0
# CPU18: 0       0       0       0       0       0       0       0       0
# CPU19: 0       0       0       0       0       0       0       0       0
# CPU20: 1903    0       0       0       0       0       0       0       0
# CPU21: 0       0       0       0       0       0       0       0       0
# CPU22: 0       0       102     0       0       0       0       0       0
# CPU23: 0       0       0       0       0       0       0       0       0
# CPU24: 0       0       0       0       0       0       0       0       0
# CPU25: 0       0       0       0       0       0       2       0       0
# CPU26: 0       0       6       0       0       0       0       0       0
#

import time
import argparse

def parse_interrupts(interface):
    """
    :return:
    """
    with open('/proc/interrupts', 'r') as f:
        data = f.readlines()

    direct_rows = [line for line in data if interface in line]

    cpu_header = data[0].split()
    cpu_count = len(cpu_header) - 1

    cpu_interrupts = {i: [0] * len(direct_rows) for i in range(cpu_count)}

    for row_index, row in enumerate(direct_rows):
        columns = row.split()
        # print(f"Row {row_index} split into columns: {columns}")

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
    :param interface:
    :param period:
    :return:
    """
    print(f"Sampling /proc/interrupts for {period} seconds...\n")

    time.sleep(period)
    cpu_names, cpu_interrupts = parse_interrupts(interface)

    for cpu_index in range(len(cpu_interrupts)):
        # Print CPU row
        print(f"CPU{cpu_index}: ", end='')
        for irq_index in range(len(cpu_interrupts[cpu_index])):
            print(f"{cpu_interrupts[cpu_index][irq_index]:<8}", end='')
        print()


if __name__ == "__main__":
    # Set up argument parsing
    parser = argparse.ArgumentParser(description="Monitor interrupts for a specific interface.")
    parser.add_argument('-i', '--interface', type=str, default='direct', help='Interface name (e.g., direct, eth0)')
    parser.add_argument('-t', '--time', type=int, default=5, help='Sampling period in seconds')
    args = parser.parse_args()
    sample_interrupts(interface=args.interface, period=args.time)

