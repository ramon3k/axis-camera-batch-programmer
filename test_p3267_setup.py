#!/usr/bin/env python3
"""
Test P3267 initial setup automation with verbose logging.
"""
import requests
from requests.auth import HTTPDigestAuth
import logging

# Enable DEBUG logging to see everything
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

P3267_IP = "192.168.1.168"
PASSWORD = "pass"

def test_p3267_setup():
    """Test the two-step setup automation on P3267."""
    
    logger.info("="*70)
    logger.info(f"Testing P3267 Initial Setup Automation at {P3267_IP}")
    logger.info("="*70)
    
    try:
        # Step 1: Check if in setup mode
        logger.info("\n[CHECK] Accessing camera homepage to detect setup mode...")
        response = requests.get(
            f"http://{P3267_IP}/", 
            timeout=10, 
            proxies={'http': None, 'https': None}, 
            allow_redirects=True
        )
        
        logger.info(f"Response URL: {response.url}")
        logger.info(f"Response Status: {response.status_code}")
        logger.info(f"Response Length: {len(response.text)} chars")
        
        # Check for setup page indicators
        response_text = response.text.lower()
        indicators = {
            'set a password': 'set a password' in response_text,
            'pwdroot in URL': 'pwdroot' in response.url.lower(),
            'setpassword in URL': 'setpassword' in response.url.lower(),
            'add user': 'add user' in response_text,
            'end user license agreement': 'end user license agreement' in response_text,
            'weak password': 'weak password' in response_text,
            'password strength': 'password strength' in response_text,
        }
        
        logger.info("\nSetup page indicators:")
        for key, found in indicators.items():
            logger.info(f"  {'✓' if found else '✗'} {key}: {found}")
        
        is_setup_page = any([
            indicators['set a password'],
            indicators['pwdroot in URL'],
            indicators['setpassword in URL'],
            indicators['add user'],
            indicators['end user license agreement']
        ])
        
        if not is_setup_page:
            logger.error("\n❌ Camera NOT in initial setup mode!")
            return False
        
        logger.info("\n✓ Camera IS in initial setup mode")
        
        # Step 2: Try setting password with 'root' username
        setup_url = f"http://{P3267_IP}/axis-cgi/pwdroot.cgi"
        
        logger.info(f"\n[STEP 1] Attempting to set password with username 'root'...")
        form_data = {
            'user': 'root',
            'pwd': PASSWORD,
            'rpwd': PASSWORD,
            'accept': 'yes',
            'termsaccepted': 'yes',
        }
        
        logger.info(f"POST to: {setup_url}")
        logger.info(f"Form data: {form_data}")
        
        response = requests.post(
            setup_url,
            data=form_data,
            timeout=15,
            proxies={'http': None, 'https': None},
            allow_redirects=False
        )
        
        logger.info(f"\nStep 1 Response:")
        logger.info(f"  Status: {response.status_code}")
        logger.info(f"  Headers: {dict(response.headers)}")
        logger.info(f"  Body (first 1000 chars):\n{response.text[:1000]}")
        
        # Check for weak password warning
        response_text = response.text.lower()
        weak_password_indicators = {
            'weak password': 'weak password' in response_text,
            'password strength': 'password strength' in response_text,
            'confirm + weak': ('confirm' in response_text and 'weak' in response_text),
            'use anyway': 'use anyway' in response_text,
        }
        
        logger.info("\nWeak password indicators:")
        for key, found in weak_password_indicators.items():
            logger.info(f"  {'✓' if found else '✗'} {key}: {found}")
        
        needs_confirmation = any(weak_password_indicators.values())
        
        if needs_confirmation or response.status_code == 200:
            logger.info(f"\n[STEP 2] Sending weak password confirmation...")
            
            confirm_data = {
                'user': 'root',
                'pwd': PASSWORD,
                'rpwd': PASSWORD,
                'accept': 'yes',
                'termsaccepted': 'yes',
                'confirmweakpassword': 'yes',
                'confirm': 'yes',
                'weak': 'yes',
                'force': 'yes',
            }
            
            logger.info(f"POST to: {setup_url}")
            logger.info(f"Confirm data: {confirm_data}")
            
            confirm_response = requests.post(
                setup_url,
                data=confirm_data,
                timeout=15,
                proxies={'http': None, 'https': None},
                allow_redirects=False
            )
            
            logger.info(f"\nStep 2 Response:")
            logger.info(f"  Status: {confirm_response.status_code}")
            logger.info(f"  Headers: {dict(confirm_response.headers)}")
            logger.info(f"  Body (first 1000 chars):\n{confirm_response.text[:1000]}")
            
            # Check if confirmation succeeded
            if confirm_response.status_code in [200, 302, 303] or 'ok' in confirm_response.text.lower():
                logger.info("\n✅ STEP 2 appears successful!")
            else:
                logger.warning(f"\n⚠ STEP 2 returned unexpected status: {confirm_response.status_code}")
        
        # Check if initial POST (without confirmation) succeeded
        if response.status_code in [200, 302, 303] or 'ok' in response.text.lower():
            logger.info("\n✅ STEP 1 appears successful!")
        else:
            logger.warning(f"\n⚠ STEP 1 returned unexpected status: {response.status_code}")
        
        # Step 3: Verify by testing authentication
        logger.info(f"\n[VERIFY] Testing authentication with root/{PASSWORD}...")
        
        import time
        time.sleep(3)  # Give camera time to complete setup
        
        session = requests.Session()
        session.auth = HTTPDigestAuth('root', PASSWORD)
        session.trust_env = False
        session.proxies = {'http': None, 'https': None}
        
        test_url = f"http://{P3267_IP}/axis-cgi/param.cgi?action=list&group=Network.eth0"
        test_response = session.get(test_url, timeout=10)
        
        logger.info(f"\nVerification Response:")
        logger.info(f"  Status: {test_response.status_code}")
        logger.info(f"  Body (first 500 chars):\n{test_response.text[:500]}")
        
        if test_response.status_code == 200:
            logger.info("\n✅✅✅ SUCCESS! Automation worked - camera is accessible!")
            
            # Extract MAC address
            for line in test_response.text.split('\n'):
                if 'MACAddress' in line:
                    mac = line.split('=')[1].strip()
                    logger.info(f"  MAC Address: {mac}")
            
            return True
        elif test_response.status_code == 401:
            logger.error("\n❌ Authentication FAILED (401) - camera still locked!")
            logger.error("This means the two-step automation didn't actually work.")
            return False
        else:
            logger.warning(f"\n⚠ Unexpected status {test_response.status_code}")
            return False
        
    except Exception as e:
        logger.exception(f"Error during test: {e}")
        return False


if __name__ == "__main__":
    success = test_p3267_setup()
    
    if success:
        print("\n" + "="*70)
        print("✅ P3267 AUTOMATION SUCCESSFUL!")
        print("The two-step weak password confirmation worked.")
        print("="*70)
    else:
        print("\n" + "="*70)
        print("❌ P3267 AUTOMATION FAILED")
        print("Manual browser setup required, or automation needs adjustment.")
        print("="*70)
