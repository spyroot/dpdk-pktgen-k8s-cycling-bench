#!/bin/bash

# ===========================
# FIO Benchmarking Script
# ===========================
#
# Description:
# This script runs a series of FIO benchmark tests on the container with different configurations.
# It supports two modes: Normal Mode (default) and Dev Mode (for faster testing).
# Results are saved to a specified output directory.
#
# Tests included:
#
# 1. **Random Read/Write (randrw) Tests**:
#    These tests simulate random read and write operations with varying block sizes and IO depths.
#    - **randrw** means the workload performs a mixture of random read and random write operations.
#    - Varying block sizes and IO depths are used to test the system's performance under different loads.
#
#    Test Profiles:
#    - **depth=1, blocksize=1M**: Random read/write with IO depth 1 and 1MB block size.
#    - **depth=16, blocksize=1M**: Random read/write with IO depth 16 and 1MB block size.
#    - **depth=16, blocksize=4K**: Random read/write with IO depth 16 and 4KB block size.
#
# 2. **Sequential Read/Write (seq) Tests**:
#    These tests simulate sequential read and write operations with varying block sizes and IO depths.
#    - **rw=rw** means the workload performs sequential read and write operations.
#    - Sequential access patterns are typical for streaming data or sequential file operations.
#
#    Test Profiles:
#    - **depth=1, blocksize=1M**: Sequential read/write with IO depth 1 and 1MB block size.
#    - **depth=16, blocksize=1M**: Sequential read/write with IO depth 16 and 1MB block size.
#    - **depth=16, blocksize=4K**: Sequential read/write with IO depth 16 and 4KB block size.
#
# To run this script:
# 1. Set the OUTPUT_DIR environment variable to specify the location where results will be saved.
#    - Default: /output
# 2. Optionally, enable Dev Mode for faster, reduced tests.
#    - Set DEV_MODE=true for shorter durations and lower workloads (default is false).
#
# Example usage:
# $ export OUTPUT_DIR=/path/to/output/directory  # (optional)
# $ export DEV_MODE=true  # (optional, enables faster tests)
# $ ./fio_test.sh  # Run the tests and store results in the specified output directory
#
# ===========================
#
# You can modify the script according to your needs for different test durations, IO depths, etc.
#
#
# Author Mus spyroot@gmail.com

OUTPUT_DIR="${OUTPUT_DIR:-/output}"
DEV_MODE="${DEV_MODE:-false}"


extract_metrics() {
    local RESULT_FILE=$1

    # Declare variables first
    local READ_IOPS
    local WRITE_IOPS
    local READ_BW
    local WRITE_BW

    # Latency variables
    local READ_SLAT_MIN
    local READ_SLAT_MAX
    local READ_SLAT_AVG
    local READ_CLAT_MIN
    local READ_CLAT_MAX
    local READ_CLAT_AVG
    local READ_LAT_MIN
    local READ_LAT_MAX
    local READ_LAT_AVG

    local WRITE_SLAT_MIN
    local WRITE_SLAT_MAX
    local WRITE_SLAT_AVG
    local WRITE_CLAT_MIN
    local WRITE_CLAT_MAX
    local WRITE_CLAT_AVG
    local WRITE_LAT_MIN
    local WRITE_LAT_MAX
    local WRITE_LAT_AVG

    # Extract IOPS and Bandwidth for both read and write
    READ_IOPS=$(grep "read: IOPS=" "$RESULT_FILE" | awk -F',' '{print $1}' | awk '{print $2}')
    WRITE_IOPS=$(grep "write: IOPS=" "$RESULT_FILE" | awk -F',' '{print $1}' | awk '{print $2}')
    READ_BW=$(grep "read:" "$RESULT_FILE" | grep -oP "BW=\K[\d\.]+")
    WRITE_BW=$(grep "write:" "$RESULT_FILE" | grep -oP "BW=\K[\d\.]+")

    # Extract Read Latency (slat, clat, lat)
    READ_SLAT_MIN=$(grep -A 3 "read:" "$RESULT_FILE" | grep "slat (usec)" | awk -F'min=' '{print $2}' | cut -d',' -f1)
    READ_SLAT_MAX=$(grep -A 3 "read:" "$RESULT_FILE" | grep "slat (usec)" | awk -F'max=' '{print $2}' | cut -d',' -f1)
    READ_SLAT_AVG=$(grep -A 3 "read:" "$RESULT_FILE" | grep "slat (usec)" | awk -F'avg=' '{print $2}' | cut -d',' -f1)

    READ_CLAT_MIN=$(grep -A 3 "read:" "$RESULT_FILE" | grep "clat (usec)" | awk -F'min=' '{print $2}' | cut -d',' -f1)
    READ_CLAT_MAX=$(grep -A 3 "read:" "$RESULT_FILE" | grep "clat (usec)" | awk -F'max=' '{print $2}' | cut -d',' -f1)
    READ_CLAT_AVG=$(grep -A 3 "read:" "$RESULT_FILE" | grep "clat (usec)" | awk -F'avg=' '{print $2}' | cut -d',' -f1)

    READ_LAT_MIN=$(grep -A 3 "read:" "$RESULT_FILE" | grep -w "lat (usec)" | awk -F'min=' '{print $2}' | cut -d',' -f1)
    READ_LAT_MAX=$(grep -A 3 "read:" "$RESULT_FILE" | grep -w "lat (usec)" | awk -F'max=' '{print $2}' | cut -d',' -f1)
    READ_LAT_AVG=$(grep -A 3 "read:" "$RESULT_FILE" | grep -w "lat (usec)" | awk -F'avg=' '{print $2}' | cut -d',' -f1)

    WRITE_SLAT_MIN=$(grep -A 3 "write:" "$RESULT_FILE" | grep "slat (usec)" | awk -F'min=' '{print $2}' | cut -d',' -f1)
    WRITE_SLAT_MAX=$(grep -A 3 "write:" "$RESULT_FILE" | grep "slat (usec)" | awk -F'max=' '{print $2}' | cut -d',' -f1)
    WRITE_SLAT_AVG=$(grep -A 3 "write:" "$RESULT_FILE" | grep "slat (usec)" | awk -F'avg=' '{print $2}' | cut -d',' -f1)

    WRITE_CLAT_MIN=$(grep -A 3 "write:" "$RESULT_FILE" | grep "clat (usec)" | awk -F'min=' '{print $2}' | cut -d',' -f1)
    WRITE_CLAT_MAX=$(grep -A 3 "write:" "$RESULT_FILE" | grep "clat (usec)" | awk -F'max=' '{print $2}' | cut -d',' -f1)
    WRITE_CLAT_AVG=$(grep -A 3 "write:" "$RESULT_FILE" | grep "clat (usec)" | awk -F'avg=' '{print $2}' | cut -d',' -f1)

    WRITE_LAT_MIN=$(grep -A 3 "write:" "$RESULT_FILE" | grep -w "lat (usec)" | awk -F'min=' '{print $2}' | cut -d',' -f1)
    WRITE_LAT_MAX=$(grep -A 3 "write:" "$RESULT_FILE" | grep -w "lat (usec)" | awk -F'max=' '{print $2}' | cut -d',' -f1)
    WRITE_LAT_AVG=$(grep -A 3 "write:" "$RESULT_FILE" | grep -w "lat (usec)" | awk -F'avg=' '{print $2}' | cut -d',' -f1)

    if [[ -z "$READ_SLAT_MIN" ]]; then READ_SLAT_MIN="N/A"; fi
    if [[ -z "$READ_SLAT_MAX" ]]; then READ_SLAT_MAX="N/A"; fi
    if [[ -z "$READ_SLAT_AVG" ]]; then READ_SLAT_AVG="N/A"; fi

    if [[ -z "$READ_CLAT_MIN" ]]; then READ_CLAT_MIN="N/A"; fi
    if [[ -z "$READ_CLAT_MAX" ]]; then READ_CLAT_MAX="N/A"; fi
    if [[ -z "$READ_CLAT_AVG" ]]; then READ_CLAT_AVG="N/A"; fi

    if [[ -z "$READ_LAT_MIN" ]]; then READ_LAT_MIN="N/A"; fi
    if [[ -z "$READ_LAT_MAX" ]]; then READ_LAT_MAX="N/A"; fi
    if [[ -z "$READ_LAT_AVG" ]]; then READ_LAT_AVG="N/A"; fi

    if [[ -z "$WRITE_SLAT_MIN" ]]; then WRITE_SLAT_MIN="N/A"; fi
    if [[ -z "$WRITE_SLAT_MAX" ]]; then WRITE_SLAT_MAX="N/A"; fi
    if [[ -z "$WRITE_SLAT_AVG" ]]; then WRITE_SLAT_AVG="N/A"; fi

    if [[ -z "$WRITE_CLAT_MIN" ]]; then WRITE_CLAT_MIN="N/A"; fi
    if [[ -z "$WRITE_CLAT_MAX" ]]; then WRITE_CLAT_MAX="N/A"; fi
    if [[ -z "$WRITE_CLAT_AVG" ]]; then WRITE_CLAT_AVG="N/A"; fi

    if [[ -z "$WRITE_LAT_MIN" ]]; then WRITE_LAT_MIN="N/A"; fi
    if [[ -z "$WRITE_LAT_MAX" ]]; then WRITE_LAT_MAX="N/A"; fi
    if [[ -z "$WRITE_LAT_AVG" ]]; then WRITE_LAT_AVG="N/A"; fi

    # Print the results
    echo "Performance Summary for $RESULT_FILE:"
    echo "===================="
    echo "Read IOPS: $READ_IOPS"
    echo "Write IOPS: $WRITE_IOPS"
    echo "Read Bandwidth: $READ_BW MB/s"
    echo "Write Bandwidth: $WRITE_BW MB/s"

    # Print latency summaries for read and write
    echo "Read Latency (slat): min=$READ_SLAT_MIN, max=$READ_SLAT_MAX, avg=$READ_SLAT_AVG us"
    echo "Read Latency (clat): min=$READ_CLAT_MIN, max=$READ_CLAT_MAX, avg=$READ_CLAT_AVG us"
    echo "Read Latency (lat): min=$READ_LAT_MIN, max=$READ_LAT_MAX, avg=$READ_LAT_AVG us"

    echo "Write Latency (slat): min=$WRITE_SLAT_MIN, max=$WRITE_SLAT_MAX, avg=$WRITE_SLAT_AVG us"
    echo "Write Latency (clat): min=$WRITE_CLAT_MIN, max=$WRITE_CLAT_MAX, avg=$WRITE_CLAT_AVG us"
    echo "Write Latency (lat): min=$WRITE_LAT_MIN, max=$WRITE_LAT_MAX, avg=$WRITE_LAT_AVG us"

    # Optionally, save the summary to a report file
    local REPORT_FILE="$OUTPUT_DIR/fio_performance_report.txt"

    echo "Performance Summary for $RESULT_FILE:" >> "$REPORT_FILE"
    echo "====================" >> "$REPORT_FILE"
    echo "Read IOPS: $READ_IOPS" >> "$REPORT_FILE"
    echo "Write IOPS: $WRITE_IOPS" >> "$REPORT_FILE"
    echo "Read Bandwidth: $READ_BW MB/s" >> "$REPORT_FILE"
    echo "Write Bandwidth: $WRITE_BW MB/s" >> "$REPORT_FILE"

    # Save latency summaries for read and write
    echo "Read Latency (slat): min=$READ_SLAT_MIN, max=$READ_SLAT_MAX, avg=$READ_SLAT_AVG us" >> "$REPORT_FILE"
    echo "Read Latency (clat): min=$READ_CLAT_MIN, max=$READ_CLAT_MAX, avg=$READ_CLAT_AVG us" >> "$REPORT_FILE"
    echo "Read Latency (lat): min=$READ_LAT_MIN, max=$READ_LAT_MAX, avg=$READ_LAT_AVG us" >> "$REPORT_FILE"

    echo "Write Latency (slat): min=$WRITE_SLAT_MIN, max=$WRITE_SLAT_MAX, avg=$WRITE_SLAT_AVG us" >> "$REPORT_FILE"
    echo "Write Latency (clat): min=$WRITE_CLAT_MIN, max=$WRITE_CLAT_MAX, avg=$WRITE_CLAT_AVG us" >> "$REPORT_FILE"
    echo "Write Latency (lat): min=$WRITE_LAT_MIN, max=$WRITE_LAT_MAX, avg=$WRITE_LAT_AVG us" >> "$REPORT_FILE"
    echo "------------------------" >> "$REPORT_FILE"
}

if [[ $# -eq 1 ]]; then
    RESULT_FILE=$1
    echo "Running extract_metrics for file: $RESULT_FILE"
    extract_metrics "$RESULT_FILE"
    exit 0
fi

if [ "$DEV_MODE" = "true" ]; then
    echo "Dev mode enabled: Running tests with shorter durations and lower workloads..."
    RUNTIME=60  # 1 minute for dev mode
    IODEPTH=4   # Lower iodepth for faster test
    NUMJOBS=1   # Reduce the number of jobs
else
    echo "Running in normal mode with full test durations..."
    RUNTIME=300  # 5 minutes for normal mode
    IODEPTH=16   # Standard iodepth for normal tests
    NUMJOBS=1    # Normal number of jobs
fi


echo "Running randrw test with depth=1 and blocksize=1M, saving to $OUTPUT_DIR/rand_io_depth1_blocksize1M_result.txt..."
fio --name=rand_io_depth1_blocksize1M \
    --ioengine=libaio \
    --iodepth=$IODEPTH \
    --rw=randrw \
    --bs=1M \
    --direct=1 \
    --runtime=$RUNTIME \
    --time_based \
    --ramp_time=30 \
    --numjobs=$NUMJOBS \
    --thread=0 \
    --refill_buffers=0 \
    --size=5G \
    --randrepeat=0 \
    --norandommap \
    --randrepeat=0 \
    --rwmixread=70 \
    > "$OUTPUT_DIR"/rand_io_depth1_blocksize1M_result.txt
extract_metrics "$OUTPUT_DIR/rand_io_depth1_blocksize1M_result.txt"
echo "Completed randrw test with depth=1 and blocksize=1M. Results saved to $OUTPUT_DIR/rand_io_depth1_blocksize1M_result.txt"

echo "Running randrw test with depth=16 and blocksize=1M, saving to $OUTPUT_DIR/rand_io_depth16_blocksize1M_result.txt..."
fio --name=rand_io_depth16_blocksize1M \
    --ioengine=libaio \
    --iodepth=$IODEPTH \
    --rw=randrw \
    --bs=1M \
    --direct=1 \
    --runtime=$RUNTIME \
    --time_based \
    --ramp_time=30 \
    --numjobs=$NUMJOBS \
    --thread=0 \
    --refill_buffers=0 \
    --size=5G \
    --randrepeat=0 \
    --norandommap \
    --randrepeat=0 \
    --rwmixread=70 \
    > "$OUTPUT_DIR"/rand_io_depth16_blocksize1M_result.txt
extract_metrics "$OUTPUT_DIR/rand_io_depth16_blocksize1M_result.txt"
echo "Completed randrw test with depth=16 and blocksize=1M. Results saved to $OUTPUT_DIR/rand_io_depth16_blocksize1M_result.txt"

echo "Running randrw test with depth=16 and blocksize=4K, saving to $OUTPUT_DIR/rand_io_depth16_blocksize4K_result.txt..."
fio --name=rand_io_depth16_blocksize4K \
    --ioengine=libaio \
    --iodepth=$IODEPTH \
    --rw=randrw \
    --bs=4K \
    --direct=1 \
    --runtime=$RUNTIME \
    --time_based \
    --ramp_time=30 \
    --numjobs=$NUMJOBS \
    --thread=0 \
    --refill_buffers=0 \
    --size=5G \
    --randrepeat=0 \
    --norandommap \
    --randrepeat=0 \
    --rwmixread=70 \
    > "$OUTPUT_DIR"/rand_io_depth16_blocksize4K_result.txt
extract_metrics "$OUTPUT_DIR/rand_io_depth16_blocksize4K_result.txt"
echo "Completed randrw test with depth=16 and blocksize=4K. Results saved to $OUTPUT_DIR/rand_io_depth16_blocksize4K_result.txt"

echo "Running seq test with depth=1 and blocksize=1M, saving to $OUTPUT_DIR/seq_io_depth1_blocksize1M_result.txt..."
fio --name=seq_io_depth1_blocksize1M \
    --ioengine=libaio \
    --iodepth=$IODEPTH \
    --rw=rw \
    --bs=1M \
    --direct=1 \
    --runtime=$RUNTIME \
    --time_based \
    --ramp_time=30 \
    --numjobs=$NUMJOBS \
    --thread=0 \
    --refill_buffers=0 \
    --size=5G \
    --randrepeat=0 \
    --norandommap \
    --randrepeat=0 \
    --rwmixread=70 \
    > "$OUTPUT_DIR"/seq_io_depth1_blocksize1M_result.txt
extract_metrics "$OUTPUT_DIR/seq_io_depth1_blocksize1M_result.txt"
echo "Completed seq test with depth=1 and blocksize=1M. Results saved to $OUTPUT_DIR/seq_io_depth1_blocksize1M_result.txt"

echo "Running seq test with depth=16 and blocksize=1M, saving to $OUTPUT_DIR/seq_io_depth16_blocksize1M_result.txt..."
fio --name=seq_io_depth16_blocksize1M \
    --ioengine=libaio \
    --iodepth=$IODEPTH \
    --rw=rw \
    --bs=1M \
    --direct=1 \
    --runtime=$RUNTIME \
    --time_based \
    --ramp_time=30 \
    --numjobs=$NUMJOBS \
    --thread=0 \
    --refill_buffers=0 \
    --size=5G \
    --randrepeat=0 \
    --norandommap \
    --randrepeat=0 \
    --rwmixread=70 \
    > "$OUTPUT_DIR"/seq_io_depth16_blocksize1M_result.txt
extract_metrics "$OUTPUT_DIR/seq_io_depth16_blocksize1M_result.txt"
echo "Completed seq test with depth=16 and blocksize=1M. Results saved to $OUTPUT_DIR/seq_io_depth16_blocksize1M_result.txt"

echo "Running seq test with depth=16 and blocksize=4K, saving to $OUTPUT_DIR/seq_io_depth16_blocksize4K_result.txt..."
fio --name=seq_io_depth16_blocksize4K \
    --ioengine=libaio \
    --iodepth=$IODEPTH \
    --rw=rw \
    --bs=4K \
    --direct=1 \
    --runtime=$RUNTIME \
    --time_based \
    --ramp_time=30 \
    --numjobs=$NUMJOBS \
    --thread=0 \
    --refill_buffers=0 \
    --size=5G \
    --randrepeat=0 \
    --norandommap \
    --randrepeat=0 \
    --rwmixread=70 \
    > "$OUTPUT_DIR"/seq_io_depth16_blocksize4K_result.txt
extract_metrics "$OUTPUT_DIR/seq_io_depth16_blocksize4K_result"
echo "Completed seq test with depth=16 and blocksize=4K. Results saved to $OUTPUT_DIR/seq_io_depth16_blocksize4K_result.txt"

echo "All fio tests completed and results saved to $OUTPUT_DIR"
