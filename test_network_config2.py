#!/usr/bin/env python3
"""
Test minimal network configuration changes.
"""

import requests
from requests.auth import HTTPDigestAuth

DEFAULT_IP = "192.168.0.90"
DEFAULT_USER = "root"
DEFAULT_PASS = "pass"

session = requests.Session()
session.auth = HTTPDigestAuth(DEFAULT_USER, DEFAULT_PASS)

print("Testing minimal network configuration...\n")

# Test 1: Try setting IP without changing BootProto
print("=" * 70)
print("Test 1: Setting ONLY IP (no BootProto change)...")
print("=" * 70)
try:
    url = f"http://{DEFAULT_IP}/axis-cgi/param.cgi"
    param_string = "action=update&root.Network.eth0.IPAddress=192.168.1.101&root.Network.eth0.SubnetMask=255.255.255.0"
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = session.post(url, data=param_string, headers=headers, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")

# Test 2: Without root prefix
print("\n" + "=" * 70)
print("Test 2: Setting IP WITHOUT 'root.' prefix...")
print("=" * 70)
try:
    url = f"http://{DEFAULT_IP}/axis-cgi/param.cgi"
    param_string = "action=update&Network.eth0.IPAddress=192.168.1.101&Network.eth0.SubnetMask=255.255.255.0"
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = session.post(url, data=param_string, headers=headers, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")

# Test 3: Check what capabilities we have
print("\n" + "=" * 70)
print("Test 3: Checking API capabilities...")
print("=" * 70)
try:
    url = f"http://{DEFAULT_IP}/axis-cgi/admin/param.cgi?action=list&group=Network.eth0"
    response = session.get(url, timeout=10)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print(f"Response: {response.text[:500]}")
except Exception as e:
    print(f"Error: {e}")

# Test 4: Try the admin endpoint for posting
print("\n" + "=" * 70)
print("Test 4: POST to admin/param.cgi...")
print("=" * 70)
try:
    url = f"http://{DEFAULT_IP}/axis-cgi/admin/param.cgi"
    param_string = "action=update&root.Network.eth0.IPAddress=192.168.1.101"
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = session.post(url, data=param_string, headers=headers, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")

print("\n")
