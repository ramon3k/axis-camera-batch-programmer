# Axis Camera Batch Programmer - Installation Guide

## Quick Start (5 minutes)

### Prerequisites
- Windows 10/11 or Windows Server
- Network access to Axis cameras
- Administrator privileges (for first-time Python installation only)

### Step 1: Install Python (if not already installed)

1. Download Python 3.11 or later from: https://www.python.org/downloads/
2. **IMPORTANT**: During installation, check "Add Python to PATH"
3. Verify installation by opening PowerShell and typing:
   ```powershell
   python --version
   ```
   Should show: `Python 3.11.x` or higher

### Step 2: Install Dependencies

Open PowerShell in the program folder and run:
```powershell
pip install -r requirements.txt
```

### Step 3: Prepare Your Camera List

1. Open `camera_config.csv` in Excel or Notepad
2. Fill in your camera details:
   - **MAC_Address**: Camera MAC address (from label or DHCP server)
   - **New_IP**: Desired IP address
   - **Subnet_Mask**: Usually `255.255.255.0`
   - **Gateway**: Your network gateway (e.g., `192.168.1.1`)
   - **Username**: Admin username (e.g., `admin`)
   - **Password**: Secure password
   - **Camera_Name**: Descriptive name
   - **Timezone**: Timezone (e.g., `America/New_York`)

3. Save the file

### Step 4: Run the Program

**Option A: Graphical Interface (Recommended)**
```powershell
python axis_batch_programmer_gui.py
```

**Option B: Command Line**
```powershell
python axis_batch_programmer.py
```

## Troubleshooting

### "Python is not recognized..."
- Python not added to PATH during installation
- Solution: Reinstall Python and check "Add Python to PATH"

### Cameras not discovered
- Ensure cameras are powered and connected to same network
- Check if your computer can ping the camera's default IP (192.168.0.90)
- Verify MAC addresses in CSV are correct

### Permission denied errors
- Run PowerShell as Administrator
- Check Windows Firewall isn't blocking network scanning

### Slow discovery (takes several minutes)
- Normal for large subnets
- ARP-based discovery takes 15-30 seconds per network interface
- Consider splitting cameras across multiple CSV files

## Network Requirements

- Computer must be on same subnet as cameras during initial programming
- For DHCP cameras: Computer must be on same subnet where DHCP server assigned IPs
- For factory-default cameras: Computer must reach 192.168.0.90

## Security Notes

- Store `camera_config.csv` securely (contains passwords)
- Use strong passwords for all cameras
- Root password is automatically updated during configuration
- Consider deleting CSV after programming or storing encrypted

## Support

For issues or questions, check:
- Log file: `axis_programmer.log`
- CSV Status column shows last error for each camera
- Enable debug logging by editing the script if needed

## Batch Processing Tips

**For Hundreds of Cameras:**
1. Connect cameras in batches (e.g., 50 at a time on a switch)
2. Program them in groups
3. CSV automatically tracks completed cameras
4. Re-run to resume if interrupted - completed cameras are skipped

**For Thousands of Cameras:**
1. Use multiple workstations with separate CSV files
2. Split by MAC address ranges or deployment zones
3. Consider scripting the CSV generation from DHCP logs
4. Plan network capacity (avoid saturating DHCP/ARP tables)
