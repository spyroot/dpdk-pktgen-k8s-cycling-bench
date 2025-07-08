#!/bin/bash

IP_LIST=("10.0.0.101" "10.0.0.102" "10.0.0.103")

USER="vmware"
PASSWORD="VMware1!"

# rename
PROFILE_NAME="mus"

# local template file that we push
LOCAL_TUNED_CONF="./tuned.conf"
LOCAL_SCRIPT="./script.sh"

# this default location for all profiles
REMOTE_PROFILE_DIR="/usr/lib/tuned/$PROFILE_NAME"

for IP in "${IP_LIST[@]}"; do
  echo "🔧 Configuring $IP..."
  sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no $USER@$IP "mkdir -p $REMOTE_PROFILE_DIR"
  sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no "$LOCAL_TUNED_CONF" "$USER@$IP:$REMOTE_PROFILE_DIR/tuned.conf"
  sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no "$LOCAL_SCRIPT" "$USER@$IP:$REMOTE_PROFILE_DIR/script.sh"
  sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no $USER@$IP "chmod +x $REMOTE_PROFILE_DIR/script.sh"
  sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no $USER@$IP "tuned-adm profile $PROFILE_NAME && systemctl restart tuned"
  echo "✅ $IP configured with tuned profile '$PROFILE_NAME'"
done
