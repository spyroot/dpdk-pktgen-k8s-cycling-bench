import matplotlib.pyplot as plt

HISTOGRAM_FILE = "cyclictest_histogram_4t_h1000.txt"

thread_counts = []

with open(HISTOGRAM_FILE, "r") as file:
    for line in file:
        parts = line.strip().split()
        if parts and parts[0].isdigit():
            latency = int(parts[0])
            counts = list(map(int, parts[1:]))
            # Ensure the thread_counts list is long enough
            while len(thread_counts) < len(counts):
                thread_counts.append([])
            for i, count in enumerate(counts):
                thread_counts[i].append((latency, count))

# Plotting
fig, axes = plt.subplots(len(thread_counts), 1, figsize=(10, 6), sharex=True)
fig.suptitle("Cyclictest Latency Histograms per Thread")
for i, ax in enumerate(axes):
    latencies, counts = zip(*thread_counts[i])
    ax.plot(latencies, counts, label=f"Thread {i+1}")
    ax.set_ylabel("Count")
    ax.legend()
axes[-1].set_xlabel("Latency (microseconds)")

plt.tight_layout()
plt.subplots_adjust(top=0.95)
plt.savefig("cyclictest_latency_histograms.png")
plt.show()

print("Cyclictest latency histograms saved to cyclictest_latency_histograms.png")
