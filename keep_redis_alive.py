import os
import subprocess

redis_server = os.path.expandvars(r"$USERPROFILE\scoop\apps\redis\current\redis-server.exe")

print("Starting Redis...")
subprocess.run([redis_server])
print("Redis exited.")
