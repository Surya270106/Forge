import subprocess

python_bin = r".\.venv_official\Scripts\python.exe"
print("Starting Worker as detached process...")
subprocess.Popen([python_bin, "-m", "services.worker.main"], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
print("Done starting Worker.")
