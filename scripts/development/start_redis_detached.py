import os
import subprocess

redis_server = os.path.expandvars(r"$USERPROFILE\scoop\apps\redis\current\redis-server.exe")

print("Starting Redis as detached process...")
DETACHED_PROCESS = 0x00000008
subprocess.Popen([redis_server], creationflags=DETACHED_PROCESS)
print("Done starting Redis.")
