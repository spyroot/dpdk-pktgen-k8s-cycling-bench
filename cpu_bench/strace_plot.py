"""
This script suite is designed to run some test with strace and produce strae log
and provide stats for read and write.

Autor mus
mustafa.bayramov@broadcom.com
"""
import argparse
import re
import numpy as np
from datetime import datetime


def parse_strace_log(filepath):
    """Parse strace log to extract syscall timestamps and
    compute basic timing statistics.

    :param filepath:
    :return:
    """
    start_times = []
    durations = []

    prev_time = None
    with open(filepath) as f:
        for line in f:
            # we match write or reads
            # we try to match 12:34:56.123456 write(3, "data", 4096) = 4096
            match = re.match(r"^(\d{2}:\d{2}:\d{2}\.\d+)\s+(write|read)\(", line)
            if not match:
                continue

            timestamp_str = match.group(1)
            syscall = match.group(2)

            timestamp = datetime.strptime(timestamp_str, "%H:%M:%S.%f").timestamp()
            start_times.append(timestamp)

            if prev_time is not None:
                durations.append(timestamp - prev_time)

            prev_time = timestamp

    durations = durations[1:]
    # inter-arrival time deltas
    inter_arrivals = np.diff(start_times)

    return {
        'start_times': start_times,
        'durations': durations,
        'inter_arrivals': inter_arrivals,
        'arrival_rate': 1 / np.mean(inter_arrivals) if len(inter_arrivals) > 0 else 0,
        'mean_duration': np.mean(durations),
        'std_duration': np.std(durations),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Parse strace log for read/write timing statistics.")
    parser.add_argument('filepath', type=str, help='Path to the strace log file')
    args = parser.parse_args()

    stats = parse_strace_log(args.filepath)
    for key, value in stats.items():
        if isinstance(value, (float, int)):
            print(f"{key}: {value:.6f}")
        elif isinstance(value, (list, np.ndarray)):
            print(f"{key}: [{len(value)} values]")
        else:
            print(f"{key}: {value}")
