#!/usr/bin/env python3
"""
Deep dive into parameter permissions and network settings.
"""

import requests
from requests.auth import HTTPDigestAuth
import time

DEFAULT_IP = "192.168.0.90"
DEFAULT_USER = "root"
DEFAULT_PASS = "pass"

session = requests.Session()
session.auth = HTTPDigestAuth(DEFAULT_USER, DEFAULT_PASS)

print("Investigating parameter permissions...\n")

# Check if there's a 'Network.IPAddress' (without eth0)
print("=" * 70)
print("Test 1: Setting Network.IPAddress (not eth0 specific)...")
print("=" * 70)
try:
    url = f"http://{DEFAULT_IP}/axis-cgi/param.cgi"
    param_string = "action=update&root.Network.BootProto=none&root.Network.IPAddress=192.168.1.101&root.Network.SubnetMask=255.255.255.0"
    response = session.get(url + "?" + param_string, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")

# Check parameter info
print("\n" + "=" * 70)
print("Test 2: Getting parameter information...")
print("=" * 70)
try:
    url = f"http://{DEFAULT_IP}/axis-cgi/param.cgi?action=listdefinitions&group=Network.eth0"
    response = session.get(url, timeout=10)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print(f"Response preview: {response.text[:500]}")
except Exception as e:
    print(f"Error: {e}")

# Try the admin endpoint specifically for network
print("\n" + "=" * 70)
print("Test 3: Using admin path for network config...")
print("=" * 70)
try:
    url = f"http://{DEFAULT_IP}/admin/param.cgi?action=update&root.Network.eth0.IPAddress=192.168.1.101"
    response = session.get(url, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:200]}")
except Exception as e:
    print(f"Error: {e}")

# Check if serverreport gives us any hints
print("\n" + "=" * 70)
print("Test 4: Camera firmware and model info...")
print("=" * 70)
try:
    url = f"http://{DEFAULT_IP}/axis-cgi/serverreport.cgi?listdefinitions=true"
    response = session.get(url, timeout=10)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        # Look for firmware version
        for line in response.text.split('\n')[:30]:
            if 'Version' in line or 'Firmware' in line or 'Product' in line:
                print(f"  {line.strip()}")
except Exception as e:
    print(f"Error: {e}")

# Try checking access control
print("\n" + "=" * 70)
print("Test 5: Checking user privileges...")
print("=" * 70)
try:
    url = f"http://{DEFAULT_IP}/axis-cgi/usergroup.cgi?action=get"
    response = session.get(url, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")

print("\n")
