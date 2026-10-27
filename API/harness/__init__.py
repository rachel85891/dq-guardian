def say(file, msg):
    """Every runtime action is printed with the harness file that performed it."""
    print(f"[{file}] {msg}", flush=True)
