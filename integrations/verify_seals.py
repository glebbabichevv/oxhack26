"""Pitch step 2: show that every sealed prediction file is unchanged since we posted its hash.

    python integrations/verify_seals.py

For each capsule/seal-*.json: when it was sealed, how many markets, which model; its SHA-256 recomputed now
(compare with the hash posted in the event Discord, time in capsule/posts.json); and the Bitcoin block that
OpenTimestamps anchored it in (capsule/seal-*.json.ots). Nothing is fetched except the .ots read; nothing is written.
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAPSULE = ROOT / "capsule"
posts = json.loads((CAPSULE / "posts.json").read_text())
ots = Path(sys.executable).with_name("ots")

for seal in sorted(CAPSULE.glob("seal-*.json")):
    d = json.loads(seal.read_text())
    sha = hashlib.sha256(seal.read_bytes()).hexdigest()
    block = "not stamped"
    if seal.with_suffix(".json.ots").exists() and ots.exists():
        info = subprocess.run([str(ots), "info", str(seal) + ".ots"], capture_output=True, text=True).stdout
        b = re.findall(r"BitcoinBlockHeaderAttestation\((\d+)\)", info)
        block = f"Bitcoin block {min(map(int, b))}" if b else "pending in the OpenTimestamps calendars"
    print(f"\n{seal.name}")
    print(f"  sealed    {d['sealed_at']}  ·  {d['n_markets']} markets ({d.get('n_primary', '?')} primary)")
    print(f"  model     {d.get('model_version', 'see backend/results/model.json at ' + d.get('code_commit', '')[:7])}"
          f"  ·  policy {(d.get('policy') or {}).get('name', 'V0 (pre-policy)')}")
    print(f"  posted    {posts.get(seal.name, 'not posted')}  (event Discord)")
    print(f"  SHA-256   {sha}")
    print(f"  anchored  {block}")
print("\nThe SHA-256 above is recomputed from the file right now: if one byte had changed since the Discord post, it would differ.")
