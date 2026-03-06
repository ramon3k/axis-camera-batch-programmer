#!/usr/bin/env python3
"""
Test network parameter changes with different approaches.
"""

import requests
from requests.auth import HTTPDigestAuth

DEFAULT_IP = "192.168.0.90"
DEFAULT_USER = "root"
DEFAULT_PASS = "pass"

session = requests.Session()
session.auth = HTTPDigestAuth(DEFAULT_USER, DEFAULT_PASS)

print("Testing network configuration methods...\n")

# Test 1: Set with root. prefix
print("=" * 70)
print("Test 1: Setting IP with 'root.' prefix...")
print("=" * 70)
try:
    url = f"http://{DEFAULT_IP}/axis-cgi/param.cgi"
    param_string = "action=update&root.Network.eth0.IPAddress=192.168.1.101"
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = session.post(url, data=param_string, headers=headers, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")

# Test 2: Check if we need to disable DHCP first
print("\n" + "=" * 70)
print("Test 2: Disabling DHCP (change to static)...")
print("=" * 70)
try:
    url = f"http://{DEFAULT_IP}/axis-cgi/param.cgi"
    param_string = "action=update&root.Network.BootProto=static"
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = session.post(url, data=param_string, headers=headers, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")

# Test 3: Try using the network configuration API if it exists
print("\n" + "=" * 70)
print("Test 3: Checking for network config API...")
print("=" * 70)
try:
    url = f"http://{DEFAULT_IP}/axis-cgi/network_settings.cgi?action=get"
    response = session.get(url, timeout=10)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print(f"Response: {response.text[:500]}")
except Exception as e:
    print(f"Error: {e}")

# Test 4: Check current BootProto
print("\n" + "=" * 70)
print("Test 4: Current network boot protocol...")
print("=" * 70)
try:
    url = f"http://{DEFAULT_IP}/axis-cgi/param.cgi?action=list&group=Network.BootProto"
    response = session.get(url, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")

# Test 5: Try updating both as a transaction
print("\n" + "=" * 70)
print("Test 5: Setting BootProto and IP together...")
print("=" * 70)
try:
    url = f"http://{DEFAULT_IP}/axis-cgi/param.cgi"
    param_string = "action=update&root.Network.BootProto=static&root.Network.eth0.IPAddress=192.168.1.101&root.Network.eth0.SubnetMask=255.255.255.0"
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = session.post(url, data=param_string, headers=headers, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")

print("\n")
