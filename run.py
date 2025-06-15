"""
run.py – Drive CORE's offline engine in Docker and capture a timestamped log

Usage:
    python3 run.py [QUERY_FILE] [DECLARATION_FILE] [CSV_FILE]

If no arguments are given, it runs the stocks demo.
A log is written to ./logs/ with the query name and a UTC timestamp.
"""

import subprocess
import sys
import os
from datetime import datetime

# ----------------------------------------------------------------------------
# Resolve repository root
# ----------------------------------------------------------------------------
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))

# ----------------------------------------------------------------------------
# Pick arguments or fall back to demo data
# ----------------------------------------------------------------------------
def_arg = lambda i, fallback: sys.argv[i] if len(sys.argv) > i else fallback

query = def_arg(1, "src/targets/experiments/stocks/queries/other-q1_none.txt")
declaration = def_arg(2, "src/targets/experiments/stocks/declaration.core")
csv = def_arg(3, "src/targets/experiments/stocks/stock_data.csv")

for f in [query, declaration, csv]:
    full_path = os.path.join(REPO_ROOT, f)
    if not os.path.isfile(full_path):
        print(f"❌  Can't find {f}", file=sys.stderr)
        sys.exit(1)

# ----------------------------------------------------------------------------
# Prepare log file path
# ----------------------------------------------------------------------------
LOG_DIR = os.path.join(REPO_ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
base = os.path.splitext(os.path.basename(query))[0]
log_file = os.path.join(LOG_DIR, f"{base}_{timestamp}.log")

print(f"▶ Running CORE – log → {log_file}")

# ----------------------------------------------------------------------------
# Construct docker command
# ----------------------------------------------------------------------------
docker_cmd = [
    "docker", "compose", "run", "--rm",
    "-e", "TRACY_NO_INVARIANT_CHECK=1",
    "-v", f"{REPO_ROOT}:/workspace",
    "-w", "/workspace",
    "core-terminal",
    "/CORE/build/Release/offline",
    "--query", query,
    "--declaration", declaration,
    "--csv", csv
]

# ----------------------------------------------------------------------------
# Run and capture output
# ----------------------------------------------------------------------------
with open(log_file, "w") as log:
    process = subprocess.Popen(docker_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in process.stdout:
        print(line, end='')
        log.write(line)
    process.wait()
    sys.exit(process.returncode)