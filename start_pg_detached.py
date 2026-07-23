import os
import subprocess
import time

postgres_bin = os.path.expandvars(r"$USERPROFILE\scoop\apps\postgresql\current\bin")
pg_ctl = os.path.join(postgres_bin, "pg_ctl.exe")
data_dir = os.path.expandvars(r"$USERPROFILE\scoop\persist\postgresql\data")

DETACHED_PROCESS = 0x00000008

print("Starting Postgres as detached process...")
subprocess.Popen([pg_ctl, "start", "-D", data_dir], creationflags=DETACHED_PROCESS)
time.sleep(3)
print("Done starting Postgres.")
