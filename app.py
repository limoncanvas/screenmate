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

# Import our modules
from screen_capture import ScreenCapture
from claude_integration import ClaudeIntegration
from input_monitor import InputMonitor
from memory_system import SmartMemorySystem
from task_executor import TaskExecutor

class ScreenMateApp:
    def __init__(self):
        self.screen_capture = ScreenCapture()
        self.claude = ClaudeIntegration()
        self.input_monitor = InputMonitor()
        self.memory = SmartMemorySystem()
        self.task_executor = TaskExecutor()
        
        # Analysis state
        self.analyzing = True
        self.analysis_thread = None
        self.last_analysis_time = 0
        self.analysis_interval = 10.0
        self.last_insight = None
        
        # Notification settings
        self.notification_duration = 30  # Increased to 30 seconds
        self.notification_sound = True
        self.notification_repeat = True
        self.notification_delay = 0.5
        
        # Create the main window
        self.app = ctk.CTk()
        self.app.title("ScreenMate")
        self.app.geometry("700x600")
        
        # Force the window to be visible and in front
        self.app.lift()
        self.app.attributes('-topmost', True)
        self.app.after_idle(self.app.attributes, '-topmost', False)
        
        # Set the appearance mode
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")
        
        # Create system tray icon
        self._create_system_tray()
        
        self._setup_ui()
        
        # Start minimized
        self.app.withdraw()
        
        # Start analysis thread
        self._start_analysis()
        
        # Start input monitoring
        self.input_monitor.start_monitoring()
        
        # Start the main loop
        self.app.mainloop()

    def _create_system_tray(self):
        """Create the system tray icon"""
        if platform.system() == "Darwin":  # macOS
            # Set up window management for macOS
            self.icon = None
            self.app.createcommand('tk::mac::ReopenApplication', self._show_window)
            self.app.protocol("WM_DELETE_WINDOW", self._minimize_to_tray)
            return
            
        try:
            # Create system tray icon for other platforms
            icon_image = PILImage.new('RGB', (64, 64), color='blue')
            menu = (
                pystray.MenuItem("Show Window", self._show_window),
                pystray.MenuItem("Toggle Analysis", self._toggle_analysis),
                pystray.MenuItem("Exit", self._quit_app)
            )
            self.icon = pystray.Icon("ScreenMate", icon_image, "ScreenMate", menu)
            threading.Thread(target=self.icon.run, daemon=True).start()
        except Exception as e:
            print(f"System tray creation failed: {e}")
            self.app.protocol("WM_DELETE_WINDOW", self._minimize_to_tray)
    
    def _show_window(self, _=None):
        """Show the main window"""
        self.app.deiconify()
        self.app.lift()
        self.app.attributes('-topmost', True)
        self.app.after_idle(self.app.attributes, '-topmost', False)
    
    def _quit_app(self):
        """Quit the application"""
        self.analyzing = False
        self.input_monitor.stop_monitoring()  # Stop input monitoring
        if self.icon and platform.system() != "Darwin":
            self.icon.stop()
        self.app.quit()
    
    def _setup_ui(self):
        """Set up the user interface with tabs"""
        # Main frame
        main_frame = ctk.CTkFrame(self.app)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Title and minimize button
        title_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        title_frame.pack(fill="x", pady=(10, 20))
        
        title_label = ctk.CTkLabel(
            title_frame, 
            text="ScreenMate", 
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.pack(side="left")
        
        minimize_button = ctk.CTkButton(
            title_frame,
            text="Minimize to Tray",
            command=self._minimize_to_tray,
            width=120
        )
        minimize_button.pack(side="right")
        
        # Status indicator
        self.status_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        self.status_frame.pack(fill="x", pady=(0, 10))
        
        self.status_indicator = ctk.CTkLabel(
            self.status_frame,
            text="●",
            font=ctk.CTkFont(size=20),
            text_color="green"
        )
        self.status_indicator.pack(side="left", padx=(10, 5))
        
        self.status_label = ctk.CTkLabel(
            self.status_frame,
            text="Active",
            font=ctk.CTkFont(size=14)
        )
        self.status_label.pack(side="left")
        
        # Create tabview
        self.tabview = ctk.CTkTabview(main_frame)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Create tabs
        self.tab_home = self.tabview.add("Home")
        self.tab_topics = self.tabview.add("Topics")
        self.tab_summaries = self.tabview.add("Summaries")
        self.tab_tasks = self.tabview.add("Tasks")  # Add Tasks tab
        self.tab_settings = self.tabview.add("Settings")
        
        # Set up each tab
        self._setup_home_tab()
        self._setup_topics_tab()
        self._setup_summaries_tab()
        self._setup_tasks_tab()  # Add tasks tab setup
        self._setup_settings_tab()

    def _setup_home_tab(self):
        """Set up the Home tab"""
        # Preview frame
        preview_label = ctk.CTkLabel(self.tab_home, text="Screen Preview:")
        preview_label.pack(anchor="w", padx=10, pady=(10, 5))
        
        self.preview_frame = ctk.CTkFrame(self.tab_home, height=150)
        self.preview_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        self.preview_image = ctk.CTkLabel(self.preview_frame, text="No preview available")
        self.preview_image.pack(expand=True, fill="both", padx=5, pady=5)
        
        # Insights frame
        insights_label = ctk.CTkLabel(self.tab_home, text="AI Insights:")
        insights_label.pack(anchor="w", padx=10, pady=(10, 5))
        
        self.insights_text = ctk.CTkTextbox(self.tab_home, height=200)
        self.insights_text.pack(fill="x", padx=10, pady=(0, 10))
        self.insights_text.insert("1.0", "Insights will appear here...")
        self.insights_text.configure(state="disabled")
        
        # Memory section
        memory_label = ctk.CTkLabel(self.tab_home, text="Related Memories:")
        memory_label.pack(anchor="w", padx=10, pady=(10, 5))
        
        self.memory_text = ctk.CTkTextbox(self.tab_home, height=150)
        self.memory_text.pack(fill="x", padx=10, pady=(0, 10))
        self.memory_text.insert("1.0", "Past relevant memories will appear here...")
        self.memory_text.configure(state="disabled")
        
        # Control buttons
        self.button_frame = ctk.CTkFrame(self.tab_home, fg_color="transparent")
        self.button_frame.pack(fill="x", pady=10)
        
        self.start_button = ctk.CTkButton(
            self.button_frame,
            text="Stop Analysis",
            command=self._toggle_analysis
        )
        self.start_button.pack(side="left", padx=10, expand=True, fill="x")
        
        self.analyze_now_button = ctk.CTkButton(
            self.button_frame,
            text="Analyze Now",
            command=self._analyze_once
        )
        self.analyze_now_button.pack(side="right", padx=10, expand=True, fill="x")

    def _setup_topics_tab(self):
        """Set up the Topics tab"""
        topics_frame = ctk.CTkFrame(self.tab_topics)
        topics_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Search box
        search_frame = ctk.CTkFrame(topics_frame)
        search_frame.pack(fill="x", padx=10, pady=(10, 20))
        
        search_label = ctk.CTkLabel(search_frame, text="Search Topics:")
        search_label.pack(side="left", padx=(10, 10))
        
        self.topic_search_entry = ctk.CTkEntry(search_frame, width=200)
        self.topic_search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.topic_search_entry.bind("<KeyRelease>", lambda e: self._search_topics())
        
        # Topics list
        topics_list_frame = ctk.CTkFrame(topics_frame)
        topics_list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        topics_list_label = ctk.CTkLabel(
            topics_list_frame,
            text="Topics:",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        topics_list_label.pack(anchor="w", padx=10, pady=(10, 5))
        
        # Create a frame for the listbox and scrollbar
        list_container = ctk.CTkFrame(topics_list_frame)
        list_container.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # Topics listbox
        self.topics_listbox = tk.Listbox(
            list_container,
            bg="#2b2b2b",
            fg="white",
            selectbackground="#1f538d",
            selectforeground="white",
            font=("Helvetica", 12),
            height=10
        )
        self.topics_listbox.pack(side="left", fill="both", expand=True)
        self.topics_listbox.bind("<<ListboxSelect>>", self._on_topic_select)
        
        # Scrollbar for topics
        topics_scrollbar = ctk.CTkScrollbar(list_container, command=self.topics_listbox.yview)
        topics_scrollbar.pack(side="right", fill="y")
        self.topics_listbox.config(yscrollcommand=topics_scrollbar.set)
        
        # Memories for selected topic
        memories_frame = ctk.CTkFrame(topics_frame)
        memories_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        memories_label = ctk.CTkLabel(
            memories_frame,
            text="Memories:",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        memories_label.pack(anchor="w", padx=10, pady=(10, 5))
        
        # Memories text
        self.topic_memories_text = ctk.CTkTextbox(
            memories_frame,
            wrap="word",
            font=ctk.CTkFont(size=12)
        )
        self.topic_memories_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # Buttons frame
        buttons_frame = ctk.CTkFrame(topics_frame)
        buttons_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        # Refresh button
        refresh_button = ctk.CTkButton(
            buttons_frame,
            text="Refresh Topics",
            command=self._populate_topics_list
        )
        refresh_button.pack(side="left", padx=10, pady=10)
        
        # Create sample topics button
        sample_button = ctk.CTkButton(
            buttons_frame,
            text="Create Sample Topics",
            command=self._create_sample_topics
        )
        sample_button.pack(side="left", padx=10, pady=10)
        
        # Populate topics list
        self._populate_topics_list()

    def _setup_summaries_tab(self):
        """Set up the Summaries tab"""
        # Summary controls
        controls_frame = ctk.CTkFrame(self.tab_summaries)
        controls_frame.pack(fill="x", padx=10, pady=10)
        
        summary_label = ctk.CTkLabel(
            controls_frame,
            text="Generate Insight Summaries:",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        summary_label.pack(side="left", padx=10)
        
        today_button = ctk.CTkButton(
            controls_frame,
            text="Today's Summary",
            command=self._generate_today_summary
        )
        today_button.pack(side="right", padx=10)
        
        # Summary display
        self.summary_text = ctk.CTkTextbox(self.tab_summaries, height=400)
        self.summary_text.pack(fill="both", expand=True, padx=10, pady=10)
        self.summary_text.insert("1.0", "Click 'Today's Summary' to generate a summary of today's insights...")
        self.summary_text.configure(state="disabled")
        
        # Export button
        export_frame = ctk.CTkFrame(self.tab_summaries)
        export_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        export_button = ctk.CTkButton(
            export_frame,
            text="Export Summary",
            command=self._export_summary
        )
        export_button.pack(side="right", padx=10)

    def _setup_tasks_tab(self):
        """Setup the Tasks tab UI"""
        # Task input section
        task_frame = ctk.CTkFrame(self.tab_tasks)
        task_frame.pack(fill="x", padx=10, pady=10)
        
        task_label = ctk.CTkLabel(task_frame, text="Enter your task:")
        task_label.pack(pady=5)
        
        self.task_entry = ctk.CTkEntry(task_frame, width=400)
        self.task_entry.pack(pady=5)
        
        execute_button = ctk.CTkButton(
            task_frame,
            text="Execute Task",
            command=self._execute_task
        )
        execute_button.pack(pady=5)
        
        # Task status section
        status_frame = ctk.CTkFrame(self.tab_tasks)
        status_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        status_label = ctk.CTkLabel(status_frame, text="Task Status:")
        status_label.pack(pady=5)
        
        self.task_status_text = ctk.CTkTextbox(status_frame, height=200)
        self.task_status_text.pack(fill="both", expand=True, pady=5)
        
        # Task history section
        history_frame = ctk.CTkFrame(self.tab_tasks)
        history_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        history_label = ctk.CTkLabel(history_frame, text="Task History:")
        history_label.pack(pady=5)
        
        self.task_history_text = ctk.CTkTextbox(history_frame, height=200)
        self.task_history_text.pack(fill="both", expand=True, pady=5)

    def _setup_settings_tab(self):
        """Set up the Settings tab"""
        settings_frame = ctk.CTkFrame(self.tab_settings)
        settings_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        settings_label = ctk.CTkLabel(
            settings_frame,
            text="Settings:",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        settings_label.pack(anchor="w", padx=10, pady=(10, 20))
        
        # Capture interval
        interval_frame = ctk.CTkFrame(settings_frame)
        interval_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        interval_label = ctk.CTkLabel(interval_frame, text="Capture Interval (seconds):")
        interval_label.pack(side="left", padx=(10, 10))
        
        self.interval_entry = ctk.CTkEntry(interval_frame, width=60)
        self.interval_entry.pack(side="left")
        self.interval_entry.insert(0, str(self.analysis_interval))
        
        # Memory retention
        retention_frame = ctk.CTkFrame(settings_frame)
        retention_frame.pack(fill="x", padx=10, pady=(10, 10))
        
        retention_label = ctk.CTkLabel(retention_frame, text="Memory Retention (days):")
        retention_label.pack(side="left", padx=(10, 10))
        
        self.retention_entry = ctk.CTkEntry(retention_frame, width=60)
        self.retention_entry.pack(side="left")
        self.retention_entry.insert(0, "30")
        
        # API Usage Settings
        api_frame = ctk.CTkFrame(settings_frame)
        api_frame.pack(fill="x", padx=10, pady=(20, 10))
        
        api_label = ctk.CTkLabel(
            api_frame,
            text="API Usage Settings:",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        api_label.pack(anchor="w", padx=10, pady=(10, 10))
        
        # Daily budget setting
        budget_frame = ctk.CTkFrame(api_frame)
        budget_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        budget_label = ctk.CTkLabel(budget_frame, text="Daily API call budget:")
        budget_label.pack(side="left", padx=(10, 10))
        
        self.budget_entry = ctk.CTkEntry(budget_frame, width=60)
        self.budget_entry.pack(side="left")
        self.budget_entry.insert(0, str(self.claude.daily_budget))
        
        # Economy mode toggle
        self.economy_mode_var = ctk.BooleanVar(value=False)
        economy_switch = ctk.CTkSwitch(
            api_frame, 
            text="Economy Mode (minimize API usage)", 
            variable=self.economy_mode_var
        )
        economy_switch.pack(anchor="w", padx=20, pady=10)
        
        # Show current usage
        self.api_usage_label = ctk.CTkLabel(
            api_frame,
            text=f"Today's API usage: {self.claude.api_calls_today} / {self.claude.daily_budget} calls"
        )
        self.api_usage_label.pack(pady=10)
        
        # Add refresh button
        refresh_usage_btn = ctk.CTkButton(
            api_frame,
            text="Refresh Usage",
            command=self._update_api_usage
        )
        refresh_usage_btn.pack(pady=(0, 10))
        
        # Apply button
        apply_button = ctk.CTkButton(
            settings_frame,
            text="Apply Settings",
            command=self._apply_settings
        )
        apply_button.pack(pady=20)
        
        # Memory management
        memory_frame = ctk.CTkFrame(settings_frame)
        memory_frame.pack(fill="x", padx=10, pady=(20, 10))
        
        memory_label = ctk.CTkLabel(
            memory_frame,
            text="Memory Management:",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        memory_label.pack(anchor="w", padx=10, pady=(10, 10))
        
        clear_button = ctk.CTkButton(
            memory_frame,
            text="Clear Old Memories",
            command=self._clear_old_memories
        )
        clear_button.pack(pady=10)
        
        # Memory stats
        self.memory_stats = ctk.CTkLabel(
            memory_frame,
            text="Memory Stats: 0 memories stored"
        )
        self.memory_stats.pack(pady=10)
        
        # Update memory stats
        self._update_memory_stats()

    def _populate_topics_list(self):
        """Populate the topics list"""
        # Clear current list
        for widget in self.topics_listbox.winfo_children():
            widget.destroy()
        
        # Get topics from memory system
        topics = self.memory.get_all_topics()
        
        if not topics:
            no_topics_label = ctk.CTkLabel(self.topics_listbox, text="No topics found")
            no_topics_label.pack(pady=10)
            return
        
        # Add each topic as a button
        for topic, count in topics.items():
            topic_btn = ctk.CTkButton(
                self.topics_listbox,
                text=f"{topic} ({count})",
                command=lambda t=topic: self._show_topic_memories(t),
                height=30,
                anchor="w"
            )
            topic_btn.pack(fill="x", pady=2)

    def _search_topics(self):
        """Search topics based on user input"""
        query = self.topic_search_entry.get().lower()
        if not query:
            self._populate_topics_list()
            return
        
        # Clear current list
        for widget in self.topics_listbox.winfo_children():
            widget.destroy()
        
        # Get all topics
        topics = self.memory.get_all_topics()
        
        # Filter topics
        filtered_topics = {k: v for k, v in topics.items() if query in k.lower()}
        
        if not filtered_topics:
            no_results = ctk.CTkLabel(self.topics_listbox, text=f"No topics matching '{query}'")
            no_results.pack(pady=10)
            return
        
        # Add matching topics
        for topic, count in filtered_topics.items():
            topic_btn = ctk.CTkButton(
                self.topics_listbox,
                text=f"{topic} ({count})",
                command=lambda t=topic: self._show_topic_memories(t),
                height=30,
                anchor="w"
            )
            topic_btn.pack(fill="x", pady=2)

    def _show_topic_memories(self, topic):
        """Show memories for a selected topic"""
        # Update title
        self.topic_title.configure(text=f"Topic: {topic}")
        
        # Get memories for topic
        memories = self.memory.get_memories_by_topic(topic)
        
        # Update memories display
        self.topic_memories_text.configure(state="normal")
        self.topic_memories_text.delete("1.0", "end")
        
        if not memories:
            self.topic_memories_text.insert("1.0", f"No memories found for topic: {topic}")
            self.topic_memories_text.configure(state="disabled")
            return
        
        # Format memories
        for memory in memories:
            # Format timestamp
            timestamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(memory['timestamp']))
            
            # Format app info
            app_info = f" [{memory['app_name']}]" if memory['app_name'] else ""
            
            # Format memory
            formatted_memory = f"[{timestamp}]{app_info}\n{memory['content']}\n\n"
            self.topic_memories_text.insert("end", formatted_memory)
            
            # Add separator
            self.topic_memories_text.insert("end", "-" * 50 + "\n\n")
        
        self.topic_memories_text.configure(state="disabled")

    def _generate_today_summary(self):
        """Generate a summary of today's insights with economy awareness"""
        self.summary_text.configure(state="normal")
        self.summary_text.delete("1.0", "end")
        self.summary_text.insert("1.0", "Generating summary...")
        self.summary_text.configure(state="disabled")
        
        # Check economy mode
        use_api = not self.economy_mode_var.get()
        
        # Run in a thread to keep UI responsive
        threading.Thread(target=self._generate_summary_thread, args=(use_api,)).start()

    def _generate_summary_thread(self, use_api=True):
        """Thread function to generate summary"""
        try:
            memories = self.memory.get_todays_memories()
            summary = self.claude.generate_daily_summary(memories, use_api=use_api)
            
            # Update UI in the main thread
            self.app.after(0, lambda: self._update_summary_text(summary))
        except Exception as e:
            error_msg = f"Error generating summary: {str(e)}"
            self.app.after(0, lambda: self._update_summary_text(error_msg))

    def _update_summary_text(self, text):
        """Update the summary text widget"""
        self.summary_text.configure(state="normal")
        self.summary_text.delete("1.0", "end")
        self.summary_text.insert("1.0", text)
        self.summary_text.configure(state="disabled")

    def _export_summary(self):
        """Export the current summary to a file"""
        try:
            # Get summary text
            summary_text = self.summary_text.get("1.0", "end")
            
            # Format filename with current date
            date_str = time.strftime("%Y-%m-%d", time.localtime())
            filename = f"ScreenMate_Summary_{date_str}.txt"
            
            # Write to file
            with open(filename, "w") as f:
                f.write(summary_text)
            
            # Show success message
            messagebox_label = ctk.CTkLabel(
                self.tab_summaries,
                text=f"Summary exported to {filename}",
                text_color="green"
            )
            messagebox_label.pack(pady=10)
            
            # Remove message after 3 seconds
            self.app.after(3000, lambda: messagebox_label.destroy())
            
        except Exception as e:
            # Show error message
            messagebox_label = ctk.CTkLabel(
                self.tab_summaries,
                text=f"Error exporting summary: {str(e)}",
                text_color="red"
            )
            messagebox_label.pack(pady=10)
            
            # Remove message after 3 seconds
            self.app.after(3000, lambda: messagebox_label.destroy())

    def _clear_old_memories(self):
        """Clear old memories based on retention setting"""
        try:
            retention_days = int(self.retention_entry.get())
            if retention_days < 1:
                return
                
            # Clear memories
            count = self.memory.clear_old_memories(days=retention_days)
            
            # Update memory stats
            self._update_memory_stats()
            
            # Show message
            messagebox_label = ctk.CTkLabel(
                self.tab_settings,
                text=f"Cleared {count} memories older than {retention_days} days",
                text_color="green"
            )
            messagebox_label.pack(pady=10)
            
            # Remove message after 3 seconds
            self.app.after(3000, lambda: messagebox_label.destroy())
            
        except Exception as e:
            # Show error message
            messagebox_label = ctk.CTkLabel(
                self.tab_settings,
                text=f"Error clearing memories: {str(e)}",
                text_color="red"
            )
            messagebox_label.pack(pady=10)
            
            # Remove message after 3 seconds
            self.app.after(3000, lambda: messagebox_label.destroy())

    def _update_memory_stats(self):
        """Update memory statistics display"""
        stats = self.memory.get_memory_stats()
        
        stats_text = f"Memory Stats: {stats.get('total_memories', 0)} memories stored"
        
        if stats.get('earliest_memory') and stats.get('latest_memory'):
            earliest = time.strftime("%Y-%m-%d", time.localtime(stats['earliest_memory']))
            latest = time.strftime("%Y-%m-%d", time.localtime(stats['latest_memory']))
            stats_text += f"\nDate Range: {earliest} to {latest}"
        
        self.memory_stats.configure(text=stats_text)

    def _update_api_usage(self):
        """Update the API usage display"""
        # Get API usage stats
        stats = self.claude.get_api_usage_stats()
        
        # Update the API usage label with cost information
        self.api_usage_label.configure(
            text=f"Today's API usage: {stats['api_calls_today']} calls\n"
                 f"Daily cost: ${stats['daily_cost']:.6f} / ${stats['daily_budget']:.2f}\n"
                 f"Total cost: ${stats['total_cost']:.6f}"
        )
        
        # Update the budget entry to show the dollar amount
        self.budget_entry.delete(0, "end")
        self.budget_entry.insert(0, f"{stats['daily_budget']:.2f}")

    def _apply_settings(self):
        """Apply settings from the UI"""
        try:
            # Capture interval
            new_interval = float(self.interval_entry.get())
            if new_interval >= 1.0:
                self.analysis_interval = new_interval
                print(f"Capture interval updated to: {new_interval}")
            
            # Memory retention
            retention_days = int(self.retention_entry.get())
            if retention_days >= 1:
                self.memory.clear_old_memories(days=retention_days)
                print(f"Memory retention updated to: {retention_days} days")
            
            # API budget
            try:
                new_budget = float(self.budget_entry.get())
                if new_budget >= 0:
                    self.claude.max_daily_cost = new_budget
                    print(f"API budget updated to: ${new_budget:.2f}")
            except ValueError:
                print("Invalid API budget value")
            
            # Update API usage display
            self._update_api_usage()
            
            # Show success message
            messagebox_label = ctk.CTkLabel(
                self.tab_settings,
                text="Settings applied successfully",
                text_color="green"
            )
            messagebox_label.pack(pady=10)
            
            # Remove message after 3 seconds
            self.app.after(3000, lambda: messagebox_label.destroy())
            
        except ValueError:
            # Show error message
            messagebox_label = ctk.CTkLabel(
                self.tab_settings,
                text="Invalid settings values",
                text_color="red"
            )
            messagebox_label.pack(pady=10)
            
            # Remove message after 3 seconds
            self.app.after(3000, lambda: messagebox_label.destroy())

    def _minimize_to_tray(self):
        """Minimize the window to system tray"""
        try:
            if platform.system() == "Darwin":  # macOS
                self.app.iconify()  # Just minimize on macOS
            else:
                self.app.withdraw()
        except Exception as e:
            print(f"Minimize failed: {e}")
            self.app.iconify()  # Fallback to basic minimize
    
    def _start_analysis(self):
        """Start the analysis thread"""
        if self.analysis_thread is None or not self.analysis_thread.is_alive():
            self.analysis_thread = threading.Thread(target=self._continuous_analysis)
            self.analysis_thread.daemon = True
            self.analysis_thread.start()
    
    def _toggle_analysis(self):
        """Toggle continuous analysis on/off"""
        if self.analyzing:
            # Stop analysis
            self.analyzing = False
            self.input_monitor.stop_monitoring()  # Stop input monitoring
            self.start_button.configure(text="Start Analysis")
            self.status_indicator.configure(text_color="red")
            self.status_label.configure(text="Inactive")
        else:
            # Start analysis
            self.analyzing = True
            self.input_monitor.start_monitoring()  # Start input monitoring
            self.start_button.configure(text="Stop Analysis")
            self.status_indicator.configure(text_color="green")
            self.status_label.configure(text="Active")
            self._start_analysis()
    
    def _toggle_privacy(self):
        """Toggle privacy mode"""
        is_enabled = self.privacy_toggle.get()
        self.input_monitor.toggle_privacy_mode(is_enabled)
    
    def _setup_privacy_settings(self):
        """Configure privacy settings"""
        privacy_window = ctk.CTkToplevel(self.app)
        privacy_window.title("Privacy Settings")
        privacy_window.geometry("400x300")
        
        ctk.CTkLabel(privacy_window, text="Privacy Settings", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(10, 20))
        
        # Excluded applications
        ctk.CTkLabel(privacy_window, text="Excluded Applications:").pack(anchor="w", padx=20)
        excluded_apps_entry = ctk.CTkEntry(privacy_window, width=300)
        excluded_apps_entry.pack(pady=(0, 10), padx=20)
        excluded_apps_entry.insert(0, ", ".join(self.input_monitor.excluded_apps))
        
        # Toggle switches
        keystroke_var = ctk.BooleanVar(value=self.input_monitor.keystroke_logging_enabled)
        keystroke_switch = ctk.CTkSwitch(privacy_window, text="Enable Keystroke Logging", variable=keystroke_var)
        keystroke_switch.pack(anchor="w", padx=20, pady=5)
        
        clicks_var = ctk.BooleanVar(value=self.input_monitor.click_logging_enabled) 
        clicks_switch = ctk.CTkSwitch(privacy_window, text="Enable Mouse Click Logging", variable=clicks_var)
        clicks_switch.pack(anchor="w", padx=20, pady=5)
        
        window_var = ctk.BooleanVar(value=self.input_monitor.window_logging_enabled)
        window_switch = ctk.CTkSwitch(privacy_window, text="Enable Window Tracking", variable=window_var)
        window_switch.pack(anchor="w", padx=20, pady=5)
        
        # Save button
        def save_settings():
            # Update excluded apps
            excluded_apps = [app.strip() for app in excluded_apps_entry.get().split(",")]
            self.input_monitor.excluded_apps = [app for app in excluded_apps if app]
            
            # Update toggle settings
            self.input_monitor.keystroke_logging_enabled = keystroke_var.get()
            self.input_monitor.click_logging_enabled = clicks_var.get() 
            self.input_monitor.window_logging_enabled = window_var.get()
            
            # Restart monitoring if active
            if self.analyzing:
                self.input_monitor.stop_monitoring()
                self.input_monitor.start_monitoring()
                
            privacy_window.destroy()
        
        ctk.CTkButton(privacy_window, text="Save Settings", command=save_settings).pack(pady=20)
    
    def _continuous_analysis(self):
        """Continuously analyze the screen at set intervals"""
        while self.analyzing:
            current_time = time.time()
            if current_time - self.last_analysis_time >= self.analysis_interval:
                self._perform_analysis()
                self.last_analysis_time = current_time
            time.sleep(1)
    
    def _analyze_once(self):
        """Perform a single analysis"""
        self._perform_analysis()
    
    def _show_notification(self, title, message, is_important=False):
        """Show a notification with improved visibility and persistence"""
        if not message or len(message) < 20:  # Skip very short messages
            return
            
        # Store full message for display
        full_message = message
        
        # Truncate message for notification preview
        if len(message) > 200:
            preview_message = message[:197] + "..."
        else:
            preview_message = message
            
        # Replace newlines with spaces for better readability in notification
        preview_message = preview_message.replace("\n", " ")
        
        system = platform.system()
        
        if system == "Darwin":  # macOS
            # Create a temporary file to store the full message
            temp_file = os.path.expanduser("~/screenguard_temp_message.txt")
            with open(temp_file, "w") as f:
                f.write(full_message)
            
            # First notification with click action and longer duration
            subprocess.run([
                "osascript",
                "-e",
                f'display notification "{preview_message}" with title "{title}" sound name "Glass"'
            ])
            
            # Second notification after delay for important insights
            if is_important and self.notification_repeat:
                time.sleep(self.notification_delay)
                subprocess.run([
                    "osascript",
                    "-e",
                    f'display notification "{preview_message}" with title "{title}" sound name "Glass"'
                ])
                
            # Show full message in a dialog when notification is clicked
            def show_full_message():
                self.app.deiconify()  # Show the main window
                self.insights_text.delete("1.0", "end")
                self.insights_text.insert("1.0", full_message)
                self.insights_text.see("1.0")  # Scroll to top
                
            # Bind click event to show full message
            self.app.bind("<Button-1>", lambda e: show_full_message())
                
        elif system == "Windows":
            from win10toast import ToastNotifier
            toaster = ToastNotifier()
            
            # Show notification with longer duration (30 seconds)
            toaster.show_toast(
                title,
                preview_message,
                duration=30,  # Increased duration
                threaded=True,
                callback_on_click=lambda: self._show_full_message(full_message)
            )
            
            # Second notification after delay for important insights
            if is_important and self.notification_repeat:
                time.sleep(self.notification_delay)
                toaster.show_toast(
                    title,
                    preview_message,
                    duration=30,  # Increased duration
                    threaded=True,
                    callback_on_click=lambda: self._show_full_message(full_message)
                )
                
        else:  # Linux
            # Use notify-send with increased duration and critical urgency
            subprocess.run([
                "notify-send",
                "-u", "critical",
                "-t", "30000",  # 30 seconds in milliseconds
                title,
                preview_message
            ])
            
            # Second notification after delay for important insights
            if is_important and self.notification_repeat:
                time.sleep(self.notification_delay)
                subprocess.run([
                    "notify-send",
                    "-u", "critical",
                    "-t", "30000",  # 30 seconds in milliseconds
                    title,
                    preview_message
                ])
                
            # For Linux, we'll show the full message in the main window
            self.app.after(0, lambda: self._show_full_message(full_message))
    
    def _show_full_message(self, message):
        """Show the full message in the main window"""
        self.app.deiconify()  # Show the main window
        self.insights_text.delete("1.0", "end")
        self.insights_text.insert("1.0", message)
        self.insights_text.see("1.0")  # Scroll to top
    
    def _perform_analysis(self):
        """Capture the screen and get insights"""
        try:
            # Update UI to show analysis is happening
            self.app.after(0, lambda: self.status_label.configure(text="Analyzing..."))
            
            # Capture and analyze the screen
            screen_data = self.screen_capture.analyze_screen()
            
            # Get input context
            input_context = self.input_monitor.get_context_data()
            
            # Check economy mode
            use_api = not self.economy_mode_var.get()
            
            # Get insights from Claude with combined context
            insight = self.claude.get_insights_with_context(
                screen_data["text"], 
                input_context,
                use_api=use_api
            )
            
            # Store the insight in memory
            app_name = input_context.get("current_app", {}).get("name")
            memory_id = self.memory.store_insight(
                content=insight,
                source="screen_analysis",
                context=screen_data["text"],
                app_name=app_name
            )
            
            # Update preview image (resized)
            self._update_preview(screen_data["image"])
            
            # Update insights text
            self.app.after(0, lambda: self._update_insights(insight))
            
            # Get relevant memories
            self._show_relevant_memories(screen_data["text"], app_name)
            
            # Show notification if window is minimized and insight is different
            if self.app.state() == "withdrawn" and insight != self.last_insight:
                # Determine if this is an important insight
                is_important = any(keyword in insight.lower() for keyword in [
                    "important", "critical", "urgent", "deadline", "action required",
                    "warning", "error", "problem", "issue", "attention needed"
                ])
                
                self._show_notification(
                    "ScreenMate Insight",
                    insight,
                    is_important=is_important
                )
                self.last_insight = insight
            
            # Update status
            self.app.after(0, lambda: self.status_label.configure(
                text="Active" if self.analyzing else "Analyzed"
            ))
            
            # Update topics list
            self.app.after(0, self._populate_topics_list)
            
        except Exception as e:
            error_msg = f"Error during analysis: {str(e)}"
            self.app.after(0, lambda: self._update_insights(error_msg))
            self.app.after(0, lambda: self.status_label.configure(text="Error"))
    
    def _show_relevant_memories(self, context, app_name):
        """Show relevant memories from the memory system"""
        relevant_memories = self.memory.retrieve_relevant_memories(
            context=context,
            app_name=app_name,
            limit=3
        )
        
        if relevant_memories:
            memory_text = "Related memories:\n\n"
            for memory in relevant_memories:
                # Format the timestamp
                timestamp = datetime.datetime.fromtimestamp(memory.get("timestamp")).strftime("%m/%d %H:%M")
                memory_text += f"• {timestamp}: {memory.get('content')[:100]}...\n\n"
            
            # Update UI with memory text
            self.app.after(0, lambda: self._update_memory_display(memory_text))
    
    def _update_memory_display(self, text):
        """Update the memory display area"""
        self.memory_text.configure(state="normal")
        self.memory_text.delete("1.0", "end")
        self.memory_text.insert("1.0", text)
        self.memory_text.configure(state="disabled")
    
    def _search_memories(self):
        """Search memories based on user query"""
        query = self.memory_search.get()
        if not query:
            return
            
        memories = self.memory.retrieve_relevant_memories(query=query, limit=10)
        
        if memories:
            memory_text = f"Search results for '{query}':\n\n"
            for memory in memories:
                # Format the timestamp
                timestamp = datetime.datetime.fromtimestamp(memory.get("timestamp")).strftime("%m/%d %H:%M")
                memory_text += f"• {timestamp}: {memory.get('content')[:100]}...\n\n"
            
            self._update_memory_display(memory_text)
        else:
            self._update_memory_display(f"No memories found for '{query}'")
    
    def _clean_old_memories(self):
        """Clean old, low-relevance memories"""
        count = self.memory.clear_old_memories(days_threshold=30)
        self._update_memory_stats()
        self._update_memory_display(f"Cleaned {count} old, low-relevance memories")
    
    def _update_preview(self, image):
        """Update the preview with a screenshot"""
        try:
            # Resize the image to fit the preview frame
            preview_width = 380
            ratio = preview_width / image.width
            preview_height = int(image.height * ratio)
            
            resized_image = image.resize((preview_width, preview_height))
            
            # Convert to CTkImage for proper scaling
            photo = ctk.CTkImage(light_image=resized_image, dark_image=resized_image, size=(preview_width, preview_height))
            
            # Store a reference to prevent garbage collection
            self.current_photo = photo
            
            # Update the label
            self.app.after(0, lambda: self.preview_image.configure(image=photo, text=""))
        except Exception as e:
            print(f"Error updating preview: {e}")
    
    def _update_insights(self, text):
        """Update the insights text box"""
        self.insights_text.configure(state="normal")
        self.insights_text.delete("1.0", "end")
        self.insights_text.insert("1.0", text)
        self.insights_text.configure(state="disabled")
    
    def _ask_question(self):
        """Ask a specific question about the screen"""
        question = self.question_entry.get()
        if not question:
            return
        
        # Capture the current screen
        screen_data = self.screen_capture.analyze_screen()
        
        # Get input context
        input_context = self.input_monitor.get_context_data()
        
        # Get answer from Claude with context
        answer = self.claude.get_answer(question, screen_data["text"])
        
        # Update preview and insights
        self._update_preview(screen_data["image"])
        self._update_insights(answer)
        
        # Clear the question entry
        self.question_entry.delete(0, "end")
    
    def _execute_task(self):
        """Execute the task entered by the user"""
        task_description = self.task_entry.get()
        if not task_description:
            self.task_status_text.delete("1.0", "end")
            self.task_status_text.insert("1.0", "Please enter a task description")
            return
            
        # Update status
        self.task_status_text.delete("1.0", "end")
        self.task_status_text.insert("1.0", f"Executing task: {task_description}\n")
        
        # Execute task in a separate thread
        threading.Thread(target=self._execute_task_thread, args=(task_description,), daemon=True).start()
        
    def _execute_task_thread(self, task_description: str):
        """Execute task in a separate thread"""
        try:
            # Execute the task
            result = self.task_executor.execute_task(task_description)
            
            # Update status
            self.app.after(0, lambda: self._update_task_status(result))
            
        except Exception as e:
            self.app.after(0, lambda: self._update_task_error(str(e)))
            
    def _update_task_status(self, result):
        """Update the task status in the UI"""
        self.task_status_text.delete("1.0", "end")
        if result["status"] == "success":
            self.task_status_text.insert("1.0", "Task completed successfully!\n\n")
            self.task_status_text.insert("end", "Actions performed:\n")
            for action_result in result["results"]:
                self.task_status_text.insert("end", f"- {action_result}\n")
        else:
            self.task_status_text.insert("1.0", f"Task failed: {result['message']}\n")
        
        # Add to history
        self.task_history_text.insert("1.0", f"Task: {result['task_description']}\n")
        self.task_history_text.insert("end", f"Status: {result['status']}\n")
        if result["status"] == "success":
            self.task_history_text.insert("end", "Actions performed:\n")
            for action_result in result["results"]:
                self.task_history_text.insert("end", f"- {action_result}\n")
        self.task_history_text.insert("end", "\n")
        
    def _update_task_error(self, error_message):
        """Update the task status with an error message"""
        self.task_status_text.delete("1.0", "end")
        self.task_status_text.insert("1.0", f"Error executing task: {error_message}")
    
    def _create_sample_topics(self):
        """Create sample topics for testing"""
        try:
            # Sample insights with different topics
            sample_insights = [
                {
                    "content": "You're working on a Python project. Consider using type hints for better code quality.",
                    "source": "sample",
                    "context": "Python code with functions and classes",
                    "app_name": "VS Code",
                    "topics": ["Python", "Programming", "Code Quality"]
                },
                {
                    "content": "You have a meeting scheduled for tomorrow at 10 AM. Don't forget to prepare the presentation.",
                    "source": "sample",
                    "context": "Calendar showing tomorrow's schedule",
                    "app_name": "Calendar",
                    "topics": ["Meetings", "Schedule", "Presentations"]
                },
                {
                    "content": "Your email inbox has several unread messages. Consider setting up filters to organize them better.",
                    "source": "sample",
                    "context": "Email client with unread messages",
                    "app_name": "Mail",
                    "topics": ["Email", "Organization", "Productivity"]
                },
                {
                    "content": "You're researching machine learning algorithms. Consider exploring neural networks for your project.",
                    "source": "sample",
                    "context": "Web page about machine learning",
                    "app_name": "Browser",
                    "topics": ["Machine Learning", "Research", "Neural Networks"]
                },
                {
                    "content": "Your system has pending updates. Consider installing them to improve security.",
                    "source": "sample",
                    "context": "System preferences showing updates",
                    "app_name": "System Preferences",
                    "topics": ["System", "Security", "Updates"]
                }
            ]
            
            # Store each insight
            for insight in sample_insights:
                self.memory.store_insight(
                    content=insight["content"],
                    source=insight["source"],
                    context=insight["context"],
                    app_name=insight["app_name"],
                    topics=insight["topics"]
                )
            
            # Update topics list
            self._populate_topics_list()
            
            # Show success message
            messagebox_label = ctk.CTkLabel(
                self.tab_topics,
                text="Sample topics created successfully",
                text_color="green"
            )
            messagebox_label.pack(pady=10)
            
            # Remove message after 3 seconds
            self.app.after(3000, lambda: messagebox_label.destroy())
            
        except Exception as e:
            # Show error message
            messagebox_label = ctk.CTkLabel(
                self.tab_topics,
                text=f"Error creating sample topics: {str(e)}",
                text_color="red"
            )
            messagebox_label.pack(pady=10)
            
            # Remove message after 3 seconds
            self.app.after(3000, lambda: messagebox_label.destroy())
            
    def _on_topic_select(self, event):
        """Handle topic selection"""
        selection = self.topics_listbox.curselection()
        if selection:
            topic = self.topics_listbox.get(selection[0])
            self._show_topic_memories(topic)
    
    def run(self):
        """Run the application"""
        self.app.mainloop() 