# Axis Camera Batch Programmer

A Python tool to batch configure Axis network cameras from factory defaults. Handles multiple cameras with the same default IP address on the same network.

## Features

- ✓ **Automatically scans all active network interfaces** (handles multiple NICs)
- ✓ **Smart ARP-based discovery** - only connects to IPs with matching MACs
- ✓ **Flexible MAC address formats** - accepts colons, dashes, or no separators (B8:A4:4F:FF:2E:D7, B8-A4-4F-FF-2E-D7, or B8A44FFF2ED7)
- ✓ **Firmware upgrade/downgrade** - automated firmware updates with progress tracking
- ✓ **Handles factory-fresh cameras** - automatically sets initial password
- ✓ Discovers cameras on network (DHCP or static, even with duplicate default IPs)
- ✓ Matches cameras by MAC address to configuration spreadsheet
- ✓ Configures IP address, subnet mask, gateway, and credentials
- ✓ Sets date, time, and timezone with NTP synchronization
- ✓ Sets camera name and zoom to minimum
- ✓ Verifies configuration was applied successfully
- ✓ Updates CSV with status and timestamps
- ✓ Fast parallel discovery (15-30 seconds per interface)
- ✓ Detailed logging to file and console

## Requirements

- Python 3.7 or newer
- Network access to cameras on default IP (192.168.0.90)
- Cameras must be at factory defaults (IP: 192.168.0.90, username: root, no password)

## Installation

1. Install Python if not already installed (download from [python.org](https://www.python.org/downloads/))

2. Open PowerShell or Command Prompt in this folder

3. Install required Python packages:
   ```powershell
   pip install -r requirements.txt
   ```

## Network Setup

### Automatic Multi-Interface Scanning
The program **automatically scans all active network interfaces** on your computer and performs:
1. **Quick check** for cameras at default IP (192.168.0.90)
2. **ARP-based discovery** - pings the subnet, reads ARP table, then only attempts connection to IPs with MAC addresses matching your CSV

This means you can:
- Connect cameras to any network interface
- Mix static and DHCP cameras on the same switch
- Have cameras at different IPs - the program finds them by MAC address
- **Efficient scanning** - only tries IPs with matching MACs (seconds instead of minutes)

**Performance:** Discovery typically takes 15-30 seconds per interface, much faster than traditional IP scanning.

### Option 1: One Camera at a Time (Easiest)
Connect one camera to an isolated network segment with your computer. Configure it, disconnect, then connect the next camera.

### Option 2: Multiple Cameras on Same Network (Recommended for Bulk Programming)
Connect all cameras to the same switch/network. The program will:
- Scan the subnet to find all cameras (even on DHCP)
- Match each camera by MAC address to your CSV
- Configure them sequentially to avoid conflicts

**This is ideal for factory programming thousands of cameras** - just connect them all to a switch and let the program discover and configure them automatically.

### Computer Network Configuration
Your computer needs to be on the same subnet as the cameras:
- Set your computer's IP to: `192.168.0.100` (or any IP in 192.168.0.x range except .90)
- Subnet mask: `255.255.255.0`
- No gateway needed for direct connection

**Windows Quick Setup:**
```powershell
# View current network adapters
Get-NetAdapter

# Set static IP (replace "Ethernet" with your adapter name)
New-NetIPAddress -InterfaceAlias "Ethernet" -IPAddress 192.168.0.100 -PrefixLength 24

# To revert to DHCP later:
Set-NetIPInterface -InterfaceAlias "Ethernet" -Dhcp Enabled
```

## CSV Configuration File

Edit `camera_config.csv` with your camera details:

| Column | Description | Example |
|--------|-------------|---------|
| **MAC_Address** | Camera MAC address (any format) | `00:40:8C:12:34:56` or `00-40-8C-12-34-56` or `0040-8C12-3456` or `00408C123456` |
| **New_IP** | Desired IP address | `192.168.1.101` || **Subnet_Mask** | Subnet mask for camera | `255.255.255.0` |
| **Gateway** | Default gateway/router IP (optional) | `192.168.1.1` or leave blank || **Username** | New admin username | `admin` |
| **Password** | New admin password | `SecurePass123` |
| **Camera_Name** | Camera hostname/name | `Front Door Camera` |
| **Timezone** | Timezone name or POSIX format | `America/New_York`, `Central`, `PST8PDT,M3.2.0,M11.1.0` |
| Status | (Auto-filled by program) | `Completed`, `Failed`, etc. |
| Message | (Auto-filled by program) | Success/error details |
| Timestamp | (Auto-filled by program) | When configured |

### Supported Timezone Names

The program automatically converts common timezone names to the POSIX format required by Axis cameras:

**US Timezones:**
- `America/New_York` or `Eastern` → US Eastern Time
- `America/Chicago` or `Central` → US Central Time  
- `America/Denver` or `Mountain` → US Mountain Time
- `America/Phoenix` → Arizona Time (no DST)
- `America/Los_Angeles` or `Pacific` → US Pacific Time
- `America/Anchorage` or `Alaska` → Alaska Time
- `Pacific/Honolulu` → Hawaii Time (no DST)

**European Timezones:**
- `Europe/London` → UK Time (GMT/BST)
- `Europe/Paris`, `Europe/Berlin`, `Europe/Rome` → Central European Time

**Asian/Pacific Timezones:**
- `Asia/Tokyo` → Japan Standard Time
- `Asia/Shanghai` → China Standard Time
- `Asia/Singapore` → Singapore Time
- `Asia/Dubai` → Gulf Standard Time
- `Australia/Sydney` → Australian Eastern Time
- `Australia/Perth` → Australian Western Time

You can also use POSIX timezone format directly (e.g., `EST5EDT,M3.2.0,M11.1.0`) if your timezone isn't listed.

### Finding Camera MAC Addresses

**Before configuration:** 
- Check the label on the camera (physical sticker)
- Or browse to http://192.168.0.90 and log in (root with no password) - MAC shown in device info

**After initial discovery:**
The program will log all discovered MACs so you can add them to your CSV.

**MAC Address Format:**
The program accepts MAC addresses in any of these formats:
- `B8:A4:4F:FF:2E:D7` (colon-separated - most common)
- `B8-A4-4F-FF-2E-D7` (dash-separated - Windows ARP format)
- `B8A44FFF2ED7` (no separators - camera label format)
- `b8:a4:4f:ff:2e:d7` (lowercase - works too)

All formats are automatically normalized internally for matching.

### Example CSV
```csv
MAC_Address,New_IP,Subnet_Mask,Gateway,Username,Password,Camera_Name,Timezone,Status,Message,Timestamp
00:40:8C:12:34:56,192.168.1.101,255.255.255.0,192.168.1.1,admin,SecurePass123,Front Door Camera,America/New_York,,,
00:40:8C:12:34:57,192.168.1.102,255.255.255.0,192.168.1.1,admin,SecurePass123,Rear Entrance,Central,,,
00:40:8C:AB:CD:EF,192.168.1.103,255.255.255.0,192.168.1.1,admin,SecurePass123,Parking Lot,America/Los_Angeles,,,
```

## Usage

### GUI Mode (Recommended)

1. **Launch the GUI:**
   ```powershell
   python axis_batch_programmer_gui.py
   ```

2. **Load Configuration:**
   - Click "Browse..." to select your CSV file (`camera_config.csv`)
   - Review the camera list in the table

3. **(Optional) Enable Firmware Upgrade:**
   - Check "Upgrade Firmware" checkbox
   - Click "Select .bin File..." to choose your firmware file
   - This will upgrade ALL discovered cameras before configuring them
   - Uncheck to skip firmware upgrade and only configure settings

4. **Scan or Program:**
   - **"Scan Only"** - Discover cameras and show their current IPs without programming
   - **"Start Programming"** - Discover and configure all cameras (with optional firmware upgrade)
   - **"Test Cameras"** - Test VAPIX compatibility without making changes

5. **Monitor Progress:**
   - Watch status updates in the camera table
   - View detailed logs in the log output panel
   - Status bar shows overall progress

6. **Review Results:**
   - Check Status column: "Completed" (success) or "Failed" (error)
   - Review Message column for details
   - CSV file is automatically updated with results

### Command-Line Mode

1. **Prepare your CSV file:**
   - Edit `camera_config.csv` 
   - Add one row per camera with MAC address and desired settings
   - Save the file

2. **Connect the cameras:**
   - Connect cameras to your network
   - Ensure your computer can reach 192.168.0.90

3. **Run the program:**
   ```powershell
   python axis_batch_programmer.py
   ```

4. **Follow the prompts:**
   - Review the cameras to be configured
   - Press Enter to start
   - Program will discover, configure, and verify each camera

5. **Check results:**
   - View console output for real-time status
   - Check `camera_config.csv` for Status column updates
   - Review `axis_programmer.log` for detailed logs

## Firmware Upgrade/Downgrade

The program supports automated firmware upgrades and downgrades for Axis cameras. This feature allows you to:
- Update cameras to the latest firmware for security patches and new features
- Downgrade cameras if newer firmware causes compatibility issues
- Standardize firmware versions across your camera fleet

### Downloading Firmware

1. Visit [Axis Firmware Downloads](https://www.axis.com/support/firmware)
2. Select your camera model (e.g., "P3267-LV")
3. Download the `.bin` firmware file
4. Save to a known location (e.g., same folder as the batch programmer)

### Upgrading a Single Camera

Use the provided example script:

```powershell
python firmware_upgrade_example.py
```

**Manual upgrade example:**
```python
from axis_batch_programmer import AxisCamera

# Connect to camera
camera = AxisCamera("192.168.1.168", "B8:A4:4F:FF:2E:D7", "root", "admin")

# Check current firmware
current_version = camera.get_firmware_version()
print(f"Current firmware: {current_version}")

# Upgrade firmware (camera will reboot)
success = camera.upgrade_firmware("AXIS_P3267LV_10_12_240.bin")

if success:
    new_version = camera.get_firmware_version()
    print(f"Upgrade successful! New firmware: {new_version}")
```

### Important Notes

- **Camera will reboot** during firmware upgrade (5-10 minutes downtime)
- **Don't interrupt** the upgrade process (power loss can brick the camera)
- **Verify firmware file** matches your camera model exactly
- **Backup configuration** if possible before upgrading
- **Test on one camera** before upgrading an entire fleet
- **Schedule upgrades** during maintenance windows if cameras are in production

### Firmware Compatibility

| Camera Model | Tested Firmware Versions |
|--------------|-------------------------|
| P3267-LV     | 9.80.x, 10.12.240       |
| P3225-LV Mk II | 9.80.132             |

Always verify firmware compatibility on [Axis Support](https://www.axis.com/support) before upgrading.

### Progress Monitoring

The upgrade process provides progress callbacks:
1. **Validating** - Checking current firmware version
2. **Uploading** - Transferring firmware file to camera (1-3 minutes for ~100MB file)
3. **Installing** - Camera installing firmware and rebooting (5-10 minutes)
4. **Rebooting** - Waiting for camera to come back online
5. **Complete** - Firmware upgraded successfully

### Troubleshooting Firmware Upgrades

**"Firmware file not found"**
- Verify the file path is correct
- Use absolute path if relative path fails

**"Upload failed"**
- Check camera has enough free space
- Verify firmware file is not corrupted (re-download if needed)
- Ensure camera model matches firmware file

**"Timeout waiting for camera"**
- Camera may take longer than 10 minutes on slow networks
- Wait an additional 5-10 minutes and check manually
- Camera may still be upgrading - don't power cycle

**"Camera not responding after upgrade"**
- Wait at least 15 minutes total before troubleshooting
- Check camera lights indicate normal operation
- Try accessing via web browser
- If camera is bricked, contact Axis support for recovery options

## Program Workflow

```
1. Read CSV Configuration
   ↓
2. Discover Cameras on Network (by MAC address)
   ↓
3. For each discovered camera:
   ├─ Set new credentials (while connection is stable)
   ├─ Configure date/time/timezone with NTP
   ├─ Set camera name  
   ├─ Set zoom to minimum
   ├─ Configure new IP address (last - may disrupt connection)
   ├─ Verify configuration
   └─ Update CSV with status
```

## Output Files

- **camera_config.csv** - Updated with Status, Message, and Timestamp columns
- **axis_programmer.log** - Detailed execution log with timestamps

## Troubleshooting

### No cameras discovered
- Verify cameras are powered on
- Check network cable connections
- Ensure your computer's IP is in 192.168.0.x subnet
- Try pinging 192.168.0.90: `ping 192.168.0.90`
- Verify cameras are at factory defaults (reset if needed)

### Authentication failed
- Confirm default credentials are root with no password
- If cameras were previously configured, reset to factory defaults
- Check camera documentation for default credentials

### Configuration fails but camera is discovered
- Check CSV for correct IP address format
- Ensure new IP is in a valid subnet for your network
- Verify the MAC address in CSV matches discovered camera
- Review `axis_programmer.log` for detailed error messages

### Can't connect after IP change
- Wait 10-15 seconds for camera to apply settings
- Check the new IP is not conflicting with another device
- Verify your computer can route to the new IP subnet
- May need to adjust your computer's network settings

### Program hangs or times out
- Some cameras are slower to respond - wait at least 30 seconds
- Check camera is not rebooting
- Verify network connection is stable
- Restart the camera and try again

## Camera Reset to Factory Defaults

If you need to reset an Axis camera to factory defaults:

1. **Via web interface:** 
   - Browse to camera IP
   - System Options → Maintenance → Factory Default
   
2. **Via reset button:**
   - Power on camera
   - Hold reset button for 15-25 seconds
   - Wait for camera to reboot

## Security Notes

- Change default passwords to strong, unique passwords
- Store the CSV file securely (contains credentials)
- Consider using a password manager for credentials
- After configuration, cameras should be on a separate VLAN or protected network

## Advanced Options

### Customize Default Settings
Edit the constants at the top of `axis_batch_programmer.py`:
```python
DEFAULT_IP = "192.168.0.90"  # Factory default IP
DEFAULT_USER = "root"        # Factory default username
DEFAULT_PASS = "pass"        # Factory default password
```

### Subnet Mask Configuration
Default subnet mask is `255.255.255.0`. To change:
Edit the `set_network_config()` method call in the `configure_camera()` function.

### Additional VAPIX Commands
The program uses Axis's VAPIX API. You can add custom configuration by extending the `AxisCamera` class methods. See [Axis VAPIX Documentation](https://www.axis.com/vapix-library/).

## Support

For issues with:
- **This program:** Check `axis_programmer.log` for detailed errors
- **Axis cameras:** See [Axis Support](https://www.axis.com/support)
- **VAPIX API:** See [VAPIX Library](https://www.axis.com/vapix-library/)

## License

Free to use and modify for your needs.

## Version History

- **v1.1** (2026-03-11)
  - ✨ **NEW:** Flexible MAC address format support (handles colons, dashes, or no separators)
  - ✨ **NEW:** Firmware upgrade/downgrade feature with progress monitoring
  - ✨ **NEW:** Automatic firmware version detection
  - 📚 Added firmware upgrade example script and documentation
  - 🔧 Enhanced MAC address normalization for better CSV compatibility
  
- **v1.0** (2026-03-04)
  - Initial release
  - Camera discovery by MAC address
  - IP, credentials, name, and zoom configuration
  - CSV tracking with status updates
  - Detailed logging
