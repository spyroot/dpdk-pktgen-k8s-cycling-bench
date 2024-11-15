#!/bin/bash

for iface in $(ip link show | grep sriov | awk -F': ' '{print $2}')
do
    if [ -e /sys/class/net/$iface/threaded ]; then
        echo "Enabling Threaded NAPI for $iface..."
        echo 1 > /sys/class/net/$iface/threaded
    else
        echo "Threaded NAPI not supported or missing for $iface."
    fi
done