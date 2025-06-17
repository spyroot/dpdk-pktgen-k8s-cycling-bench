#!/bin/bash
# tuned profile generator for RT system.  Note TBD need finish a few parts.
# Author: Mus spyroot@gmail.com

echo "Enter the default huge page size (in GB):"
read -r default_hugepagesz
echo "Enter the huge page size (in GB):"
read -r hugepagesz
echo "Enter the number of huge pages:"
read -r hugepages

if [[ -z "$default_hugepagesz" || -z "$hugepagesz" || -z "$hugepages" ]]; then
    echo "All inputs are required. Exiting."
    exit 1
fi

cat <<EOF > tuned.conf
[main]
summary=Optimize for realtime workloads with security mitigations disabled and performance parameters
include = network-latency

[variables]
include = /etc/tuned/realtime-variables.conf

isolated_cores_assert_check = \${isolated_cores}
isolated_cores = \${isolated_cores}
assert1=\${f:assertion_non_equal:isolated_cores are set:\${isolated_cores}:\${isolated_cores_assert_check}}

not_isolated_cpumask = \${f:cpulist2hex_invert:\${isolated_cores}}
isolated_cores_expanded=\${f:cpulist_unpack:\${isolated_cores}}
isolated_cpumask=\${f:cpulist2hex:\${isolated_cores_expanded}}
isolated_cores_online_expanded=\${f:cpulist_online:\${isolated_cores}}

assert2=\${f:assertion:isolated_cores contains online CPU(s):\${isolated_cores_expanded}:\${isolated_cores_online_expanded}}

isolate_managed_irq = \${isolate_managed_irq}
managed_irq=\${f:regex_search_ternary:\${isolate_managed_irq}:\b[y,Y,1,t,T]\b:managed_irq,domain,:}

sched_isolation = \${sched_isolation}
sched=\${f:regex_search_ternary:\${sched_isolation}:\b[y,Y,1,t,T]\b:sched,:}

[net]
channels=combined \${f:check_net_queue_count:\${netdev_queue_count}}

[sysctl]
kernel.sched_rt_runtime_us = -1

[sysfs]
/sys/bus/workqueue/devices/writeback/cpumask = \${not_isolated_cpumask}
/sys/devices/virtual/workqueue/cpumask = \${not_isolated_cpumask}
/sys/devices/virtual/workqueue/*/cpumask = \${not_isolated_cpumask}
/sys/devices/system/machinecheck/machinecheck*/ignore_ce = 1

[bootloader]
# Additional kernel parameters for performance tuning, hugepages, and other settings
cmdline_realtime=+isolcpus=\${managed_irq}\${sched}\${isolated_cores} intel_pstate=disable nosoftlockup mitigations=off nopti default_hugepagesz=${default_hugepagesz}G hugepagesz=${hugepagesz}G hugepages=${hugepages} intel_iommu=on iommu=pt idle=poll nmi_watchdog=0 audit=0 processor.max_cstate=0 intel_idle.max_cstate=0 hpet=disable mce=off tsc=reliable numa_balancing=disable

[irqbalance]
banned_cpus=\${isolated_cores}

[script]
script = \${i:PROFILE_DIR}/script.sh

[scheduler]
isolated_cores=\${isolated_cores}
EOF

echo "tuned.conf generated successfully with the following hugepages settings:"
echo "  - default_hugepagesz: ${default_hugepagesz}G"
echo "  - hugepagesz: ${hugepagesz}G"
echo "  - hugepages: ${hugepages}"