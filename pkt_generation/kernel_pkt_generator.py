import argparse
import subprocess
import socket
import struct
import fcntl
import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


def get_mac_address(
        interface: str
) -> str:
    """return interface mac address, note it require NET capability, so we can read.
    :param interface:
    :return:
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    info = fcntl.ioctl(s.fileno(), 0x8927, struct.pack('256s', interface[:15].encode()))
    return ':'.join(f'0x{b:02x}' for b in info[18:24])


# The rest.
# define SIOCGIFNAME	0x8910		/* get iface name		*/
# define SIOCSIFLINK	0x8911		/* set iface channel		*/
# define SIOCGIFCONF	0x8912		/* get iface list		*/
# define SIOCGIFFLAGS	0x8913		/* get flags			*/
# define SIOCSIFFLAGS	0x8914		/* set flags			*/
# define SIOCGIFADDR	0x8915		/* get PA address		*/
# define SIOCSIFADDR	0x8916		/* set PA address		*/
# define SIOCGIFDSTADDR	0x8917		/* get remote PA address	*/
# define SIOCSIFDSTADDR	0x8918		/* set remote PA address	*/
# define SIOCGIFBRDADDR	0x8919		/* get broadcast PA address	*/
# define SIOCSIFBRDADDR	0x891a		/* set broadcast PA address	*/
# define SIOCGIFNETMASK	0x891b		/* get network PA mask		*/
# define SIOCSIFNETMASK	0x891c		/* set network PA mask		*/
# define SIOCGIFMETRIC	0x891d		/* get metric			*/
# define SIOCSIFMETRIC	0x891e		/* set metric			*/
# define SIOCGIFMEM	0x891f		/* get memory address (BSD)	*/
# define SIOCSIFMEM	0x8920		/* set memory address (BSD)	*/
# define SIOCGIFMTU	0x8921		/* get MTU size			*/
# define SIOCSIFMTU	0x8922		/* set MTU size			*/
# define SIOCSIFNAME	0x8923		/* set interface name		*/
# define SIOCSIFHWADDR	0x8924		/* set hardware address 	*/
# define SIOCGIFENCAP	0x8925		/* get/set encapsulations       */
# define SIOCSIFENCAP	0x8926
# define SIOCGIFHWADDR	0x8927		/* Get hardware address		*/
# define SIOCGIFSLAVE	0x8929		/* Driver slaving support	*/
# define SIOCSIFSLAVE	0x8930
# define SIOCADDMULTI	0x8931		/* Multicast address lists	*/
# define SIOCDELMULTI	0x8932
# define SIOCGIFINDEX	0x8933		/* name -> if_index mapping	*/
# define SIOGIFINDEX	SIOCGIFINDEX	/* misprint compatibility :-)	*/
# define SIOCSIFPFLAGS	0x8934		/* set/get extended flags set	*/
# define SIOCGIFPFLAGS	0x8935
# define SIOCDIFADDR	0x8936		/* delete PA address		*/
# define SIOCSIFHWBROADCAST	0x8937	/* set hardware broadcast addr	*/
# define SIOCGIFCOUNT	0x8938		/* get number of devices */
#
# define SIOCGIFBR	0x8940		/* Bridging support		*/
# define SIOCSIFBR	0x8941		/* Set bridging options 	*/
#
# define SIOCGIFTXQLEN	0x8942		/* Get the tx queue length	*/
# define SIOCSIFTXQLEN	0x8943		/* Set the tx queue length 	*/

def get_ip_address(
        interface: str
) -> str:
    """
    :param interface:
    :return:
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(
        fcntl.ioctl(s.fileno(), 0x8915, struct.pack('256s', interface[:15].encode()))[20:24]
    )


def get_iface_mtu(
        interface: str
) -> str:
    """
    :param interface:
    :return:
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(
        fcntl.ioctl(s.fileno(), 0x8921, struct.pack('256s', interface[:15].encode()))[20:24]
    )


def get_default_gateway_mac(
        interface: str
) -> str:
    """
    Get the default gateway MAC address of the egress interface, where egress interface that we use
    to generate.

    Note we need resolve ARP hence tools uses arping.

    :param interface: egress_interface.
    :return:
    """

    # todo I need check linux api to get that directly.
    gateway_ip = subprocess.check_output("ip route | grep default | awk '{print $3}'", shell=True).decode().strip()

    subprocess.call(f"ping -c 2 {gateway_ip}", shell=True, stdout=subprocess.DEVNULL)
    subprocess.call(f"arping -c 1 -I {interface} {gateway_ip}", shell=True, stdout=subprocess.DEVNULL)
    mac = subprocess.check_output(f"arp -n | awk -v gw={gateway_ip} '$1 == gw {{print $3}}'",
                                  shell=True).decode().strip()
    if not mac:
        raise RuntimeError("Could not resolve gateway MAC.")

    return ', '.join([f'0x{b}' for b in mac.split(':')])


def set_rxtx_queue_size(
        interface: str,
        tx_queue_size: int,
        rx_queue_size: int,
) -> None:
    """
    Set adapter tx and rx queue size.
    :param rx_queue_size:
    :param tx_queue_size:
    :param interface:
    :return:
    """
    subprocess.call(f"ethtool -G {interface} "
                    f"tx {tx_queue_size} "
                    f"rx {rx_queue_size}",
                    shell=True,
                    stdout=subprocess.DEVNULL
                    )


def generate_config(
        dst_ip: str,
        src_port: int,
        dst_port: int,
        payload_size: int,
        random_src: bool,
        interface: str
) -> str:
    """

    :param dst_ip:
    :param src_port:
    :param dst_port:
    :param payload_size:
    :param random_src:
    :param interface:
    :return:
    """
    dst_ip_parts = dst_ip.split('.')
    total_length = 20 + 8 + payload_size
    udp_length = 8 + payload_size

    src_mac = get_mac_address(interface).replace(':', ' ')
    src_ip = get_ip_address(interface)
    src_ip_bytes = ', '.join(src_ip.split('.'))

    dst_mac = get_default_gateway_mac(interface)

    config_lines = [
        "#define ETH_P_IP 0x0800",
        "{",
        f"{dst_mac},",
        f"{src_mac},",
        "const16(ETH_P_IP),",
        "0b01000101, 0,",
        f"const16({total_length}),",
        "const16(2),",
        "0b01000000, 0,",
        "64,",
        "17,",
        "csumip(14, 33),",
        f"{src_ip_bytes},",
        f"{', '.join(dst_ip_parts)},",
        f"{'drnd(2)' if random_src else f'const16({src_port})'},",
        f"const16({dst_port}),",
        f"const16({udp_length}),",
        "const16(0),",
        f"fill('B', {payload_size}),",
        "}"
    ]
    return '\n'.join(config_lines)


def thread_call(host, cmd):
    """

    :param host:
    :param cmd:
    :return:
    """
    cmd_arg_stack = [
        "timeout", str(cmd.duration), "trafgen",
        "--cpp", "--dev", cmd.interface, "-i",
        cmd.output, "--no-sock-mem", "--jumbo-support"
    ]

    if cmd.cpus:
        cmd_arg_stack.append(f"--cpus={cmd.cpus}")
    if cmd.rate:
        cmd_arg_stack.append(f"--rate={cmd.rate}")

    print(cmd_arg_stack)
    p = subprocess.run(cmd_arg_stack, capture_output=True, text=True)
    return host, p.stdout, p.stderr, p.returncode


def main():
    """

    :return:
    """
    parser = argparse.ArgumentParser(description="Generate and run trafgen config for UDP traffic.")
    parser.add_argument("-s", "--src-port", type=int, default=9, help="Source port")
    parser.add_argument("-d", "--dst-port", type=int, default=6666, help="Destination port")
    parser.add_argument("-p", "--payload-size", type=int, default=22, help="Payload size in bytes")
    parser.add_argument("-i", "--dst-ip", required=True, help="Destination IP")
    parser.add_argument("--random-src", action="store_true", help="Randomize source port")
    parser.add_argument("--interface", default="ens33", help="Network interface to use")
    parser.add_argument("--rate", default="1000000pps", help="Trafgen rate")
    parser.add_argument("--cpus", default=None, help="Comma-separated list of CPU cores")
    # parser.add_argument("--cpus", default="1,2,3,4", help="Comma-separated list of CPU cores")
    parser.add_argument("--output", default="udp_test.trafgen", help="Output trafgen file")
    parser.add_argument("--duration", type=int, default=120, help="duration of test")

    args = parser.parse_args()

    print("🔧 Generating trafgen config...")
    config_str = generate_config(args.dst_ip,
                                 args.src_port,
                                 args.dst_port,
                                 args.payload_size,
                                 args.random_src,
                                 args.interface
                                 )

    with open(args.output, "w") as f:
        f.write(config_str)

    print(f"🚀 Running trafgen on {args.interface} at rate {args.rate} using CPUs {args.cpus}")

    all_tx_nodes = ["10.100.74.225"]
    thread_results = []

    with ThreadPoolExecutor(max_workers=8) as executor:

        futures = {executor.submit(thread_call, node, args): node for node in all_tx_nodes}
        for future in futures:
            h, stdout_, stderr_, exit_code = future.result()
            thread_results[h] = {
                "stdout": stdout_,
                "stderr": stderr_,
                "exit_code": exit_code
            }


if __name__ == "__main__":
    main()
