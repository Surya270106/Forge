import os
import subprocess
import time

pg_ctl = os.path.expandvars(r"$USERPROFILE\scoop\apps\postgresql\current\bin\pg_ctl.exe")
data_dir = os.path.expandvars(r"$USERPROFILE\scoop\persist\postgresql\data")

print("Starting Postgres...")
subprocess.run([pg_ctl, "start", "-D", data_dir])
print("Keeping alive...")

try:
    while True:
        time.sleep(10)
except KeyboardInterrupt:
    print("Stopping Postgres...")
    subprocess.run([pg_ctl, "stop", "-D", data_dir])
