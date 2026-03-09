#!/usr/bin/env python3
"""
Diagnostic tool to test connectivity to Axis cameras.
Helps troubleshoot network routing and camera discovery issues.
"""

import socket
import requests
import psutil
from requests.auth import HTTPDigestAuth
import time

DEFAULT_IP = "192.168.1.92"
DEFAULT_USER = "root"
DEFAULT_PASS = "pass"
TIMEOUT = 5

def test_ping(ip: str) -> bool:
    """Test if we can reach the IP at TCP level."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)
        result = sock.connect_ex((ip, 80))
        sock.close()
        return result == 0
    except:
        return False

def test_http(ip: str) -> bool:
    """Test basic HTTP connectivity."""
    try:
        response = requests.get(f"http://{ip}/", timeout=TIMEOUT)
        return True
    except:
        return False

def test_vapix(ip: str) -> tuple:
    """Test VAPIX API with authentication."""
    try:
        url = f"http://{ip}/axis-cgi/basicdeviceinfo.cgi"
        session = requests.Session()
        session.auth = HTTPDigestAuth(DEFAULT_USER, DEFAULT_PASS)
        response = session.get(url, timeout=TIMEOUT)
        
        if response.status_code == 200:
            return (True, "OK", response.text[:100])
        else:
            return (False, f"Status {response.status_code}", "")
    except Exception as e:
        return (False, str(e), "")

def get_mac_from_camera(ip: str) -> str:
    """Try to retrieve MAC address from camera."""
    try:
        url = f"http://{ip}/axis-cgi/param.cgi?action=list&group=Network.eth0"
        session = requests.Session()
        session.auth = HTTPDigestAuth(DEFAULT_USER, DEFAULT_PASS)
        response = session.get(url, timeout=TIMEOUT)
        
        if response.status_code == 200:
            for line in response.text.split('\n'):
                if 'MACAddress' in line:
                    return line.split('=')[1].strip().upper()
    except:
        pass
    return "Unable to retrieve"

def main():
    print("\n" + "="*70)
    print(" "*20 + "Camera Connection Diagnostic Tool")
    print("="*70 + "\n")
    
    # Show all network interfaces
    print("Active Network Interfaces:")
    print("-" * 70)
    
    try:
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        
        for interface_name, addr_list in addrs.items():
            if interface_name in stats and stats[interface_name].isup:
                for addr in addr_list:
                    if addr.family == socket.AF_INET:
                        ip = addr.address
                        if not ip.startswith('127.') and not ip.startswith('169.254.'):
                            status = "UP" if stats[interface_name].isup else "DOWN"
                            print(f"  [{status}] {interface_name}: {ip}")
    except Exception as e:
        print(f"  Error getting interfaces: {e}")
    
    print("\n" + "="*70)
    print(f"Testing connection to camera at {DEFAULT_IP}")
    print("="*70 + "\n")
    
    # Test 1: TCP Socket
    print(f"Test 1: TCP Socket (port 80)...", end=" ")
    if test_ping(DEFAULT_IP):
        print("✓ SUCCESS - Port 80 is reachable")
    else:
        print("✗ FAILED - Cannot reach port 80")
        print("         → Camera may be off, disconnected, or behind firewall")
    
    # Test 2: HTTP
    print(f"Test 2: HTTP GET request...", end=" ")
    if test_http(DEFAULT_IP):
        print("✓ SUCCESS - HTTP server responds")
    else:
        print("✗ FAILED - HTTP request timeout")
        print("         → Camera not responding or wrong IP")
    
    # Test 3: VAPIX API
    print(f"Test 3: VAPIX API with auth...", end=" ")
    success, message, data = test_vapix(DEFAULT_IP)
    if success:
        print("✓ SUCCESS - Camera API accessible")
        print(f"         → Response preview: {data[:50]}...")
    else:
        print(f"✗ FAILED - {message}")
        print("         → Check credentials or camera firmware")
    
    # Test 4: Get MAC address
    print(f"Test 4: Retrieve MAC address...", end=" ")
    mac = get_mac_from_camera(DEFAULT_IP)
    if mac != "Unable to retrieve":
        print(f"✓ SUCCESS")
        print(f"         → MAC Address: {mac}")
    else:
        print("✗ FAILED - Cannot retrieve MAC")
    
    print("\n" + "="*70)
    print("Route Testing")
    print("="*70 + "\n")
    
    print(f"Testing which interface is used to reach {DEFAULT_IP}...")
    try:
        # Create a socket and connect to see which interface is used
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect((DEFAULT_IP, 80))
        local_ip = s.getsockname()[0]
        s.close()
        
        print(f"✓ Routes through local IP: {local_ip}")
        
        # Find which interface has this IP
        addrs = psutil.net_if_addrs()
        for interface_name, addr_list in addrs.items():
            for addr in addr_list:
                if addr.family == socket.AF_INET and addr.address == local_ip:
                    print(f"  Interface: {interface_name}")
                    break
    except Exception as e:
        print(f"✗ Cannot determine route: {e}")
    
    print("\n" + "="*70)
    print("Recommendations")
    print("="*70 + "\n")
    
    # Provide recommendations based on results
    if not test_ping(DEFAULT_IP):
        print("⚠ Camera is not reachable on network")
        print("  • Verify camera is powered on")
        print("  • Check network cable connection")
        print("  • Ensure Ethernet 3 is connected to camera network")
        print(f"  • Try: ping {DEFAULT_IP}")
    
    if test_ping(DEFAULT_IP) and not test_http(DEFAULT_IP):
        print("⚠ Network reaches camera but HTTP fails")
        print("  • Camera may still be booting (wait 30 seconds)")
        print("  • Try accessing http://192.168.0.90 in browser")
    
    if test_http(DEFAULT_IP) and not test_vapix(DEFAULT_IP)[0]:
        print("⚠ HTTP works but VAPIX authentication fails")
        print("  • Camera may not be at factory defaults")
        print("  • Try accessing http://192.168.0.90 in browser")
        print(f"  • Verify credentials: {DEFAULT_USER} / {DEFAULT_PASS}")
    
    print()

if __name__ == "__main__":
    main()
