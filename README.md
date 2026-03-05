# Axis Camera Batch Programmer

A Python tool to batch configure Axis network cameras from factory defaults. Handles multiple cameras with the same default IP address on the same network.

## Features

- ✓ **Automatically scans all active network interfaces** (handles multiple NICs)
- ✓ **Smart ARP-based discovery** - only connects to IPs with matching MACs
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
| **MAC_Address** | Camera MAC address (any format) | `00:40:8C:12:34:56` or `00-40-8C-12-34-56` |
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

### Example CSV
```csv
MAC_Address,New_IP,Subnet_Mask,Gateway,Username,Password,Camera_Name,Timezone,Status,Message,Timestamp
00:40:8C:12:34:56,192.168.1.101,255.255.255.0,192.168.1.1,admin,SecurePass123,Front Door Camera,America/New_York,,,
00:40:8C:12:34:57,192.168.1.102,255.255.255.0,192.168.1.1,admin,SecurePass123,Rear Entrance,Central,,,
00:40:8C:AB:CD:EF,192.168.1.103,255.255.255.0,192.168.1.1,admin,SecurePass123,Parking Lot,America/Los_Angeles,,,
```

## Usage

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

- **v1.0** (2026-03-04)
  - Initial release
  - Camera discovery by MAC address
  - IP, credentials, name, and zoom configuration
  - CSV tracking with status updates
  - Detailed logging
