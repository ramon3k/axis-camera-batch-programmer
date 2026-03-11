#!/usr/bin/env python3
"""
Axis Camera Firmware Upgrade Example

This script demonstrates how to upgrade (or downgrade) Axis camera firmware.

Usage:
    python firmware_upgrade_example.py

Requirements:
    - Camera must be accessible on network
    - Firmware .bin file must be downloaded from Axis website
    - Camera will reboot during upgrade (5-10 minutes downtime)

Firmware Downloads:
    https://www.axis.com/support/firmware
    
VAPIX Documentation:
    https://developer.axis.com/vapix/
"""

import logging
from axis_batch_programmer import AxisCamera

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def progress_callback(stage, message):
    """Callback function to display upgrade progress."""
    print(f"[{stage.upper()}] {message}")


def upgrade_single_camera():
    """Example: Upgrade a single camera's firmware."""
    
    # Camera connection details
    camera_ip = "192.168.1.101"
    camera_mac = "B8:A4:4F:FF:2E:D7"  # Can also use "B8A44FFF2ED7" without colons
    username = "admin"
    password = "admin"
    
    # Firmware file path (download from https://www.axis.com/support/firmware)
    firmware_file = "P3267-LV_12_5_56.bin"  # Change to your firmware file
    
    print("="*60)
    print("Axis Camera Firmware Upgrade")
    print("="*60)
    
    # Connect to camera
    camera = AxisCamera(camera_ip, camera_mac, username, password)
    
    # Get current firmware version
    print("\n1. Checking current firmware...")
    current_version = camera.get_firmware_version()
    
    if not current_version:
        print("ERROR: Could not connect to camera or retrieve firmware version")
        return False
    
    print(f"   Current firmware: {current_version}")
    
    # Confirm upgrade
    print(f"\n2. Ready to upgrade to: {firmware_file}")
    print("   WARNING: Camera will reboot and be unavailable for 5-10 minutes")
    response = input("   Continue? (yes/no): ")
    
    if response.lower() != 'yes':
        print("Upgrade cancelled")
        return False
    
    # Perform upgrade
    print("\n3. Starting firmware upgrade...")
    success = camera.upgrade_firmware(firmware_file, progress_callback=progress_callback)
    
    if success:
        print("\n" + "="*60)
        print("✓ FIRMWARE UPGRADE SUCCESSFUL!")
        print("="*60)
        
        # Verify new firmware
        new_version = camera.get_firmware_version()
        print(f"\nOld firmware: {current_version}")
        print(f"New firmware: {new_version}")
        
        return True
    else:
        print("\n" + "="*60)
        print("✗ FIRMWARE UPGRADE FAILED")
        print("="*60)
        print("\nTroubleshooting:")
        print("  1. Verify firmware file path is correct")
        print("  2. Ensure firmware file matches camera model")
        print("  3. Check camera is accessible on network")
        print("  4. Try manual upgrade via web interface")
        
        return False


def upgrade_multiple_cameras():
    """Example: Upgrade multiple cameras from CSV."""
    
    # This would integrate with the CSV batch programming workflow
    # Each camera row could have an optional "FirmwareFile" column
    
    print("Multiple camera firmware upgrade:")
    print("  1. Add 'FirmwareFile' column to cameras_config.csv")
    print("  2. Specify firmware .bin file path for each camera")
    print("  3. Run batch programmer with firmware upgrade enabled")
    print("\nExample CSV:")
    print("MAC Address,Camera Name,Current IP,New IP,Username,Password,Timezone,FirmwareFile")
    print("B8:A4:4F:FF:2E:D7,KBO-001,192.168.1.168,192.168.1.101,admin,password,Mountain,AXIS_P3267LV_10_12_240.bin")


if __name__ == "__main__":
    print("\nAxis Camera Firmware Upgrade Tool")
    print("-" * 60)
    print("\n1. Single Camera Upgrade")
    print("2. Multiple Camera Upgrade Info")
    print("3. Exit")
    
    choice = input("\nSelect option (1-3): ")
    
    if choice == "1":
        upgrade_single_camera()
    elif choice == "2":
        upgrade_multiple_cameras()
    else:
        print("Exiting...")
