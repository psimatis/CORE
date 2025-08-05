"""
This experiment executes CORE on ordered and unordered data to compare the results.
It logs both in files and the console.

data_order_experiment.py – runs CORE with stocks and unordered stocks datasets and compares processing metrics.
Usage:
  python data_order_experiment.py [local|remote] [debug|release]
  
  Compares ordered vs unordered data processing performance.
"""
import subprocess, sys, os, datetime, json, shlex, time

# Project root is two levels up from this script's location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
MODE = (sys.argv[1].lower() if len(sys.argv) > 1 else "remote")
BUILD = (sys.argv[2].lower() if len(sys.argv) > 2 else "release")

# Validate build
if BUILD not in ["debug", "release"]:
    sys.exit(f"❌ Invalid build: {BUILD}. Use 'debug' or 'release'.")

DIR = "Debug" if BUILD == "debug" else "Release"

# Define experiment configurations
EXPERIMENTS = [
    {
        "name": "Unordered My Data",
        "query": "src/targets/experiments/my_data_unordered/query_1.txt",
        "declaration": "src/targets/experiments/my_data_unordered/declaration.core",
        "csv": "src/targets/experiments/my_data_unordered/my_data.csv"
    },
    {
        "name": "Ordered My Data",
        "query": "src/targets/experiments/my_data/query_1.txt",
        "declaration": "src/targets/experiments/my_data/declaration.core",
        "csv": "src/targets/experiments/my_data/my_data.csv"
    }
]

IMG_REMOTE = "core-terminal"
IMG_LOCAL = "core-dev"
ENV_FLAG = ["-e", "TRACY_NO_INVARIANT_CHECK=1"]


def count_events(csv_path):
    with open(csv_path) as f:
        return sum(1 for _ in f) - 1


def run_timed(args, console_log_file=None):
    cmd_str = " ".join(shlex.quote(a) for a in args)
    print("➜", cmd_str)

    # Log the command to the console log file if provided
    if console_log_file:
        with open(console_log_file, 'a') as f:
            f.write(f"➜ {cmd_str}\n")

    t0 = time.perf_counter()
    try:
        result = subprocess.run(args, capture_output=True, text=True, check=True)
        elapsed = time.perf_counter() - t0
        output_lines = result.stdout.splitlines()
        num_results = sum(1 for line in output_lines if line.strip().startswith('['))
        # Print and log the output
        print(result.stdout, end="")
        if console_log_file:
            with open(console_log_file, 'a') as f:
                f.write(result.stdout)
        return num_results, elapsed
    except subprocess.CalledProcessError as e:
        print("\n[ERROR] Subprocess failed!")
        if e.stdout:
            print("[STDOUT]:\n" + e.stdout)
        if e.stderr:
            print("[STDERR]:\n" + e.stderr)
        raise


def run_experiment(experiment, console_log_file=None):
    # Resolve paths
    query_path = os.path.join(PROJECT_ROOT, experiment["query"])
    declaration_path = os.path.join(PROJECT_ROOT, experiment["declaration"])
    csv_path = os.path.join(PROJECT_ROOT, experiment["csv"])
    
    # Check if files exist
    for f, f_path in zip(("QUERY", "DECLARATION", "CSV"), (query_path, declaration_path, csv_path)):
        if not os.path.isfile(f_path):
            sys.exit(f"❌ Missing: {f_path}")
    
    # Use container paths for docker command
    query_container = f"/workspace/{experiment['query']}"
    declaration_container = f"/workspace/{experiment['declaration']}"
    csv_container = f"/workspace/{experiment['csv']}"

    # Setup mount flags and command
    mount_flags = ["-v", f"{PROJECT_ROOT}:/workspace", "-w", "/workspace"]
    core_args = ["/CORE/build/" + DIR + "/offline", "--query", query_container, "--declaration", declaration_container, "--csv", csv_container]
    if MODE == "remote":
        docker_cmd = ["docker", "compose", "run", "--rm", *ENV_FLAG, *mount_flags, IMG_REMOTE, *core_args]
        num_results, elapsed = run_timed(docker_cmd, console_log_file)
    else:
        if subprocess.call(["docker", "image", "inspect", IMG_LOCAL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL):
            print("Building local image (core-dev)…")
            if console_log_file:
                with open(console_log_file, 'a') as f:
                    f.write("Building local image (core-dev)…\n")
            subprocess.run(["docker", "build", "--target", "build", "-t", IMG_LOCAL, "."], check=True, cwd=PROJECT_ROOT)
        docker_cmd = ["docker", "run", "--rm", *ENV_FLAG, *mount_flags, IMG_LOCAL, *core_args]
        num_results, elapsed = run_timed(docker_cmd, console_log_file)
    
    # Calculate metrics
    input_events = count_events(csv_path)
    
    return {
        "name": experiment["name"],
        "input_events": input_events,
        "results": num_results,
        "execution_time": elapsed
    }


if __name__ == "__main__":
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Create logs directory if it doesn't exist
    logs_dir = os.path.join(PROJECT_ROOT, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    
    # Create a timestamped directory for this run
    run_dir = os.path.join(logs_dir, f"experiment_{timestamp}")
    os.makedirs(run_dir, exist_ok=True)
    
    console_log = os.path.join(run_dir, "console.log")
    summary_log = os.path.join(run_dir, "summary.log")
    
    # Initialize console log
    with open(console_log, 'w') as f:
        f.write(f"ORDER EXPERIMENT LOG\n")
        f.write(f"===================\n")
        f.write(f"Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Mode: {MODE}\n")
        f.write(f"Build: {BUILD}\n\n")
        f.write(f"Running {len(EXPERIMENTS)} experiments...\n\n")
    
    # Run experiments
    results = []
    for experiment in EXPERIMENTS:
        # Create formatted header for this experiment
        separator = "=" * 80
        header = f"RUNNING: {experiment['name']}"
        
        print(f"\n{separator}")
        print(header)
        print(f"{separator}\n")
        
        # Log to console file
        with open(console_log, 'a') as f:
            f.write(f"\n{separator}\n")
            f.write(f"{header}\n")
            f.write(f"{separator}\n\n")
        
        result = run_experiment(experiment, console_log)
        results.append(result)
    
    # Print comparison summary
    print("\n\n" + "=" * 80)
    print("EXPERIMENT COMPARISON SUMMARY")
    print("=" * 80)
    print(f"{'Experiment':<25} {'Input Events':<15} {'Results':<10} {'Time (s)':<10} {'Events/s':<10}")
    print("-" * 75)
    
    for result in results:
        events_per_second = result["input_events"] / result["execution_time"] if result["execution_time"] > 0 else 0
        print(f"{result['name']:<25} {result['input_events']:<15} {result['results']:<10} {result['execution_time']:.3f}s{' ':<6} {events_per_second:.1f}")
    
    # Calculate differences between ordered and unordered experiments
    if len(results) == 2:
        time_diff = results[1]["execution_time"] - results[0]["execution_time"]
        time_percent = (time_diff / results[0]["execution_time"]) * 100 if results[0]["execution_time"] > 0 else 0
        result_diff = results[1]["results"] - results[0]["results"]
        
        print("\nPerformance Difference:")
        print(f"Time difference: {time_diff:.3f}s ({time_percent:.1f}%)")
        print(f"Result difference: {result_diff} results")
        
        comparison_result = ""
        if time_percent > 0:
            comparison_result = f"{results[1]['name']} is {abs(time_percent):.1f}% slower than {results[0]['name']}"
            print(comparison_result)
        elif time_percent < 0:
            comparison_result = f"{results[1]['name']} is {abs(time_percent):.1f}% faster than {results[0]['name']}"
            print(comparison_result)
        else:
            comparison_result = "Both experiments performed equally"
            print(comparison_result)
            
        # Add comparison data to results
        summary = {
            "time_diff": time_diff,
            "time_percent": time_percent,
            "result_diff": result_diff,
            "comparison": comparison_result
        }
    else:
        summary = {}
    # Write results to summary log file
    log_data = {
        "timestamp": datetime.datetime.now().isoformat(),
        "mode": MODE,
        "build": BUILD,
        "experiments": results,
    }
    
    with open(summary_log, 'w') as f:
        # Write human-readable summary
        f.write(f"ORDER EXPERIMENT RESULTS\n")
        f.write(f"=====================\n")
        f.write(f"Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Mode: {MODE}\n")
        f.write(f"Build: {BUILD}\n\n")
        
        f.write(f"{'Experiment':<25} {'Input Events':<15} {'Results':<10} {'Time (s)':<10} {'Events/s':<10}\n")
        f.write("-" * 75 + "\n")
        
        for result in results:
            events_per_second = result["input_events"] / result["execution_time"] if result["execution_time"] > 0 else 0
            f.write(f"{result['name']:<25} {result['input_events']:<15} {result['results']:<10} {result['execution_time']:.3f}s{' ':<6} {events_per_second:.1f}\n")
        
        # Also write JSON data for programmatic access
        f.write("\n\n--- JSON DATA ---\n")
        f.write(json.dumps(log_data, indent=2))
    
    print(f"\nResults saved to:\n - Summary: {summary_log}\n - Console: {console_log}")
