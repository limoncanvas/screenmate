import os
import time
import threading
import json
import sqlite3
from datetime import datetime
import platform
import subprocess
import tempfile
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from PIL import Image, ImageTk
import io
import base64
import logging
from dotenv import load_dotenv
import pystray
from PIL import Image as PILImage, ImageDraw

# Import our modules
from screen_capture import ScreenCapture
from claude_integration import ClaudeIntegration
from input_monitor import InputMonitor
from memory_system import SmartMemorySystem
from task_executor import TaskExecutor

class ScreenMateApp:
    def __init__(self):
        """Initialize the Key Points Extractor MVP"""
        # Initialize core components
        self.screen_capture = ScreenCapture()
        self.claude = ClaudeIntegration()
        
        # Analysis state
        self.analyzing = False
        self.analysis_thread = None
        self.last_analysis_time = 0
        self.analysis_interval = 15.0  # Longer interval for cost efficiency
        
        # Create the main window
        self.app = ctk.CTk()
        self.app.title("ScreenMate - Key Points Extractor")
        self.app.geometry("600x500")
        
        # Set up UI
        self._setup_ui()
        
        # Set up system tray
        self._setup_system_tray()
        
        # Start the main loop
        self.app.mainloop()
    
    def _setup_ui(self):
        """Set up a simplified UI focused on key points extraction"""
        # Configure the theme
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")
        
        # Main frame
        main_frame = ctk.CTkFrame(self.app)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Title
        title_label = ctk.CTkLabel(
            main_frame,
            text="ScreenMate",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.pack(pady=(10, 20))
        
        # Status indicator
        status_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        status_frame.pack(fill="x", pady=(0, 10))
        
        self.status_indicator = ctk.CTkLabel(
            status_frame,
            text="●",
            font=ctk.CTkFont(size=20),
            text_color="red"
        )
        self.status_indicator.pack(side="left", padx=(10, 5))
        
        self.status_label = ctk.CTkLabel(
            status_frame,
            text="Inactive",
            font=ctk.CTkFont(size=14)
        )
        self.status_label.pack(side="left")
        
        # Key Points section
        key_points_label = ctk.CTkLabel(
            main_frame,
            text="Key Points:",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        key_points_label.pack(anchor="w", padx=10, pady=(10, 5))
        
        self.key_points_text = ctk.CTkTextbox(main_frame, height=250)
        self.key_points_text.pack(fill="x", padx=10, pady=(0, 10))
        self.key_points_text.insert("1.0", "Key points will appear here...")
        self.key_points_text.configure(state="disabled")
        
        # Control buttons
        control_frame = ctk.CTkFrame(main_frame)
        control_frame.pack(fill="x", padx=10, pady=10)
        
        self.start_button = ctk.CTkButton(
            control_frame,
            text="Start Monitoring",
            command=self._toggle_monitoring
        )
        self.start_button.pack(side="left", padx=(0, 10), expand=True, fill="x")
        
        self.analyze_now_button = ctk.CTkButton(
            control_frame,
            text="Extract Now",
            command=self._analyze_once
        )
        self.analyze_now_button.pack(side="right", padx=(10, 0), expand=True, fill="x")
        
        # Settings section
        settings_frame = ctk.CTkFrame(main_frame)
        settings_frame.pack(fill="x", padx=10, pady=10)
        
        # Economy mode toggle
        self.economy_mode_var = ctk.BooleanVar(value=False)
        economy_switch = ctk.CTkSwitch(
            settings_frame, 
            text="Economy Mode (no API)", 
            variable=self.economy_mode_var
        )
        economy_switch.pack(anchor="w", padx=20, pady=10)
        
        # Interval setting
        interval_frame = ctk.CTkFrame(settings_frame)
        interval_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        interval_label = ctk.CTkLabel(interval_frame, text="Capture Interval (seconds):")
        interval_label.pack(side="left", padx=(10, 10))
        
        self.interval_entry = ctk.CTkEntry(interval_frame, width=60)
        self.interval_entry.pack(side="left")
        self.interval_entry.insert(0, "15")  # Longer default interval to reduce API costs
    
    def _setup_system_tray(self):
        """Set up system tray icon for easy access"""
        # Create a simple icon
        icon_size = (64, 64)
        icon_image = PILImage.new('RGB', icon_size, color=(0, 120, 212))
        draw = ImageDraw.Draw(icon_image)
        draw.rectangle((10, 10, 54, 54), fill=(255, 255, 255))
        
        # Create system tray menu
        menu = (
            pystray.MenuItem("Show Window", self._show_window),
            pystray.MenuItem("Extract Now", self._analyze_once),
            pystray.MenuItem("Toggle Monitoring", self._toggle_monitoring),
            pystray.MenuItem("Quit", self._quit_app)
        )
        
        # Create and run the icon
        self.tray_icon = pystray.Icon("ScreenMate", icon_image, "ScreenMate", menu)
        
        # Start in a separate thread
        self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        self.tray_thread.start()
    
    def _show_window(self):
        """Show the main window"""
        self.app.deiconify()
        self.app.lift()
    
    def _quit_app(self):
        """Quit the application"""
        if self.tray_icon:
            self.tray_icon.stop()
        self.app.quit()
    
    def _toggle_monitoring(self):
        """Toggle continuous monitoring"""
        if self.analyzing:
            self.analyzing = False
            self.start_button.configure(text="Start Monitoring")
            self.status_indicator.configure(text_color="red")
            self.status_label.configure(text="Inactive")
        else:
            self.analyzing = True
            self.start_button.configure(text="Stop Monitoring")
            self.status_indicator.configure(text_color="green")
            self.status_label.configure(text="Active")
            self._start_analysis_thread()
    
    def _analyze_once(self):
        """Perform a one-time analysis"""
        self._perform_analysis()
    
    def _start_analysis_thread(self):
        """Start the analysis thread"""
        if self.analysis_thread and self.analysis_thread.is_alive():
            return
        
        self.analysis_thread = threading.Thread(target=self._analysis_loop, daemon=True)
        self.analysis_thread.start()
    
    def _analysis_loop(self):
        """Continuous analysis loop"""
        while self.analyzing:
            current_time = time.time()
            if current_time - self.last_analysis_time >= self.analysis_interval:
                self._perform_analysis()
                self.last_analysis_time = current_time
            time.sleep(1)
    
    def _perform_analysis(self):
        """Extract key points from the current screen content"""
        try:
            # Update UI to show analysis is happening
            self.app.after(0, lambda: self.status_label.configure(text="Analyzing..."))
            
            # Capture screen and extract text
            screen_data = self.screen_capture.analyze_screen()
            
            if not screen_data or not screen_data["text"] or len(screen_data["text"]) < 50:
                self.app.after(0, lambda: self.status_label.configure(
                    text="Not enough text to analyze" if not self.analyzing else "Active"
                ))
                return
            
            # Check if content has changed significantly
            if hasattr(self, 'last_screen_text'):
                # Simple similarity check
                from difflib import SequenceMatcher
                similarity = SequenceMatcher(None, self.last_screen_text, screen_data["text"]).ratio()
                
                # Skip if content is very similar to last analysis (>90% similar)
                if similarity > 0.9:
                    self.app.after(0, lambda: self.status_label.configure(
                        text="Content unchanged" if not self.analyzing else "Active"
                    ))
                    return
            
            # Save current text for future comparison
            self.last_screen_text = screen_data["text"]
            
            # Check economy mode
            use_api = not self.economy_mode_var.get()
            
            # Get key points from Claude
            key_points = self.claude.get_key_points(screen_data["text"], use_api=use_api)
            
            # Update key points text
            self.app.after(0, lambda: self._update_key_points(key_points))
            
            # Update status
            self.app.after(0, lambda: self.status_label.configure(
                text="Active" if self.analyzing else "Analyzed"
            ))
            
        except Exception as e:
            error_msg = f"Error during analysis: {str(e)}"
            self.app.after(0, lambda: self._update_key_points(error_msg))
            self.app.after(0, lambda: self.status_label.configure(text="Error"))
    
    def _update_key_points(self, text):
        """Update the key points text widget"""
        self.key_points_text.configure(state="normal")
        self.key_points_text.delete("1.0", "end")
        self.key_points_text.insert("1.0", text)
        self.key_points_text.configure(state="disabled")

if __name__ == "__main__":
    app = ScreenMateApp() 