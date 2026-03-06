#!/usr/bin/env python3
"""
Test changing from DHCP to static IP configuration.
"""

import requests
from requests.auth import HTTPDigestAuth
import time

DEFAULT_IP = "192.168.0.90"
DEFAULT_USER = "root"
DEFAULT_PASS = "pass"

session = requests.Session()
session.auth = HTTPDigestAuth(DEFAULT_USER, DEFAULT_PASS)

print("Testing DHCP to Static conversion...\n")

# Test 1: Current state
print("=" * 70)
print("Current Configuration:")
print("=" * 70)
try:
    url = f"http://{DEFAULT_IP}/axis-cgi/param.cgi?action=list&group=Network"
    response = session.get(url, timeout=10)
    if response.status_code == 200:
        for line in response.text.split('\n'):
            if 'BootProto' in line or ('eth0' in line and ('IP' in line or 'Subnet' in line)):
                print(f"  {line}")
except Exception as e:
    print(f"Error: {e}")

# Test 2: Try setting BootProto to 'none'
print("\n" + "=" * 70)
print("Test 1: Setting BootProto to 'none' (static IP mode)...")
print("=" * 70)
try:
    url = f"http://{DEFAULT_IP}/axis-cgi/param.cgi"
    param_string = "action=update&root.Network.BootProto=none"
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    response = session.post(url, data=param_string, headers=headers, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
    
    if response.status_code == 200 and "Error" not in response.text:
        print("SUCCESS! BootProto set to 'none'")
        time.sleep(2)
except Exception as e:
    print(f"Error: {e}")

# Test 3: Now try setting IP after BootProto is 'none'
print("\n" + "=" * 70)
print("Test 2: Now setting IP address...")
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

# Test 4: Try doing both in one request
print("\n" + "=" * 70)
print("Test 3: Setting BootProto=none AND IP in single request...")
print("=" * 70)
try:
    # First reset to DHCP
    url = f"http://{DEFAULT_IP}/axis-cgi/param.cgi"
    session.post(url, data="action=update&root.Network.BootProto=dhcp", 
                 headers={'Content-Type': 'application/x-www-form-urlencoded'}, timeout=10)
    time.sleep(2)
    
    # Now try setting everything at once
    param_string = "action=update&root.Network.BootProto=none&root.Network.eth0.IPAddress=192.168.1.101&root.Network.eth0.SubnetMask=255.255.255.0"
    response = session.post(url, data=param_string, headers={'Content-Type': 'application/x-www-form-urlencoded'}, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")

# Final: Check what happened
print("\n" + "=" * 70)
print("Final Configuration Check:")
print("=" * 70)
try:
    time.sleep(3)
    url = f"http://{DEFAULT_IP}/axis-cgi/param.cgi?action=list&group=Network"
    response = session.get(url, timeout=10)
    if response.status_code == 200:
        for line in response.text.split('\n'):
            if 'BootProto' in line or ('eth0' in line and ('IP' in line or 'Subnet' in line)):
                print(f"  {line}")
except Exception as e:
    print(f"Error: {e}")

print("\n")
