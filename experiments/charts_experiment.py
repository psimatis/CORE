"""
Usage:
  python experiment.py [mode] [build] [query] [declaration] [csv] [options]
"""
import subprocess, os, shlex, re, csv, sys, time
import pandas as pd
import matplotlib.pyplot as plt

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))

BUILD = (sys.argv[1].lower() if len(sys.argv) > 2 else "release")
QUERY = sys.argv[2] if len(sys.argv) > 3 else "src/targets/experiments/maritime/q1.txt"
DECL = sys.argv[3] if len(sys.argv) > 4 else "src/targets/experiments/maritime/maritime.core"
CSV = sys.argv[4] if len(sys.argv) > 5 else "src/targets/experiments/maritime/1M.csv"
OPTIONS = sys.argv[5] if len(sys.argv) > 6 else "src/targets/experiments/maritime/quarantine2.core"

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
    '''print(f"\n{'='*60}")
    print(f"🔬 {description}")
    print(f"{'='*60}")
    print("➜", " ".join(shlex.quote(a) for a in cmd))
    print("\nQuery:\n  " + query_contents)'''
    
    drops = 0
    received = 0
    sent = 0

    t0 = time.perf_counter()
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    elapsed_time = time.perf_counter() - t0

    if options_contents is None:
        log_file = open(os.path.join(PROJECT_ROOT, "logs/logfile_experiment_direct.log"), "w")
    elif options_contents is not None:
        #print("\nQuarantine fixed time:\n  " + options_contents)
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
                if line.startswith("Number of events DROPPED"):
                    match = re.search(r"\d+", line)
                    if match:
                        drops = int(match.group())
                elif line.startswith("Number of events RECEIVED"):
                    match = re.search(r"\d+", line)
                    if match:
                        received = int(match.group())
                elif line.startswith("Number of events SENT"):
                    match = re.search(r"\d+", line)
                    if match:
                        sent = int(match.group())
                quarantine_file.write(f"{line}\n")
    
    if options_contents is None:
        num_results = sum(1 for line in result.stdout.splitlines() if line.strip().startswith('['))
        return num_results, elapsed_time
    
    received_order, sent_order, complex_events = extract_events(result.stdout)
    '''print("\n🦠 Quarantine Results:")
    print(f"📥 Number of events RECEIVED by quarantine: {received}")
    print(f"📤 Number of events SENT by quarantine:     {sent}")
    print(f"🗑️  Number of events DROPPED by quarantine:  {drops}")
    print(f"🔍 Number of complex events found: {len(complex_events)}")'''
    
    '''if received_order != sent_order:
        print(f"✅ REORDERING DETECTED: Events were reordered by quarantine")
        if sent_order == sorted(received_order):
            print(f"✅ CORRECT ORDERING: Events sent in chronological order")
    else:
        print(f"❌ NO REORDERING: Events sent in same order as received")'''

    return received_order, sent_order, complex_events, elapsed_time, drops

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

    print("\nQuery:\n  " + query_contents)

    match = re.search(r'FIXED_TIME\s+(\d+)\s+seconds', options_contents)
    number = None
    quarantine_times = []
    if match:
        number = int(match.group(1))
    
    x = number / 2
    while x >= 1:
        quarantine_times.append(int(x))
        x /= 2

    x = number
    for i in range(5):
        if x > 45:
            break
        quarantine_times.append(int(x))
        x *= 2

    quarantine_times = sorted(quarantine_times)
    print(f"\nQuarantine times to test: {quarantine_times}\n")

    direct_results = []
    execution_time = []
    throughput = []
    numOfResults = []
    numOfDrops = []
    results_labels = ["Execution Time (s)", "Throughput (results/s)", "Number of Results", "Number of Drops"]

    for i in quarantine_times:
        options_contents = re.sub(r'FIXED_TIME\s+\d+\s+seconds',
                    f'FIXED_TIME {i} seconds',
                    options_contents)

        with open(OPTIONS_PATH, "w") as f:
            f.write(options_contents)

        cmd_direct = ["docker", "run", "--rm", *PLATFORM_FLAG, *ENV_FLAG, *MOUNT_FLAGS, IMG_LOCAL, *CMD_WITHOUT_QUARANTINE]
        cmd_wait = ["docker", "run", "--rm", *PLATFORM_FLAG, *ENV_FLAG, *MOUNT_FLAGS, IMG_LOCAL, *CMD_WITH_QUARANTINE]
        
        directPolicy = []
        #print("\nRunning DIRECT policy (no quarantine)…")
        num_results_direct, core_time = run_test("DIRECT Policy (No Quarantine)", cmd_direct, query_contents)
        #print(f"Query execution time   : {core_time:.2f}s")
        #print(f"Query throughput       : {num_results_direct / core_time:.2f} results/sec")
        directPolicy.append(round(core_time,2))
        directPolicy.append(round((num_results_direct / core_time),2))
        directPolicy.append(num_results_direct)
        directPolicy.append(0)
        direct_results.append(directPolicy)

        #print("\nRunning WAIT quarantine policy…")
        received_wait, sent_wait, events_wait, core_time, drops = run_test("WAIT Quarantine Policy", cmd_wait, query_contents, options_contents)
        #print(f"Query execution time   : {core_time:.2f}s")
        #print(f"Query throughput       : {len(events_wait) / core_time:.2f} results/sec")
        execution_time.append(round(core_time,2))
        throughput.append(round((num_results_direct / core_time),2))
        numOfResults.append(len(events_wait))
        numOfDrops.append(drops)
        
        '''print("\n🔍 Comparison Results:")
        print(f"Number of input events         : {count_events(CSV_PATH)}")
        print(f"Number of results (DIRECT)     : {num_results_direct}")
        print(f"Number of results (WAIT)       : {len(events_wait)}")'''
    
    direct_averages = [round(sum(row[i] for row in direct_results) / len(direct_results), 2) 
            for i in range(len(results_labels))]
    
    print("== Quarantine Time ==", end="")
    for i in range(len(results_labels)):
        print(f"== {results_labels[i]} ==", end="")
    print()
    print(f"       direct        ", end="")
    print(f"         {direct_averages[0]}        ", end="")
    print(f"              {direct_averages[1]}            ", end="")
    print(f"          {direct_averages[2]}            ", end="")
    print(f"       {direct_averages[3]}            ", end="")
    for i in range(len(quarantine_times)):
        print()
        if quarantine_times[i] < 10:
            print(f"       {quarantine_times[i]}s          ", end="")
            print(f"           {execution_time[i]}       ", end="")
            print(f"              {throughput[i]}        ", end="")
            print(f"              {numOfResults[i]}       ", end="")
            print(f"              {numOfDrops[i]}            ", end="")
        else:
            print(f"       {quarantine_times[i]}s         ", end="")
            print(f"           {execution_time[i]}       ", end="")
            print(f"              {throughput[i]}        ", end="")
            print(f"              {numOfResults[i]}       ", end="")
            print(f"              {numOfDrops[i]}            ", end="")
    print()

    # ======= Execution Time =======
    plt.figure(figsize=(8,5))
    plt.plot(quarantine_times, execution_time, marker='o', color='tab:orange', label='WAIT Policy')
    plt.axhline(y=direct_averages[0], color='gray', linestyle='--', label=f'DIRECT (avg {direct_averages[0]}s)')
    for x, y in zip(quarantine_times, execution_time):
        plt.text(x, y+0.5, f"{y:.2f}", ha='center', fontsize=9)
    plt.title('Execution Time vs Quarantine Fixed Time')
    plt.xlabel('Quarantine Fixed Time (s)')
    plt.ylabel('Execution Time (s)')
    plt.legend()
    plt.grid(True)
    plt.savefig("Execution Time.png", dpi=300)
    #plt.show()

    # ======= Throughput =======
    plt.figure(figsize=(8,5))
    plt.plot(quarantine_times, throughput, marker='o', color='tab:blue', label='WAIT Policy')
    plt.axhline(y=direct_averages[1], color='gray', linestyle='--', label=f'DIRECT (avg {direct_averages[1]})')
    for x, y in zip(quarantine_times, throughput):
        plt.text(x, y+0.5, f"{y:.2f}", ha='center', fontsize=9)
    plt.title('Query Throughput vs Quarantine Fixed Time')
    plt.xlabel('Quarantine Fixed Time (s)')
    plt.ylabel('Throughput (results/sec)')
    plt.legend()
    plt.grid(True)
    plt.savefig("Throughput.png", dpi=300)
    #plt.show()

    # ======= Results Found =======
    plt.figure(figsize=(8,5))
    plt.plot(quarantine_times, numOfResults, marker='o', color='tab:green', label='WAIT Policy')
    plt.axhline(y=direct_averages[2], color='gray', linestyle='--', label=f'DIRECT (avg {direct_averages[2]})')
    for x, y in zip(quarantine_times, numOfResults):
        plt.text(x, y+0.5, f"{y}", ha='center', fontsize=9)
    plt.title('Complex Events Found vs Quarantine Fixed Time')
    plt.xlabel('Quarantine Fixed Time (s)')
    plt.ylabel('Number of Results')
    plt.legend()
    plt.grid(True)
    plt.savefig("Results.png", dpi=300)
    #plt.show()

    # ======= Drops =======
    plt.figure(figsize=(8,5))
    plt.plot(quarantine_times, numOfDrops, marker='o', color='tab:red', label='Dropped Events')
    plt.axhline(y=direct_averages[3], color='gray', linestyle='--', label=f'DIRECT (avg {direct_averages[3]})')
    for x, y in zip(quarantine_times, numOfDrops):
        plt.text(x, y+0.5, f"{y}", ha='center', fontsize=9)
    plt.title('Dropped Events vs Quarantine Fixed Time')
    plt.xlabel('Quarantine Fixed Time (s)')
    plt.ylabel('Dropped Events')
    plt.legend()
    plt.grid(True)
    plt.savefig("Drops.png", dpi=300)
    #plt.show()

    options_contents = re.sub(r'FIXED_TIME\s+\d+\s+seconds',
                    f'FIXED_TIME {number} seconds',
                    options_contents)
    
    with open(OPTIONS_PATH, "w") as f:
            f.write(options_contents)
        
        
