#!/bin/bash

num_cpus=$(nproc)
stress-ng --cpu "$num_cpus" --cpu-method all --timeout 120s
