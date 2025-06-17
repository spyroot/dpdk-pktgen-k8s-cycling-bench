#!/bin/bash
# Generate udp trafgen config per pod
# - get own IP req for IP header
# - resolve default gateway send 2 ping so arp cache populated
# - parse,so we get dst mac
# - take own src mac
# create C struct
# generate and show in console, so we can verify
# Mus mbayramov@vmware.com

DEFAULT_SRC_PORT="9"
DEFAULT_DST_PORT="6666"
DEFAULT_PD_SIZE="22"
PD_SIZE="$DEFAULT_PD_SIZE"

if [ -n "$1" ]; then
    SRC_PORT="$1"
else
    SRC_PORT="$DEFAULT_SRC_PORT"
fi

SRC_PORT="$DEFAULT_SRC_PORT"
DST_PORT="$DEFAULT_DST_PORT"
PD_SIZE="$DEFAULT_PD_SIZE"

display_help() {
    echo "Usage: $0 [-s <source port>] [-d <destination port>] [-p <payload size>] [-i <destination IP>] [-r]"
    echo "-s: Source port for UDP traffic"
    echo "-d: Destination port for UDP traffic"
    echo "-p: Payload size for UDP packets"
    echo "-i: Destination IP for UDP packets"
    echo "-r: Use randomized source port"
}

while getopts ":s:d:p:i:r" opt; do
    case ${opt} in
        s)
            SRC_PORT=$OPTARG
            ;;
        d)
            DST_PORT=$OPTARG
            ;;
        p)
            PD_SIZE=$OPTARG
            ;;
        i)
            DEST_IP=$OPTARG
            ;;
        r)
            RANDOMIZED_CONFIG="true"
            ;;
        \?)
            display_help
            exit 1
            ;;
        :)
            echo "Option -$OPTARG requires an argument."
            display_help
            exit 1
            ;;
    esac
done
shift $((OPTIND -1))

# Extract each byte from mac addr and return as comma separate str
get_src_ip_components() {
    ifconfig ens33 | grep 'inet ' | awk '{print $2}' | \
    awk -F '.' '{printf("%d, %d, %d, %d", $1, $2, $3, $4)}'
}

# Extract MAC address from ifconfig for eth0
get_mac_eth0() {
    ifconfig ens33 | grep 'ether ' | awk '{print $2}' | \
    awk -F ':' '{printf("0x%s, 0x%s, 0x%s, 0x%s, 0x%s, 0x%s", $1, $2, $3, $4, $5, $6)}'
}

# ping gw , do arping , get gateway mac addr
# create string i.e. byte command seperated
get_gateway_mac() {
    local gateway_ip
    local gateway_mac

    gateway_ip=$(ip route | grep default | awk '{print $3}')
    gateway_mac=$(arp -n | awk -v gw="$gateway_ip" '$1 == gw {print $3}')

    if [ -z "$gateway_mac" ]; then
      ping -c 2 "$gateway_ip" > /dev/null
      arping -c 1 -I eth0 "$gateway_ip" > /dev/null
      gateway_mac=$(arp -n | awk -v gw="$gateway_ip" '$1 == gw {print $3}')
   fi

    if [ -n "$gateway_mac" ]; then
        echo "$gateway_mac" | awk -F ':' '{printf("0x%s, 0x%s, 0x%s, 0x%s, 0x%s, 0x%s", $1, $2, $3, $4, $5, $6)}'
    else
        echo "Error: MAC address for gateway $gateway_ip not found" >&2
        return 1
    fi
}

# generate config
generate_config() {
    local dst_ip
    local dst_ip_arr
    local total_length
    local udp_length

    dst_ip="$DEST_IP"
    dst_ip_arr=($(echo "$dst_ip" | tr '.' ' '))
    total_length=$((20 + 8 + PD_SIZE))
    udp_length=$((8 + PD_SIZE))

    echo "#define ETH_P_IP 0x0800"
    echo "{"
    get_gateway_mac
    echo ","
    get_mac_eth0
    echo ","
    echo "const16(ETH_P_IP),"
    echo "0b01000101, 0,  /* IPv4 Version, IHL, TOS */"
    echo "const16($total_length),    /* IPv4 Total Len (UDP len + IP hdr 20 bytes)*/"
    echo "const16(2),     /* IPv4 Ident */"
    echo "0b01000000, 0,  /* IPv4 Flags, Frag Off */"
    echo "64,             /* IPv4 TTL */"
    echo "17,             /* Proto UDP */"
    echo "csumip(14, 33), /* IPv4 Checksum (IP header from, to) */"
    get_src_ip_components
    echo ","
    echo "${dst_ip_arr[0]}, ${dst_ip_arr[1]}, ${dst_ip_arr[2]}, ${dst_ip_arr[3]},"
    echo "const16($SRC_PORT), /* UDP Source Port e.g. drnd(2)*/"
    echo "const16($DST_PORT), /* UDP Dest Port */"
    echo "const16($udp_length),   /* UDP length (UDP hdr 8 bytes + payload size */"
    echo "const16(0),"
    echo "fill('B', $PD_SIZE),"
    echo "}"
}


# generate config
generate_randomized_config() {
    local dst_ip
    local dst_ip_arr
    local total_length
    local udp_length

    dst_ip="$DEST_IP"
    dst_ip_arr=($(echo "$dst_ip" | tr '.' ' '))
    total_length=$((20 + 8 + PD_SIZE))
    udp_length=$((8 + PD_SIZE))

    echo "#define ETH_P_IP 0x0800"
    echo "{"
    get_gateway_mac
    echo ","
    get_mac_eth0
    echo ","
    echo "const16(ETH_P_IP),"
    echo "0b01000101, 0,  /* IPv4 Version, IHL, TOS */"
    echo "const16($total_length),    /* IPv4 Total Len (UDP len + IP hdr 20 bytes)*/"
    echo "const16(2),     /* IPv4 Ident */"
    echo "0b01000000, 0,  /* IPv4 Flags, Frag Off */"
    echo "64,             /* IPv4 TTL */"
    echo "17,             /* Proto UDP */"
    echo "csumip(14, 33), /* IPv4 Checksum (IP header from, to) */"
    get_src_ip_components
    echo ","
    echo "${dst_ip_arr[0]}, ${dst_ip_arr[1]}, ${dst_ip_arr[2]}, ${dst_ip_arr[3]},"
    echo "drnd(2),"
    echo "const16($DST_PORT), /* UDP Dest Port */"
    echo "const16($udp_length),"
    echo "const16(0),"
    echo "fill('B', $PD_SIZE),"
    echo "}"
}

if [ "$RANDOMIZED_CONFIG" = "true" ]; then
    generate_randomized_config
else
    generate_config
fi