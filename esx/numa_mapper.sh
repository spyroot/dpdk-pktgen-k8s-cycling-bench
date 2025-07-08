#!/bin/bash

# This script take array of IP/FQDN and collect vnic - numa node
# note ssh with root must be enabled on each host,  and on the system
# you run must have sshpass.   either use brew install sshpass or apt-get etc.
# Author Mus

USER="root"
PASS="VMware1!"

ESXI_HOSTS=(
  10.192.16.4
  10.192.16.5
  10.192.16.6
)

for HOST in "${ESXI_HOSTS[@]}"; do
  echo "🔍 Checking NUMA info on $HOST"

  sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no ${USER}@$HOST << 'EOF'
vsish -e ls /net/pNics/ | sed 's:/$::' | while read -r nic; do
  echo -n "$nic: "
  vsish -e cat /net/pNics/$nic/properties | grep -i 'Numa Node'
done
EOF

  echo ""
done
