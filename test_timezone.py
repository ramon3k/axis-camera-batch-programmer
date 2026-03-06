#!/usr/bin/env python3
"""Test timezone configuration on camera."""

import requests
from requests.auth import HTTPDigestAuth
import sys

# Import from main program
sys.path.insert(0, '.')
from axis_batch_programmer import AxisCamera, convert_timezone

def test_timezone():
    """Test timezone conversion and application."""
    
    print("Testing Timezone Configuration")
    print("=" * 60)
    
    # Test conversion
    test_cases = [
        "America/New_York",
        "Central", 
        "Pacific",
        "Europe/London",
        "Asia/Tokyo"
    ]
    
    print("\nTimezone Conversion Tests:")
    print("-" * 60)
    for tz in test_cases:
        posix = convert_timezone(tz)
        print(f"  {tz:25s} → {posix}")
    
    # Test on actual camera
    print("\n" + "=" * 60)
    print("Testing on Camera 192.168.1.101")
    print("=" * 60)
    
    camera = AxisCamera("192.168.1.101", "00:40:8C:12:34:56")
    camera.username = "admin"
    camera.password = "SecurePass123"
    camera.session.auth = HTTPDigestAuth(camera.username, camera.password)
    
    # Test setting timezone
    print("\nSetting timezone to 'America/New_York' (Eastern Time)...")
    success = camera.set_date_time(timezone="America/New_York")
    
    if success:
        print("✓ Timezone configuration succeeded")
        
        # Verify it was set
        print("\nVerifying timezone settings...")
        response = camera.session.get(
            "http://192.168.1.101/axis-cgi/param.cgi?action=list&group=Time",
            timeout=5
        )
        
        if response.status_code == 200:
            print("\nCurrent Time Configuration:")
            print("-" * 60)
            for line in response.text.strip().split('\n'):
                if 'Time' in line:
                    print(f"  {line}")
            print()
        else:
            print(f"✗ Failed to retrieve time config: {response.status_code}")
    else:
        print("✗ Timezone configuration failed")

if __name__ == "__main__":
    try:
        test_timezone()
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
