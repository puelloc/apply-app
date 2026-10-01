#!/usr/bin/env python3
"""N5: the browser (on the internal browser_net) can't bypass the egress proxy.

Checks: (1) UDP to a public IP is blocked (WebRTC/STUN uses UDP to leak the real IP), (2) direct TCP
to a public site fails, (3) traffic via the egress proxy works. Run inside a browser_net container
(via scripts/n5-test.sh).
"""
import os
import socket
import urllib.request

PROXY = os.environ.get("EGRESS_PROXY", "http://apply-egress-proxy:3128")
PASS = 0
FAIL = 0


def check(name, ok, detail):
    global PASS, FAIL
    print(f"{'PASS' if ok else 'FAIL'}: {name} ({detail})")
    PASS += ok
    FAIL += 0 if ok else 1


def udp_reachable(host, port, timeout=3):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(b"\x00" * 20, (host, port))
        s.recvfrom(1024)
        return True, "got a UDP response"
    except socket.timeout:
        return False, "no response (timeout)"
    except OSError as e:
        return False, f"send failed (errno {e.errno})"


def http_status(url, proxy=None, timeout=10):
    handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy}) if proxy else urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(handler)
    try:
        return opener.open(url, timeout=timeout).status, ""
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


print("=== N5: no proxy bypass (TCP) + no UDP (WebRTC) ===")
reachable, detail = udp_reachable("8.8.8.8", 53)
check("UDP 8.8.8.8:53 blocked (WebRTC can't leak)", not reachable, detail)

status, err = http_status("https://example.com")
check("direct https://example.com blocked", status is None, err or "unexpectedly reached")

status, err = http_status("https://example.com", proxy=PROXY)
check("via proxy https://example.com works", status == 200, f"status={status} err={err}")

print(f"\nN5 SUMMARY: pass={PASS} fail={FAIL}")
raise SystemExit(0 if FAIL == 0 else 1)
