#!/bin/bash

num_cpus=$(nproc)
sysbench cpu --cpu-max-prime=20000 --threads="$num_cpus" run
