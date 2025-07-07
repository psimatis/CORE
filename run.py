"""
run.py – runs CORE (remote or local image).
Usage:
  python run.py [local|remote] [debug|release] [QUERY] [DECL] [CSV]
"""
import subprocess, sys, os, time, shlex

ROOT = os.path.dirname(os.path.abspath(__file__))
MODE = (sys.argv[1].lower() if len(sys.argv) > 1 else "remote")
BUILD = (sys.argv[2].lower() if len(sys.argv) > 2 else "release")
DIR = "Debug" if BUILD == "debug" else "Release"

# Stocks/default
# QUERY = sys.argv[3] if len(sys.argv) > 3 else "src/targets/experiments/stocks/queries/other-q1_none.txt"
# DECL = sys.argv[4] if len(sys.argv) > 4 else "src/targets/experiments/stocks/declaration.core"
# CSV = sys.argv[5] if len(sys.argv) > 5 else "src/targets/experiments/stocks/stock_data.csv"

# Unordered stocks
# QUERY = "src/targets/experiments/unordered_stocks/queries/other-q1_none.txt"
# DECL = "src/targets/experiments/unordered_stocks/declaration.core"
# CSV = "src/targets/experiments/unordered_stocks/stock_data.csv"

# Smart homes
# QUERY = "src/targets/experiments/smart_homes/queries/q1_none.txt"
# DECL = "src/targets/experiments/smart_homes/declaration.core"
# CSV = "src/targets/experiments/smart_homes/smart_homes_data.csv"

# My data
QUERY = "src/targets/experiments/my_data/query_2.txt"
DECL = "src/targets/experiments/my_data/declaration.core"
CSV = "src/targets/experiments/my_data/my_data.csv"

IMG_REMOTE = "core-terminal"
IMG_LOCAL = "core-dev"
MOUNT_FLAGS = ["-v", f"{ROOT}:/workspace", "-w", "/workspace"]
ENV_FLAG = ["-e", "TRACY_NO_INVARIANT_CHECK=1"]

for f in (QUERY, DECL, CSV):
    if not os.path.isfile(os.path.join(ROOT, f)):
        sys.exit(f"❌ Missing: {f}")

CMD = [f"/CORE/build/{DIR}/offline", "--query", f"/workspace/{QUERY}","--declaration", f"/workspace/{DECL}", "--csv", f"/workspace/{CSV}"]

def count_events(csv_path):
    with open(os.path.join(ROOT, csv_path)) as f:
        return sum(1 for _ in f) - 1

def run_timed(args):
    print("➜", " ".join(shlex.quote(a) for a in args))
    t0 = time.perf_counter()
    result = subprocess.run(args, capture_output=True, text=True, check=True)
    elapsed = time.perf_counter() - t0
    output_lines = result.stdout.splitlines()
    num_results = sum(1 for line in output_lines if line.strip().startswith('['))
    print(result.stdout, end="")
    return num_results, elapsed

if MODE == "remote":
    cmd = ["docker", "compose", "run", "--rm", *ENV_FLAG, *MOUNT_FLAGS, IMG_REMOTE, *CMD]
    num_results, elapsed = run_timed(cmd)
else:
    if subprocess.call(["docker", "image", "inspect", IMG_LOCAL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL):
        print("Building local image (core-dev)…")
        subprocess.run(["docker", "build", "--target", "build", "-t", IMG_LOCAL, "."], check=True)
    cmd = ["docker", "run", "--rm", *ENV_FLAG, *MOUNT_FLAGS, IMG_LOCAL, *CMD]
    num_results, elapsed = run_timed(cmd)

print(f"\nSummary:")
print(f"Number of input events : {count_events(CSV)}")
print(f"Number of results      : {num_results}")
print(f"Query execution time   : {elapsed:.3f}s")
