#!/usr/bin/env python3
"""
Test P3267 API endpoints to find the correct initial setup method
"""
import requests
from requests.auth import HTTPDigestAuth

# Camera details
IP = "192.168.1.168"
USERNAME = "root"
PASSWORD = "admin"

# Create session with auth
session = requests.Session()
session.auth = HTTPDigestAuth(USERNAME, PASSWORD)
session.trust_env = False
session.proxies = {'http': None, 'https': None}

print(f"Testing P3267 camera at {IP} with credentials {USERNAME}/{PASSWORD}")
print("=" * 80)

# Test 1: Check current user info
print("\n[TEST 1] Getting current user info...")
try:
    url = f"http://{IP}/axis-cgi/pwdgrp.cgi?action=get"
    response = session.get(url, timeout=10)
    print(f"  Status: {response.status_code}")
    print(f"  Response: {response.text[:500]}")
except Exception as e:
    print(f"  Error: {e}")

# Test 2: List all users
print("\n[TEST 2] Listing all users...")
try:
    url = f"http://{IP}/axis-cgi/pwdgrp.cgi?action=list"
    response = session.get(url, timeout=10)
    print(f"  Status: {response.status_code}")
    print(f"  Response: {response.text[:500]}")
except Exception as e:
    print(f"  Error: {e}")

# Test 3: Try adding a test user
print("\n[TEST 3] Trying to add test user 'testuser'...")
try:
    url = f"http://{IP}/axis-cgi/pwdgrp.cgi?action=add&user=testuser&pwd=testpass123&grp=users&sgrp=viewer"
    response = session.get(url, timeout=10)
    print(f"  Status: {response.status_code}")
    print(f"  Response: {response.text[:500]}")
except Exception as e:
    print(f"  Error: {e}")

# Test 4: Check if testuser was created
print("\n[TEST 4] Checking if testuser exists...")
try:
    url = f"http://{IP}/axis-cgi/pwdgrp.cgi?action=get&user=testuser"
    response = session.get(url, timeout=10)
    print(f"  Status: {response.status_code}")
    print(f"  Response: {response.text[:500]}")
except Exception as e:
    print(f"  Error: {e}")

# Test 5: Try to remove testuser
print("\n[TEST 5] Removing testuser...")
try:
    url = f"http://{IP}/axis-cgi/pwdgrp.cgi?action=remove&user=testuser"
    response = session.get(url, timeout=10)
    print(f"  Status: {response.status_code}")
    print(f"  Response: {response.text[:500]}")
except Exception as e:
    print(f"  Error: {e}")

# Test 6: Check camera parameters to understand its state
print("\n[TEST 6] Getting camera info...")
try:
    url = f"http://{IP}/axis-cgi/param.cgi?action=list&group=root.Brand"
    response = session.get(url, timeout=10)
    print(f"  Status: {response.status_code}")
    for line in response.text.split('\n'):
        if any(x in line for x in ['ProdFullName', 'ProdNbr', 'Version']):
            print(f"  {line.strip()}")
except Exception as e:
    print(f"  Error: {e}")

# Test 7: Check if there's a setup/initialization API
print("\n[TEST 7] Checking for initialization endpoints...")
test_urls = [
    "/axis-cgi/admin/initialconfig.cgi",
    "/axis-cgi/admin/setup.cgi",
    "/axis-cgi/setup.cgi",
    "/api/setup",
    "/camera/api/setup",
]
for endpoint in test_urls:
    try:
        url = f"http://{IP}{endpoint}"
        response = session.get(url, timeout=5)
        print(f"  {endpoint}: Status {response.status_code}")
        if response.status_code != 404:
            print(f"    Response: {response.text[:200]}")
    except Exception as e:
        print(f"  {endpoint}: Error - {e}")

print("\n" + "=" * 80)
print("Testing complete!")
