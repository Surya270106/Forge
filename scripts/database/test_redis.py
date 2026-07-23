import os
import subprocess

redis_server = os.path.expandvars(r"$USERPROFILE\scoop\apps\redis\current\redis-server.exe")

try:
    res = subprocess.run([redis_server], capture_output=True, timeout=5)
    print("Stdout:", res.stdout.decode())
    print("Stderr:", res.stderr.decode())
except subprocess.TimeoutExpired:
    print("Timeout (so it is running)")
