#!/usr/bin/env python3
"""Tiny chrome-bridge client: enqueue a command on a tab and print the result."""
import json
import sys
import urllib.request

DAEMON = "http://127.0.0.1:8224"

def main():
    tab_id = sys.argv[1]
    cmd_type = sys.argv[2]
    payload = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}

    body = json.dumps({"tab_id": int(tab_id), "cmd_type": cmd_type, "payload": payload}).encode()
    req = urllib.request.Request(f"{DAEMON}/enqueue", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        enq = json.load(resp)
    cmd_id = enq["cmd_id"]

    url = f"{DAEMON}/await_result?tab_id={enq['tab_id']}&cmd_id={cmd_id}&timeout_ms=30000"
    with urllib.request.urlopen(url, timeout=40) as resp:
        result = json.load(resp)
    if "error" in result:
        print("RESULT ERROR:", result["error"], file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    main()
