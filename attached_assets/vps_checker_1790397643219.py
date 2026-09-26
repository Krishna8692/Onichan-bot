#!/usr/bin/env python3
"""
VPS Checker
===========
Reads a list of VPS servers from vps_list.txt and checks which ones are
live, dead, or reachable-but-not-logging-in. For every LIVE server it also
pulls basic specs (OS, CPU, RAM, disk, uptime) over SSH.

INPUT FILE (vps_list.txt), one server per line:
    IP:PORT:USERNAME:PASSWORD
    IP:USERNAME:PASSWORD              (port defaults to 22 if omitted)

Lines starting with # or blank lines are ignored.

HOW IT WORKS
------------
1. Parse every line into (ip, port, user, password).
2. For each entry, in parallel (thread pool):
     a. TCP connect to ip:port with a short timeout -> LIVE or DEAD.
     b. If LIVE, try an SSH login with the given credentials.
        - Success -> run a handful of read-only commands to fetch specs.
        - Bad credentials -> AUTH_FAILED.
        - Other SSH error (e.g. banner/protocol issue) -> LIVE_SSH_ERROR.
3. Print a live progress line and a final summary table to the console.
4. Write two output files:
     - all_results.csv           -> every entry, every status, all columns
     - live_vps_full_details.txt -> only LIVE+authenticated servers, full
                                    detail block per server (incl. password)

USAGE
-----
    pip install paramiko --break-system-packages
    python3 vps_checker.py
    python3 vps_checker.py --file my_list.txt --workers 20

SECURITY NOTE
-------------
live_vps_full_details.txt contains plaintext passwords for every server
that responded. Don't commit it, don't share it, delete it once you're
done with it.
"""

import argparse
import csv
import socket
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import paramiko
except ImportError:
    print("Missing dependency. Run: pip install paramiko --break-system-packages")
    sys.exit(1)

DEFAULT_PORT = 22
TCP_TIMEOUT = 5     # seconds — reachability check
SSH_TIMEOUT = 8     # seconds — login + command timeout


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_line(line, line_no):
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    parts = line.split(":")
    try:
        if len(parts) == 4:
            ip, port, user, pwd = parts
            port = int(port)
        elif len(parts) == 3:
            ip, user, pwd = parts
            port = DEFAULT_PORT
        else:
            raise ValueError(f"expected 3 or 4 colon-separated fields, got {len(parts)}")
        return {"line_no": line_no, "ip": ip.strip(), "port": port,
                "user": user.strip(), "pwd": pwd.strip(), "error": None}
    except Exception as e:
        return {"line_no": line_no, "raw": line, "error": str(e)}


def load_entries(path):
    entries, bad = [], []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for i, line in enumerate(f, start=1):
            parsed = parse_line(line, i)
            if parsed is None:
                continue
            (bad if parsed["error"] else entries).append(parsed)
    return entries, bad


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def tcp_check(ip, port):
    try:
        with socket.create_connection((ip, port), timeout=TCP_TIMEOUT):
            return True
    except Exception:
        return False


def ssh_pull_specs(ip, port, user, pwd):
    """Returns (ok: bool, specs_dict | error_code: str)."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=ip, port=port, username=user, password=pwd,
            timeout=SSH_TIMEOUT, banner_timeout=SSH_TIMEOUT, auth_timeout=SSH_TIMEOUT,
            look_for_keys=False, allow_agent=False,
        )

        def run(cmd):
            try:
                _, stdout, _ = client.exec_command(cmd, timeout=SSH_TIMEOUT)
                return stdout.read().decode(errors="ignore").strip()
            except Exception:
                return ""

        specs = {
            "os": run("cat /etc/os-release 2>/dev/null | grep PRETTY_NAME") or run("uname -a"),
            "cpu": run("nproc"),
            "ram": run("free -m | awk '/Mem:/ {print $3\"MB used / \"$2\"MB total\"}'"),
            "disk": run("df -h / | awk 'NR==2 {print $3\" used / \"$2\" total (\"$5\")\"}'"),
            "uptime": run("uptime -p"),
        }
        return True, specs

    except paramiko.AuthenticationException:
        return False, "AUTH_FAILED"
    except Exception as e:
        return False, str(e)
    finally:
        client.close()


def check_entry(entry):
    ip, port, user, pwd = entry["ip"], entry["port"], entry["user"], entry["pwd"]
    result = {**entry, "status": "DEAD", "os": "", "cpu": "", "ram": "", "disk": "", "uptime": ""}

    if not tcp_check(ip, port):
        return result

    ok, data = ssh_pull_specs(ip, port, user, pwd)
    if not ok:
        result["status"] = "AUTH_FAILED" if data == "AUTH_FAILED" else "LIVE_SSH_ERROR"
        if data != "AUTH_FAILED":
            result["os"] = data  # stash the error message for visibility
        return result

    result["status"] = "LIVE"
    result.update(data)
    return result


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_csv(results, bad_lines, path="all_results.csv"):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Line", "IP", "Port", "Status", "OS", "CPU", "RAM", "Disk", "Uptime"])
        for r in results:
            writer.writerow([r["line_no"], r["ip"], r["port"], r["status"],
                              r.get("os", ""), r.get("cpu", ""), r.get("ram", ""),
                              r.get("disk", ""), r.get("uptime", "")])
        for b in bad_lines:
            writer.writerow([b["line_no"], "PARSE_ERROR", "", b["error"], "", "", "", "", ""])


def write_live_details(results, path="live_vps_full_details.txt"):
    live = [r for r in results if r["status"] == "LIVE"]
    blocks = []
    for r in live:
        blocks.append(
            f"IP: {r['ip']}\n"
            f"Port: {r['port']}\n"
            f"Username: {r['user']}\n"
            f"Password: {r['pwd']}\n"
            f"OS: {r.get('os','')}\n"
            f"CPU cores: {r.get('cpu','')}\n"
            f"RAM: {r.get('ram','')}\n"
            f"Disk: {r.get('disk','')}\n"
            f"Uptime: {r.get('uptime','')}\n"
            + "-" * 40
        )
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(blocks) if blocks else "No live + authenticated VPS found.")
    return len(live)


def print_summary(results, bad_lines):
    live = [r for r in results if r["status"] == "LIVE"]
    dead = [r for r in results if r["status"] == "DEAD"]
    auth_failed = [r for r in results if r["status"] == "AUTH_FAILED"]
    ssh_errors = [r for r in results if r["status"] == "LIVE_SSH_ERROR"]

    print("\n" + "=" * 60)
    print(f"{'IP':<16}{'Port':<7}{'Status':<15}{'OS':<25}")
    print("-" * 60)
    for r in sorted(results, key=lambda x: x["line_no"]):
        os_short = (r.get("os", "") or "")[:24]
        print(f"{r['ip']:<16}{r['port']:<7}{r['status']:<15}{os_short:<25}")
    print("=" * 60)
    print(f"Total checked : {len(results)}")
    print(f"Live          : {len(live)}")
    print(f"Dead          : {len(dead)}")
    print(f"Auth failed   : {len(auth_failed)}")
    print(f"SSH errors    : {len(ssh_errors)}")
    print(f"Bad lines     : {len(bad_lines)}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Check a list of VPS servers for liveness + specs.")
    parser.add_argument("--file", default="vps_list.txt", help="Path to the VPS list file")
    parser.add_argument("--workers", type=int, default=15, help="Number of concurrent checks")
    args = parser.parse_args()

    try:
        entries, bad_lines = load_entries(args.file)
    except FileNotFoundError:
        print(f"File not found: {args.file}")
        sys.exit(1)

    if not entries:
        print("No valid entries found in the file.")
        sys.exit(1)

    print(f"Loaded {len(entries)} entries ({len(bad_lines)} bad lines skipped). Checking...")

    results = []
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(check_entry, e): e for e in entries}
        for fut in as_completed(futures):
            results.append(fut.result())
            done += 1
            print(f"\rChecked {done}/{len(entries)}", end="", flush=True)
    print()  # newline after progress

    print_summary(results, bad_lines)
    write_csv(results, bad_lines)
    live_count = write_live_details(results)

    print(f"\nWrote all_results.csv ({len(results)} rows)")
    print(f"Wrote live_vps_full_details.txt ({live_count} live servers, includes passwords — handle with care)")


if __name__ == "__main__":
    main()
