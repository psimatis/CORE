"""
Test if WAIT quarantine policy actually reorders events by timestamp.

Usage:
  python quarantine_experiment.py
"""
import subprocess, os, shlex, re, csv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))

# Data
QUERY = "src/targets/experiments/my_data_unordered/query_1.txt"
DECL = "src/targets/experiments/my_data_unordered/declaration.core"
CSV = "src/targets/experiments/my_data_unordered/my_data.csv"
OPTIONS = "src/targets/experiments/my_data_unordered/quarantine_wait.core"

IMG_LOCAL = "core-dev"
MOUNT_FLAGS = ["-v", f"{PROJECT_ROOT}:/workspace", "-w", "/workspace"]
ENV_FLAG = ["-e", "TRACY_NO_INVARIANT_CHECK=1"]
CMD_WITH_QUARANTINE = [f"/CORE/build/Release/offline", "--query", f"/workspace/{QUERY}", "--declaration", f"/workspace/{DECL}", "--csv", f"/workspace/{CSV}", "--options", f"/workspace/{OPTIONS}"]


def read_event_order(csv_path):
    csv_order = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            csv_order.append(int(row['stock_time']))
    return csv_order


def extract_event_order(output):
    received_order = []
    sent_order = []
    
    for line in output.splitlines():
        if "QUARANTINE RECEIVE: event time=" in line:
            match = re.search(r"time=(\d+)", line)
            if match:
                received_order.append(int(match.group(1)))
        
        if "QUARANTINE SEND: event time=" in line or "QUARANTINE FORCE SEND EVENT: time=" in line:
            match = re.search(r"time=(\d+)", line)
            if match:
                sent_order.append(int(match.group(1)))
                    
    return received_order, sent_order


def run_test(description, cmd):
    print(f"\n{'='*60}")
    print(f"🔬 {description}")
    print(f"{'='*60}")
    print("➜", " ".join(shlex.quote(a) for a in cmd))
    
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    
    print("\n🔍 Debug output:")
    for line in result.stdout.splitlines():
        print(f"  {line}")
    
    received_order, sent_order = extract_event_order(result.stdout)
    print(f"📥 Events RECEIVED by quarantine: {received_order}")
    print(f"📤 Events SENT by quarantine:     {sent_order}")
    
    if received_order != sent_order:
        print(f"✅ REORDERING DETECTED: Events were reordered from {received_order} to {sent_order}")
        if sent_order == sorted(received_order):
            print(f"✅ CORRECT ORDERING: Events sent in chronological order")
    else:
        print(f"❌ NO REORDERING: Events sent in same order as received")
    
    return received_order, sent_order


if __name__ == "__main__":
    event_order = read_event_order(os.path.join(PROJECT_ROOT, CSV))
    
    if subprocess.call(["docker", "image", "inspect", IMG_LOCAL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL):
        print("Building local image (core-dev)…")
        subprocess.run(["docker", "build", "--target", "build", "-t", IMG_LOCAL, "."], check=True, cwd=PROJECT_ROOT)

    # Test with WAIT quarantine policy
    cmd = ["docker", "run", "--rm", *ENV_FLAG, *MOUNT_FLAGS, IMG_LOCAL, *CMD_WITH_QUARANTINE]
    received, sent = run_test("WAIT Quarantine Policy", cmd)

    # Summary
    print(f"\n📊 REORDERING ANALYSIS")
    print(f"Original event order:   {event_order}")
    print(f"Quarantine received:    {received}")
    print(f"Quarantine sent:        {sent}")
    print(f"Expected chronological: {sorted(event_order)}")
    print(f"")
