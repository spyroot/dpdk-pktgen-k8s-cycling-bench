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
# Author Mus spyroot@gmail.com

OUTPUT_DIR="${OUTPUT_DIR:-/output}"
DEV_MODE="${DEV_MODE:-false}"

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
echo "Completed seq test with depth=16 and blocksize=4K. Results saved to $OUTPUT_DIR/seq_io_depth16_blocksize4K_result.txt"

echo "All fio tests completed and results saved to $OUTPUT_DIR"
