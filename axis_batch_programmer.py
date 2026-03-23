#!/usr/bin/env python3
"""
Axis Camera Batch Programmer
Discovers factory-fresh Axis P3267-LV cameras via DHCP/ARP and configures them based on CSV data.
Automates initial setup (password, EULA) and batch configuration.
"""

import csv
import socket
import requests
import time
import ipaddress
import os
from datetime import datetime
from typing import Dict, List, Optional
from requests.auth import HTTPDigestAuth
import logging
import psutil
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import re
from urllib.parse import quote

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
DEFAULT_IP = "192.168.0.90"  # Older models only - P3267-LV uses DHCP
DEFAULT_USER = "root"  # Most Axis cameras use "root" (including P3267-LV)
DEFAULT_PASS = ""  # Factory default has no password
FACTORY_INITIAL_PASSWORD = "pass"  # Temporary password to set on factory-fresh cameras during discovery
# NOTE: P3267-LV and newer models require:
#   1. Accepting EULA/terms checkbox on first boot
#   2. Setting "root" password via the initial setup form
#   The setup_initial_password() method handles both automatically
VAPIX_TIMEOUT = 30  # For managed switches with rate limiting, increase to 30-60 seconds
NETWORK_CONFIG_TIMEOUT = 60  # Longer timeout for network changes (important for VLANs)
NETWORK_VERIFY_TIMEOUT = 45  # Timeout for verifying network changes
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

def normalize_mac_address(mac: str) -> str:
    """Normalize MAC address to consistent format with colons.
    
    Handles multiple input formats:
    - B8:A4:4F:FF:2E:D7 (colon format)
    - B8-A4-4F-FF-2E-D7 (dash format) 
    - B8A44FFF2ED7 (no separator)
    - b8:a4:4f:ff:2e:d7 (lowercase)
    
    Returns:
        MAC in uppercase colon format: "B8:A4:4F:FF:2E:D7"
    """
    # Remove all separators and convert to uppercase
    clean_mac = mac.upper().replace(':', '').replace('-', '').replace('.', '')
    
    # Validate length
    if len(clean_mac) != 12:
        raise ValueError(f"Invalid MAC address length: {mac}")
    
    # Insert colons every 2 characters
    formatted_mac = ':'.join(clean_mac[i:i+2] for i in range(0, 12, 2))
    return formatted_mac


def convert_timezone(tz_name: str) -> str:
    """Convert common timezone name to POSIX format.
    
    Args:
        tz_name: Timezone name (e.g., "America/New_York", "Eastern", "America/Denver (GMT -6)")
    
    Returns:
        POSIX timezone string (e.g., "EST5EDT,M3.2.0,M11.1.0")
        If not found in map, returns input as-is (assumes already POSIX format)
    """
    # Strip any GMT offset information in parentheses (e.g., "America/Denver (GMT -6)" -> "America/Denver")
    tz_name_clean = re.sub(r'\s*\([^)]*\)\s*', '', tz_name).strip()
    
    return TIMEZONE_MAP.get(tz_name_clean, tz_name_clean)


class AxisCamera:
    """Represents an Axis camera with configuration methods."""
    
    def __init__(self, ip: str, mac: str, username: str = DEFAULT_USER, password: str = DEFAULT_PASS):
        self.ip = ip
        self.mac = normalize_mac_address(mac)  # Handles all MAC formats
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.auth = HTTPDigestAuth(username, password)
        
        # CRITICAL FIX: Disable proxy for direct camera connections
        # Corporate laptops often have proxy settings that break direct IP connections
        self.session.trust_env = False  # Ignore system proxy settings
        self.session.proxies = {
            'http': None,
            'https': None
        }
        
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
                logger.warning(f"No MAC address found in response from {self.ip}")
            elif response.status_code == 401:
                logger.warning(f"Authentication failed at {self.ip} (401 Unauthorized) - Wrong credentials?")
            elif response.status_code == 403:
                logger.warning(f"Access forbidden at {self.ip} (403 Forbidden) - Check user permissions")
            else:
                logger.warning(f"Unexpected response from {self.ip}: {response.status_code}")
        except requests.exceptions.ConnectTimeout:
            logger.warning(f"Connection timeout to {self.ip} - Camera may be slow or unreachable")
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"Connection error to {self.ip}: {str(e)[:100]}")
        except Exception as e:
            logger.warning(f"Failed to get MAC from {self.ip}: {type(e).__name__}: {str(e)[:100]}")
        return None
    
    def setup_initial_password(self, password: str = "pass") -> bool:
        """Set initial admin password on factory-fresh camera.
        
        Factory-reset cameras require accepting EULA/terms and setting the admin password 
        via the web setup before API access is allowed. This automates that initial setup.
        
        P3267-LV shows "root" username on initial setup page and requires EULA acceptance.
        
        Returns:
            True if setup was attempted (camera was in setup mode)
            False if camera not in setup mode (already configured)
        """
        try:
            # Try multiple URLs - different firmware versions use different paths
            # P3225: http://IP/ redirects to setup
            # P3267: http://IP/camera/index.html is the setup page
            setup_check_urls = [
                f"http://{self.ip}/camera/index.html",  # P3267 and newer
                f"http://{self.ip}/",                    # P3225 and older
            ]
            
            response = None
            for check_url in setup_check_urls:
                try:
                    logger.info(f"  Trying setup URL: {check_url}")
                    response = requests.get(check_url, timeout=10, proxies={'http': None, 'https': None}, allow_redirects=True)
                    logger.info(f"  Response: status={response.status_code}, length={len(response.text)} bytes, final_url={response.url}")
                    if response.status_code == 200 and len(response.text) > 200:  # Must be substantial content
                        logger.info(f"  ✓ Found substantial content at {check_url}")
                        break
                    else:
                        logger.info(f"  ✗ Response too small or wrong status, trying next URL...")
                except Exception as e:
                    logger.info(f"  ✗ Request failed: {e}")
                    continue
            
            if not response or response.status_code != 200:
                logger.info(f"  ✗ Could not access any initial setup page for {self.ip}")
                return False
            
            # P3267 firmware uses a JavaScript SPA (single-page app) for setup
            # The /camera/index.html returns only ~861 bytes of skeleton HTML
            # All content (passwords, EULA, etc.) is rendered by JavaScript after page load
            # We can't parse the content, so we detect setup mode by:
            # 1. If we got /camera/index.html with status 200 and small size, attempt setup
            # 2. If we got / and it contains setup indicators, attempt setup
            
            response_text = response.text.lower()
            is_spa_setup_page = False
            is_traditional_setup_page = False
            
            # Check if this is P3267-style SPA setup page (small HTML skeleton)
            if '/camera/index.html' in response.url and len(response.text) < 2000:
                logger.info(f"  Detected P3267 JavaScript SPA setup page (skeleton size: {len(response.text)} bytes)")
                is_spa_setup_page = True
            
            # Check if this is traditional setup page with content indicators
            indicators = {
                'set a password': 'set a password' in response_text,
                'pwdroot in URL': 'pwdroot' in response.url.lower(),
                'setpassword in URL': 'setpassword' in response.url.lower(),
                'add user': 'add user' in response_text,
                'EULA': 'end user license agreement' in response_text,
            }
            
            if any(indicators.values()):
                logger.info(f"  Detected traditional setup page with content indicators: {indicators}")
                is_traditional_setup_page = True
            
            is_setup_page = is_spa_setup_page or is_traditional_setup_page
            
            if not is_setup_page:
                # Camera not in initial setup mode - already configured
                logger.info(f"  ✗ Camera at {self.ip} not in initial setup mode")
                return False
            
            logger.info(f"Camera at {self.ip} IS in initial setup mode - attempting automation...")
            
            # P3267 firmware 10.12.240+ uses pwdgrp.cgi with GET method and Digest auth
            # Discovery via browser DevTools: GET /axis-cgi/pwdgrp.cgi?action=add&user=root&pwd={password}&grp=root&sgrp=admin:operator:viewer:ptz
            
            username = 'root'
            logger.info(f"  Setting up initial user '{username}' with password...")
            
            # Create a temporary session with the NEW password for Digest auth
            # P3267 accepts Digest auth with the password being set during initial setup
            temp_session = requests.Session()
            temp_session.auth = HTTPDigestAuth(username, password)
            temp_session.trust_env = False
            temp_session.proxies = {'http': None, 'https': None}
            
            # Build the pwdgrp.cgi URL with parameters
            # action=add: Create new user
            # user=root: Username
            # pwd={password}: Password to set
            # grp=root: Primary group
            # sgrp=admin:operator:viewer:ptz: Secondary groups (full permissions)
            setup_url = (
                f"http://{self.ip}/axis-cgi/pwdgrp.cgi?"
                f"action=add&user={username}&pwd={password}&grp=root&sgrp=admin:operator:viewer:ptz"
            )
            
            try:
                logger.info(f"  GET request to: {setup_url.replace(f'pwd={password}', 'pwd=****')}")
                response = temp_session.get(setup_url, timeout=15, allow_redirects=False)
                
                logger.info(f"  Response: status={response.status_code}, Content-Type={response.headers.get('Content-Type', 'unknown')}")
                logger.info(f"  Response body: {response.text[:200]}")
                
                # Success indicators: 200 OK, or response contains "OK" or "Created account"
                if response.status_code == 200 and ('ok' in response.text.lower() or 'created' in response.text.lower() or len(response.text.strip()) == 0):
                    logger.info(f"  ✓ Password set successfully for {self.ip} (username: {username})")
                    
                    # Update our session with the new credentials
                    self.username = username
                    self.password = password
                    self.session.auth = HTTPDigestAuth(username, password)
                    
                    return True
                else:
                    logger.warning(f"  ✗ Setup request returned unexpected response")
                    logger.warning(f"  Status: {response.status_code}, Body: {response.text[:500]}")
                    
            except Exception as e:
                logger.warning(f"  ✗ Setup request failed: {e}")
            
            # If we got here, all setup attempts failed
            logger.warning(f"All initial setup attempts failed for {self.ip}")
            logger.warning(f"Camera requires MANUAL web setup: http://{self.ip}/")
            return True  # Setup was needed but automation failed
            
        except Exception as e:
            logger.warning(f"Error during initial password setup check: {e}")
            return False  # Couldn't determine setup status
    
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
            try:
                response = self.session.get(url + "?" + param_string, timeout=NETWORK_CONFIG_TIMEOUT)
                
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
                    
            except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout, ConnectionResetError) as conn_err:
                # Connection dropped or timed out during IP change - this is NORMAL!
                # Camera closes connection while reconfiguring network or times out before responding
                logger.info(f"Connection interrupted during IP change (expected) - waiting for camera to reconfigure...")
                logger.debug(f"Connection error details: {conn_err}")
                
                # Update our IP to the new one and wait for camera to come back online
                self.ip = new_ip
                
                # For VLAN environments, give extra time for routing table updates
                logger.info("Waiting 15 seconds for network changes and routing updates...")
                time.sleep(15)
                
                # Try multiple times to verify the new IP is reachable (important for VLANs)
                max_verify_attempts = 5
                verify_delay = 5  # seconds between attempts
                
                for attempt in range(1, max_verify_attempts + 1):
                    try:
                        logger.info(f"Verification attempt {attempt}/{max_verify_attempts}: Checking camera at {new_ip}...")
                        test_url = f"http://{new_ip}/axis-cgi/param.cgi?action=list&group=Network.eth0"
                        test_response = self.session.get(test_url, timeout=NETWORK_VERIFY_TIMEOUT)
                        
                        if test_response.status_code == 200:
                            logger.info(f"✓ Camera successfully reconfigured and online at {new_ip}")
                            return True
                        else:
                            logger.warning(f"Camera responded at {new_ip} but with status {test_response.status_code}")
                            if attempt < max_verify_attempts:
                                logger.info(f"Retrying in {verify_delay} seconds...")
                                time.sleep(verify_delay)
                            else:
                                # Last attempt - accept any response as success
                                logger.info("Camera responding - assuming network change succeeded")
                                return True
                                
                    except Exception as verify_err:
                        if attempt < max_verify_attempts:
                            logger.warning(f"Verification attempt {attempt} failed: {verify_err}")
                            logger.info(f"Retrying in {verify_delay} seconds...")
                            time.sleep(verify_delay)
                        else:
                            logger.error(f"Could not verify new IP {new_ip} after {max_verify_attempts} attempts")
                            logger.error(f"Last error: {verify_err}")
                            logger.warning("Network change may have failed - searching for camera at old IP or default IP...")
                            
                            # Try to find camera at old IP or default IP and retry
                            search_ips = [old_ip, '192.168.0.90']
                            found_ip = None
                            
                            for search_ip in search_ips:
                                if search_ip == new_ip:
                                    continue  # Already tried this
                                    
                                try:
                                    logger.info(f"Checking if camera is at {search_ip}...")
                                    # Update session to point to search IP temporarily
                                    test_url = f"http://{search_ip}/axis-cgi/param.cgi?action=list&group=Brand"
                                    test_session = requests.Session()
                                    test_session.auth = HTTPDigestAuth(self.username, self.password)
                                    test_response = test_session.get(test_url, timeout=10)
                                    
                                    if test_response.status_code == 200:
                                        logger.info(f"✓ Found camera at {search_ip}!")
                                        found_ip = search_ip
                                        self.ip = search_ip
                                        self.session = test_session
                                        break
                                except Exception as search_err:
                                    logger.debug(f"Camera not at {search_ip}: {search_err}")
                                    continue
                            
                            if found_ip:
                                logger.info(f"Camera found at {found_ip}, retrying network configuration to {new_ip}...")
                                logger.info("Waiting 5 seconds before retry...")
                                time.sleep(5)
                                
                                # Retry the network configuration
                                try:
                                    param_string = f"action=update&root.Network.IPAddress={new_ip}&root.Network.SubnetMask={subnet_mask}"
                                    if gateway:
                                        param_string += f"&root.Network.DefaultRouter={gateway}"
                                    
                                    url = f"http://{self.ip}/axis-cgi/param.cgi"
                                    retry_response = self.session.get(url + "?" + param_string, timeout=NETWORK_CONFIG_TIMEOUT)
                                    
                                    logger.info(f"Retry network config sent, waiting 15 seconds...")
                                    self.ip = new_ip
                                    time.sleep(15)
                                    
                                    # Verify after retry
                                    test_url = f"http://{new_ip}/axis-cgi/param.cgi?action=list&group=Network.eth0"
                                    final_test = self.session.get(test_url, timeout=NETWORK_VERIFY_TIMEOUT)
                                    
                                    if final_test.status_code == 200:
                                        logger.info(f"✓ RETRY SUCCESSFUL: Camera now at {new_ip}")
                                        return True
                                    else:
                                        logger.warning(f"Retry verification returned status {final_test.status_code}")
                                        logger.warning(f"Camera may still be at {found_ip} - check manually")
                                        return False
                                        
                                except Exception as retry_err:
                                    logger.error(f"Retry failed: {retry_err}")
                                    logger.error(f"Camera may still be at {found_ip}")
                                    return False
                            else:
                                logger.error(f"Could not find camera at {new_ip}, {old_ip}, or 192.168.0.90")
                                logger.error("Manual intervention may be required")
                                return False
                    
        except Exception as e:
            logger.error(f"Unexpected error setting network config: {e}")
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
            
            # Set POSIX timezone - URL encode the timezone string to handle special characters
            posix_tz_encoded = quote(posix_tz, safe='')
            param_string = f"action=update&root.Time.POSIXTimeZone={posix_tz_encoded}"
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
    
    def set_resolution(self, width: int = 1024, height: int = 768) -> bool:
        """Set camera resolution.
        
        Args:
            width: Resolution width in pixels (default: 1024)
            height: Resolution height in pixels (default: 768)
        
        Note: Some cameras may briefly disconnect when resolution changes.
        This function handles connection errors gracefully and won't fail the configuration.
        """
        try:
            url = f"http://{self.ip}/axis-cgi/param.cgi"
            
            # Try multiple possible parameter names for resolution
            # Different Axis camera models/firmware use different parameters
            # P3267-LV confirmed working: root.Image.I0.Appearance.Resolution
            resolution_params = [
                f"root.Image.I0.Appearance.Resolution={width}x{height}",  # P3267-LV, P3225 (most common)
                f"root.Image.I0.Stream.1.Resolution={width}x{height}",  # Stream-specific
                f"root.Properties.Image.Resolution={width}x{height}",  # Global properties
                f"root.ImageSource.I0.Sensor.Resolution={width}x{height}",  # Sensor resolution
            ]
            
            for param in resolution_params:
                try:
                    param_string = f"action=update&{param}"
                    logger.info(f"Trying resolution parameter: {param.split('=')[0]}")
                    response = self.session.get(url + "?" + param_string, timeout=VAPIX_TIMEOUT)
                    
                    # Success is indicated by HTTP 200 with "OK" response (not containing "Error")
                    if response.status_code == 200:
                        response_text = response.text.strip()
                        if response_text == "OK" or (response_text and "error" not in response_text.lower()):
                            logger.info(f"✓ Resolution set to {width}x{height} for {self.mac}")
                            logger.info(f"  Used parameter: {param.split('=')[0]}")
                            
                            # Some cameras may briefly disconnect after resolution change
                            # Wait a moment and recreate session if needed
                            time.sleep(2)
                            return True
                        else:
                            logger.debug(f"  Response: {response_text[:100]}")
                    else:
                        logger.debug(f"  HTTP {response.status_code}")
                
                except requests.exceptions.ConnectionError as conn_err:
                    # Camera may have briefly disconnected due to resolution change
                    logger.info(f"  Connection interrupted (camera may be adjusting resolution)")
                    logger.info(f"  Waiting for camera to stabilize...")
                    time.sleep(3)
                    
                    # Try to reconnect with a fresh session
                    try:
                        self.session = requests.Session()
                        self.session.auth = HTTPDigestAuth(self.username, self.password)
                        # Test reconnection
                        test_response = self.session.get(f"http://{self.ip}/axis-cgi/param.cgi?action=list&group=Brand", timeout=10)
                        if test_response.status_code == 200:
                            logger.info(f"  ✓ Reconnected successfully")
                            # Resolution may have been set despite connection error
                            return True
                        else:
                            logger.warning(f"  Reconnection returned status {test_response.status_code}")
                    except Exception as reconnect_err:
                        logger.warning(f"  Reconnection failed: {reconnect_err}")
                    
                    # Continue trying other parameters
                    continue
                
                except Exception as param_err:
                    logger.debug(f"  Error with this parameter: {param_err}")
                    continue
            
            # If none worked, log warning but don't fail
            logger.warning(f"Could not confirm resolution set to {width}x{height} - may not be supported or camera disconnected")
            logger.warning(f"Resolution remains at camera default")
            return True  # Don't fail - may not be supported on all models
                
        except Exception as e:
            logger.warning(f"Error setting resolution for {self.mac}: {e}")
            logger.warning(f"Continuing with configuration...")
            return True  # Don't fail the whole process for resolution
    
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
    
    def get_firmware_version(self) -> Optional[str]:
        """Get current firmware version.
        
        Returns:
            Firmware version string (e.g., "10.12.240") or None if unable to retrieve
        """
        try:
            url = f"http://{self.ip}/axis-cgi/param.cgi?action=list&group=root.Properties.Firmware"
            response = self.session.get(url, timeout=VAPIX_TIMEOUT)
            
            if response.status_code == 200:
                for line in response.text.split('\n'):
                    if 'Version' in line:
                        version = line.split('=')[1].strip()
                        logger.info(f"Current firmware version: {version}")
                        return version
            
            logger.warning(f"Could not retrieve firmware version from {self.ip}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting firmware version: {e}")
            return None
    
    def upgrade_firmware(self, firmware_path: str, progress_callback=None) -> bool:
        """Upload and install firmware update.
        
        Args:
            firmware_path: Path to .bin firmware file
            progress_callback: Optional callback function(stage, message) for progress updates
        
        Returns:
            True if upgrade successful, False otherwise
        """
        try:
            if not os.path.exists(firmware_path):
                logger.error(f"Firmware file not found: {firmware_path}")
                return False
            
            firmware_filename = os.path.basename(firmware_path)
            logger.info(f"Starting firmware upgrade for {self.mac} using {firmware_filename}")
            
            if progress_callback:
                progress_callback("validating", "Checking current firmware...")
            
            current_version = self.get_firmware_version()
            if current_version:
                logger.info(f"Current firmware: {current_version}")
            
            # Step 1: Upload firmware file
            if progress_callback:
                progress_callback("uploading", "Uploading firmware file...")
            
            logger.info(f"Uploading firmware file ({os.path.getsize(firmware_path) / 1024 / 1024:.1f} MB)...") 
            
            # Try simple binary POST first (works on many Axis cameras)
            url = f"http://{self.ip}/axis-cgi/firmwaremanagement.cgi?method=upgrade"
            
            with open(firmware_path, 'rb') as f:
                # Send raw binary file as request body
                headers = {'Content-Type': 'application/octet-stream'}
                response = self.session.post(url, data=f, headers=headers, timeout=600)
            
            logger.info(f"Firmware upload response: HTTP {response.status_code}")
            logger.info(f"Response content: {response.text[:500]}")  # Changed to INFO to always see it
            
            if response.status_code == 200:
                logger.info("Firmware upload successful")
                
                # Check if response contains JSON error (even with 200 status)
                has_json_error = False
                try:
                    response_json = response.json()
                    if 'error' in response_json:
                        logger.warning(f"Upload returned error in JSON: {response_json['error'].get('message', 'Unknown error')}")
                        has_json_error = True
                except ValueError:
                    # Not JSON, continue with normal processing
                    pass
                
                if not has_json_error:
                    if progress_callback:
                        progress_callback("installing", "Installing firmware (camera will reboot)...")
                    
                    # Check response for success indicators
                    response_text = response.text.lower()
                    
                    # VAPIX 3 returns JSON with data field on success
                    try:
                        response_json = response.json()
                        if 'data' in response_json and 'firmwareVersion' in response_json.get('data', {}):
                            new_fw_version = response_json['data']['firmwareVersion']
                            logger.info(f"Firmware upgrade accepted! Target version: {new_fw_version}")
                            logger.info("Camera will reboot - this may take 5-10 minutes")
                            
                            if progress_callback:
                                progress_callback("rebooting", "Waiting for camera to reboot (5-10 minutes)...")
                            
                            # Wait for camera to reboot
                            logger.info("Waiting 2 minutes before checking camera status...")
                            time.sleep(120)
                            
                            # NOTE: Firmware upgrade may change camera IP!
                            # Camera temporarily enables DHCP during upgrade, gets new IP,
                            # then converts DHCP address to static. We need to find it by MAC.
                            original_ip = self.ip
                            camera_found = False
                            
                            # Poll for camera to come back online (up to 10 minutes)
                            max_attempts = 60
                            for attempt in range(max_attempts):
                                try:
                                    # Try original IP first
                                    test_response = self.session.get(
                                        f"http://{self.ip}/axis-cgi/param.cgi?action=list&group=root.Properties.Firmware",
                                        timeout=10
                                    )
                                    
                                    if test_response.status_code == 200:
                                        camera_found = True
                                        break
                                        
                                except:
                                    # Camera not at original IP - it may have moved during firmware upgrade
                                    if attempt % 6 == 0:  # Every minute
                                        logger.info(f"Camera not responding at {self.ip}, scanning for new IP...")
                                        
                                        # Scan ARP table for camera by MAC address
                                        try:
                                            import subprocess
                                            result = subprocess.run(['arp', '-a'], capture_output=True, text=True, timeout=5)
                                            
                                            # Look for our MAC in ARP table
                                            target_mac_formats = [
                                                self.mac.replace(':', '-').lower(),  # Windows format
                                                self.mac.lower(),  # Colon format
                                            ]
                                            
                                            for line in result.stdout.split('\n'):
                                                for mac_format in target_mac_formats:
                                                    if mac_format in line.lower():
                                                        # Extract IP from line
                                                        parts = line.split()
                                                        if len(parts) >= 1:
                                                            potential_ip = parts[0].strip()
                                                            if potential_ip != self.ip and '.' in potential_ip:
                                                                logger.info(f"Found camera at new IP: {potential_ip} (was {self.ip})")
                                                                self.ip = potential_ip
                                                                break
                                        except:
                                            pass
                                
                                if attempt % 6 == 0:  # Log every minute
                                    logger.info(f"Still waiting for camera to come online... ({attempt * 10}s elapsed)")
                                
                                time.sleep(10)
                            
                            if camera_found:
                                # Camera is back online - verify new firmware
                                new_version = self.get_firmware_version()
                                
                                if progress_callback:
                                    progress_callback("complete", f"Firmware upgrade complete: {new_version}")
                                
                                logger.info(f"✓ Firmware upgrade successful!")
                                logger.info(f"  Old version: {current_version}")
                                logger.info(f"  New version: {new_version}")
                                if self.ip != original_ip:
                                    logger.warning(f"  Camera IP changed during upgrade: {original_ip} → {self.ip}")
                                return True
                            else:
                                logger.error("Timeout waiting for camera to come back online after firmware upgrade")
                                logger.warning("Camera may still be upgrading - check manually after a few minutes")
                                return False
                    except ValueError:
                        pass  # Not JSON, continue checking text
                    
                    # Fallback: Check for text-based success indicators
                    if 'ok' in response_text or 'success' in response_text:
                        logger.info("Firmware upgrade initiated - camera will reboot")
                        logger.info("This may take 5-10 minutes. Camera will be unavailable during upgrade.")
                        
                        if progress_callback:
                            progress_callback("rebooting", "Waiting for camera to reboot (5-10 minutes)...")
                        
                        # Wait for camera to reboot and come back online
                        logger.info("Waiting 2 minutes before checking camera status...")
                        time.sleep(120)
                        
                        # Poll for camera to come back online (up to 10 minutes)
                        max_attempts = 60  # 10 minutes (10 second intervals)
                        for attempt in range(max_attempts):
                            try:
                                test_response = self.session.get(
                                    f"http://{self.ip}/axis-cgi/param.cgi?action=list&group=root.Properties.Firmware",
                                    timeout=10
                                )
                                
                                if test_response.status_code == 200:
                                    # Camera is back online - verify new firmware
                                    new_version = self.get_firmware_version()
                                    
                                    if progress_callback:
                                        progress_callback("complete", f"Firmware upgrade complete: {new_version}")
                                    
                                    logger.info(f"✓ Firmware upgrade successful!")
                                    logger.info(f"  Old version: {current_version}")
                                    logger.info(f"  New version: {new_version}")
                                    return True
                                    
                            except:
                                pass  # Camera still rebooting
                            
                            if attempt % 6 == 0:  # Log every minute
                                logger.info(f"Still waiting for camera to come online... ({attempt * 10}s elapsed)")
                            
                            time.sleep(10)
                        
                        logger.error("Timeout waiting for camera to come back online after firmware upgrade")
                        logger.warning("Camera may still be upgrading - check manually after a few minutes")
                        return False
                    else:
                        logger.warning(f"Unexpected response from firmware upgrade: {response.text[:200]}")
                        # Fall through to legacy method
                else:
                    logger.info("Modern API returned error - will try legacy method")
                    # Fall through to legacy method
            
            # If we get here, try legacy method (either status != 200 or unexpected response)
            if response.status_code != 200:
                logger.error(f"Firmware upload failed: HTTP {response.status_code}")
                logger.debug(f"Response: {response.text[:200]}")
            
            # Try older upgrade method for compatibility
            logger.info("Trying legacy upgrade method...")
            url = f"http://{self.ip}/axis-cgi/admin/upgrade.cgi"
            
            with open(firmware_path, 'rb') as f:
                files = {'file': (firmware_filename, f, 'application/octet-stream')}
                response = self.session.post(url, files=files, timeout=600)
            
            if response.status_code == 200:
                logger.info("Firmware upload successful (legacy method)")
                logger.info("Firmware upgrade initiated - camera will reboot")
                logger.info("This may take 5-10 minutes. Camera will be unavailable during upgrade.")
                
                if progress_callback:
                    progress_callback("rebooting", "Waiting for camera to reboot (5-10 minutes)...")
                
                # Wait for camera to reboot
                logger.info("Waiting 2 minutes before checking camera status...")
                time.sleep(120)
                
                # Poll for camera to come back online
                max_attempts = 60
                for attempt in range(max_attempts):
                    try:
                        test_response = self.session.get(
                            f"http://{self.ip}/axis-cgi/param.cgi?action=list&group=root.Properties.Firmware",
                            timeout=10
                        )
                        
                        if test_response.status_code == 200:
                            new_version = self.get_firmware_version()
                            
                            if progress_callback:
                                progress_callback("complete", f"Firmware upgrade complete: {new_version}")
                            
                            logger.info(f"✓ Firmware upgrade successful!")
                            logger.info(f"  Old version: {current_version}")
                            logger.info(f"  New version: {new_version}")
                            return True
                            
                    except:
                        pass
                    
                    if attempt % 6 == 0:
                        logger.info(f"Still waiting for camera to come online... ({attempt * 10}s elapsed)")
                    
                    time.sleep(10)
                
                logger.error("Timeout waiting for camera after legacy upgrade")
                return False
            else:
                logger.error(f"Legacy firmware upload also failed: HTTP {response.status_code}")
                if response.status_code == 404:
                    logger.error("Legacy upgrade endpoint not available on this firmware version")
                    logger.error("This camera requires the modern firmwaremanagement.cgi API")
                logger.debug(f"Response: {response.text[:200]}")
                return False
                    
        except Exception as e:
            logger.error(f"Error during firmware upgrade: {e}")
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
                    mac = normalize_mac_address(match.group(2))
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
                    mac = normalize_mac_address(match.group(2))
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
    logger.info("Proxy bypass is ENABLED for direct camera connections (fixes corporate laptop issues)")
    
    
    # Extract target MACs from configs and normalize them
    target_macs = []
    config_by_mac = {}
    if configs:
        for cfg in configs:
            mac = normalize_mac_address(cfg['mac'])  # Normalize MAC from CSV
            target_macs.append(mac)
            config_by_mac[mac] = cfg
        logger.info(f"Searching for {len(target_macs)} specific camera MAC(s) from CSV")
    
    # Get all active network interfaces
    interfaces = get_active_network_interfaces()
    
    if not interfaces:
        logger.warning("No active network interfaces found!")
        return discovered
    
    logger.info(f"Scanning {len(interfaces)} active network interface(s)...\n")
    # P3267-LV cameras use DHCP on first boot - no static 192.168.0.90 scanning needed
    # ARP-based discovery finds cameras at whatever DHCP address they received
    
    # ARP-based discovery for DHCP cameras
    logger.info("\nARP-based discovery (for DHCP factory-reset cameras)...")
    
    # Target MACs are already normalized by config processing above
    target_macs_normalized = target_macs
    
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
                
                # FIRST: Check if camera is in initial setup mode (factory-fresh)
                # This must be done BEFORE trying authentication
                logger.info(f"  Checking if {ip} ({mac}) is in initial setup mode...")
                setup_success = False
                try:
                    # Create temporary camera object just for setup check
                    temp_camera = AxisCamera(ip, mac, "root", "")
                    setup_result = temp_camera.setup_initial_password(FACTORY_INITIAL_PASSWORD)
                    
                    # Verify the setup actually worked by testing authentication
                    if setup_result:
                        time.sleep(3)  # Give camera time to complete setup
                        
                        # Try to authenticate with the password we just set
                        logger.debug(f"  Verifying initial setup by testing authentication...")
                        test_camera = AxisCamera(ip, mac, "root", FACTORY_INITIAL_PASSWORD)
                        test_mac = test_camera.get_mac_address()
                        
                        if test_mac:
                            logger.info(f"  ✓ Initial setup completed successfully - camera now has root/{FACTORY_INITIAL_PASSWORD}")
                            setup_success = True
                        else:
                            logger.warning(f"  ⚠ Initial setup attempted but verification failed")
                            logger.warning(f"  Camera may require MANUAL web setup: http://{ip}/")
                    
                except Exception as e:
                    logger.debug(f"  Initial setup check error: {e}")
                
                # If setup automation failed, check if it's truly in setup mode or just needs CSV credentials
                if not setup_success:
                    # Check if camera responds to unauthenticated requests (true setup mode)
                    # vs. requires authentication (already configured)
                    try:
                        test_url = f"http://{ip}/axis-cgi/param.cgi?action=list&group=Network"
                        test_resp = requests.get(test_url, timeout=5, proxies={'http': None, 'https': None})
                        
                        # 401 means authentication required - could be setup mode OR already configured
                        # We should still try CSV credentials
                        if test_resp.status_code == 401:
                            logger.info(f"  Camera at {ip} requires authentication - will try CSV credentials")
                        elif test_resp.status_code == 200:
                            # Camera responding without auth - unusual but proceed
                            logger.debug(f"  Camera at {ip} responding without authentication")
                    except:
                        pass
                
                # NOW: Try factory credentials - different models use different defaults
                factory_credentials = [
                    ("root", ""),      # Most Axis cameras (older models) - no password set
                    ("admin", ""),     # Newer models - no password set
                    ("root", FACTORY_INITIAL_PASSWORD),   # Factory-fresh after our setup
                    ("admin", FACTORY_INITIAL_PASSWORD),  # Newer models after our setup
                ]
                
                for factory_user, factory_pass in factory_credentials:
                    try:
                        pass_desc = "empty" if factory_pass == "" else factory_pass
                        logger.info(f"  Attempting {ip} ({mac}) with factory credentials ({factory_user}/{pass_desc})...")
                        camera = AxisCamera(ip, mac, factory_user, factory_pass)
                        
                        camera_mac = camera.get_mac_address()
                        
                        if camera_mac and camera_mac == mac:
                            auth_method = f'factory_{factory_user}'
                            logger.info(f"  ✓ SUCCESS: Camera at {ip} authenticated with {factory_user}/{pass_desc}")
                            break  # Found working credentials
                        else:
                            camera = None
                    except Exception as e:
                        logger.debug(f"  Factory credentials {factory_user}/{pass_desc} failed: {e}")
                        camera = None
                        continue
                
                # Try CSV credentials (for already-programmed cameras)
                # Always try CSV credentials, even if factory credentials worked
                # This ensures we use the correct credentials for already-configured cameras
                if not camera and cfg:
                    try:
                        logger.info(f"  Attempting {ip} ({mac}) with CSV credentials ({csv_username}/***) ...")
                        camera = AxisCamera(ip, mac, csv_username, csv_password)
                        camera_mac = camera.get_mac_address()
                        
                        if camera_mac and camera_mac == mac:
                            auth_method = 'csv_credentials'
                            logger.info(f"  ✓ SUCCESS: Camera at {ip} authenticated with CSV credentials ({csv_username})")
                        else:
                            logger.warning(f"  ✗ CSV credentials failed to authenticate camera at {ip}")
                            camera = None
                    except Exception as e:
                        logger.warning(f"  ✗ CSV credentials failed: {e}")
                        camera = None
                
                # Log overall failure for this device
                if not camera:
                    logger.error(f"  ✗ FAILED: Could not authenticate to camera {mac} at {ip}")
                    logger.error(f"  Tried: Factory credentials and CSV credentials ({csv_username}/***)")
                    logger.error(f"  Verify camera is accessible and credentials in CSV are correct")
                
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
                
                # Small delay between connection attempts to avoid rate limiting on managed switches
                time.sleep(0.5)
            
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
                    'mac': normalize_mac_address(row['MAC_Address']),  # Normalize all MAC formats
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
                # Normalize both MACs for comparison to handle all formats
                if normalize_mac_address(row['MAC_Address']) == normalize_mac_address(mac):
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
        logger.info(f"Step 1/7: Setting credentials (user: {config['username']})...")
        if not camera.set_credentials(config['username'], config['password']):
            raise Exception("Failed to set credentials")
        
        # Step 2: Set date/time/timezone
        logger.info(f"Step 2/7: Setting timezone to {config.get('timezone', 'America/New_York')}...")
        camera.set_date_time(config.get('timezone', 'America/New_York'))  # Best effort, don't fail
        
        # Step 3: Set camera name (if provided)
        if config.get('name'):
            logger.info("Step 3/7: Setting camera name...")
            if not camera.set_camera_name(config['name']):
                logger.warning("Failed to set camera name (may not be supported on this model)")
        else:
            logger.info("Step 3/7: Skipping camera name (not provided)")
        
        # Step 4: Set resolution
        logger.info("Step 4/7: Setting resolution to 1024x768...")
        camera.set_resolution(1024, 768)  # Best effort, don't fail if not available
        
        # Step 5: Set zoom
        logger.info("Step 5/7: Setting zoom to minimum...")
        camera.zoom_out_fully()  # Best effort, don't fail if not available
        
        # Step 6: Set new IP address LAST (this may disrupt connection)
        subnet = config.get('subnet_mask', '255.255.255.0')
        gateway = config.get('gateway')
        if gateway:
            logger.info(f"Step 6/7: Setting IP to {config['new_ip']}, subnet {subnet}, gateway {gateway}...")
        else:
            logger.info(f"Step 6/7: Setting IP to {config['new_ip']}, subnet {subnet}...")
        old_ip = camera.ip
        if not camera.set_network_config(config['new_ip'], subnet, gateway):
            raise Exception(f"Failed to set IP to {config['new_ip']}")
        
        # Give camera time to reconfigure
        logger.info("Waiting for camera to apply network settings...")
        time.sleep(5)
        
        # Step 7: Verify configuration
        logger.info("Step 7/7: Verifying configuration...")
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
        logger.info("  1. Ensure cameras are powered on and connected to network")
        logger.info("  2. Verify cameras are getting DHCP addresses (P3267-LV doesn't use static 192.168.0.90)")
        logger.info("  3. Check that camera MAC addresses in CSV match actual camera MACs")
        logger.info("  4. Try running 'arp -a' to see if camera appears in ARP table")
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
