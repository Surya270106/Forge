import subprocess

uvicorn_bin = r".\.venv_official\Scripts\uvicorn.exe"
print("Starting Uvicorn API Server as detached process...")
subprocess.Popen(
    [uvicorn_bin, "apps.api.main:app", "--port", "8000"],
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
)
print("Done starting API.")
