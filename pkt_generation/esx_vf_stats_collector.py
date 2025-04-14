import csv
import os
import re
import subprocess
import threading
import time
from datetime import datetime


def run_ssh_command(
        esxi_host,
        command,
        password="VMware1!"
):
    """
     Executes a remote SSH command on an ESXi host using `sshpass`.

    :param esxi_host: IP or hostname of the ESXi host
    :param command: Command and arguments to run (as list)
    :param password: SSH password (default is 'VMware1!')
    :return: Output of the command as a string
    """
    ssh_cmd = [
                  "sshpass", "-p", password,
                  "ssh", "-o", "StrictHostKeyChecking=no",
                  f"root@{esxi_host}"
              ] + command

    try:
        output = subprocess.check_output(ssh_cmd, text=True)
        return output
    except subprocess.CalledProcessError as e:
        print(f"❌ SSH command failed on {esxi_host}: {e}")
        return ""


def get_active_vfs(
        esxi_host,
        nic_name
):
    """Fetch list of active VF IDs for a given NIC."""
    try:
        output = run_ssh_command(esxi_host, ["esxcli", "network", "sriovnic", "vf", "list", "-n", nic_name])
        vfs = []
        for line in output.splitlines():
            match = re.match(r"\s*(\d+)\s+true", line)
            if match:
                vfs.append(int(match.group(1)))
        return vfs
    except Exception as e:
        print(f"❌ Error fetching VF list from {esxi_host}: {e}")
        return []


def get_vf_stats(
        esxi_host,
        nic_name,
        vf_id
):
    """

    :param esxi_host:
    :param nic_name:
    :param vf_id:
    :return:
    """
    try:
        output = run_ssh_command(
            esxi_host,
            ["esxcli", "network", "sriovnic", "vf", "stats", "-n", nic_name, "-v", str(vf_id)],
        )
        stats = {}
        for line in output.splitlines():
            match = re.match(r"(.+?):\s+(\d+)", line.strip())
            if match:
                key = match.group(1).strip().replace(" ", "_").lower()
                stats[key] = int(match.group(2))
        return stats
    except Exception as e:
        print(f"❌ Error fetching stats for VF {vf_id} on {nic_name}@{esxi_host}: {e}")
        return {}


def monitor_vf_stats_remote(
        esxi_host,
        nic_name,
        interval,
        duration,
        output_dir="results"
):
    """

    :param esxi_host:
    :param nic_name:
    :param interval:
    :param duration:
    :param output_dir:
    :return:
    """
    vfs = get_active_vfs(esxi_host, nic_name)
    if not vfs:
        print(f"⚠️ No active VFs found on {esxi_host} for {nic_name}")
        return

    os.makedirs(output_dir, exist_ok=True)
    csv_file = os.path.join(output_dir, f"{esxi_host.replace('.', '_')}_{nic_name}_vf_stats.csv")

    with open(csv_file, "w", newline="") as f:
        writer = None
        start_time = time.time()
        while time.time() - start_time < duration:
            timestamp = datetime.utcnow().isoformat()
            for vf in vfs:
                stats = get_vf_stats(esxi_host, nic_name, vf)
                if stats:
                    stats["timestamp"] = timestamp
                    stats["vf_id"] = vf
                    stats["nic_name"] = nic_name
                    stats["esxi_host"] = esxi_host

                    if writer is None:
                        fieldnames = list(stats.keys())
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()

                    writer.writerow(stats)
                    f.flush()
            time.sleep(interval)


def start_vf_stats_threads(
        esxi_nic_map: dict,
        interval: int,
        duration: int,
        output_dir: str = "results"
):
    """

    :param esxi_nic_map:
    :param interval:
    :param duration:
    :param output_dir:
    :return:
    """
    threads = []
    for esxi_host, nic_name in esxi_nic_map.items():
        t = threading.Thread(
            target=monitor_vf_stats_remote,
            args=(esxi_host, nic_name, interval, duration, output_dir),
            daemon=True
        )
        t.start()
        threads.append(t)
    return threads


if __name__ == "__main__":
    esxi_nic_map = {
        "10.192.18.9": "vmnic3",
    }

    duration = 60  # total duration of monitoring in seconds
    interval = 2  # sampling interval in seconds
    output_dir = "vf_stats_test_results"

    print("🚀 Starting VF stats monitoring...")
    threads = start_vf_stats_threads(esxi_nic_map, interval, duration, output_dir)

    # Optional: wait for all threads to complete
    for t in threads:
        t.join()

    print(f"✅ VF monitoring finished. CSVs saved in '{output_dir}'")
