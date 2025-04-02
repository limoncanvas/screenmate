import threading
import time
import queue
import platform
from pynput import keyboard, mouse
from collections import deque
import json
import os

# For window tracking
if platform.system() == "Windows":
    import pygetwindow as gw
elif platform.system() == "Darwin":  # macOS
    from AppKit import NSWorkspace
    from Quartz import (
        CGWindowListCopyWindowInfo,
        kCGWindowListOptionOnScreenOnly,
        kCGNullWindowID
    )

class InputMonitor:
    def __init__(self, context_size=100):
        """Initialize the input monitoring system"""
        # Store recent interactions
        self.recent_keystrokes = deque(maxlen=context_size)
        self.recent_clicks = deque(maxlen=20)
        self.current_app = {"name": "", "title": "", "since": time.time()}
        self.previous_apps = deque(maxlen=5)
        
        # Processing queue
        self.input_queue = queue.Queue()
        
        # Privacy settings
        self.excluded_apps = ["keychain", "password", "wallet", "1password", "lastpass", "bitwarden"]
        self.keystroke_logging_enabled = True
        self.click_logging_enabled = True
        self.window_logging_enabled = True
        
        # Privacy mode state
        self.privacy_mode = False
        
        # For text accumulation
        self.current_text_buffer = ""
        self.last_keystroke_time = 0
        self.keystroke_timeout = 2.0  # seconds
        
        # Monitoring state
        self.monitoring = False
        self.monitoring_thread = None
        self.listener_keyboard = None
        self.listener_mouse = None
        self.window_monitor_thread = None
    
    def start_monitoring(self):
        """Start all monitoring activities"""
        if self.monitoring:
            return
            
        self.monitoring = True
        
        # Start keyboard listener
        if self.keystroke_logging_enabled:
            self.listener_keyboard = keyboard.Listener(
                on_press=self._on_key_press,
                on_release=self._on_key_release
            )
            self.listener_keyboard.start()
        
        # Start mouse listener
        if self.click_logging_enabled:
            self.listener_mouse = mouse.Listener(
                on_click=self._on_mouse_click,
                on_move=self._on_mouse_move
            )
            self.listener_mouse.start()
        
        # Start window monitor
        if self.window_logging_enabled:
            self.window_monitor_thread = threading.Thread(target=self._monitor_active_window)
            self.window_monitor_thread.daemon = True
            self.window_monitor_thread.start()
        
        # Start the processing thread
        self.monitoring_thread = threading.Thread(target=self._process_inputs)
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()
    
    def stop_monitoring(self):
        """Stop all monitoring activities"""
        self.monitoring = False
        
        if self.listener_keyboard:
            self.listener_keyboard.stop()
            self.listener_keyboard = None
            
        if self.listener_mouse:
            self.listener_mouse.stop()
            self.listener_mouse = None
    
    def toggle_privacy_mode(self, enabled=None):
        """Toggle privacy mode on/off"""
        if enabled is not None:
            self.privacy_mode = enabled
        else:
            self.privacy_mode = not self.privacy_mode
        
        return self.privacy_mode
    
    def _on_key_press(self, key):
        """Handle key press events"""
        if not self.monitoring or self.privacy_mode:
            return
            
        # Check if we should be logging keystrokes in the current app
        if self._is_sensitive_app():
            return
            
        try:
            # For regular characters
            if hasattr(key, 'char') and key.char:
                char = key.char
                self._add_to_text_buffer(char)
            # For special keys
            else:
                key_name = str(key).replace("Key.", "")
                
                # Handle common editing keys
                if key_name == "space":
                    self._add_to_text_buffer(" ")
                elif key_name == "enter":
                    # Commit the current buffer as it's likely a complete thought
                    self._commit_text_buffer(True)
                elif key_name == "backspace":
                    # Handle backspace by removing last character
                    if self.current_text_buffer:
                        self.current_text_buffer = self.current_text_buffer[:-1]
                else:
                    # Just note the special key press but don't add to text buffer
                    self.input_queue.put({"type": "special_key", "key": key_name, "time": time.time()})
                    
        except Exception as e:
            print(f"Error processing keystroke: {e}")
    
    def _on_key_release(self, key):
        """Handle key release events"""
        # Not doing anything special on key release for now
        pass
    
    def _add_to_text_buffer(self, char):
        """Add character to the current text buffer"""
        self.current_text_buffer += char
        self.last_keystroke_time = time.time()
        
    def _commit_text_buffer(self, force=False):
        """Commit the current text buffer if it's meaningful"""
        current_time = time.time()
        
        # Only commit if buffer has content and enough time has passed or force commit
        if self.current_text_buffer and (force or current_time - self.last_keystroke_time > self.keystroke_timeout):
            if len(self.current_text_buffer.strip()) > 3:  # Only record meaningful text
                self.recent_keystrokes.append({
                    "text": self.current_text_buffer,
                    "app": self.current_app["name"],
                    "time": current_time
                })
                
                # Add to processing queue
                self.input_queue.put({
                    "type": "text_input",
                    "text": self.current_text_buffer,
                    "app": self.current_app["name"],
                    "time": current_time
                })
            
            # Clear the buffer
            self.current_text_buffer = ""
    
    def _on_mouse_click(self, x, y, button, pressed):
        """Handle mouse click events"""
        if not self.monitoring or self.privacy_mode:
            return
            
        if pressed:  # Only capture press, not release
            click_info = {
                "x": x, 
                "y": y,
                "button": str(button).replace("Button.", ""),
                "app": self.current_app["name"],
                "time": time.time()
            }
            
            self.recent_clicks.append(click_info)
            self.input_queue.put({"type": "mouse_click", "data": click_info})
            
            # Commit any pending text when user clicks
            self._commit_text_buffer()
    
    def _on_mouse_move(self, x, y):
        """Handle mouse movement"""
        # Not storing every movement for privacy and performance reasons
        # Could implement to track general activity levels
        pass
    
    def _monitor_active_window(self):
        """Monitor the currently active window/application"""
        while self.monitoring:
            if not self.privacy_mode and self.window_logging_enabled:
                try:
                    current_app_info = self._get_active_window_info()
                    
                    # If the application changed
                    if current_app_info["name"] != self.current_app["name"] or \
                       current_app_info["title"] != self.current_app["title"]:
                        
                        # Store the previous app if it was open for more than 3 seconds
                        if time.time() - self.current_app["since"] > 3:
                            self.previous_apps.append(self.current_app)
                        
                        # Update current app
                        self.current_app = {
                            "name": current_app_info["name"],
                            "title": current_app_info["title"],
                            "since": time.time()
                        }
                        
                        # Add to queue
                        self.input_queue.put({
                            "type": "app_switch",
                            "from": self.previous_apps[-1]["name"] if self.previous_apps else None,
                            "to": current_app_info["name"],
                            "title": current_app_info["title"],
                            "time": time.time()
                        })
                        
                        # Commit any pending text when switching apps
                        self._commit_text_buffer()
                    
                except Exception as e:
                    print(f"Error monitoring active window: {e}")
            
            # Check every second - adjust as needed
            time.sleep(1)
    
    def _get_active_window_info(self):
        """Get information about the currently active window"""
        result = {"name": "unknown", "title": "unknown"}
        
        try:
            if platform.system() == "Windows":
                # Windows implementation
                active_window = gw.getActiveWindow()
                if active_window:
                    result["title"] = active_window.title
                    # Extract app name from window title or process name
                    result["name"] = active_window.title.split(" - ")[-1] if " - " in active_window.title else active_window.title
                
            elif platform.system() == "Darwin":  # macOS
                # macOS implementation
                active_app = NSWorkspace.sharedWorkspace().activeApplication()
                if active_app:
                    result["name"] = active_app['NSApplicationName']
                    
                    # Try to get window title - more complex on macOS
                    window_info = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)
                    for info in window_info:
                        if info.get('kCGWindowOwnerName') == result["name"]:
                            result["title"] = info.get('kCGWindowName', 'unknown')
                            break
            
            elif platform.system() == "Linux":
                # Basic Linux implementation - would need enhancement
                # This is a simplified approach that might not work on all Linux distros
                try:
                    import subprocess
                    cmd = "xdotool getwindowfocus getwindowname"
                    title = subprocess.check_output(cmd, shell=True).decode().strip()
                    result["title"] = title
                    result["name"] = title.split(" - ")[-1] if " - " in title else title
                except:
                    pass
        
        except Exception as e:
            print(f"Error getting active window: {e}")
        
        return result
    
    def _process_inputs(self):
        """Process the input queue"""
        while self.monitoring:
            try:
                # Check for text buffer timeout
                current_time = time.time()
                if self.current_text_buffer and current_time - self.last_keystroke_time > self.keystroke_timeout:
                    self._commit_text_buffer()
                
                # Process any queued inputs
                try:
                    # Non-blocking get with timeout
                    item = self.input_queue.get(timeout=0.5)
                    # Process the input item - for now just storing in memory
                    # Later, this could feed into an analysis system
                except queue.Empty:
                    continue
            
            except Exception as e:
                print(f"Error processing input: {e}")
            
            # Sleep briefly to reduce CPU usage
            time.sleep(0.1)
    
    def _is_sensitive_app(self):
        """Check if the current app is in the sensitive/excluded list"""
        if not self.current_app:
            return False
            
        app_name = self.current_app["name"].lower()
        title = self.current_app["title"].lower()
        
        # Check against excluded apps list
        for excluded in self.excluded_apps:
            if excluded in app_name or excluded in title:
                return True
        
        # Additional checks for sensitive windows
        sensitive_terms = ["password", "login", "credential", "secure", "private", "credit card", "payment"]
        for term in sensitive_terms:
            if term in title:
                return True
                
        return False
    
    def get_context_data(self):
        """Get contextual data for AI processing"""
        # Commit any pending text
        self._commit_text_buffer(True)
        
        # Build context data
        context = {
            "current_app": {
                "name": self.current_app["name"],
                "title": self.current_app["title"],
                "time_spent": time.time() - self.current_app["since"]
            },
            "recent_apps": [app for app in self.previous_apps],
            "recent_input": []
        }
        
        # Add recent text input (be careful with privacy here)
        recent_text = []
        for item in self.recent_keystrokes:
            # Only include text that might be relevant and not too private
            if len(item["text"]) >= 5 and not self._is_likely_sensitive(item["text"]):
                recent_text.append({
                    "text": item["text"],
                    "app": item["app"]
                })
        
        context["recent_input"] = recent_text[-10:]  # Only last 10 entries
        
        return context
    
    def _is_likely_sensitive(self, text):
        """Check if text is likely sensitive and should be excluded"""
        # Check for patterns that suggest sensitive information
        sensitive_patterns = [
            # Passwords and credentials
            r"\bpassword\b", r"\bpasswort\b", r"\bpwd\b", 
            # Credit card patterns
            r"\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}", 
            # SSN patterns
            r"\d{3}[\s-]?\d{2}[\s-]?\d{4}"
        ]
        
        import re
        for pattern in sensitive_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        return False 