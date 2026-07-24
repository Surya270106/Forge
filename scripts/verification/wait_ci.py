import json
import urllib.request
import zipfile

req = urllib.request.Request("https://api.github.com/repos/Surya270106/Forge/actions/runs?per_page=10")
req.add_header("User-Agent", "Mozilla/5.0")
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode())
    for run in data["workflow_runs"]:
        if run["name"] == "Docker-Isolated Alpha Verification" and run["conclusion"] == "failure":
            run_id = run["id"]
            break

print(f"Tracking Run ID: {run_id}")

req = urllib.request.Request(f"https://api.github.com/repos/Surya270106/Forge/actions/runs/{run_id}/jobs")
req.add_header("User-Agent", "Mozilla/5.0")
failed_step = None
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read().decode())
    for job in data["jobs"]:
        for step in job["steps"]:
            if step["conclusion"] == "failure":
                print(f"Failed Job: {job['name']}, Step: {step['name']}")
                failed_step = step["name"]

if failed_step:
    req = urllib.request.Request(f"https://api.github.com/repos/Surya270106/Forge/actions/runs/{run_id}/logs")
    req.add_header("User-Agent", "Mozilla/5.0")
    try:
        with urllib.request.urlopen(req) as response, open("logs.zip", "wb") as f:
            f.write(response.read())
        with zipfile.ZipFile("logs.zip", "r") as z:
            for name in z.namelist():
                if failed_step in name:
                    print(f"\\n--- LOG FOR {name} ---")
                    print(z.read(name).decode("utf-8")[-10000:])
    except Exception as e:
        print(f"Error downloading logs: {e}")
