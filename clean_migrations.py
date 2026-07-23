import glob

for file in glob.glob("migrations/versions/*.py"):
    with open(file) as f:
        lines = f.readlines()
    with open(file, "w") as f:
        for line in lines:
            if 'op.execute("CREATE TYPE' in line:
                continue
            f.write(line)
