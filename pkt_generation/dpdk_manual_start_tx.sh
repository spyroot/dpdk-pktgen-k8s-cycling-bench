#!/bin/bash
# This manual runner mainly for debuging


SESSION="tx_testpmd"
WINDOW="tx"

FLOW_DIR="flows"
TARGET_DIR="/"


for pair_dir in "$FLOW_DIR"/tx*-rx*; do
  [ -d "$pair_dir" ] || continue
  pod_name=$(basename "$pair_dir" | cut -d'-' -f1)
  echo "📦 Packing Lua files from $pair_dir for pod $pod_name..."
  tar --no-xattrs -cf - -C "$pair_dir" . | kubectl exec -i "$pod_name" -- tar -xf - -C "$TARGET_DIR"
  echo "✅ All Lua files copied to $pod_name in one batch."
done

tmux kill-session -t "$SESSION" 2>/dev/null

TX_PODS=("tx0" "tx1")

for pod in "${TX_PODS[@]}"; do
  echo "📂 Copying Pktgen.lua into $pod..."
  kubectl exec "$pod" -- cp /root/Pktgen-DPDK/Pktgen.lua /usr/local/bin/
done

echo "✅ All TX pods updated with Pktgen.lua."

for pod in rx0 rx1; do
  echo "🔪 Killing dpdk-testpmd in pod $pod..."
  kubectl exec "$pod" -- pkill -9 dpdk-testpmd 2>/dev/null || true
done

COLS=$(tput cols)
LINES=$(tput lines)

#tmux new-session -d -s "$SESSION" -n "$WINDOW"

TX_PODS=("tx0" "tx1")

# Check Lua profile exists before launching pktgen
LUA_PROFILE="/profile_10000_flows_pkt_size_512B_100_rate_s.lua"

for pod in "${TX_PODS[@]}"; do
  echo "🔍 Checking if Lua profile $LUA_PROFILE exists in pod $pod..."
  if ! kubectl exec "$pod" -- test -f "$LUA_PROFILE"; then
    echo "❌ Lua profile $LUA_PROFILE not found in pod $pod!"
    exit 1
  fi
done

echo "✅ Lua profile $LUA_PROFILE exists in all TX pods."

# Then proceed to tmux loop that launches pktgen
first=true

for pod in "${TX_PODS[@]}"; do
  echo "🚀 Launching pktgen in pod $pod..."

  CMD=$(cat <<EOF
kubectl exec -it $pod -- sh -c 'cd /usr/local/bin &&
  raw=\$(numactl -s | grep physcpubind | sed "s/.*physcpubind://")
  cores=(\$(echo \$raw))
  main=\${cores[0]}
  len=\${#cores[@]}
  half=\$(( (len - 1) / 2 ))

  tx_start=\${cores[1]}
  tx_end=\${cores[\$((half))]}
  rx_start=\${cores[\$((half + 1))]}
  rx_end=\${cores[\$((len - 1))]}

  echo "[ℹ️] Launching pktgen on $pod main=\$main tx=\$tx_start-\$tx_end rx=\$rx_start-\$rx_end"
  cd /usr/local/bin && pktgen \\
    --no-telemetry -l \${cores[*]} -n 4 \\
    --socket-mem 2048 \\
    --main-lcore \$main --proc-type auto --file-prefix pg_$pod \\
    -a \$PCIDEVICE_INTEL_COM_DPDK \\
    -- -G --txd=2048 --rxd=2048 \\
    -f /profile_100_flows_pkt_size_64B_100_rate_s.lua -l /tmp/$pod.log\\
    -m [\$tx_start-\$tx_end:\$rx_start-\$rx_end].0
'
EOF
)

  echo "$CMD"
#
#  if $first; then
#    tmux new-session -d -s "$SESSION" -n "$WINDOW" "$CMD"
#    tmux set -g mouse on
#    first=false
#  else
#    tmux split-window -h -t "$SESSION:$WINDOW" "$CMD"
#  fi

#  sleep 1
done


# Set layout and attach
#tmux select-layout -t "$SESSION:$WINDOW" even-vertical
#tmux resize-pane -t "$SESSION:$WINDOW".0 -x 160
tmux display-panes
tmux attach -t "$SESSION"