import os
import re
import matplotlib.pyplot as plt
import numpy as np

CURRENT_DIRECTORY = os.getenv("OUTPUT_DIR", os.getcwd())
DEFAULT_PLOTS_DIRECTORY = os.path.join(CURRENT_DIRECTORY, "plots")


def create_plots_directory(output_directory=DEFAULT_PLOTS_DIRECTORY):
    """Create directory for plots if it doesn't exist.
    :param output_directory: Directory path for saving plots.
    """
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)


def parse_filename(filename):
    """
    Parse the filename to extract the number of threads and duration.
    :param filename: Filename in format cyclictest_histogram_<num_threads>_threads_<duration>_seconds.txt
    :return: num_threads, duration
    """
    match = re.match(r"cyclictest_histogram_(\d+)_threads_(\d+)_seconds.txt", filename)
    if match:
        num_threads = int(match.group(1))
        duration = int(match.group(2))
        return num_threads, duration
    return None, None


def read_latency_data(filepath):
    """Read latency from histogram file note it -h vs -H no summary col
    :param filepath:
    :return:
    """
    thread_counts = []
    max_latencies = []
    avg_latencies = []
    with open(filepath, "r") as file:
        for line in file:
            if line.startswith('# Max Latencies:'):
                max_latencies = list(map(int, line.strip().split(':')[1].strip().split()))
            elif line.startswith('# Avg Latencies:'):
                avg_latencies = list(map(float, line.strip().split(':')[1].strip().split()))
            parts = line.strip().split()
            if parts and parts[0].isdigit():
                latency = int(parts[0])
                counts = list(map(int, parts[1:]))
                while len(thread_counts) < len(counts):
                    thread_counts.append([])
                for i, count in enumerate(counts):
                    thread_counts[i].append((latency, count))
    return thread_counts, max_latencies, avg_latencies


def generate_colors(num_threads):
    """
    Generate a list of unique colors for plotting, based on the number of threads.
    :param num_threads: Number of threads.
    :return: List of colors.
    """
    colormap = plt.get_cmap('tab20')
    colors = [colormap(i / num_threads) for i in range(num_threads)]
    return colors


def plot_latency_data(thread_counts, filename, num_threads, max_latencies, avg_latencies, output_directory):
    """
    Plot latency data for each thread.
    :param thread_counts: List of lists containing latency counts for each thread.
    :param filename: Filename to save the plot.py as.
    :param num_threads: Number of threads used in the test.
    :param max_latencies: List of max latencies for each thread.
    :param avg_latencies: List of average latencies for each thread.
    :param output_directory: Directory to save the plot.py.
    """
    fig, ax = plt.subplots(figsize=(12, 8), dpi=150)
    colors = generate_colors(num_threads)
    overall_max_latency = max(max_latencies)

    for i in range(num_threads):
        latencies, counts = zip(*thread_counts[i])
        label = f'CPU{i} (max {max_latencies[i]} μs, avg {avg_latencies[i]:.2f} μs)'
        ax.plot(latencies, counts, label=label, color=colors[i % len(colors)])

    ax.set_yscale('log')
    ax.set_xlabel("Latency (μs)")
    ax.set_ylabel("Number of latency samples")
    ax.set_title(f"Latency Plot by CPU - {num_threads} cores, max {overall_max_latency} μs")
    ax.legend()

    plot_path = os.path.join(output_directory, filename + ".png")
    plt.savefig(plot_path, bbox_inches="tight")
    plt.close()
    print(f"Plot generated with {num_threads} threads, "
          f"maximum latency {overall_max_latency} μs. Plot saved to '{plot_path}'")


def process_all_histogram_files(directory, output_directory=DEFAULT_PLOTS_DIRECTORY):
    """
    Process all cycling test histogram files in a specified directory.
    :param directory: Path to the directory containing histogram files.
    :param output_directory: Directory to save the plots.
    """
    create_plots_directory(output_directory)
    for filename in os.listdir(directory):
        if filename.startswith("cyclictest_histogram") and filename.endswith(".txt"):
            num_threads, _ = parse_filename(filename)
            if num_threads is not None:
                filepath = os.path.join(directory, filename)
                thread_counts, max_latencies, avg_latencies = read_latency_data(filepath)
                plot_latency_data(thread_counts, filename.replace('.txt', ''), num_threads, max_latencies,
                                  avg_latencies, output_directory)


if __name__ == '__main__':
    output_dir = os.getenv("OUTPUT_DIR", DEFAULT_PLOTS_DIRECTORY)
    process_all_histogram_files(CURRENT_DIRECTORY, output_directory=output_dir)
