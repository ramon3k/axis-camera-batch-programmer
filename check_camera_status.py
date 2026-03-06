#!/usr/bin/env python3
"""
Check current camera configuration at 192.168.1.101
"""

import requests
from requests.auth import HTTPDigestAuth

NEW_IP = "192.168.1.101"

print("Checking camera configuration at 192.168.1.101...\n")

# Test with old credentials (root/pass)
print("=" * 70)
print("Test 1: Connecting with root/pass...")
print("=" * 70)
session1 = requests.Session()
session1.auth = HTTPDigestAuth('root', 'pass')
try:
    url = f"http://{NEW_IP}/axis-cgi/param.cgi?action=list&group=Network"
    response = session1.get(url, timeout=5)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print("SUCCESS - root/pass still works")
        for line in response.text.split('\n'):
            if 'IPAddress' in line or 'BootProto' in line:
                print(f"  {line}")
    else:
        print("FAILED - root/pass doesn't work")
except Exception as e:
    print(f"Error: {e}")

# Test with new credentials (admin/SecurePass123)
print("\n" + "=" * 70)
print("Test 2: Connecting with admin/SecurePass123...")
print("=" * 70)
session2 = requests.Session()
session2.auth = HTTPDigestAuth('admin', 'SecurePass123')
try:
    url = f"http://{NEW_IP}/axis-cgi/param.cgi?action=list&group=Network"
    response = session2.get(url, timeout=5)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print("SUCCESS - admin/SecurePass123 works!")
    else:
        print("FAILED - admin user not configured")
except Exception as e:
    print(f"Error: {e}")

# Check camera name
print("\n" + "=" * 70)
print("Test 3: Checking camera name...")
print("=" * 70)
try:
    url = f"http://{NEW_IP}/axis-cgi/param.cgi?action=list&group=System"
    response = session1.get(url, timeout=5)
    if response.status_code == 200:
        for line in response.text.split('\n'):
            if 'HostName' in line:
                print(f"  {line}")
except Exception as e:
    print(f"Error: {e}")

# Check users
print("\n" + "=" * 70)
print("Test 4: Checking configured users...")
print("=" * 70)
try:
    url = f"http://{NEW_IP}/axis-cgi/usergroup.cgi?action=get"
    response = session1.get(url, timeout=5)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print(f"Users: {response.text}")
except Exception as e:
    print(f"Error: {e}")

print("\n")
