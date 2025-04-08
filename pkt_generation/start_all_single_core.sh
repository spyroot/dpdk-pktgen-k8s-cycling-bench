#!/bin/bash
#
# This script will run all profile one by one.
# Author: Mus
# mbayramov@vmware.com

DURATION=120

profiles=(
    "profile_10000_flows_pkt_size_128B_100_rate_s.lua"
    "profile_10000_flows_pkt_size_128B_10_rate_s.lua"
    "profile_10000_flows_pkt_size_1500B_100_rate_s.lua"
    "profile_10000_flows_pkt_size_1500B_10_rate_s.lua"
    "profile_10000_flows_pkt_size_2000B_100_rate_s.lua"
    "profile_10000_flows_pkt_size_2000B_10_rate_s.lua"
    "profile_10000_flows_pkt_size_512B_100_rate_s.lua"
    "profile_10000_flows_pkt_size_512B_10_rate_s.lua"
    "profile_10000_flows_pkt_size_64B_100_rate_s.lua"
    "profile_10000_flows_pkt_size_64B_10_rate_s.lua"
    "profile_10000_flows_pkt_size_9000B_100_rate_s.lua"
    "profile_10000_flows_pkt_size_9000B_10_rate_s.lua"
    "profile_100_flows_pkt_size_128B_100_rate_s.lua"
    "profile_100_flows_pkt_size_128B_10_rate_s.lua"
    "profile_100_flows_pkt_size_1500B_100_rate_s.lua"
    "profile_100_flows_pkt_size_1500B_10_rate_s.lua"
    "profile_100_flows_pkt_size_2000B_100_rate_s.lua"
    "profile_100_flows_pkt_size_2000B_10_rate_s.lua"
    "profile_100_flows_pkt_size_512B_100_rate_s.lua"
    "profile_100_flows_pkt_size_512B_10_rate_s.lua"
    "profile_100_flows_pkt_size_64B_100_rate_s.lua"
    "profile_100_flows_pkt_size_64B_10_rate_s.lua"
    "profile_100_flows_pkt_size_9000B_100_rate_s.lua"
    "profile_100_flows_pkt_size_9000B_10_rate_s.lua"
    "profile_1_flows_pkt_size_128B_100_rate_s.lua"
    "profile_1_flows_pkt_size_128B_10_rate_s.lua"
    "profile_1_flows_pkt_size_1500B_100_rate_s.lua"
    "profile_1_flows_pkt_size_1500B_10_rate_s.lua"
    "profile_1_flows_pkt_size_2000B_100_rate_s.lua"
    "profile_1_flows_pkt_size_2000B_10_rate_s.lua"
    "profile_1_flows_pkt_size_512B_100_rate_s.lua"
    "profile_1_flows_pkt_size_512B_10_rate_s.lua"
    "profile_1_flows_pkt_size_64B_100_rate_s.lua"
    "profile_1_flows_pkt_size_64B_10_rate_s.lua"
    "profile_1_flows_pkt_size_9000B_100_rate_s.lua"
    "profile_1_flows_pkt_size_9000B_10_rate_s.lua"
)

# Loop through each profile and run the test
for profile in "${profiles[@]}"; do
    echo "Starting test for profile: $profile"
    python packet_generator.py start_generator --profile "$profile" --duration "$DURATION"
    echo "Completed test for profile: $profile"
    echo "-----------------------------------"
    sleep 5
done
