import os
import json
import glob
import argparse
import re


def process_json_file(file_path, interface_mapping):
    """

    :param file_path:
    :param interface_mapping:
    :return:
    """
    if os.path.getsize(file_path) == 0:
        print(f"Skipping empty file: {file_path}")
        return None

    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from {file_path}: {e}")
        return None

    filename = os.path.basename(file_path)
    parts = filename.split('_')
    if len(parts) < 6:
        print(f"Filename {filename} does not conform to expected format.")
        return None

    protocol = parts[0].upper()
    packet_size = parts[1]
    interface = parts[2]
    zerocopy = parts[3]
    affinity = parts[4]
    parallel = parts[5].split('.')[0]

    interface = interface_mapping.get(interface, interface)

    is_sender = False
    if 'start' in data and 'test_start' in data['start']:
        is_sender = data['start']['test_start'].get('role') == 'client'

    summary = data['end'].get('sum_sent') if is_sender else data['end'].get('sum_received')
    if not summary:
        print(f"Summary data not found in {filename}.")
        return None

    total_packets = summary.get('packets', 0)
    lost_packets = summary.get('lost_packets', 0)
    duration = summary.get('seconds', 1)
    pps = total_packets / duration
    lost_percent = (lost_packets / total_packets) * 100 if total_packets > 0 else 0

    return {
        'Protocol': protocol,
        'Packet Size': packet_size,
        'Interface': interface,
        'Zerocopy': zerocopy,
        'Affinity': affinity,
        'Parallel': parallel,
        'PPS (Mpps)': f"{pps / 1_000_000:.3f}",
        'Lost Percent (%)': f"{lost_percent:.3f}"
    }


def natural_sort_key(s):
    """

    :param s:
    :return:
    """
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]


def parse_interface_mapping(mapping_str):
    """

    :param mapping_str:
    :return:
    """
    mapping = {}
    if mapping_str:
        pairs = mapping_str.split(',')
        for pair in pairs:
            key, value = pair.split(':')
            mapping[key.strip()] = value.strip()
    return mapping


def main():
    """

    :return:
    """
    parser = argparse.ArgumentParser(description="Process iPerf3 JSON output files.")
    parser.add_argument('-d', '--directory', default='/output/', help='Directory containing JSON files.')
    parser.add_argument('-m', '--mapping', help='Interface mapping in the format "eth0:cni,net1:macvlan,net2:sriov".')
    args = parser.parse_args()

    output_dir = args.directory
    interface_mapping = parse_interface_mapping(args.mapping)

    json_files = glob.glob(os.path.join(output_dir, '*.json'))
    json_files.sort(key=natural_sort_key)
    results = []

    for json_file in json_files:
        result = process_json_file(json_file, interface_mapping)
        if result:
            results.append(result)

    if results:
        headers = results[0].keys()
        header_line = ' | '.join(f"{header:<15}" for header in headers)
        separator_line = '-' * len(header_line)
        print(header_line)
        print(separator_line)
        for result in results:
            print(' | '.join(f"{str(value):<15}" for value in result.values()))


if __name__ == '__main__':
    main()
