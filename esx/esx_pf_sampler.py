import argparse
import time
import json
import numpy as np
from collections import defaultdict
from typing import Optional, Dict, List, Any
from cisco_samplers.ssh_operator import SSHOperator
import os


def stats_parser(
        stdout_buffer: str,
        default_token: Optional[str] = ":"
) -> Dict[str, str]:
    """Parses the raw output from 'esxcli network nic stats get' into a dictionary.

    :param stdout_buffer:  Raw output from esxcli command.
    :param default_token: (Optional[str]): Delimiter used between keys and values.
    :return:  Dict[str, str]: Parsed dictionary with stat name as key and value as string.
    """
    tokens = stdout_buffer.split('\n')
    tokens = [t.strip().split(default_token) for t in tokens if default_token in t]
    return {
        t[0].strip(): t[1].strip()
        for t in tokens
        if len(t) == 2 and t[1].strip().replace(',', '').replace('.', '').isdigit()
    }


def collect_nic_stats(
    host_info: Dict[str, Any],
    sample_interval: int = 1,
    num_samples: int = 10
) -> Dict[str, Dict[str, Any]]:
    """Collects NIC statistics from a given ESXi host over multiple samples.

    :param host_info: A dictionary containing 'host', 'username', 'password', and 'nics'.
    :param sample_interval: Time in seconds between each sample.
    :param num_samples:  Number of samples to collect per NIC.
    :return: Dict[str, Dict[str, Any]]: Dictionary of results per NIC with parsed keys and sample arrays.
    """
    ssh = SSHOperator(
        host_info["host"],
        username=host_info["username"],
        password=host_info["password"],
        is_password_auth_only=True
    )

    host_results: Dict[str, Dict[str, Any]] = {}
    for nic in host_info["nics"]:
        all_samples: Dict[str, List[str]] = defaultdict(list)

        print(f"📡 Collecting stats from {host_info['host']} NIC: {nic}")

        for _ in range(num_samples):
            time.sleep(sample_interval)
            cmd = f"esxcli network nic stats get -n {nic}"
            output, _, _ = ssh.run(host_info["host"], cmd)
            parsed = stats_parser(output)
            for key, val in parsed.items():
                all_samples[key].append(val)

        keys = list(all_samples.keys())
        np_data = np.array([list(map(int, all_samples[k])) for k in keys])
        host_results[nic] = {"keys": keys, "data": np_data}

    return host_results


def save_results(
        results: Dict[str, Dict[str, Any]],
        host: str
) -> None:
    """
    Saves NIC stats to .npz files for each NIC under a given host.

    Args:
        results (Dict[str, Dict[str, Any]]): NIC stats results per NIC.
        host (str): Host IP address or identifier.
    """
    out_dir = "nic_stats"
    os.makedirs(out_dir, exist_ok=True)
    for nic, content in results.items():
        filename = f"{host.replace('.', '_')}_{nic}.npz"
        path = os.path.join(out_dir, filename)
        np.savez(path, keys=content["keys"], data=content["data"])
        print(f"✅ Saved stats to {path}")


def main() -> None:
    """
    Entry point for the script. Parses arguments, reads JSON config,
    collects NIC stats, and saves results.
    """
    parser = argparse.ArgumentParser(description="Collect NIC stats from multiple ESXi hosts.")
    parser.add_argument(
        "-f", "--file", required=True,
        help="Path to input JSON file with host and NIC info"
    )
    parser.add_argument(
        "-n", "--num", default=10, type=int,
        help="Number of samples per NIC"
    )
    parser.add_argument(
        "-i", "--interval", default=1, type=int,
        help="Sampling interval in seconds"
    )
    args = parser.parse_args()

    with open(args.file, "r") as f:
        hosts: List[Dict[str, Any]] = json.load(f)

    for host_info in hosts:
        results = collect_nic_stats(
            host_info,
            sample_interval=args.interval,
            num_samples=args.num
        )
        save_results(results, host_info["host"])


if __name__ == '__main__':
    main()
