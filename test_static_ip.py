#!/usr/bin/env python3
"""
Test network configuration with different API approaches.
"""

import requests
from requests.auth import HTTPDigestAuth, HTTPBasicAuth
import time

DEFAULT_IP = "192.168.0.90"
DEFAULT_USER = "root"
DEFAULT_PASS = "pass"

# Try both Basic and Digest auth
digest_session = requests.Session()
digest_session.auth = HTTPDigestAuth(DEFAULT_USER, DEFAULT_PASS)

basic_session = requests.Session()
basic_session.auth = HTTPBasicAuth(DEFAULT_USER, DEFAULT_PASS)

print("Testing different authentication and API methods...\n")

# Test 1: Try with Basic Auth instead of Digest
print("=" * 70)
print("Test 1: Setting IP with Basic Auth...")
print("=" * 70)
try:
    url = f"http://{DEFAULT_IP}/axis-cgi/param.cgi"
    param_string = "action=update&root.Network.BootProto=none&root.Network.eth0.IPAddress=192.168.1.101"
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = basic_session.post(url, data=param_string, headers=headers, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:200]}")
except Exception as e:
    print(f"Error: {e}")

# Test 2: Try setting IP with URL parameters instead of POST body
print("\n" + "=" * 70)
print("Test 2: Setting IP via GET with URL params...")
print("=" * 70)
try:
    url = f"http://{DEFAULT_IP}/axis-cgi/param.cgi?action=update&root.Network.BootProto=none&root.Network.eth0.IPAddress=192.168.1.101"
    response = digest_session.get(url, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:200]}")
except Exception as e:
    print(f"Error: {e}")

# Test 3: Check if there's a network.cgi endpoint
print("\n" + "=" * 70)
print("Test 3: Trying network.cgi endpoint...")
print("=" * 70)
try:
    url = f"http://{DEFAULT_IP}/axis-cgi/network.cgi?action=set&IPAddress=192.168.1.101"
    response = digest_session.get(url, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:200]}")
except Exception as e:
    print(f"Error: {e}")

# Test 4: Set IP using individual parameter updates
print("\n" + "=" * 70)
print("Test 4: Setting each parameter separately...")
print("=" * 70)
try:
    # First set BootProto
    url = f"http://{DEFAULT_IP}/axis-cgi/param.cgi?action=update&root.Network.BootProto=none"
    response1 = digest_session.get(url, timeout=10)
    print(f"BootProto status: {response1.status_code} - {response1.text.strip()}")
    time.sleep(2)
    
    # Then set IP
    url = f"http://{DEFAULT_IP}/axis-cgi/param.cgi?action=update&root.Network.eth0.IPAddress=192.168.1.101"
    response2 = digest_session.get(url, timeout=10)
    print(f"IP status: {response2.status_code} - {response2.text.strip()}")
    
except Exception as e:
    print(f"Error: {e}")

# Verify
print("\n" + "=" * 70)
print("Final Check:")
print("=" * 70)
try:
    time.sleep(3)
    url = f"http://{DEFAULT_IP}/axis-cgi/param.cgi?action=list&group=Network.eth0"
    response = digest_session.get(url, timeout=10)
    if response.status_code == 200:
        for line in response.text.split('\n'):
            if 'IPAddress' in line or 'BootProto' in line or 'SubnetMask' in line:
                print(f"  {line}")
except Exception as e:
    print(f"Error: {e}")

print("\n")
