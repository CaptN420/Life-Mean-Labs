"""
Network Connectivity Diagnostic for Python
Run: python check_network.py
"""
import sys
import socket
import ssl
import urllib.request
import urllib.error

print("=" * 60)
print("Python Network Diagnostic")
print("=" * 60)
print(f"Python version : {sys.version}")
print(f"Executable     : {sys.executable}")
print()

# --- 1. DNS Resolution ---
print("--- DNS Resolution ---")
for host in ["example.com", "google.com", "8.8.8.8"]:
    try:
        ip = socket.gethostbyname(host)
        print(f"  {host}  ->  {ip}   OK")
    except Exception as e:
        print(f"  {host}  ->  FAILED: {e}")

# --- 2. TCP Connectivity (Port Tests) ---
print()
print("--- TCP Port Tests ---")
tests = [
    ("example.com", 80,  "HTTP"),
    ("example.com", 443, "HTTPS"),
    ("8.8.8.8",     53,  "DNS (UDP-style TCP)"),
    ("1.1.1.1",     53,  "Cloudflare DNS"),
]
for host, port, label in tests:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, port))
        if result == 0:
            print(f"  {label:20s}  {host}:{port}  ->  OPEN")
        else:
            print(f"  {label:20s}  {host}:{port}  ->  CLOSED (errno={result})")
        sock.close()
    except Exception as e:
        print(f"  {label:20s}  {host}:{port}  ->  ERROR: {e}")

# --- 3. HTTP Request Test ---
print()
print("--- HTTP Request Test ---")
for url in ["http://example.com", "https://example.com"]:
    try:
        req = urllib.request.urlopen(url, timeout=10)
        print(f"  {url}  ->  OK (status={req.status})")
    except urllib.error.HTTPError as e:
        print(f"  {url}  ->  HTTP Error {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        print(f"  {url}  ->  URL Error: {e.reason}")
    except Exception as e:
        print(f"  {url}  ->  ERROR: {e}")

# --- 4. SSL/TLS Test ---
print()
print("--- SSL/TLS Test ---")
try:
    context = ssl.create_default_context()
    with socket.create_connection(("google.com", 443), timeout=5) as sock:
        with context.wrap_socket(sock, server_hostname="google.com") as ssock:
            print(f"  TLS connected to google.com:443  ->  OK")
            print(f"  Protocol : {ssock.version()}")
            print(f"  Cipher   : {ssock.cipher()}")
except Exception as e:
    print(f"  SSL/TLS test FAILED: {e}")

# --- 5. Proxy Environment Check ---
print()
print("--- Proxy / Environment Variables ---")
import os
for var in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "NO_PROXY"]:
    val = os.environ.get(var)
    if val:
        print(f"  {var} = {val}")
    else:
        print(f"  {var} = (not set)")

print()
print("=" * 60)
print("Diagnostic complete.")
print("=" * 60)
