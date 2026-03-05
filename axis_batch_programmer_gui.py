"""
Axis Camera Batch Programmer - GUI Version
Professional interface for batch configuring Axis cameras
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import threading
import queue
import csv
import logging
from datetime import datetime
from pathlib import Path
import sys

# Import the core logic from the main program
from axis_batch_programmer import (
    discover_cameras_on_network,
    configure_camera,
    read_camera_config_csv,
    update_csv_status
)


class TextHandler(logging.Handler):
    """Custom logging handler that writes to a text widget."""
    
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
        
    def emit(self, record):
        msg = self.format(record)
        
        def append():
            self.text_widget.configure(state='normal')
            self.text_widget.insert(tk.END, msg + '\n')
            self.text_widget.see(tk.END)
            self.text_widget.configure(state='disabled')
            
            # Color code by log level
            if record.levelname == 'ERROR':
                # Get the last line and tag it red
                line_start = self.text_widget.index("end-2c linestart")
                line_end = self.text_widget.index("end-1c")
                self.text_widget.tag_add("error", line_start, line_end)
                self.text_widget.tag_config("error", foreground="red")
            elif record.levelname == 'WARNING':
                line_start = self.text_widget.index("end-2c linestart")
                line_end = self.text_widget.index("end-1c")
                self.text_widget.tag_add("warning", line_start, line_end)
                self.text_widget.tag_config("warning", foreground="orange")
            elif record.levelname == 'INFO' and '[OK]' in msg:
                line_start = self.text_widget.index("end-2c linestart")
                line_end = self.text_widget.index("end-1c")
                self.text_widget.tag_add("success", line_start, line_end)
                self.text_widget.tag_config("success", foreground="green")
        
        self.text_widget.after(0, append)


class AxisBatchProgrammerGUI:
    """Main GUI application for Axis Camera Batch Programmer."""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Axis Camera Batch Programmer")
        self.root.geometry("1200x800")
        
        # State
        self.csv_filename = "camera_config.csv"
        self.configs = []
        self.is_running = False
        self.status_queue = queue.Queue()
        
        # Setup UI
        self.setup_ui()
        self.setup_logging()
        
        # Load initial data
        self.load_csv()
        
        # Start status update checker
        self.check_status_updates()
        
    def setup_ui(self):
        """Create the user interface."""
        
        # Style configuration
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure colors
        style.configure('Title.TLabel', font=('Arial', 16, 'bold'), foreground='#2c3e50')
        style.configure('Header.TLabel', font=('Arial', 10, 'bold'), foreground='#34495e')
        style.configure('Status.TLabel', font=('Arial', 9), foreground='#7f8c8d')
        
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)
        
        # ===== Header Section =====
        header_frame = ttk.Frame(main_frame)
        header_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        title_label = ttk.Label(
            header_frame,
            text="Axis Camera Batch Programmer",
            style='Title.TLabel'
        )
        title_label.pack(side=tk.LEFT)
        
        # CSV File selection
        csv_frame = ttk.Frame(header_frame)
        csv_frame.pack(side=tk.RIGHT)
        
        ttk.Label(csv_frame, text="CSV File:", style='Header.TLabel').pack(side=tk.LEFT, padx=(0, 5))
        
        self.csv_label = ttk.Label(
            csv_frame,
            text=self.csv_filename,
            style='Status.TLabel',
            relief=tk.SUNKEN,
            padding=5
        )
        self.csv_label.pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(
            csv_frame,
            text="Browse...",
            command=self.browse_csv
        ).pack(side=tk.LEFT)
        
        # ===== Camera Status Table =====
        table_frame = ttk.LabelFrame(main_frame, text="Camera Status", padding="5")
        table_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        
        # Create Treeview with scrollbars
        tree_scroll_y = ttk.Scrollbar(table_frame, orient=tk.VERTICAL)
        tree_scroll_x = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL)
        
        self.tree = ttk.Treeview(
            table_frame,
            columns=('MAC', 'Name', 'Current_IP', 'New_IP', 'Username', 'Status', 'Message'),
            show='headings',
            yscrollcommand=tree_scroll_y.set,
            xscrollcommand=tree_scroll_x.set,
            height=10
        )
        
        tree_scroll_y.config(command=self.tree.yview)
        tree_scroll_x.config(command=self.tree.xview)
        
        # Define columns
        self.tree.heading('MAC', text='MAC Address')
        self.tree.heading('Name', text='Camera Name')
        self.tree.heading('Current_IP', text='Current IP')
        self.tree.heading('New_IP', text='New IP')
        self.tree.heading('Username', text='Username')
        self.tree.heading('Status', text='Status')
        self.tree.heading('Message', text='Message')
        
        # Column widths
        self.tree.column('MAC', width=150)
        self.tree.column('Name', width=150)
        self.tree.column('Current_IP', width=120)
        self.tree.column('New_IP', width=120)
        self.tree.column('Username', width=100)
        self.tree.column('Status', width=100)
        self.tree.column('Message', width=300)
        
        # Tags for row colors
        self.tree.tag_configure('pending', background='#ecf0f1')
        self.tree.tag_configure('discovering', background='#3498db', foreground='white')
        self.tree.tag_configure('configuring', background='#f39c12', foreground='white')
        self.tree.tag_configure('completed', background='#27ae60', foreground='white')
        self.tree.tag_configure('failed', background='#e74c3c', foreground='white')
        
        # Grid layout
        self.tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        tree_scroll_y.grid(row=0, column=1, sticky=(tk.N, tk.S))
        tree_scroll_x.grid(row=1, column=0, sticky=(tk.W, tk.E))
        
        # ===== Log Output =====
        log_frame = ttk.LabelFrame(main_frame, text="Log Output", padding="5")
        log_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            width=100,
            height=20,
            font=('Consolas', 9),
            background='#2c3e50',
            foreground='#ecf0f1',
            state='disabled'
        )
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # ===== Control Buttons =====
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, sticky=(tk.W, tk.E))
        
        self.start_button = ttk.Button(
            button_frame,
            text="Start Programming",
            command=self.start_programming,
            width=20
        )
        self.start_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.stop_button = ttk.Button(
            button_frame,
            text="Stop",
            command=self.stop_programming,
            state=tk.DISABLED,
            width=15
        )
        self.stop_button.pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(
            button_frame,
            text="Refresh CSV",
            command=self.load_csv,
            width=15
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(
            button_frame,
            text="Clear Log",
            command=self.clear_log,
            width=15
        ).pack(side=tk.LEFT)
        
        # Status bar
        self.status_bar = ttk.Label(
            button_frame,
            text="Ready",
            style='Status.TLabel',
            relief=tk.SUNKEN,
            padding=5
        )
        self.status_bar.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0))
        
    def setup_logging(self):
        """Configure logging to output to the text widget."""
        # Get the logger from axis_batch_programmer
        logger = logging.getLogger('axis_programmer')
        
        # Create text handler
        text_handler = TextHandler(self.log_text)
        text_handler.setLevel(logging.DEBUG)
        
        # Format
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s',
                                     datefmt='%H:%M:%S')
        text_handler.setFormatter(formatter)
        
        # Add handler
        logger.addHandler(text_handler)
        logger.setLevel(logging.DEBUG)
        
    def browse_csv(self):
        """Open file dialog to select CSV file."""
        filename = filedialog.askopenfilename(
            title="Select Camera Configuration CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialdir=Path.cwd()
        )
        
        if filename:
            self.csv_filename = filename
            self.csv_label.config(text=Path(filename).name)
            self.load_csv()
            
    def load_csv(self):
        """Load camera configurations from CSV and populate table."""
        # Load all cameras (including completed ones) for GUI display
        self.configs = read_camera_config_csv(self.csv_filename, skip_completed=False)
        
        if not self.configs:
            messagebox.showwarning(
                "No Cameras",
                f"No camera configurations found in {self.csv_filename}"
            )
            return
        
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Add cameras to tree
        for cfg in self.configs:
            # Use existing status from CSV if present
            existing_status = cfg.get('status', '')
            if existing_status == 'Completed':
                status = 'Completed'
                message = 'Previously configured'
                tag = 'completed'
            else:
                status = 'Pending'
                message = 'Waiting to start...'
                tag = 'pending'
            
            self.tree.insert(
                '',
                tk.END,
                iid=cfg['mac'],
                values=(
                    cfg['mac'],
                    cfg.get('name', 'N/A'),
                    'Unknown',  # Current IP (will be populated during discovery)
                    cfg['new_ip'],
                    cfg['username'],
                    status,
                    message
                ),
                tags=(tag,)
            )
        
        self.update_status_bar(f"Loaded {len(self.configs)} camera(s) from CSV")
        
    def update_camera_status(self, mac, current_ip=None, status=None, message=None):
        """Update a camera's status in the tree."""
        if not self.tree.exists(mac):
            return
        
        # Get current values
        values = list(self.tree.item(mac)['values'])
        
        # Update values
        if current_ip:
            values[2] = current_ip  # Current_IP column
        if status:
            values[5] = status  # Status column
        if message:
            values[6] = message  # Message column
        
        # Determine tag based on status
        tag = 'pending'
        if status:
            status_lower = status.lower()
            if 'discover' in status_lower:
                tag = 'discovering'
            elif 'configur' in status_lower:
                tag = 'configuring'
            elif 'completed' in status_lower or 'success' in status_lower:
                tag = 'completed'
            elif 'failed' in status_lower or 'error' in status_lower:
                tag = 'failed'
        
        # Update tree item
        self.tree.item(mac, values=values, tags=(tag,))
        
    def update_status_bar(self, message):
        """Update the status bar text."""
        self.status_bar.config(text=message)
        
    def clear_log(self):
        """Clear the log output."""
        self.log_text.configure(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state='disabled')
        
    def start_programming(self):
        """Start the batch programming process in a background thread."""
        if self.is_running:
            return
        
        if not self.configs:
            messagebox.showwarning("No Cameras", "Please load a CSV file with camera configurations.")
            return
        
        # Count pending vs completed
        completed_count = sum(1 for cfg in self.configs if cfg.get('status') == 'Completed')
        pending_count = len(self.configs) - completed_count
        
        # Confirm start
        message = f"Start programming {len(self.configs)} camera(s)?\n\n"
        if completed_count > 0:
            message += f"• {pending_count} camera(s) pending\n"
            message += f"• {completed_count} camera(s) already completed\n\n"
            message += "Note: Already-completed cameras will be reprogrammed if you proceed.\n\n"
        message += "This will discover cameras on the network and configure them according to the CSV file."
        
        result = messagebox.askyesno("Start Programming", message)
        
        if not result:
            return
        
        # Update UI state
        self.is_running = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.update_status_bar("Starting batch programming...")
        
        # Start worker thread
        thread = threading.Thread(target=self.programming_worker, daemon=True)
        thread.start()
        
    def stop_programming(self):
        """Stop the batch programming process."""
        self.is_running = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.update_status_bar("Stopping...")
        
    def programming_worker(self):
        """Worker thread that runs the batch programming logic."""
        try:
            logger = logging.getLogger('axis_programmer')
            logger.info("="*70)
            logger.info("Starting Axis Camera Batch Programming")
            logger.info("="*70)
            
            # Update all cameras to "Discovering" status
            for cfg in self.configs:
                self.status_queue.put({
                    'mac': cfg['mac'],
                    'status': 'Discovering',
                    'message': 'Searching for camera on network...'
                })
            
            self.status_queue.put({'status_bar': 'Discovering cameras...'})
            
            # Step 1: Discover cameras
            logger.info(f"\nDiscovering {len(self.configs)} camera(s) on network...")
            discovered = discover_cameras_on_network(self.configs)
            
            if not discovered:
                logger.error("No cameras discovered!")
                self.status_queue.put({'status_bar': 'Discovery failed - no cameras found'})
                
                for cfg in self.configs:
                    self.status_queue.put({
                        'mac': cfg['mac'],
                        'status': 'Failed',
                        'message': 'Camera not found on network'
                    })
                return
            
            logger.info(f"Discovered {len(discovered)} camera(s)")
            
            # Update discovered cameras with current IP
            discovered_macs = {cam['mac']: cam['ip'] for cam in discovered}
            for cfg in self.configs:
                if cfg['mac'] in discovered_macs:
                    self.status_queue.put({
                        'mac': cfg['mac'],
                        'current_ip': discovered_macs[cfg['mac']],
                        'status': 'Ready',
                        'message': 'Camera found, ready to configure'
                    })
                else:
                    self.status_queue.put({
                        'mac': cfg['mac'],
                        'status': 'Failed',
                        'message': 'Camera not discovered'
                    })
            
            # Step 2: Configure each discovered camera
            success_count = 0
            failed_count = 0
            
            for cam_info in discovered:
                if not self.is_running:
                    logger.warning("Programming stopped by user")
                    break
                
                mac = cam_info['mac']
                
                # Find matching config
                config = next((cfg for cfg in self.configs if cfg['mac'] == mac), None)
                if not config:
                    logger.warning(f"No configuration found for discovered camera {mac}")
                    continue
                
                # Update status to configuring
                self.status_queue.put({
                    'mac': mac,
                    'status': 'Configuring',
                    'message': 'Applying configuration...'
                })
                
                self.status_queue.put({
                    'status_bar': f'Configuring {mac}... ({success_count + failed_count + 1}/{len(discovered)})'
                })
                
                # Configure the camera (pass the AxisCamera object, not the dict)
                result = configure_camera(cam_info['camera'], config, self.csv_filename)
                
                if result:
                    success_count += 1
                    self.status_queue.put({
                        'mac': mac,
                        'status': 'Completed',
                        'message': 'Successfully configured'
                    })
                else:
                    failed_count += 1
                    self.status_queue.put({
                        'mac': mac,
                        'status': 'Failed',
                        'message': 'Configuration failed - see log'
                    })
            
            # Final summary
            logger.info("\n" + "="*70)
            logger.info("Batch Programming Complete")
            logger.info(f"  Success: {success_count}")
            logger.info(f"  Failed: {failed_count}")
            logger.info(f"  Total: {success_count + failed_count}")
            logger.info("="*70)
            
            self.status_queue.put({
                'status_bar': f'Complete - Success: {success_count}, Failed: {failed_count}'
            })
            
        except Exception as e:
            logger.error(f"Programming worker error: {e}", exc_info=True)
            self.status_queue.put({'status_bar': f'Error: {e}'})
            
        finally:
            # Re-enable start button
            def reset_ui():
                self.is_running = False
                self.start_button.config(state=tk.NORMAL)
                self.stop_button.config(state=tk.DISABLED)
            
            self.root.after(0, reset_ui)
            
    def check_status_updates(self):
        """Check for status updates from the worker thread."""
        try:
            while True:
                update = self.status_queue.get_nowait()
                
                if 'status_bar' in update:
                    self.update_status_bar(update['status_bar'])
                elif 'mac' in update:
                    self.update_camera_status(
                        update['mac'],
                        current_ip=update.get('current_ip'),
                        status=update.get('status'),
                        message=update.get('message')
                    )
                    
        except queue.Empty:
            pass
        
        # Schedule next check
        self.root.after(100, self.check_status_updates)


def main():
    """Main entry point for the GUI application."""
    root = tk.Tk()
    app = AxisBatchProgrammerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
