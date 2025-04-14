#!/bin/bash

SESSION="rx_testpmd"
WINDOW="rx"

FLOW_DIR="flows"
TARGET_DIR="/"

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

# Start new tmux session: top pane runs rx0
tmux new-session -d -s "$SESSION" -n "$WINDOW" \
"kubectl exec -it rx0 -- sh -c '
    export COLUMNS=160; stty cols 160
    raw=\$(numactl -s | grep physcpubind | sed \"s/.*physcpubind://\")
    cores=\$(echo \$raw | tr \" \" \",\")
    main=\$(echo \$raw | awk \"{print \\\$1}\")
    echo \"[ℹ️] Launching testpmd on rx0 with main core \$main and cores \$cores\"
    cd /usr/local/bin && dpdk-testpmd \
      --main-lcore \$main -l \$cores -n 4 \
      --socket-mem 2048 \
      --proc-type auto --file-prefix testpmd_rx0 \
      -a \$PCIDEVICE_INTEL_COM_DPDK \
      -- --forward-mode=rxonly --auto-start --stats-period 1'"

tmux set -g pane-border-status bottom

# Wait a bit before splitting
sleep 2

# Bottom pane: run rx1
tmux split-window -h -t "$SESSION:$WINDOW" \
"kubectl exec -it rx1 -- sh -c '
    export COLUMNS=160; stty cols 160
    raw=\$(numactl -s | grep physcpubind | sed \"s/.*physcpubind://\")
    cores=\$(echo \$raw | tr \" \" \",\")
    main=\$(echo \$raw | awk \"{print \\\$1}\")
    echo \"[ℹ️] Launching testpmd on rx1 with main core \$main and cores \$cores\"
    cd /usr/local/bin && dpdk-testpmd \
      --main-lcore \$main -l \$cores -n 4 \
      --socket-mem 2048 \
      --proc-type auto --file-prefix testpmd_rx1 \
      -a \$PCIDEVICE_INTEL_COM_DPDK \
      -- --forward-mode=rxonly --auto-start --stats-period 1'"

# Set layout and attach
#tmux select-layout -t "$SESSION:$WINDOW" even-vertical
#tmux resize-pane -t "$SESSION:$WINDOW".0 -x 160
tmux display-panes
tmux attach -t "$SESSION"

