import os
import subprocess
import time

# Start Postgres
postgres_bin = os.path.expandvars(r"$USERPROFILE\scoop\apps\postgresql\current\bin")
pg_ctl = os.path.join(postgres_bin, "pg_ctl.exe")
pg_isready = os.path.join(postgres_bin, "pg_isready.exe")
data_dir = os.path.expandvars(r"$USERPROFILE\scoop\persist\postgresql\data")

print("Starting Postgres...")
subprocess.run([pg_ctl, "start", "-D", data_dir], check=False)

print("Waiting for Postgres...")
while True:
    res = subprocess.run([pg_isready, "-q"])
    if res.returncode == 0:
        break
    time.sleep(1)

print("Postgres is ready. Upgrading...")
alembic = r".\.venv_official\Scripts\alembic.exe"
subprocess.run([alembic, "upgrade", "head"], check=True)
print("Done!")
