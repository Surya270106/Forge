import os
import subprocess
import time

postgres_bin = os.path.expandvars(r"$USERPROFILE\scoop\apps\postgresql\current\bin")
postgres = os.path.join(postgres_bin, "postgres.exe")
data_dir = os.path.expandvars(r"$USERPROFILE\scoop\persist\postgresql\data")

print("Starting Postgres directly...")
proc = subprocess.Popen([postgres, "-D", data_dir])

print(f"Postgres started with PID {proc.pid}")
try:
    while True:
        if proc.poll() is not None:
            print(f"Postgres exited with code {proc.returncode}")
            break
        time.sleep(1)
except KeyboardInterrupt:
    print("Stopping...")
    proc.terminate()
