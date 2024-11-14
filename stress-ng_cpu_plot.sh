#!/bin/bash

num_cpus=$(nproc)
mkdir -p /root/cpu_data
echo "Starting CPU stress test with $num_cpus CPUs."
mpstat -P ALL 1 120 > /root/cpu_data/cpu_usage.txt &
stress-ng --cpu $num_cpus --cpu-method all --timeout 120s
kill %1
echo "Stress test completed. CPU usage data saved to /root/cpu_data/cpu_usage.txt"

