import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request


def print_header(title):
    print(f"\n{'=' * 80}\n{title}\n{'=' * 80}")


def run_cmd(cmd, cwd=None, env=None, capture=False):
    print(f"Running: {' '.join(cmd)}")
    start = time.time()
    res = subprocess.run(cmd, cwd=cwd, env=env, capture_output=capture, text=capture)
    duration = time.time() - start
    print(f"Finished in {duration:.2f}s with exit code {res.returncode}")
    return res


def wait_for_port(port, timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/ready")
            with urllib.request.urlopen(req) as response:
                if response.status == 200:
                    return True
        except urllib.error.URLError:
            pass
        time.sleep(1)
    return False


def main():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    # Python tools
    if shutil.which("uv"):
        uv_cmd = "uv"
    else:
        # Fallback if uv is not in PATH
        uv_cmd = os.path.expandvars(r"$USERPROFILE\.cargo\bin\uv.exe")

    python_bin = os.path.join(root_dir, ".venv", "Scripts", "python.exe")
    alembic_bin = os.path.join(root_dir, ".venv", "Scripts", "alembic.exe")
    pytest_bin = os.path.join(root_dir, ".venv", "Scripts", "pytest.exe")
    ruff_bin = os.path.join(root_dir, ".venv", "Scripts", "ruff.exe")
    pyright_bin = os.path.join(root_dir, ".venv", "Scripts", "pyright.exe")
    uvicorn_bin = os.path.join(root_dir, ".venv", "Scripts", "uvicorn.exe")

    # Services
    postgres_bin = os.path.expandvars(r"$USERPROFILE\scoop\apps\postgresql\current\bin")
    pg_ctl = os.path.join(postgres_bin, "pg_ctl.exe")
    data_dir = os.path.expandvars(r"$USERPROFILE\scoop\persist\postgresql\data")
    redis_bin = os.path.expandvars(r"$USERPROFILE\scoop\apps\redis\current\redis-server.exe")
    redis_conf = os.path.expandvars(r"$USERPROFILE\scoop\apps\redis\current\redis.conf")

    print_header("1. CLEAN CHECKOUT & REPRODUCIBILITY")
    # Python dependencies
    res = run_cmd([uv_cmd, "sync", "--all-extras"], cwd=root_dir)
    if res.returncode != 0:
        print("Dependency sync failed. Aborting.")
        sys.exit(1)

    frontend_dir = os.path.join(root_dir, "apps", "frontend")
    res = run_cmd(["npm.cmd", "ci"], cwd=frontend_dir)
    if res.returncode != 0:
        print("npm ci failed. Aborting.")
        sys.exit(1)

    print_header("2. INFRASTRUCTURE & MIGRATIONS")
    print("Starting Redis...")
    redis_proc = subprocess.Popen([redis_bin], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("Starting Postgres...")
    subprocess.run([pg_ctl, "start", "-D", data_dir])

    env = os.environ.copy()
    env["ENVIRONMENT"] = "test"
    env["DATABASE_URL"] = "postgresql+asyncpg://forge:forge@localhost:5432/forge_test"
    env["PYTHONPATH"] = root_dir

    print("Resetting test database...")
    res = run_cmd([python_bin, "reset_db.py", "--confirm"], cwd=root_dir, env=env)
    if res.returncode != 0:
        print("Database reset failed. Aborting.")
        sys.exit(1)

    print_header("3. BACKEND QUALITY MATRIX")
    try:
        checks = [
            [uv_cmd, "run", "ruff", "format", "--check", "."],
            [uv_cmd, "run", "ruff", "check", "."],
            [uv_cmd, "run", "pytest", "--ignore=tests/e2e", "-v"],
        ]
        for cmd in checks:
            if run_cmd(cmd, cwd=root_dir, env=env).returncode != 0:
                print("Backend checks failed. Aborting.")
                sys.exit(1)

        print_header("4. FRONTEND QUALITY MATRIX")
        checks = [
            ["npm.cmd", "run", "lint"],
            ["npm.cmd", "run", "typecheck", "--if-present"],
            ["npm.cmd", "test", "--if-present"],
            ["npm.cmd", "run", "build"],
        ]
        for cmd in checks:
            if run_cmd(cmd, cwd=frontend_dir).returncode != 0:
                print("Frontend checks failed. Aborting.")
                sys.exit(1)

        print_header("5. STARTING SERVICES")
        api_proc = subprocess.Popen([uvicorn_bin, "apps.api.main:app", "--port", "8000"], env=env, cwd=root_dir)
        worker_proc = subprocess.Popen([python_bin, "-m", "services.worker.main"], env=env, cwd=root_dir)

        if not wait_for_port(8000):
            print("API failed to start. Aborting.")
            sys.exit(1)

        print_header("6. END-TO-END VERIFICATION")
        run_cmd([uv_cmd, "run", "pytest", "tests/e2e", "-v"], cwd=root_dir, env=env)
        pw_res = run_cmd(["npx.cmd", "playwright", "test"], cwd=frontend_dir, env=env)

        if pw_res.returncode == 0:
            print("\nSUCCESS! Full Internal Alpha verified from a clean checkout.")
            sys.exit(0)
        else:
            print("\nFAILURE! Playwright E2E failed.")
            sys.exit(1)

    finally:
        print_header("7. TEARDOWN")
        if "api_proc" in locals():
            api_proc.terminate()
        if "worker_proc" in locals():
            worker_proc.terminate()
        if "redis_proc" in locals():
            redis_proc.terminate()
        subprocess.run([pg_ctl, "stop", "-D", data_dir])


if __name__ == "__main__":
    main()
