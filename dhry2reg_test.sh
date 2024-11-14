#!/bin/bash
# This script adds additional optimizations to UnixBench and runs
# the dhry2reg benchmark, first using the default Makefile and then the optimized one.
#
# Author Mus spyroot@gmail.com

OUTPUT_DIR="${OUTPUT_DIR:-/output}"
UNIXBENCH_DIR="/root/unixbench/UnixBench"
MAKEFILE="$UNIXBENCH_DIR/Makefile"
MAKEFILE_ORG="$UNIXBENCH_DIR/Makefile.org"

cp "$MAKEFILE" "$MAKEFILE.bak"

echo "Running dhry2reg benchmark with the default Makefile..."
cp "$MAKEFILE_ORG" "$MAKEFILE"
cd "$UNIXBENCH_DIR"
make clean
make
./Run dhry2reg > "$OUTPUT_DIR/dhry2reg_results_default.log"
make clean

echo "Default benchmark completed. Results are saved in $OUTPUT_DIR/dhry2reg_results_default.log"

if ! grep -q "## Added optimization flags" "$MAKEFILE"; then
    echo "Inserting additional optimization flags to Makefile..."

    sed -i '89a\
    ## Added optimization flags\n\
    OPTON += -O3 -ffast-math -fomit-frame-pointer -frename-registers -funroll-loops # Unroll loops for faster execution\n\
    OPTON += -falign-loops -falign-functions -fno-strict-aliasing  # Memory optimization\n\
    OPTON += -march=native         # Optimize for the host CPU architecture\n\
    OPTON += -mtune=native         # Tune for the host CPU\n\
    OPTON += -fexpensive-optimizations # Enable expensive but powerful optimizations\n\
    OPTON += -fprefetch-loop-arrays  # Improve cache performance for loops' "$MAKEFILE"

    echo "Optimization flags added successfully."
else
    echo "Optimization flags already added. Skipping insertion."
fi

echo "Running dhry2reg benchmark with the optimized Makefile..."
cd "$UNIXBENCH_DIR" || exit
make clean
make
./Run dhry2reg > "$OUTPUT_DIR/dhry2reg_results_optimized.log"
echo "Optimized benchmark completed. Results are saved in $OUTPUT_DIR/dhry2reg_results_optimized.log"
