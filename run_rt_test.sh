#!/bin/bash

mkdir -p output

thread_counts=(2 4 8)
durations=(60 300)  

# Loop over thread counts and durations to run cyclictest_plot.sh
for threads in "${thread_counts[@]}"; do
  for duration in "${durations[@]}"; do
    echo "Running cyclictest_plot.sh for ${threads} threads and ${duration} seconds..."
    docker run --privileged -it \
      -v "$(pwd)/output:/output" \
      dpdk-pktgen-k8s-cycling-bench /cyclictest_plot.sh "$threads" "$duration"
  done
done

echo "Running cyclictest_per_thread.py to generate plots..."
docker run --privileged -it \
  -v "$(pwd)/output:/output" \
  -e OUTPUT_DIR="/output" \
  dpdk-pktgen-k8s-cycling-bench python /cyclictest_per_thread.py

echo "All tests and plots are completed. Results are saved in the output directory."

