"""
Usage:
  python experiment.py [mode] [build] [query] [declaration] [csv] [options]
"""
import subprocess, os, shlex, re, csv, sys, time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))

MODE = sys.argv[1] if len(sys.argv) > 1 else "direct"
BUILD = (sys.argv[2].lower() if len(sys.argv) > 2 else "release")
QUERY = sys.argv[3] if len(sys.argv) > 3 else "src/targets/experiments/maritime/q1.txt"
DECL = sys.argv[4] if len(sys.argv) > 4 else "src/targets/experiments/maritime/maritime.core"
CSV = sys.argv[5] if len(sys.argv) > 5 else "src/targets/experiments/maritime/100000.csv"
OPTIONS = sys.argv[6] if len(sys.argv) > 6 else "src/targets/experiments/maritime/quarantine2.core"

DIR = "Debug" if BUILD == "debug" else "Release"
MOUNT_FLAGS = ["-v", f"{PROJECT_ROOT}:/workspace", "-w", "/workspace"]
ENV_FLAG = ["-e", "TRACY_NO_INVARIANT_CHECK=1"]
PLATFORM_FLAG = ["--platform", "linux/amd64"]
IMG_LOCAL = "core-dev"

CSV_PATH = os.path.join(PROJECT_ROOT, CSV)
QUERY_PATH = os.path.join(PROJECT_ROOT, QUERY)
OPTIONS_PATH = os.path.join(PROJECT_ROOT, OPTIONS)
CMD_WITHOUT_QUARANTINE = [f"/CORE/build/{DIR}/offline", "--query", f"/workspace/{QUERY}", "--declaration", f"/workspace/{DECL}", "--csv", f"/workspace/{CSV}"]
CMD_WITH_QUARANTINE = [f"/CORE/build/{DIR}/offline", "--query", f"/workspace/{QUERY}", "--declaration", f"/workspace/{DECL}", "--csv", f"/workspace/{CSV}", "--options", f"/workspace/{OPTIONS}"]

def count_events(csv_path):
    with open(csv_path) as f:
        return sum(1 for _ in f) - 1
    
def extract_events(output):
    received_order = []
    sent_order = []
    complex_events = []
    
    for line in output.splitlines():
        if "QUARANTINE RECEIVE: event time=" in line:
            match = re.search(r"time=(\d+)", line)
            if match:
                received_order.append(int(match.group(1)))
        
        if "QUARANTINE SEND: event time=" in line or "QUARANTINE FORCE SEND EVENT: time=" in line:
            match = re.search(r"time=(\d+)", line)
            if match:
                sent_order.append(int(match.group(1)))
        
        # Extract complex events (query results)
        if line.strip().startswith('[') and '], ((' in line:
            match = re.search(r'^\[(\d+),(\d+)\],', line.strip())
            if match:
                time1, time2 = int(match.group(1)), int(match.group(2))
                complex_events.append([time1, time2])
                    
    return received_order, sent_order, complex_events

def run_test(description, cmd, query_contents, options_contents=None):
    print(f"\n{'='*60}")
    print(f"🔬 {description}")
    print(f"{'='*60}")
    print("➜", " ".join(shlex.quote(a) for a in cmd))
    print("\nQuery:\n  " + query_contents)

    
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)

    if options_contents is None:
        log_file = open(os.path.join(PROJECT_ROOT, "logs/logfile_experiment_direct.log"), "w")
    elif options_contents is not None:
        print("\nQuarantine fixed time:\n  " + options_contents)
        quarantine_file = open(os.path.join(PROJECT_ROOT, "logs/logfile_quarantine.log"), "w")
        result_log_file = open(os.path.join(PROJECT_ROOT, "logs/logfile_experiment_wait.log"), "w")

    for line in result.stdout.splitlines():
        if line.startswith('[') and options_contents is None:
            log_file.write(f"{line.split(') )')[0]}" + ") )\n")
        elif options_contents is not None:
            if line.startswith("STREAMING"):
                quarantine_file.write(f"\n{line}\n")
            elif line.startswith('['):
                result_log_file.write(f"{line.split(') )')[0]}" + ") )\n")
            else:
                quarantine_file.write(f"{line}\n")
    
    if options_contents is None:
        num_results = sum(1 for line in result.stdout.splitlines() if line.strip().startswith('['))
        return num_results
    
    received_order, sent_order, complex_events = extract_events(result.stdout)
    print("\n🦠 Quarantine Results:")
    print(f"📥 Number of events RECEIVED by quarantine: {len(received_order)}")
    print(f"📤 Number of events SENT by quarantine:     {len(sent_order)}")
    print(f"🗑️  Number of events DROPPED by quarantine:  {len(received_order)-len(sent_order)}")
    print(f"🔍 Number of complex events found: {len(complex_events)}")
    
    if received_order != sent_order:
        print(f"✅ REORDERING DETECTED: Events were reordered by quarantine")
        if sent_order == sorted(received_order):
            print(f"✅ CORRECT ORDERING: Events sent in chronological order")
    else:
        print(f"❌ NO REORDERING: Events sent in same order as received")
    
    return received_order, sent_order, complex_events

if __name__ == "__main__":
    if subprocess.call(["docker", "image", "inspect", IMG_LOCAL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL):
        print("Building local image (core-dev)…")
        subprocess.run([
            "docker", "buildx", "build", *PLATFORM_FLAG,
            "--target", "build", "-t", IMG_LOCAL, ".",
            "--load"
        ], check=True, cwd=PROJECT_ROOT)

    with open(QUERY_PATH, 'r') as f:
        query_contents = '  '.join(line.strip() + '\n' for line in f)

    with open(OPTIONS_PATH, 'r') as f:
        options_contents = '  '.join(line.strip() + '\n' for line in f)

    if MODE == "direct":
        cmd_direct = ["docker", "run", "--rm", *PLATFORM_FLAG, *ENV_FLAG, *MOUNT_FLAGS, IMG_LOCAL, *CMD_WITHOUT_QUARANTINE]
        t0 = time.perf_counter()
        num_results = run_test("DIRECT Policy (No Quarantine)", cmd_direct, query_contents)
        elapsed = time.perf_counter() - t0
        print("\n🔍 Results:")
        print(f"Number of input events : {count_events(CSV_PATH)}")
        print(f"Number of results      : {num_results}")
        print(f"Query execution time   : {elapsed:.3f}s")
        print(f"Query throughput       : {num_results / elapsed:.2f} results/sec")
    elif MODE == "wait":
        cmd_wait = ["docker", "run", "--rm", *PLATFORM_FLAG, *ENV_FLAG, *MOUNT_FLAGS, IMG_LOCAL, *CMD_WITH_QUARANTINE]
        t0 = time.perf_counter()
        received_wait, sent_wait, events_wait = run_test("WAIT Quarantine Policy", cmd_wait, query_contents, options_contents)
        elapsed = time.perf_counter() - t0
        print("\n🔍 Results:")
        print(f"Number of input events : {count_events(CSV_PATH)}")
        print(f"Number of results      : {len(events_wait)}")
        print(f"Query execution time   : {elapsed:.3f}s")
        print(f"Query throughput       : {len(events_wait) / elapsed:.2f} results/sec")
    elif MODE == "compare":
        cmd_direct = ["docker", "run", "--rm", *PLATFORM_FLAG, *ENV_FLAG, *MOUNT_FLAGS, IMG_LOCAL, *CMD_WITHOUT_QUARANTINE]
        cmd_wait = ["docker", "run", "--rm", *PLATFORM_FLAG, *ENV_FLAG, *MOUNT_FLAGS, IMG_LOCAL, *CMD_WITH_QUARANTINE]
        
        print("\nRunning DIRECT policy (no quarantine)…")
        t0 = time.perf_counter()
        num_results_direct = run_test("DIRECT Policy (No Quarantine)", cmd_direct, query_contents)
        elapsed_direct = time.perf_counter() - t0
        print(f"Query execution time   : {elapsed_direct:.3f}s")
        print(f"Query throughput       : {num_results_direct / elapsed_direct:.2f} results/sec")
        
        print("\nRunning WAIT quarantine policy…")
        t0 = time.perf_counter()
        received_wait, sent_wait, events_wait = run_test("WAIT Quarantine Policy", cmd_wait, query_contents, options_contents)
        elapsed_wait = time.perf_counter() - t0
        print(f"Query execution time   : {elapsed_wait:.3f}s")
        print(f"Query throughput       : {len(events_wait) / elapsed_wait:.2f} results/sec")
        
        print("\n🔍 Comparison Results:")
        print(f"Number of input events         : {count_events(CSV_PATH)}")
        print(f"Number of results (DIRECT)     : {num_results_direct}")
        print(f"Number of results (WAIT)       : {len(events_wait)}")
        
        if num_results_direct == len(events_wait):
            print("✅ Both policies produced the SAME number of results.")
        else:
            print("❌ Different number of results between policies!")
        
        


