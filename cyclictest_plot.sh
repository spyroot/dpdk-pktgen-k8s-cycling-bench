#!/bin/bash
# Run cyclictest for some duration read from arg and save result in txt
# i.e., histogram

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <number_of_threads> <duration_in_seconds>"
    exit 1
fi

NUM_THREADS=$1
DURATION=$2
INTERVAL=1000  # Interval in microseconds
PRIORITY=99    # Thread priority
HISTOGRAM_MAX=1000  # Maximum latency to track in microseconds

# Ensure output directory exists
OUTPUT_DIR="/output"
mkdir -p "$OUTPUT_DIR"

# Update the histogram file path to the output directory
HISTFILE="${OUTPUT_DIR}/cyclictest_histogram_${NUM_THREADS}_threads_${DURATION}_seconds.txt"

# Run cyclictest with specified parameters
cyclictest -t$NUM_THREADS -p$PRIORITY -i$INTERVAL -l$((DURATION * 1000)) -h $HISTOGRAM_MAX --histfile=$HISTFILE

echo "Cyclictest completed. Histogram data saved to $HISTFILE"
