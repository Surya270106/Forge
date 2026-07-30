import subprocess

commands = [
    r".\.venv_official\Scripts\ruff.exe format --check .",
    r".\.venv_official\Scripts\ruff.exe check .",
    r".\.venv_official\Scripts\pyright.exe",
    r".\.venv_official\Scripts\pytest.exe tests/unit -v",
    r".\.venv_official\Scripts\pytest.exe tests/integration -v",
    r".\.venv_official\Scripts\pytest.exe tests/security -v",
    r".\.venv_official\Scripts\pytest.exe tests/e2e -v",
    r".\.venv_official\Scripts\pytest.exe tests -v",
]

import os

env = os.environ.copy()
env["PYTHONPATH"] = "."

for cmd in commands:
    print(f"Running: {cmd}")
    res = subprocess.run(cmd, shell=True, env=env)
    print(f"Exit code: {res.returncode}")
    print("-" * 40)
