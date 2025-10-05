"""
Compare the behavior of the quarantine policies.

Usage:
  python quarantine_experiment.py
"""
import subprocess, os, shlex, re, csv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))

QUERY = "src/targets/experiments/maritime/q2.txt"
DECL = "src/targets/experiments/maritime/maritime.core"
CSV = "src/targets/experiments/maritime/100000.csv"
OPTIONS = "src/targets/experiments/maritime/quarantine2.core"


IMG_LOCAL = "core-dev"
MOUNT_FLAGS = ["-v", f"{PROJECT_ROOT}:/workspace", "-w", "/workspace"]
ENV_FLAG = ["-e", "TRACY_NO_INVARIANT_CHECK=1"]
CMD_WITHOUT_QUARANTINE = [f"/CORE/build/Release/offline", "--query", f"/workspace/{QUERY}", "--declaration", f"/workspace/{DECL}", "--csv", f"/workspace/{CSV}"]
CMD_WITH_QUARANTINE = [f"/CORE/build/Release/offline", "--query", f"/workspace/{QUERY}", "--declaration", f"/workspace/{DECL}", "--csv", f"/workspace/{CSV}", "--options", f"/workspace/{OPTIONS}"]

def read_event_order(csv_path):
    csv_order = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            csv_order.append(int(row['Time_A']))
    return csv_order


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


def run_test(description, cmd):
    print(f"\n{'='*60}")
    print(f"🔬 {description}")
    print(f"{'='*60}")
    print("➜", " ".join(shlex.quote(a) for a in cmd))
    
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    
    print("\n🔍 Debug output:")
    for line in result.stdout.splitlines():
        print(f"  {line}")
    
    received_order, sent_order, complex_events = extract_events(result.stdout)
    print(f"📥 Events RECEIVED by quarantine: {received_order}")
    print(f"📤 Events SENT by quarantine:     {sent_order}")
    print(f"🔍 Complex events found: {complex_events}")
    
    if received_order != sent_order:
        print(f"✅ REORDERING DETECTED: Events were reordered from {received_order} to {sent_order}")
        if sent_order == sorted(received_order):
            print(f"✅ CORRECT ORDERING: Events sent in chronological order")
    else:
        print(f"❌ NO REORDERING: Events sent in same order as received")
    
    return received_order, sent_order, complex_events


if __name__ == "__main__":
    if subprocess.call(["docker", "image", "inspect", IMG_LOCAL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL):
        print("Building local image (core-dev)…")
        subprocess.run(["docker", "build", "--target", "build", "-t", IMG_LOCAL, "."], check=True, cwd=PROJECT_ROOT)

    cmd_direct = ["docker", "run", "--rm", *ENV_FLAG, *MOUNT_FLAGS, IMG_LOCAL, *CMD_WITHOUT_QUARANTINE]
    received_direct, sent_direct, events_direct = run_test("DIRECT Policy (No Quarantine)", cmd_direct)

    cmd_wait = ["docker", "run", "--rm", *ENV_FLAG, *MOUNT_FLAGS, IMG_LOCAL, *CMD_WITH_QUARANTINE]
    received_wait, sent_wait, events_wait = run_test("WAIT Quarantine Policy", cmd_wait)

    # Comparison Summary
    event_order = read_event_order(os.path.join(PROJECT_ROOT, CSV))
    print(f"\n📊 POLICY COMPARISON")
    print(f"Original event order:     {event_order}")
    print(f"Chronological order:   {sorted(event_order)}\n")

    print(f"DIRECT Policy:")
    print(f"  Received: {received_direct}")
    print(f"  Sent:     {sent_direct}")
    print(f"  Complex events: {events_direct}")
    print(f"  Reordered: {'✅ YES' if received_direct != sent_direct else '❌ NO'}\n")

    print(f"WAIT Policy:")
    print(f"  Received: {received_wait}")
    print(f"  Sent:     {sent_wait}")
    print(f"  Complex events: {events_wait}")
    print(f"  Reordered: {'✅ YES' if received_wait != sent_wait else '❌ NO'}")
    print(f"🔍 Number of complex events found: {len(events_wait)}")
