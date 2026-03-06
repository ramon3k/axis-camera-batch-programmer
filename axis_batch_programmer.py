#!/usr/bin/env python3
"""
Axis Camera Batch Programmer
Discovers Axis cameras on network and configures them based on CSV data.
Handles multiple cameras with same default IP (192.168.0.90).
"""

import csv
import socket
import requests
import time
import ipaddress
from datetime import datetime
from typing import Dict, List, Optional
from requests.auth import HTTPDigestAuth
import logging
import psutil
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import re

# Configure logging with UTF-8 encoding for Windows compatibility
import sys
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('axis_programmer.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants
DEFAULT_IP = "192.168.0.90"
DEFAULT_USER = "root"
DEFAULT_PASS = ""  # Factory default has no password
VAPIX_TIMEOUT = 10
DISCOVERY_TIMEOUT = 5

# Timezone mapping: Common timezone names to POSIX format  
TIMEZONE_MAP = {
    # US Timezones
    "America/New_York": "EST5EDT,M3.2.0,M11.1.0",
    "Eastern": "EST5EDT,M3.2.0,M11.1.0",
    "America/Chicago": "CST6CDT,M3.2.0,M11.1.0",
    "Central": "CST6CDT,M3.2.0,M11.1.0",
    "America/Denver": "MST7MDT,M3.2.0,M11.1.0",
    "Mountain": "MST7MDT,M3.2.0,M11.1.0",
    "America/Phoenix": "MST7",  # Arizona (no DST)
    "America/Los_Angeles": "PST8PDT,M3.2.0,M11.1.0",
    "Pacific": "PST8PDT,M3.2.0,M11.1.0",
    "America/Anchorage": "AKST9AKDT,M3.2.0,M11.1.0",
    "Alaska": "AKST9AKDT,M3.2.0,M11.1.0",
    "Pacific/Honolulu": "HST10",  # Hawaii (no DST)
    # European Timezones
    "Europe/London": "GMT0BST,M3.5.0/1,M10.5.0",
    "Europe/Paris": "CET-1CEST,M3.5.0,M10.5.0/3",
    "Europe/Berlin": "CET-1CEST,M3.5.0,M10.5.0/3",
    "Europe/Rome": "CET-1CEST,M3.5.0,M10.5.0/3",
    # Asian Timezones
    "Asia/Tokyo": "JST-9",
    "Asia/Shanghai": "CST-8",
    "Asia/Singapore": "SGT-8",
    "Asia/Dubai": "GST-4",
    # Australian Timezones
    "Australia/Sydney": "AEST-10AEDT,M10.1.0,M4.1.0/3",
    "Australia/Perth": "AWST-8",
}

def convert_timezone(tz_name: str) -> str:
    """Convert common timezone name to POSIX format.
    
    Args:
        tz_name: Timezone name (e.g., "America/New_York", "Eastern")
    
    Returns:
        POSIX timezone string (e.g., "EST5EDT,M3.2.0,M11.1.0")
        If not found in map, returns input as-is (assumes already POSIX format)
    """
    return TIMEZONE_MAP.get(tz_name, tz_name)


class AxisCamera:
    """Represents an Axis camera with configuration methods."""
    
    def __init__(self, ip: str, mac: str, username: str = DEFAULT_USER, password: str = DEFAULT_PASS):
        self.ip = ip
        self.mac = mac.upper().replace('-', ':')
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.auth = HTTPDigestAuth(username, password)
        
    def test_connection(self) -> bool:
        """Test if we can connect to the camera."""
        try:
            # Try multiple endpoints for compatibility with different firmware versions
            endpoints = [
                "/axis-cgi/param.cgi?action=list&group=Network",  # Most compatible
                "/axis-cgi/basicdeviceinfo.cgi",
                "/axis-cgi/serverreport.cgi"
            ]
            
            for endpoint in endpoints:
                try:
                    url = f"http://{self.ip}{endpoint}"
                    response = self.session.get(url, timeout=VAPIX_TIMEOUT)
                    if response.status_code == 200:
                        logger.debug(f"Connection successful to {self.ip} via {endpoint}")
                        return True
                except:
                    continue
            
            logger.debug(f"All connection tests failed for {self.ip}")
            return False
            
        except Exception as e:
            logger.debug(f"Connection test failed for {self.ip}: {e}")
            return False
    
    def get_mac_address(self) -> Optional[str]:
        """Retrieve the camera's MAC address."""
        try:
            url = f"http://{self.ip}/axis-cgi/param.cgi?action=list&group=Network.eth0"
            response = self.session.get(url, timeout=VAPIX_TIMEOUT)
            if response.status_code == 200:
                for line in response.text.split('\n'):
                    if 'MACAddress' in line:
                        mac = line.split('=')[1].strip().upper()
                        return mac
        except Exception as e:
            logger.error(f"Failed to get MAC for {self.ip}: {e}")
        return None
    
    def setup_initial_password(self, password: str = "pass") -> bool:
        """Set initial root password on factory-fresh camera.
        
        Factory-reset cameras require setting the root password via the web setup
        before API access is allowed. This automates that initial setup step.
        """
        try:
            # Try to access without auth to see if in initial setup mode
            response = requests.get(f"http://{self.ip}/", timeout=5)
            
            # Check if redirected to password setup page
            if 'pwdroot' in response.url.lower() or 'pwdRoot' in response.text:
                logger.info(f"Camera at {self.ip} requires initial password setup")
                
                # Set the initial root password via POST
                setup_url = f"http://{self.ip}/axis-cgi/pwdroot.cgi"
                
                # Try the pwdroot.cgi endpoint
                data = {
                    'user': 'root',
                    'pwd': password,
                    'rpwd': password  # Confirm password
                }
                
                response = requests.post(setup_url, data=data, timeout=10)
                
                if response.status_code == 200:
                    logger.info(f"Initial password set successfully for {self.ip}")
                    # Update our session with the new password
                    self.password = password
                    self.session.auth = HTTPDigestAuth('root', password)
                    time.sleep(2)  # Give camera time to apply
                    return True
                else:
                    logger.warning(f"Initial password setup returned status: {response.status_code}")
                    # Try updating session anyway
                    self.password = password
                    self.session.auth = HTTPDigestAuth('root', password)
                    return True
            
            # Camera not in initial setup mode - already configured
            return True
            
        except Exception as e:
            logger.warning(f"Error during initial password setup: {e}")
            # Don't fail - camera might already be set up
            return True
    
    def set_network_config(self, new_ip: str, subnet_mask: str = "255.255.255.0", gateway: str = None) -> bool:
        """Configure camera's network settings."""
        try:
            old_ip = self.ip
            
            # Step 1: Disable DHCP and set to static (none)
            url = f"http://{self.ip}/axis-cgi/param.cgi"
            param_string = f"action=update&root.Network.BootProto=none"
            response = self.session.get(url + "?" + param_string, timeout=VAPIX_TIMEOUT)
            
            if response.status_code != 200:
                logger.error(f"Failed to disable DHCP: {response.status_code}")
                return False
            
            logger.info(f"DHCP disabled for {self.mac}")
            time.sleep(1)
            
            # Step 2: Set IP, subnet, and gateway using root.Network (not eth0 specific)
            param_string = f"action=update&root.Network.IPAddress={new_ip}&root.Network.SubnetMask={subnet_mask}"
            
            # Add gateway if provided
            if gateway:
                param_string += f"&root.Network.DefaultRouter={gateway}"
                logger.info(f"Setting gateway to {gateway} for {self.mac}")
            
            # Use GET request - Axis VAPIX often works better with GET for param updates
            response = self.session.get(url + "?" + param_string, timeout=VAPIX_TIMEOUT)
            
            # Note: 401 response with "OK" text often means the change was applied
            # but the connection was interrupted due to network change
            if response.status_code == 200 or (response.status_code == 401 and response.text.strip() == "OK"):
                logger.info(f"Network config set for {self.mac}: {new_ip}")
                # Update our IP for further communication
                self.ip = new_ip
                time.sleep(5)  # Wait longer for camera to apply network settings
                return True
            else:
                logger.error(f"Failed to set network config: {response.status_code}")
                logger.debug(f"Response: {response.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"Error setting network config: {e}")
            return False
    
    def set_credentials(self, new_username: str, new_password: str) -> bool:
        """Set new administrator credentials."""
        try:
            url = f"http://{self.ip}/axis-cgi/pwdgrp.cgi"
            
            # If keeping root username, just update the password
            if new_username == 'root':
                # Update root password
                param_string = f"action=update&user=root&pwd={new_password}"
                response = self.session.get(url + "?" + param_string, timeout=VAPIX_TIMEOUT)
                
                if response.status_code == 200 and ("OK" in response.text or "Modified account" in response.text):
                    # Update session auth
                    self.password = new_password
                    self.session.auth = HTTPDigestAuth(new_username, new_password)
                    logger.info(f"Root password updated for {self.mac}")
                    return True
                else:
                    logger.error(f"Failed to update root password: {response.status_code} - {response.text[:100]}")
                    return False
            
            else:
                # First, update root password to secure it
                logger.info(f"Updating root password first for {self.mac}...")
                param_string = f"action=update&user=root&pwd={new_password}"
                response = self.session.get(url + "?" + param_string, timeout=VAPIX_TIMEOUT)
                
                if response.status_code == 200 and ("OK" in response.text or "Modified account" in response.text):
                    logger.info(f"Root password updated for {self.mac}")
                    # Update session to use new root password immediately
                    self.password = new_password
                    self.session.auth = HTTPDigestAuth('root', new_password)
                else:
                    logger.warning(f"Root password update had issues: {response.status_code} - {response.text[:100]}")
                    # Still update auth in case it worked but response was unexpected
                    self.password = new_password
                    self.session.auth = HTTPDigestAuth('root', new_password)
                
                # Try to update user first (in case user already exists)
                logger.info(f"Checking if user '{new_username}' exists for {self.mac}...")
                param_string = f"action=update&user={new_username}&pwd={new_password}"
                response = self.session.get(url + "?" + param_string, timeout=VAPIX_TIMEOUT)
                
                user_updated = False
                if response.status_code == 200 and ("OK" in response.text or "Modified account" in response.text):
                    logger.info(f"User '{new_username}' password updated for {self.mac}")
                    user_updated = True
                else:
                    # User doesn't exist, try to create it
                    logger.info(f"User doesn't exist, creating new user '{new_username}' for {self.mac}...")
                    param_string = f"action=add&user={new_username}&pwd={new_password}&grp=admin&sgrp=admin:operator:viewer"
                    response = self.session.get(url + "?" + param_string, timeout=VAPIX_TIMEOUT)
                    
                    if response.status_code == 200 and ("OK" in response.text or "Created account" in response.text):
                        logger.info(f"New user '{new_username}' created for {self.mac}")
                        user_updated = True
                    else:
                        logger.error(f"Failed to create user: {response.status_code} - {response.text[:100]}")
                        return False
                
                if user_updated:
                    # Update session auth to new user
                    self.username = new_username
                    self.password = new_password
                    self.session.auth = HTTPDigestAuth(new_username, new_password)
                    
                    # Optionally remove root user (commented out for safety)
                    # self._remove_user(DEFAULT_USER)
                    
                    return True
                else:
                    return False
                    
        except Exception as e:
            logger.error(f"Error setting credentials: {e}")
            return False
    
    def _remove_user(self, username: str) -> bool:
        """Remove a user account."""
        try:
            url = f"http://{self.ip}/axis-cgi/pwdgrp.cgi"
            params = {'action': 'remove', 'user': username}
            response = self.session.post(url, data=params, timeout=VAPIX_TIMEOUT)
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Error removing user {username}: {e}")
            return False
    
    def set_camera_name(self, name: str) -> bool:
        """Set the camera's system name."""
        try:
            # Try multiple possible name parameters
            url = f"http://{self.ip}/axis-cgi/param.cgi"
            
            # Some cameras use System.HostName, others use Network.HostName
            param_string = f"action=update&root.System.HostName={name}&root.Network.HostName={name}"
            response = self.session.get(url + "?" + param_string, timeout=VAPIX_TIMEOUT)
            
            if response.status_code == 200:
                logger.info(f"Camera name set to '{name}' for {self.mac}")
                return True
            else:
                logger.error(f"Failed to set camera name: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Error setting camera name: {e}")
            return False
    
    def set_date_time(self, timezone: str = "America/New_York", use_ntp: bool = True, ntp_server: str = "pool.ntp.org") -> bool:
        """Configure date, time, and timezone settings.
        
        Args:
            timezone: Timezone name (e.g., "America/New_York", "Central") or POSIX format
                      Common names are automatically converted to POSIX format
            use_ntp: Enable NTP time synchronization
            ntp_server: NTP server address
        """
        try:
            url = f"http://{self.ip}/axis-cgi/param.cgi"
            
            # Convert timezone name to POSIX format
            posix_tz = convert_timezone(timezone)
            logger.info(f"Setting timezone '{timezone}' (POSIX: {posix_tz}) for {self.mac}")
            
            # Set POSIX timezone
            param_string = f"action=update&root.Time.POSIXTimeZone={posix_tz}"
            response = self.session.get(url + "?" + param_string, timeout=VAPIX_TIMEOUT)
            
            if response.status_code != 200 or "Error" in response.text:
                logger.warning(f"Timezone setting had issues: {response.text[:100]}")
                # Don't fail - timezone may already be correct
            else:
                logger.info(f"Timezone configured successfully for {self.mac}")
            
            # Configure NTP
            if use_ntp:
                # Enable NTP and set NTP server
                param_string = f"action=update&root.Time.SyncSource=NTP&root.Time.NTP.Server={ntp_server}"
                response = self.session.get(url + "?" + param_string, timeout=VAPIX_TIMEOUT)
                
                if response.status_code == 200 and "Error" not in response.text:
                    logger.info(f"NTP enabled with server '{ntp_server}' for {self.mac}")
                else:
                    logger.warning(f"NTP configuration had issues: {response.text[:100]}")
            
            return True
            
        except Exception as e:
            logger.warning(f"Error setting date/time: {e}")
            return True  # Don't fail the whole process for time config
    
    def zoom_out_fully(self) -> bool:
        """Zoom out camera to minimum zoom level."""
        try:
            # Check if camera has PTZ capabilities
            url = f"http://{self.ip}/axis-cgi/param.cgi?action=list&group=PTZ"
            response = self.session.get(url, timeout=VAPIX_TIMEOUT)
            
            if response.status_code == 200 and 'PTZ' in response.text:
                # PTZ camera - use PTZ command
                zoom_url = f"http://{self.ip}/axis-cgi/com/ptz.cgi?zoom=1"
                zoom_response = self.session.get(zoom_url, timeout=VAPIX_TIMEOUT)
                
                if zoom_response.status_code == 200:
                    logger.info(f"Zoom set to minimum for {self.mac}")
                    return True
            else:
                # Fixed camera or no PTZ - try digital zoom settings
                url = f"http://{self.ip}/axis-cgi/param.cgi"
                params = {
                    'action': 'update',
                    'Image.I0.Appearance.Zoom': '1'  # Minimum zoom
                }
                response = self.session.post(url, data=params, timeout=VAPIX_TIMEOUT)
                
                if response.status_code == 200:
                    logger.info(f"Digital zoom adjusted for {self.mac}")
                    return True
            
            logger.warning(f"No zoom control available for {self.mac}")
            return True  # Not a failure, just not applicable
            
        except Exception as e:
            logger.warning(f"Could not adjust zoom for {self.mac}: {e}")
            return True  # Don't fail the whole process for zoom
    
    def verify_configuration(self, expected_ip: str, expected_name: str = None) -> bool:
        """Verify that configuration was applied correctly."""
        try:
            # Test connection with new IP
            url = f"http://{self.ip}/axis-cgi/param.cgi?action=list&group=Network.eth0"
            response = self.session.get(url, timeout=VAPIX_TIMEOUT)
            
            if response.status_code != 200:
                logger.error(f"Cannot verify config - connection failed")
                return False
            
            # Check IP address
            config_text = response.text
            if f"Network.eth0.IPAddress={expected_ip}" not in config_text:
                logger.error(f"IP verification failed. Expected {expected_ip}")
                return False
            
            # Check name if provided
            if expected_name:
                url = f"http://{self.ip}/axis-cgi/param.cgi?action=list&group=System"
                response = self.session.get(url, timeout=VAPIX_TIMEOUT)
                if f"System.HostName={expected_name}" not in response.text:
                    logger.warning(f"Name verification failed. Expected '{expected_name}'")
                    # Don't fail for name mismatch, just warn
            
            logger.info(f"Configuration verified for {self.mac}")
            return True
            
        except Exception as e:
            logger.error(f"Error verifying configuration: {e}")
            return False
    
    def test_compatibility(self) -> Dict[str, any]:
        """Test camera compatibility without making changes.
        
        Returns dictionary with test results for each function.
        """
        results = {
            'camera_model': 'Unknown',
            'firmware': 'Unknown',
            'current_ip': self.ip,
            'mac_address': None,
            'tests': {}
        }
        
        try:
            logger.info(f"\n{'='*60}")
            logger.info(f"Testing Camera Compatibility: {self.ip}")
            logger.info(f"{'='*60}")
            
            # Test 1: Basic connectivity
            logger.info("Test 1: Basic Connectivity")
            try:
                response = self.session.get(
                    f"http://{self.ip}/axis-cgi/param.cgi?action=list&group=root.Brand",
                    timeout=VAPIX_TIMEOUT
                )
                if response.status_code == 200:
                    results['tests']['connectivity'] = 'PASS'
                    logger.info("  ✓ Connection successful")
                    
                    # Try to get model info
                    for line in response.text.split('\n'):
                        if 'ProdFullName' in line:
                            results['camera_model'] = line.split('=')[1].strip()
                        elif 'Version' in line:
                            results['firmware'] = line.split('=')[1].strip()
                else:
                    results['tests']['connectivity'] = 'FAIL'
                    logger.error(f"  ✗ Connection failed: {response.status_code}")
            except Exception as e:
                results['tests']['connectivity'] = 'FAIL'
                logger.error(f"  ✗ Connection failed: {e}")
                return results
            
            # Test 2: MAC address retrieval
            logger.info("\nTest 2: MAC Address Retrieval")
            try:
                mac = self.get_mac_address()
                if mac:
                    results['mac_address'] = mac
                    results['tests']['mac_retrieval'] = 'PASS'
                    logger.info(f"  ✓ MAC Address: {mac}")
                else:
                    results['tests']['mac_retrieval'] = 'FAIL'
                    logger.error("  ✗ Could not retrieve MAC address")
            except Exception as e:
                results['tests']['mac_retrieval'] = 'FAIL'
                logger.error(f"  ✗ MAC retrieval error: {e}")
            
            # Test 3: Network configuration read
            logger.info("\nTest 3: Network Configuration Read")
            try:
                response = self.session.get(
                    f"http://{self.ip}/axis-cgi/param.cgi?action=list&group=Network",
                    timeout=VAPIX_TIMEOUT
                )
                if response.status_code == 200 and 'Network.IPAddress' in response.text:
                    results['tests']['network_read'] = 'PASS'
                    logger.info("  ✓ Can read network configuration")
                    
                    # Extract current settings
                    for line in response.text.split('\n'):
                        if 'Network.IPAddress=' in line:
                            logger.info(f"    Current IP: {line.split('=')[1].strip()}")
                        elif 'Network.SubnetMask=' in line:
                            logger.info(f"    Current Subnet: {line.split('=')[1].strip()}")
                        elif 'Network.DefaultRouter=' in line:
                            logger.info(f"    Current Gateway: {line.split('=')[1].strip()}")
                else:
                    results['tests']['network_read'] = 'FAIL'
                    logger.error("  ✗ Cannot read network configuration")
            except Exception as e:
                results['tests']['network_read'] = 'FAIL'
                logger.error(f"  ✗ Network read error: {e}")
            
            # Test 4: User management endpoint
            logger.info("\nTest 4: User Management Capability")
            try:
                response = self.session.get(
                    f"http://{self.ip}/axis-cgi/pwdgrp.cgi?action=get",
                    timeout=VAPIX_TIMEOUT
                )
                if response.status_code == 200 or response.status_code == 204:
                    results['tests']['user_management'] = 'PASS'
                    logger.info("  ✓ User management endpoint accessible")
                else:
                    results['tests']['user_management'] = 'WARN'
                    logger.warning(f"  ⚠ User management returned: {response.status_code}")
            except Exception as e:
                results['tests']['user_management'] = 'WARN'
                logger.warning(f"  ⚠ User management test: {e}")
            
            # Test 5: DateTime configuration
            logger.info("\nTest 5: Date/Time Configuration")
            try:
                response = self.session.get(
                    f"http://{self.ip}/axis-cgi/param.cgi?action=list&group=Time",
                    timeout=VAPIX_TIMEOUT
                )
                if response.status_code == 200 and 'Time.TimeZone' in response.text:
                    results['tests']['datetime'] = 'PASS'
                    logger.info("  ✓ Timezone configuration supported")
                else:
                    results['tests']['datetime'] = 'WARN'
                    logger.warning("  ⚠ Timezone configuration may not be supported")
            except Exception as e:
                results['tests']['datetime'] = 'WARN'
                logger.warning(f"  ⚠ DateTime test: {e}")
            
            # Test 6: Camera name/hostname
            logger.info("\nTest 6: Camera Name Configuration")
            try:
                response = self.session.get(
                    f"http://{self.ip}/axis-cgi/param.cgi?action=list&group=System",
                    timeout=VAPIX_TIMEOUT
                )
                if response.status_code == 200 and ('System.HostName' in response.text or 'System.Name' in response.text):
                    results['tests']['camera_name'] = 'PASS'
                    logger.info("  ✓ Camera name configuration supported")
                else:
                    results['tests']['camera_name'] = 'WARN'
                    logger.warning("  ⚠ Camera name configuration may not be supported")
            except Exception as e:
                results['tests']['camera_name'] = 'WARN'
                logger.warning(f"  ⚠ Camera name test: {e}")
            
            # Summary
            logger.info(f"\n{'='*60}")
            logger.info("Compatibility Test Summary")
            logger.info(f"{'='*60}")
            logger.info(f"Model: {results['camera_model']}")
            logger.info(f"Firmware: {results['firmware']}")
            logger.info(f"MAC: {results.get('mac_address', 'Unknown')}")
            logger.info("")
            
            pass_count = sum(1 for v in results['tests'].values() if v == 'PASS')
            warn_count = sum(1 for v in results['tests'].values() if v == 'WARN')
            fail_count = sum(1 for v in results['tests'].values() if v == 'FAIL')
            
            for test_name, test_result in results['tests'].items():
                icon = '✓' if test_result == 'PASS' else ('⚠' if test_result == 'WARN' else '✗')
                logger.info(f"  {icon} {test_name}: {test_result}")
            
            logger.info("")
            logger.info(f"Results: {pass_count} PASS, {warn_count} WARN, {fail_count} FAIL")
            
            if fail_count == 0:
                logger.info("\n✓ Camera is FULLY COMPATIBLE - All critical functions work!")
            elif fail_count <= 2 and pass_count >= 3:
                logger.info("\n⚠ Camera is MOSTLY COMPATIBLE - Core functions work, some features may not")
            else:
                logger.error("\n✗ Camera may have COMPATIBILITY ISSUES - Review test results")
            
            logger.info(f"{'='*60}\n")
            
            return results
            
        except Exception as e:
            logger.error(f"Compatibility test error: {e}")
            results['tests']['overall'] = 'ERROR'
            return results


def get_arp_table() -> Dict[str, str]:
    """
    Get the ARP table from the system.
    Returns dict mapping MAC addresses to IP addresses.
    """
    arp_table = {}
    
    try:
        if sys.platform == 'win32':
            # Windows: use 'arp -a'
            result = subprocess.run(['arp', '-a'], capture_output=True, text=True, timeout=10)
            output = result.stdout
            
            # Parse Windows ARP output
            # Format: 192.168.1.100    00-40-8c-12-34-56     dynamic
            for line in output.split('\n'):
                match = re.search(r'(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F-]{17})', line)
                if match:
                    ip = match.group(1)
                    mac = match.group(2).upper().replace('-', ':')
                    arp_table[mac] = ip
        else:
            # Linux/Mac: use 'arp -n'
            result = subprocess.run(['arp', '-n'], capture_output=True, text=True, timeout=10)
            output = result.stdout
            
            # Parse Linux/Mac ARP output
            for line in output.split('\n'):
                match = re.search(r'(\d+\.\d+\.\d+\.\d+).*?([0-9a-fA-F:]{17})', line)
                if match:
                    ip = match.group(1)
                    mac = match.group(2).upper()
                    arp_table[mac] = ip
        
        logger.info(f"Found {len(arp_table)} devices in ARP table")
        return arp_table
        
    except Exception as e:
        logger.warning(f"Could not read ARP table: {e}")
        return {}


def ping_subnet(network: ipaddress.IPv4Network) -> None:
    """
    Ping all IPs in a subnet to populate the ARP table.
    Uses parallel pings for speed.
    """
    def ping_ip(ip: str):
        try:
            if sys.platform == 'win32':
                subprocess.run(['ping', '-n', '1', '-w', '100', ip], 
                             capture_output=True, timeout=2)
            else:
                subprocess.run(['ping', '-c', '1', '-W', '1', ip], 
                             capture_output=True, timeout=2)
        except:
            pass  # Silent fail
    
    hosts = [str(ip) for ip in network.hosts()]
    logger.info(f"  Pinging {len(hosts)} IPs to populate ARP table (10-20 seconds)...")
    
    # Parallel ping with many workers for speed
    with ThreadPoolExecutor(max_workers=100) as executor:
        list(executor.map(ping_ip, hosts))


def get_active_network_interfaces() -> List[Dict]:
    """
    Get all active network interfaces with their IP addresses.
    Returns list of interface info including name and IP address.
    """
    interfaces = []
    
    try:
        # Get all network interface addresses
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        
        for interface_name, addr_list in addrs.items():
            # Skip if interface is down
            if interface_name in stats and not stats[interface_name].isup:
                continue
            
            # Look for IPv4 addresses
            for addr in addr_list:
                if addr.family == socket.AF_INET:  # IPv4
                    ip = addr.address
                    
                    # Skip loopback and link-local addresses
                    if ip.startswith('127.') or ip.startswith('169.254.'):
                        continue
                    
                    interfaces.append({
                        'name': interface_name,
                        'ip': ip,
                        'netmask': addr.netmask
                    })
                    logger.info(f"Found active interface: {interface_name} ({ip})")
        
        return interfaces
        
    except Exception as e:
        logger.error(f"Error getting network interfaces: {e}")
        return []


# Removed old scan_subnet and check_ip_for_camera functions - now using ARP-based discovery


def discover_cameras_on_network(configs: List[Dict] = None) -> List[Dict]:
    """
    Discover Axis cameras on all active network interfaces.
    If configs provided, only attempts connection to IPs with matching MACs and tries CSV credentials.
    
    Args:
        configs: List of camera configurations from CSV (contains MAC, credentials, etc.)
    
    Returns list of discovered cameras with their info.
    """
    discovered = []
    discovered_macs = set()  # Track MACs to avoid duplicates
    
    logger.info("Starting camera discovery across all network interfaces...")
    
    # Extract target MACs from configs
    target_macs = []
    config_by_mac = {}
    if configs:
        for cfg in configs:
            mac = cfg['mac']
            target_macs.append(mac)
            config_by_mac[mac] = cfg
        logger.info(f"Searching for {len(target_macs)} specific camera MAC(s) from CSV")
    
    # Get all active network interfaces
    interfaces = get_active_network_interfaces()
    
    if not interfaces:
        logger.warning("No active network interfaces found!")
    else:
        logger.info(f"Scanning {len(interfaces)} active network interface(s)...\n")
    
    # Method 1: Try to connect to default IP directly (works if on same network)
    logger.info("Method 1: Direct connection to default IP...")
    
    # Try factory credentials first
    camera = None
    mac = None
    try:
        camera = AxisCamera(DEFAULT_IP, "", "root", "")
        logger.debug(f"Attempting to connect to {DEFAULT_IP} with factory credentials...")
        
        # Try initial password setup if needed (factory-fresh cameras)
        camera.setup_initial_password("pass")
        
        # Try to get MAC address directly
        mac = camera.get_mac_address()
        if mac and mac not in discovered_macs:
            discovered.append({
                'ip': DEFAULT_IP,
                'mac': mac,
                'method': 'direct',
                'auth_method': 'factory',
                'interface': 'default',
                'camera': camera
            })
            discovered_macs.add(mac)
            logger.info(f"[OK] Found camera at {DEFAULT_IP} with MAC {mac} (factory credentials)")
    except Exception as e:
        logger.debug(f"Factory credentials failed at {DEFAULT_IP}: {e}")
        camera = None
    
    # If factory credentials failed, try CSV credentials
    if not camera and config_by_mac:
        for cfg in config_by_mac.values():
            try:
                logger.debug(f"Trying {DEFAULT_IP} with CSV credentials ({cfg['username']})...")
                camera = AxisCamera(DEFAULT_IP, "", cfg['username'], cfg['password'])
                mac = camera.get_mac_address()
                
                if mac and mac not in discovered_macs:
                    # Update the camera's MAC now that we know it
                    camera.mac = mac
                    discovered.append({
                        'ip': DEFAULT_IP,
                        'mac': mac,
                        'method': 'direct',
                        'auth_method': 'csv_credentials',
                        'interface': 'default',
                        'camera': camera
                    })
                    discovered_macs.add(mac)
                    logger.info(f"[OK] Found camera at {DEFAULT_IP} with MAC {mac} (CSV credentials)")
                    break
            except Exception as e:
                logger.debug(f"CSV credentials {cfg['username']} failed at {DEFAULT_IP}: {e}")
                continue
    
    # Method 2: Scan each network interface's subnet
    logger.info("\nMethod 2: Scanning subnets on each interface...")
    for interface in interfaces:
        interface_ip = interface['ip']
        interface_name = interface['name']
        
        logger.info(f"Scanning interface '{interface_name}' ({interface_ip})...")
        
        try:
            network = ipaddress.ip_network(f"{interface_ip}/24", strict=False)
            
            # Common Axis default IPs to check
            common_ips = [
                DEFAULT_IP,
                f"{network.network_address.exploded.rsplit('.', 1)[0]}.90"
            ]
            
            # Remove duplicates
            common_ips = list(set(common_ips))
            
            for ip in common_ips:
                if ip in [d['ip'] for d in discovered]:
                    continue
                    
                # Try factory credentials first
                camera = None
                mac = None
                try:
                    logger.debug(f"  Trying {ip} with factory credentials...")
                    camera = AxisCamera(ip, "", "root", "")
                    camera.setup_initial_password("pass")
                    mac = camera.get_mac_address()
                    
                    if mac and mac not in discovered_macs:
                        camera.mac = mac
                        discovered.append({
                            'ip': ip,
                            'mac': mac,
                            'method': 'subnet_scan',
                            'auth_method': 'factory',
                            'interface': interface_name,
                            'camera': camera
                        })
                        discovered_macs.add(mac)
                        logger.info(f"  [OK] Found camera at {ip} with MAC {mac} (factory credentials, via {interface_name})")
                except Exception as e:
                    logger.debug(f"  Factory credentials failed: {e}")
                    camera = None
                
                # If factory credentials failed, try CSV credentials
                if not camera and config_by_mac:
                    for cfg in config_by_mac.values():
                        try:
                            logger.debug(f"  Trying {ip} with CSV credentials ({cfg['username']})...")
                            camera = AxisCamera(ip, "", cfg['username'], cfg['password'])
                            mac = camera.get_mac_address()
                            
                            if mac and mac not in discovered_macs:
                                camera.mac = mac
                                discovered.append({
                                    'ip': ip,
                                    'mac': mac,
                                    'method': 'subnet_scan',
                                    'auth_method': 'csv_credentials',
                                    'interface': interface_name,
                                    'camera': camera
                                })
                                discovered_macs.add(mac)
                                logger.info(f"  [OK] Found camera at {ip} with MAC {mac} (CSV credentials, via {interface_name})")
                                break
                        except Exception as e:
                            logger.debug(f"  CSV credentials {cfg['username']} failed: {e}")
                            continue
                    
        except Exception as e:
            logger.debug(f"Error scanning interface {interface_name}: {e}")
    
    # Method 3: ARP-based discovery for DHCP cameras
    logger.info("\nMethod 3: ARP-based discovery for DHCP cameras...")
    
    # Normalize target MACs for comparison
    if target_macs:
        target_macs_normalized = [mac.upper().replace('-', ':') for mac in target_macs]
    else:
        target_macs_normalized = []
    
    for interface in interfaces:
        interface_ip = interface['ip']
        interface_name = interface['name']
        
        try:
            network = ipaddress.ip_network(f"{interface_ip}/24", strict=False)
            
            logger.info(f"ARP scan of '{interface_name}' subnet {network}...")
            
            # Step 1: Ping subnet to populate ARP table
            ping_subnet(network)
            
            # Step 2: Read ARP table
            arp_table = get_arp_table()
            
            # Step 3: Filter to only target MACs if provided
            ips_to_check = []
            if target_macs_normalized:
                for mac, ip in arp_table.items():
                    if mac in target_macs_normalized:
                        ips_to_check.append({'ip': ip, 'mac': mac})
                        logger.info(f"  Found target MAC {mac} at {ip}")
            else:
                # No filter - check all IPs in ARP table (for discovery mode)
                ips_to_check = [{'ip': ip, 'mac': mac} for mac, ip in arp_table.items()]
            
            logger.info(f"  Found {len(ips_to_check)} device(s) to check for cameras...")
            
            # Step 4: Try to connect only to filtered IPs
            for device in ips_to_check:
                ip = device['ip']
                mac = device['mac']
                
                # Skip if already discovered
                if mac in discovered_macs:
                    continue
                
                # Get credentials for this MAC from CSV
                cfg = config_by_mac.get(mac, {})
                csv_username = cfg.get('username', 'admin')
                csv_password = cfg.get('password', 'password')
                
                camera = None
                auth_method = None
                
                try:
                    # Try 1: Factory default credentials (root with empty password)
                    logger.debug(f"  Trying {ip} ({mac}) with factory credentials...")
                    camera = AxisCamera(ip, mac, "root", "")
                    camera.setup_initial_password("pass")  # Handle factory-fresh cameras
                    camera_mac = camera.get_mac_address()
                    
                    if camera_mac and camera_mac == mac:
                        auth_method = 'factory'
                        logger.info(f"  [OK] Found camera at {ip} with MAC {mac} (factory credentials)")
                    else:
                        camera = None
                except Exception as e:
                    logger.debug(f"  Factory credentials failed: {e}")
                    camera = None
                
                # Try 2: CSV credentials (for already-programmed cameras)
                if not camera and cfg:
                    try:
                        logger.debug(f"  Trying {ip} ({mac}) with CSV credentials ({csv_username})...")
                        camera = AxisCamera(ip, mac, csv_username, csv_password)
                        camera_mac = camera.get_mac_address()
                        
                        if camera_mac and camera_mac == mac:
                            auth_method = 'csv_credentials'
                            logger.info(f"  [OK] Found camera at {ip} with MAC {mac} (CSV credentials)")
                        else:
                            camera = None
                    except Exception as e:
                        logger.debug(f"  CSV credentials failed: {e}")
                        camera = None
                
                # If we successfully connected, add to discovered list
                if camera:
                    discovered.append({
                        'ip': ip,
                        'mac': mac,
                        'method': 'arp_discovery',
                        'auth_method': auth_method,
                        'interface': interface_name,
                        'camera': camera
                    })
                    discovered_macs.add(mac)
                else:
                    logger.debug(f"  Not a camera or auth failed: {ip} ({mac})")
            
        except Exception as e:
            logger.error(f"Error during ARP discovery on {interface_name}: {e}")
    
    logger.info(f"\nDiscovery complete. Found {len(discovered)} unique camera(s)")
    return discovered


def read_camera_config_csv(filename: str, skip_completed: bool = True) -> List[Dict]:
    """Read camera configuration from CSV file.
    
    Args:
        filename: Path to CSV file
        skip_completed: If True, skip cameras with Status='Completed' (default for CLI).
                       If False, load all cameras (useful for GUI).
    """
    configs = []
    
    try:
        with open(filename, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            # Verify required columns
            required_columns = ['MAC_Address', 'New_IP', 'Username', 'Password']
            if not all(col in reader.fieldnames for col in required_columns):
                logger.error(f"CSV missing required columns. Need: {required_columns}")
                return []
            
            for row in reader:
                # Skip empty rows
                if not row.get('MAC_Address'):
                    continue
                
                # Optionally skip completed cameras
                if skip_completed and row.get('Status') == 'Completed':
                    continue
                    
                configs.append({
                    'mac': row['MAC_Address'].upper().replace('-', ':'),
                    'new_ip': row['New_IP'],
                    'subnet_mask': row.get('Subnet_Mask', '255.255.255.0').strip(),
                    'gateway': row.get('Gateway', '').strip() or None,
                    'username': row['Username'],
                    'password': row['Password'],
                    'name': row.get('Camera_Name', '').strip(),
                    'timezone': row.get('Timezone', 'America/New_York').strip(),
                    'status': row.get('Status', '').strip(),
                    'original_row': row
                })
        
        logger.info(f"Loaded {len(configs)} camera configurations from CSV")
        return configs
        
    except FileNotFoundError:
        logger.error(f"CSV file not found: {filename}")
        return []
    except Exception as e:
        logger.error(f"Error reading CSV: {e}")
        return []


def update_csv_status(filename: str, mac: str, status: str, message: str = ""):
    """Update the status of a camera in the CSV file."""
    try:
        rows = []
        
        # Read all rows
        with open(filename, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            
            # Add Status and Message columns if they don't exist
            if 'Status' not in fieldnames:
                fieldnames = list(fieldnames) + ['Status', 'Message', 'Timestamp']
            
            for row in reader:
                if row['MAC_Address'].upper().replace('-', ':') == mac.upper().replace('-', ':'):
                    row['Status'] = status
                    row['Message'] = message
                    row['Timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                rows.append(row)
        
        # Write back all rows
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            
        logger.debug(f"Updated CSV status for {mac}: {status}")
        
    except Exception as e:
        logger.error(f"Error updating CSV: {e}")


def configure_camera(camera: AxisCamera, config: Dict, csv_filename: str) -> bool:
    """Configure a single camera with the provided settings."""
    mac = camera.mac
    logger.info(f"\n{'='*60}")
    logger.info(f"Configuring camera {mac}")
    logger.info(f"{'='*60}")
    
    try:
        update_csv_status(csv_filename, mac, 'In Progress', 'Starting configuration')
        
        # Step 1: Set credentials FIRST (while on stable connection at default IP)
        logger.info(f"Step 1/6: Setting credentials (user: {config['username']})...")
        if not camera.set_credentials(config['username'], config['password']):
            raise Exception("Failed to set credentials")
        
        # Step 2: Set date/time/timezone
        logger.info(f"Step 2/6: Setting timezone to {config.get('timezone', 'America/New_York')}...")
        camera.set_date_time(config.get('timezone', 'America/New_York'))  # Best effort, don't fail
        
        # Step 3: Set camera name (if provided)
        if config.get('name'):
            logger.info("Step 3/6: Setting camera name...")
            if not camera.set_camera_name(config['name']):
                logger.warning("Failed to set camera name (may not be supported on this model)")
        else:
            logger.info("Step 3/6: Skipping camera name (not provided)")
        
        # Step 4: Set zoom
        logger.info("Step 4/6: Setting zoom to minimum...")
        camera.zoom_out_fully()  # Best effort, don't fail if not available
        
        # Step 5: Set new IP address LAST (this may disrupt connection)
        subnet = config.get('subnet_mask', '255.255.255.0')
        gateway = config.get('gateway')
        if gateway:
            logger.info(f"Step 5/6: Setting IP to {config['new_ip']}, subnet {subnet}, gateway {gateway}...")
        else:
            logger.info(f"Step 5/6: Setting IP to {config['new_ip']}, subnet {subnet}...")
        old_ip = camera.ip
        if not camera.set_network_config(config['new_ip'], subnet, gateway):
            raise Exception(f"Failed to set IP to {config['new_ip']}")
        
        # Give camera time to reconfigure
        logger.info("Waiting for camera to apply network settings...")
        time.sleep(5)
        
        # Step 6: Verify configuration
        logger.info("Step 6/6: Verifying configuration...")
        if not camera.verify_configuration(config['new_ip'], config.get('name')):
            logger.warning("Configuration verification failed, but changes may have been applied")
            # Don't fail - verification can be flaky after network change
        
        # Success!
        update_csv_status(csv_filename, mac, 'Completed', f'Successfully configured')
        logger.info(f"[SUCCESS] Camera {mac} configured successfully!")
        logger.info(f"  New IP: {config['new_ip']}/{subnet}")
        if gateway:
            logger.info(f"  Gateway: {gateway}")
        logger.info(f"  Username: {config['username']}")
        logger.info(f"  Name: {config.get('name', 'N/A')}")
        logger.info(f"  Timezone: {config.get('timezone', 'N/A')}")
        
        return True
        
    except Exception as e:
        error_msg = f"Configuration failed: {str(e)}"
        logger.error(f"[FAILED] {error_msg}")
        update_csv_status(csv_filename, mac, 'Failed', error_msg)
        return False


def main():
    """Main program execution."""
    print("\n" + "="*70)
    print(" "*15 + "Axis Camera Batch Programmer")
    print("="*70 + "\n")
    
    csv_filename = "camera_config.csv"
    
    # Step 1: Read configuration from CSV
    logger.info("Step 1: Reading camera configurations from CSV...")
    configs = read_camera_config_csv(csv_filename)
    
    if not configs:
        logger.error("No camera configurations loaded. Please check your CSV file.")
        logger.info(f"Expected CSV file: {csv_filename}")
        logger.info("Required columns: MAC_Address, New_IP, Username, Password, Camera_Name")
        return
    
    print(f"\nLoaded {len(configs)} camera(s) to configure:\n")
    for i, cfg in enumerate(configs, 1):
        print(f"  {i}. MAC: {cfg['mac']}")
        print(f"     New IP: {cfg['new_ip']}/{cfg.get('subnet_mask', '255.255.255.0')}")
        if cfg.get('gateway'):
            print(f"     Gateway: {cfg['gateway']}")
        print(f"     Name: {cfg.get('name', 'N/A')}")
        print()
    
    input("Press Enter to start discovery and configuration...")
    
    # Step 2: Discover cameras on network
    logger.info("\nStep 2: Discovering cameras on network...")
    
    # Pass full configs to discovery (for MAC filtering and credential lookup)
    logger.info(f"Will search for {len(configs)} camera(s) matching CSV MAC addresses")
    
    discovered = discover_cameras_on_network(configs)
    
    if not discovered:
        logger.error("No cameras discovered on network!")
        logger.info("\nTroubleshooting tips:")
        logger.info("  1. Ensure cameras are powered on and connected")
        logger.info(f"  2. Verify your computer can reach {DEFAULT_IP}")
        logger.info("  3. Check that cameras are set to factory defaults")
        return
    
    print(f"\nDiscovered {len(discovered)} camera(s) on network\n")
    
    # Step 3: Match and configure each camera
    logger.info("\nStep 3: Configuring cameras...")
    
    configured_count = 0
    failed_count = 0
    
    for discovered_cam in discovered:
        mac = discovered_cam['mac']
        ip = discovered_cam['ip']
        
        # Find matching configuration
        config = next((c for c in configs if c['mac'] == mac), None)
        
        if not config:
            logger.warning(f"Camera {mac} at {ip} not found in CSV - skipping")
            continue
        
        # Use camera object from discovery if available (already has auth set up)
        # Otherwise create new one with default credentials
        if 'camera' in discovered_cam:
            camera = discovered_cam['camera']
        else:
            camera = AxisCamera(ip, mac, DEFAULT_USER, DEFAULT_PASS)
        
        # Configure it
        if configure_camera(camera, config, csv_filename):
            configured_count += 1
        else:
            failed_count += 1
        
        print()  # Blank line between cameras
    
    # Final summary
    print("\n" + "="*70)
    print("Configuration Complete!")
    print("="*70)
    print(f"\nResults:")
    print(f"  [OK] Successfully configured: {configured_count}")
    print(f"  [X] Failed: {failed_count}")
    print(f"  [-] Not found on network: {len(configs) - configured_count - failed_count}")
    print(f"\nDetails saved to: axis_programmer.log")
    print(f"Status updated in: {csv_filename}")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        logger.info("Program terminated by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print(f"\nFatal error: {e}")
