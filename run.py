"""
run.py – run CORE offline via Docker (remote or local image) and time it.
Usage:
  python run.py [local|remote] [debug|release] [QUERY] [DECL] [CSV]
"""

import subprocess, sys, os, time, shlex

ROOT = os.path.dirname(os.path.abspath(__file__))
MODE  = (sys.argv[1].lower() if len(sys.argv) > 1 else "remote")
BUILD = (sys.argv[2].lower() if len(sys.argv) > 2 else "release")
DIR   = "Debug" if BUILD == "debug" else "Release"

QUERY = sys.argv[3] if len(sys.argv) > 3 else \
        "src/targets/experiments/stocks/queries/other-q1_none.txt"
DECL  = sys.argv[4] if len(sys.argv) > 4 else \
        "src/targets/experiments/stocks/declaration.core"
CSV   = sys.argv[5] if len(sys.argv) > 5 else \
        "src/targets/experiments/stocks/stock_data.csv"

for f in (QUERY, DECL, CSV):
    if not os.path.isfile(os.path.join(ROOT, f)):
        sys.exit(f"❌ Missing: {f}")

IMG_REMOTE = "core-terminal"
IMG_LOCAL  = "core-dev"
MOUNT_FLAGS = ["-v", f"{ROOT}:/workspace", "-w", "/workspace"]
ENV_FLAG = ["-e", "TRACY_NO_INVARIANT_CHECK=1"]

CMD = [f"/CORE/build/{DIR}/offline",
       "--query",        f"/workspace/{QUERY}",
       "--declaration", f"/workspace/{DECL}",
       "--csv",         f"/workspace/{CSV}"]

def run_timed(args):
    print("➜", " ".join(shlex.quote(a) for a in args))
    t0 = time.perf_counter()
    subprocess.run(args, check=True)
    print(f"real {time.perf_counter() - t0:.3f}s")

if MODE == "remote":
    cmd = ["docker", "compose", "run", "--rm", *ENV_FLAG, *MOUNT_FLAGS, IMG_REMOTE, *CMD]
    run_timed(cmd)
else:
    if subprocess.call(["docker", "image", "inspect", IMG_LOCAL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL):
        print("Building local image (core-dev)…")
        subprocess.run(["docker", "build", "--target", "build", "-t", IMG_LOCAL, "."], check=True)
    cmd = ["docker", "run", "--rm", *ENV_FLAG, *MOUNT_FLAGS, IMG_LOCAL, *CMD]
    run_timed(cmd)
