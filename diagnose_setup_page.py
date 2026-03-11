#!/usr/bin/env python3
"""
Diagnostic tool to analyze the initial setup page structure of factory-reset Axis cameras.
This helps determine the correct form fields for automated setup.
"""

import requests
import re
from bs4 import BeautifulSoup

CAMERA_IP = "192.168.1.92"  # Factory-reset camera IP

def analyze_setup_page():
    """Fetch and analyze the initial setup page."""
    
    print("="*70)
    print("Axis Camera Initial Setup Page Diagnostic")
    print("="*70)
    print(f"\nTarget Camera: {CAMERA_IP}")
    print("\nStep 1: Fetching initial setup page...")
    
    try:
        # Fetch the page without authentication
        response = requests.get(
            f"http://{CAMERA_IP}/", 
            timeout=10, 
            proxies={'http': None, 'https': None},
            allow_redirects=True
        )
        
        print(f"  Status Code: {response.status_code}")
        print(f"  Final URL: {response.url}")
        print(f"  Content Length: {len(response.text)} bytes")
        
        # Check if this is a setup page
        text_lower = response.text.lower()
        is_setup_page = any([
            'set a password' in text_lower,
            'pwdroot' in response.url.lower(),
            'setpassword' in response.url.lower(),
            'add user' in text_lower,
            'end user license agreement' in text_lower,
            'eula' in text_lower
        ])
        
        print(f"\n  Is Setup Page: {'YES' if is_setup_page else 'NO'}")
        
        if not is_setup_page:
            print("\n✗ Camera is NOT in initial setup mode")
            print("  Factory reset the camera and try again")
            return
        
        print("\n✓ Camera IS in initial setup mode\n")
        
        # Parse HTML to find forms
        print("Step 2: Analyzing HTML form structure...")
        soup = BeautifulSoup(response.text, 'html.parser')
        
        forms = soup.find_all('form')
        print(f"\n  Found {len(forms)} form(s)")
        
        for idx, form in enumerate(forms, 1):
            print(f"\n  --- Form #{idx} ---")
            action = form.get('action', 'No action')
            method = form.get('method', 'No method')
            print(f"  Action: {action}")
            print(f"  Method: {method}")
            
            # Find all input fields
            inputs = form.find_all('input')
            print(f"  Input fields ({len(inputs)}):")
            for inp in inputs:
                name = inp.get('name', 'unnamed')
                inp_type = inp.get('type', 'text')
                value = inp.get('value', '')
                placeholder = inp.get('placeholder', '')
                required = 'required' if inp.get('required') else ''
                
                print(f"    - {name}: type={inp_type}, value='{value}', placeholder='{placeholder}' {required}")
            
            # Find select fields
            selects = form.find_all('select')
            if selects:
                print(f"  Select fields ({len(selects)}):")
                for sel in selects:
                    name = sel.get('name', 'unnamed')
                    options = [opt.get('value', '') for opt in sel.find_all('option')]
                    print(f"    - {name}: options={options}")
            
            # Find checkboxes
            checkboxes = form.find_all('input', {'type': 'checkbox'})
            if checkboxes:
                print(f"  Checkboxes ({len(checkboxes)}):")
                for cb in checkboxes:
                    name = cb.get('name', 'unnamed')
                    value = cb.get('value', '')
                    print(f"    - {name}: value='{value}'")
        
        # Look for EULA/terms text
        print("\nStep 3: Looking for EULA/Terms acceptance...")
        eula_indicators = [
            'end user license agreement',
            'terms and conditions',
            'accept',
            'agree',
            'eula'
        ]
        
        for indicator in eula_indicators:
            if indicator in text_lower:
                # Find context around the indicator
                idx = text_lower.find(indicator)
                context = response.text[max(0, idx-100):idx+200]
                print(f"\n  Found '{indicator}':")
                print(f"  Context: {context[:300]}")
        
        # Try to find any JavaScript that might set up the form
        print("\nStep 4: Looking for JavaScript setup code...")
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string and ('pwdroot' in script.string or 'password' in script.string.lower()):
                print(f"\n  Relevant script snippet:")
                print(f"  {script.string[:500]}")
        
        # Save the full HTML for manual inspection
        output_file = "setup_page.html"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(response.text)
        print(f"\n✓ Full HTML saved to: {output_file}")
        
        # Now test the POST endpoint
        print("\n" + "="*70)
        print("Step 5: Testing POST endpoint variations...")
        print("="*70)
        
        setup_url = f"http://{CAMERA_IP}/axis-cgi/pwdroot.cgi"
        
        test_cases = [
            {
                'name': 'Test 1: Basic (root, pass, accept)',
                'data': {
                    'user': 'root',
                    'pwd': 'pass',
                    'rpwd': 'pass',
                    'accept': 'yes'
                }
            },
            {
                'name': 'Test 2: With slocale',
                'data': {
                    'user': 'root',
                    'pwd': 'pass',
                    'rpwd': 'pass',
                    'slocale': 'en'
                }
            },
            {
                'name': 'Test 3: With multiple accept fields',
                'data': {
                    'user': 'root',
                    'pwd': 'pass',
                    'rpwd': 'pass',
                    'accept': '1',
                    'terms': '1',
                    'eula': 'yes'
                }
            },
            {
                'name': 'Test 4: Minimal (just password)',
                'data': {
                    'pwd': 'pass',
                    'rpwd': 'pass'
                }
            },
            {
                'name': 'Test 5: With action parameter',
                'data': {
                    'action': 'set',
                    'user': 'root',
                    'pwd': 'pass',
                    'rpwd': 'pass'
                }
            }
        ]
        
        for test in test_cases:
            print(f"\n{test['name']}")
            print(f"  Data: {test['data']}")
            
            try:
                resp = requests.post(
                    setup_url,
                    data=test['data'],
                    timeout=10,
                    proxies={'http': None, 'https': None},
                    allow_redirects=False
                )
                
                print(f"  Response Status: {resp.status_code}")
                print(f"  Response Headers: {dict(resp.headers)}")
                print(f"  Response Body: {resp.text[:200]}")
                
                if resp.status_code in [200, 302, 303]:
                    print(f"  ✓ POTENTIAL SUCCESS!")
                
            except Exception as e:
                print(f"  ✗ Error: {e}")
        
        print("\n" + "="*70)
        print("Diagnostic Complete!")
        print("="*70)
        print("\nReview the output above to determine:")
        print("  1. What form fields are required")
        print("  2. What values the EULA acceptance field expects")
        print("  3. Which POST combination worked (if any)")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    analyze_setup_page()
