"""
run_comparison.py – runs CORE offline executable in both modes for comparison.
Usage:
  python run_comparison.py [local|remote] [debug|release] [QUERY] [DECL] [CSV] [OPTIONS]
"""
import subprocess, sys, os, time, shlex

# Project root is two levels up from this script's location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
MODE = (sys.argv[1].lower() if len(sys.argv) > 1 else "remote")
BUILD = (sys.argv[2].lower() if len(sys.argv) > 2 else "release")
DIR = "Debug" if BUILD == "debug" else "Release"

# Arguments
QUERY = sys.argv[3] if len(sys.argv) > 3 else "src/targets/experiments/my_data_unordered/query_1.txt"
DECL = sys.argv[4] if len(sys.argv) > 4 else "src/targets/experiments/my_data_unordered/declaration.core"
CSV = sys.argv[5] if len(sys.argv) > 5 else "src/targets/experiments/my_data_unordered/my_data.csv"
OPTIONS = sys.argv[6] if len(sys.argv) > 6 else "src/targets/experiments/my_data_unordered/quarantine_wait.core"

# Always resolve data file paths relative to the project root
QUERY_PATH = os.path.join(PROJECT_ROOT, QUERY)
DECL_PATH = os.path.join(PROJECT_ROOT, DECL)
CSV_PATH = os.path.join(PROJECT_ROOT, CSV)
OPTIONS_PATH = os.path.join(PROJECT_ROOT, OPTIONS)

IMG_REMOTE = "core-terminal"
IMG_LOCAL = "core-dev"
MOUNT_FLAGS = ["-v", f"{PROJECT_ROOT}:/workspace", "-w", "/workspace"]
ENV_FLAG = ["-e", "TRACY_NO_INVARIANT_CHECK=1"]

for f, f_path in zip(("QUERY", "DECL", "CSV", "OPTIONS"), (QUERY_PATH, DECL_PATH, CSV_PATH, OPTIONS_PATH)):
    if not os.path.isfile(f_path):
        sys.exit(f"❌ Missing: {f_path}")

def count_events(csv_path):
    with open(csv_path) as f:
        return sum(1 for _ in f) - 1

def run_timed(args, description):
    print(f"\n{'='*60}")
    print(f"🔬 {description}")
    print(f"{'='*60}")
    print("➜", " ".join(shlex.quote(a) for a in args))
    t0 = time.perf_counter()
    result = subprocess.run(args, capture_output=True, text=True, check=True)
    elapsed = time.perf_counter() - t0
    output_lines = result.stdout.splitlines()
    num_results = sum(1 for line in output_lines if line.strip().startswith('['))
    print(result.stdout, end="")
    return num_results, elapsed

# Build Docker image if needed
if MODE == "local":
    if subprocess.call(["docker", "image", "inspect", IMG_LOCAL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL):
        print("Building local image (core-dev)…")
        subprocess.run(["docker", "build", "--target", "build", "-t", IMG_LOCAL, "."], check=True, cwd=PROJECT_ROOT)

# Test 1: With --options argument (loads from file)
CMD_WITH_OPTIONS = [f"/CORE/build/{DIR}/offline", "--query", f"/workspace/{QUERY}", "--declaration", f"/workspace/{DECL}", "--csv", f"/workspace/{CSV}", "--options", f"/workspace/{OPTIONS}"]

if MODE == "remote":
    cmd1 = ["docker", "compose", "run", "--rm", *ENV_FLAG, *MOUNT_FLAGS, IMG_REMOTE, *CMD_WITH_OPTIONS]
else:
    cmd1 = ["docker", "run", "--rm", *ENV_FLAG, *MOUNT_FLAGS, IMG_LOCAL, *CMD_WITH_OPTIONS]

num_results1, elapsed1 = run_timed(cmd1, "TEST 1: With --options argument (loads quarantine from file)")

# Test 2: Without --options argument (uses hardcoded quarantine)
CMD_WITHOUT_OPTIONS = [f"/CORE/build/{DIR}/offline", "--query", f"/workspace/{QUERY}", "--declaration", f"/workspace/{DECL}", "--csv", f"/workspace/{CSV}"]

if MODE == "remote":
    cmd2 = ["docker", "compose", "run", "--rm", *ENV_FLAG, *MOUNT_FLAGS, IMG_REMOTE, *CMD_WITHOUT_OPTIONS]
else:
    cmd2 = ["docker", "run", "--rm", *ENV_FLAG, *MOUNT_FLAGS, IMG_LOCAL, *CMD_WITHOUT_OPTIONS]

num_results2, elapsed2 = run_timed(cmd2, "TEST 2: Without --options argument (uses default DIRECT policy)")

# Summary
print(f"\n{'='*60}")
print(f"📊 COMPARISON SUMMARY")
print(f"{'='*60}")
print(f"Input events: {count_events(CSV_PATH)}")
print(f"")
print(f"Test 1 (with --options):    {num_results1} results in {elapsed1:.3f}s")
print(f"Test 2 (without --options): {num_results2} results in {elapsed2:.3f}s")
print(f"")
if num_results1 < num_results2:
    print(f"✅ EXPECTED: Quarantine policy filters out {num_results2 - num_results1} temporally invalid matches")
    print(f"✅ Test 1 (WAIT policy): {num_results1} results - temporal filtering active")
    print(f"✅ Test 2 (DIRECT policy): {num_results2} results - no temporal filtering")
    print(f"✅ Quarantine policy working correctly!")
elif num_results1 == num_results2:
    print(f"⚠️  WARNING: Both modes produce the same results ({num_results1})")
    print(f"⚠️  This suggests quarantine policy may not be working as expected")
else:
    print(f"❌ UNEXPECTED: Test 1 has more results than Test 2")
    print(f"❌ This should not happen - quarantine should filter, not add results")
