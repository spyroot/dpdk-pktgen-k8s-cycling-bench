#!/bin/bash

OUTPUT_DIR="${OUTPUT_DIR:-/output}"

fio --name=rand_io_depth1_blocksize1M \
    --ioengine=libaio \
    --iodepth=1 \
    --rw=randrw \
    --bs=1M \
    --direct=1 \
    --runtime=300 \
    --time_based \
    --ramp_time=30 \
    --numjobs=1 \
    --thread=0 \
    --refill_buffers=0 \
    --size=5G \
    --randrepeat=0 \
    --norandommap \
    --randrepeat=0 \
    --rwmixread=70 \
    > $OUTPUT_DIR/rand_io_depth1_blocksize1M_result.txt

fio --name=rand_io_depth16_blocksize1M \
    --ioengine=libaio \
    --iodepth=16 \
    --rw=randrw \
    --bs=1M \
    --direct=1 \
    --runtime=300 \
    --time_based \
    --ramp_time=30 \
    --numjobs=1 \
    --thread=0 \
    --refill_buffers=0 \
    --size=5G \
    --randrepeat=0 \
    --norandommap \
    --randrepeat=0 \
    --rwmixread=70 \
    > $OUTPUT_DIR/rand_io_depth16_blocksize1M_result.txt

fio --name=rand_io_depth16_blocksize4K \
    --ioengine=libaio \
    --iodepth=16 \
    --rw=randrw \
    --bs=4K \
    --direct=1 \
    --runtime=300 \
    --time_based \
    --ramp_time=30 \
    --numjobs=1 \
    --thread=0 \
    --refill_buffers=0 \
    --size=5G \
    --randrepeat=0 \
    --norandommap \
    --randrepeat=0 \
    --rwmixread=70 \
    > $OUTPUT_DIR/rand_io_depth16_blocksize4K_result.txt

fio --name=seq_io_depth1_blocksize1M \
    --ioengine=libaio \
    --iodepth=1 \
    --rw=rw \
    --bs=1M \
    --direct=1 \
    --runtime=300 \
    --time_based \
    --ramp_time=30 \
    --numjobs=1 \
    --thread=0 \
    --refill_buffers=0 \
    --size=5G \
    --randrepeat=0 \
    --norandommap \
    --randrepeat=0 \
    --rwmixread=70 \
    > $OUTPUT_DIR/seq_io_depth1_blocksize1M_result.txt

fio --name=seq_io_depth16_blocksize1M \
    --ioengine=libaio \
    --iodepth=16 \
    --rw=rw \
    --bs=1M \
    --direct=1 \
    --runtime=300 \
    --time_based \
    --ramp_time=30 \
    --numjobs=1 \
    --thread=0 \
    --refill_buffers=0 \
    --size=5G \
    --randrepeat=0 \
    --norandommap \
    --randrepeat=0 \
    --rwmixread=70 \
    > $OUTPUT_DIR/seq_io_depth16_blocksize1M_result.txt

fio --name=seq_io_depth16_blocksize4K \
    --ioengine=libaio \
    --iodepth=16 \
    --rw=rw \
    --bs=4K \
    --direct=1 \
    --runtime=300 \
    --time_based \
    --ramp_time=30 \
    --numjobs=1 \
    --thread=0 \
    --refill_buffers=0 \
    --size=5G \
    --randrepeat=0 \
    --norandommap \
    --randrepeat=0 \
    --rwmixread=70 \
    > $OUTPUT_DIR/seq_io_depth16_blocksize4K_result.txt

