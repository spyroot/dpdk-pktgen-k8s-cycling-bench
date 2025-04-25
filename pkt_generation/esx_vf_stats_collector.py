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


def get_vmids_for_cluster(esxi_host: str, cluster_keyword: str) -> list:
    """
    Fetch VM IDs on a remote ESXi host that match a given cluster name substring.

    :param esxi_host: IP or hostname of the ESXi host
    :param cluster_keyword: Substring to match against VM names
    :return: List of matching VM IDs
    """
    output = run_ssh_command(esxi_host, ["vim-cmd", "vmsvc/getallvms"])
    vm_ids = []

    for line in output.splitlines():
        if cluster_keyword in line:
            match = re.match(r"^\s*(\d+)\s+([^\s]+)", line)
            if match:
                vm_id = int(match.group(1))
                vm_ids.append(vm_id)

    return vm_ids

import re

def parse_sriov_devices(raw_output: str):
    devices = []
    current_device = {}
    inside_sriov_block = False

    for line in raw_output.splitlines():
        line = line.strip()

        # Detect start of SR-IOV device block
        if line.startswith("(vim.vm.device.VirtualSriovEthernetCard) {"):
            inside_sriov_block = True
            current_device = {}

        elif inside_sriov_block:
            if line.startswith("macAddress"):
                mac_match = re.search(r'"([^"]+)"', line)
                if mac_match:
                    current_device["macAddress"] = mac_match.group(1)

            elif "pciSlotNumber" in line:
                slot_match = re.search(r"(\d+)", line)
                if slot_match:
                    current_device["pciSlotNumber"] = int(slot_match.group(1))

            elif "numaNode" in line:
                numa_match = re.search(r"(\d+)", line)
                if numa_match:
                    current_device["numaNode"] = int(numa_match.group(1))

            elif line.startswith("id =") and "physicalFunctionBacking" in prev_line:
                pf_match = re.search(r'"([^"]+)"', line)
                if pf_match:
                    current_device["pf_pci_id"] = pf_match.group(1)

            elif line.startswith("}"):  # end of block
                if current_device:
                    devices.append(current_device)
                inside_sriov_block = False

        prev_line = line

    return devices

def save_vm_device_dump(esxi_host: str, vmid: int, output_dir="vm_dumps", password="VMware1!"):
    """
    SSH to ESXi and save the output of 'vim-cmd vmsvc/device.getdevices <vmid>' to a local file.

    :param esxi_host: IP or hostname of the ESXi host
    :param vmid: VM ID to fetch device info from
    :param output_dir: Directory to save the output file
    :param password: SSH password
    """
    os.makedirs(output_dir, exist_ok=True)
    filename = os.path.join(output_dir, f"{esxi_host.replace('.', '_')}_vmid_{vmid}_devices.txt")

    print(f"📥 Fetching devices for VM ID {vmid} from {esxi_host}...")
    raw_output = run_ssh_command(
        esxi_host,
        ["vim-cmd", "vmsvc/device.getdevices", str(vmid)],
        password=password
    )

    with open(filename, "w") as f:
        f.write(raw_output)

    print(f"✅ Saved to {filename}")
    return filename

def get_sriov_devices_for_vm(esxi_host: str, vmid: str) -> list:
    """
    Fetch SR-IOV device PF PCI addresses for a given VM ID on a remote ESXi host.

    :param esxi_host: IP or hostname of the ESXi host
    :param vmid: VM ID as a string (e.g., "2")
    :return: List of dictionaries with SR-IOV device info (label, mac, PF PCI address)
    """
    output = run_ssh_command(esxi_host, ["vim-cmd", "vmsvc/device.getdevices", vmid])
    sriov_devices = []

    current_device = {}
    inside_sriov_block = False

    for line in output.splitlines():
        line = line.strip()

        # Start of SR-IOV device block
        if line.startswith('(vim.vm.device.VirtualSriovEthernetCard)'):
            current_device = {}
            inside_sriov_block = True

        if inside_sriov_block:
            if 'label =' in line:
                current_device['label'] = line.split('"')[1]
            elif 'macAddress =' in line:
                current_device['mac'] = line.split('"')[1]
            elif 'id =' in line and 'physicalFunctionBacking' in previous_line:
                pci = line.split('"')[1]
                current_device['pf_pci'] = pci
            elif line == '},':
                if 'pf_pci' in current_device:
                    sriov_devices.append(current_device)
                current_device = {}
                inside_sriov_block = False

        previous_line = line

    return sriov_devices


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

    cluster = "perf"
    vmids = get_vmids_for_cluster( "10.192.18.9", cluster)
    print(f"🔍 Found VM IDs for cluster '{cluster}': {vmids}")
    vmids = get_vmids_for_cluster( "esxi03.perf.pocs.broadcom.run", cluster)
    print(f"🔍 Found VM IDs for cluster '{cluster}': {vmids}")

    esxi_nic_map = {
        "10.192.18.9": "vmnic3",
    }

    vmids_1 = get_vmids_for_cluster("10.192.18.9", "perf")
    vmids_2 = get_vmids_for_cluster("esxi03.perf.pocs.broadcom.run", "perf")

    save_all_vm_device_dumps("10.192.18.9", vmids_1)
    save_all_vm_device_dumps("esxi03.perf.pocs.broadcom.run", vmids_2)

    #
    # duration = 60  # total duration of monitoring in seconds
    # interval = 2  # sampling interval in seconds
    # output_dir = "vf_stats_test_results"
    #
    # print("🚀 Starting VF stats monitoring...")
    # threads = start_vf_stats_threads(esxi_nic_map, interval, duration, output_dir)
    #
    # # Optional: wait for all threads to complete
    # for t in threads:
    #     t.join()
    #
    # print(f"✅ VF monitoring finished. CSVs saved in '{output_dir}'")
