#!/usr/bin/env python3
"""
Test different methods to configure Axis camera network settings.
"""

import requests
from requests.auth import HTTPDigestAuth

DEFAULT_IP = "192.168.0.90"
DEFAULT_USER = "root"
DEFAULT_PASS = "pass"
TEST_IP = "192.168.1.101"

session = requests.Session()
session.auth = HTTPDigestAuth(DEFAULT_USER, DEFAULT_PASS)

print("Testing different parameter configuration methods...\n")

# First, check what parameters are available
print("=" * 70)
print("1. Checking current network parameters...")
print("=" * 70)
try:
    url = f"http://{DEFAULT_IP}/axis-cgi/param.cgi?action=list&group=Network"
    response = session.get(url, timeout=10)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        lines = [l for l in response.text.split('\n') if 'IPAddress' in l or 'BootProto' in l or 'SubnetMask' in l]
        for line in lines[:20]:  # Show first 20 matches
            print(f"  {line}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 70)
print("2. Testing POST with form data dict...")
print("=" * 70)
try:
    url = f"http://{DEFAULT_IP}/axis-cgi/param.cgi"
    params = {
        'action': 'update',
        'Network.eth0.IPAddress': TEST_IP,
    }
    response = session.post(url, data=params, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:200]}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 70)
print("3. Testing POST with URL-encoded string...")
print("=" * 70)
try:
    url = f"http://{DEFAULT_IP}/axis-cgi/param.cgi"
    param_string = f"action=update&Network.eth0.IPAddress={TEST_IP}"
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = session.post(url, data=param_string, headers=headers, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:200]}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 70)
print("4. Testing with multiple parameters...")
print("=" * 70)
try:
    url = f"http://{DEFAULT_IP}/axis-cgi/param.cgi"
    param_string = f"action=update&Network.eth0.IPAddress={TEST_IP}&Network.eth0.BootProto=none"
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = session.post(url, data=param_string, headers=headers, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:200]}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 70)
print("5. Testing simple parameter update (non-network)...")
print("=" * 70)
try:
    url = f"http://{DEFAULT_IP}/axis-cgi/param.cgi"
    param_string = "action=update&System.HostName=TestCamera"
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = session.post(url, data=param_string, headers=headers, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:200]}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 70)
print("6. Checking authentication info...")
print("=" * 70)
try:
    url = f"http://{DEFAULT_IP}/axis-cgi/usergroup.cgi?action=get"
    response = session.get(url, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:300]}")
except Exception as e:
    print(f"Error: {e}")

print("\n")
