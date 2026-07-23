import json
import urllib.request
import zipfile

try:
    req = urllib.request.Request("https://api.github.com/repos/Surya270106/Forge/actions/runs?per_page=1")
    req.add_header("User-Agent", "Mozilla/5.0")
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        run_id = data["workflow_runs"][0]["id"]
        print(f"Latest Run ID: {run_id}")

    print("Fetching logs url...")
    req = urllib.request.Request(f"https://api.github.com/repos/Surya270106/Forge/actions/runs/{run_id}/logs")
    req.add_header("User-Agent", "Mozilla/5.0")
    try:
        with urllib.request.urlopen(req) as response:
            with open("logs.zip", "wb") as f:
                f.write(response.read())
            print("Downloaded logs.zip")
            
        with zipfile.ZipFile("logs.zip", "r") as z:
            for name in z.namelist():
                if "Capture Logs" in name or "Start Containerized Stack" in name:
                    print(f"\\n--- LOG FOR {name} ---")
                    print(z.read(name).decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code}")
except Exception as e:
    print("Error:", e)
