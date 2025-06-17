
import argparse
import json
from typing import List, Optional
from cisco_samplers.ssh_operator import SSHOperator


def parse_args():
    """
    :return:
    """
    parser = argparse.ArgumentParser(description="Collect JSON stats from Cisco Nexus interfaces.")
    parser.add_argument("--device", default="10.210.24.253", help="Device IP or hostname")
    parser.add_argument("--username", default="admin", help="SSH username")
    parser.add_argument("--password", default="KaJkREVRwmsRjUcG84", help="SSH password")
    parser.add_argument(
        "--interfaces", default="Ethernet1/1,Ethernet1/2",
        help="Comma-separated list of interfaces"
    )
    return parser.parse_args()


def query_interface(
        operator: SSHOperator,
        host: str,
        interface: str) -> Optional[dict]:
    """

    :param operator:
    :param host:
    :param interface:
    :return:
    """
    cmd = f"show interface {interface} | json"
    output, exit_code, exec_time = operator.run(host, cmd)
    if exit_code != 0:
        print(f"❌ Command failed on {host} for {interface}: exit code {exit_code}")
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        print(f"⚠️ Failed to parse JSON output from {host} for {interface}")
        return None


def extract_summary(
        if_data: dict,
        iface_name: str
):
    """
    :param if_data:
    :param iface_name:
    :return:
    """
    print(if_data)
    row = if_data.get("TABLE_interface", {}).get("ROW_interface", [])
    if isinstance(row, list):
        for entry in row:
            if entry.get("interface") == iface_name:
                return entry
    elif isinstance(row, dict) and row.get("interface") == iface_name:
        return row
    return None


def main():
    args = parse_args()
    interfaces: List[str] = args.interfaces.split(",")

    operator = SSHOperator(
        args.device,
        username=args.username,
        password=args.password,
        is_password_auth_only=True
    )

    for iface in interfaces:
        iface = iface.strip()
        print(f"🔍 Querying {iface}...")
        iface_json = query_interface(operator, args.device, iface)
        if iface_json:
            stats = extract_summary(iface_json, iface)
            if stats:
                print(f"📊 {iface} - RX: {stats.get('eth_inrate1_summary_bits')}, "
                      f"TX: {stats.get('eth_outrate1_summary_bits')}, "
                      f"RX PPS: {stats.get('eth_inrate1_pktsz')}, "
                      f"TX PPS: {stats.get('eth_outrate1_summary_pkts')}")
            else:
                print(f"⚠️ No data found for {iface}")
        print()


if __name__ == '__main__':
    main()
