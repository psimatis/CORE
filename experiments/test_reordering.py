"""
test_reordering.py – Test if WAIT quarantine policy actually reorders events by timestamp.
Usage:
  python test_reordering.py [local|remote] [debug|release]
"""
import subprocess, sys, os, time, shlex, re

# Project root is two levels up from this script's location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..'))
MODE = (sys.argv[1].lower() if len(sys.argv) > 1 else "local")
BUILD = (sys.argv[2].lower() if len(sys.argv) > 2 else "release")
DIR = "Debug" if BUILD == "debug" else "Release"

# Use unordered data
QUERY = "src/targets/experiments/my_data_unordered/query_1.txt"
DECL = "src/targets/experiments/my_data_unordered/declaration.core"
CSV = "src/targets/experiments/my_data_unordered/my_data.csv"
OPTIONS = "src/targets/experiments/my_data_unordered/quarantine_short.core"

IMG_REMOTE = "core-terminal"
IMG_LOCAL = "core-dev"
MOUNT_FLAGS = ["-v", f"{PROJECT_ROOT}:/workspace", "-w", "/workspace"]
ENV_FLAG = ["-e", "TRACY_NO_INVARIANT_CHECK=1"]

def extract_event_order(output):
    """Extract the order events are received and sent from debug output."""
    received_order = []
    sent_order = []
    
    for line in output.splitlines():
        # Extract received events
        if "QUARANTINE RECEIVE: event time=" in line:
            match = re.search(r"event time=(\d+)", line)
            if match:
                received_order.append(int(match.group(1)))
        
        # Extract sent events (regular send)
        if "QUARANTINE SEND: event time=" in line:
            match = re.search(r"event time=(\d+)", line)
            if match:
                sent_order.append(int(match.group(1)))
                
        # Extract force sent events
        if "QUARANTINE FORCE SEND EVENT: time=" in line:
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
    
    # Print relevant debug lines
    print("\n🔍 Debug output (quarantine messages only):")
    for line in result.stdout.splitlines():
        if any(keyword in line for keyword in ["QUARANTINE", "OFFLINE LISTENER"]):
            print(f"  {line}")
    
    received_order, sent_order = extract_event_order(result.stdout)
    
    print(f"📥 Events RECEIVED by quarantine: {received_order}")
    print(f"📤 Events SENT by quarantine:     {sent_order}")
    
    # Check if reordering happened
    if received_order != sent_order:
        print(f"✅ REORDERING DETECTED: Events were reordered from {received_order} to {sent_order}")
        if sent_order == sorted(received_order):
            print(f"✅ CORRECT ORDERING: Events sent in chronological order")
        else:
            print(f"⚠️  PARTIAL ORDERING: Events reordered but not fully chronological")
    else:
        print(f"❌ NO REORDERING: Events sent in same order as received")
    
    return received_order, sent_order

# Build Docker image if needed
if MODE == "local":
    if subprocess.call(["docker", "image", "inspect", IMG_LOCAL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL):
        print("Building local image (core-dev)…")
        subprocess.run(["docker", "build", "--target", "build", "-t", IMG_LOCAL, "."], check=True, cwd=PROJECT_ROOT)

# Test with WAIT quarantine policy
CMD_WITH_QUARANTINE = [f"/CORE/build/{DIR}/offline", "--query", f"/workspace/{QUERY}", "--declaration", f"/workspace/{DECL}", "--csv", f"/workspace/{CSV}", "--options", f"/workspace/{OPTIONS}"]

if MODE == "remote":
    cmd = ["docker", "compose", "run", "--rm", *ENV_FLAG, *MOUNT_FLAGS, IMG_REMOTE, *CMD_WITH_QUARANTINE]
else:
    cmd = ["docker", "run", "--rm", *ENV_FLAG, *MOUNT_FLAGS, IMG_LOCAL, *CMD_WITH_QUARANTINE]

received, sent = run_test("WAIT Quarantine Policy - Event Reordering Test", cmd)

# Summary
print(f"\n{'='*60}")
print(f"📊 REORDERING ANALYSIS")
print(f"{'='*60}")
print(f"Original CSV order:     [9, 0, 4, 7, 20]")
print(f"Quarantine received:    {received}")
print(f"Quarantine sent:        {sent}")
print(f"Expected chronological: [0, 4, 7, 9, 20]")
print(f"")

if sent == [0, 4, 7, 9, 20]:
    print(f"🎯 PERFECT: Events reordered to perfect chronological order!")
elif sent == sorted(received):
    print(f"✅ GOOD: Events reordered to chronological order")
elif received != sent:
    print(f"⚠️  PARTIAL: Some reordering occurred but not perfect")
else:
    print(f"❌ FAILED: No reordering detected - WAIT policy may not be working")
