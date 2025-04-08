import os
import time
import threading
import queue
import json
import sqlite3
from datetime import datetime, timedelta
import platform
import subprocess
import tempfile
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk
from PIL import Image, ImageTk
import io
import base64
import logging
from dotenv import load_dotenv
import pystray
from PIL import Image as PILImage, ImageDraw
from difflib import SequenceMatcher

# Import our modules
from screen_capture import ScreenCapture
from claude_integration import ClaudeIntegration
from input_monitor import InputMonitor
from memory_system import SmartMemorySystem
from task_executor import TaskExecutor

class ScreenMateApp(ctk.CTk):
    def __init__(self):
        """Initialize the Key Points Extractor MVP"""
        super().__init__()
        
        # Initialize core components
        self.memory_system = SmartMemorySystem()
        self.screen_capture = ScreenCapture()
        self.claude = ClaudeIntegration()
        
        # Message queue for thread communication
        self.message_queue = queue.Queue()
        
        # Analysis settings
        self.analysis_interval = 15  # seconds
        self.analyzing = False
        self.monitoring = False
        
        # Setup UI
        self.title("ScreenMate - Knowledge Library")
        self.geometry("800x600")
        
        # Create tab view
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Create tabs
        self.key_points_tab = self.tabview.add("Key Points")
        self.knowledge_tab = self.tabview.add("Knowledge Library")
        self.journal_tab = self.tabview.add("Journal")
        self.settings_tab = self.tabview.add("Settings")
        
        # Setup each tab
        self._setup_key_points_tab()
        self._setup_knowledge_tab()
        self._setup_journal_tab()
        self._setup_settings_tab()
        
        # Setup system tray
        self._setup_system_tray()
        
        # Start message processing
        self._process_messages()

    def _process_messages(self):
        """Process messages from the analysis thread"""
        try:
            while True:
                message = self.message_queue.get_nowait()
                if message["type"] == "status":
                    self.status_label.configure(text=message["text"])
                    if "color" in message:
                        self.status_indicator.configure(text_color=message["color"])
                elif message["type"] == "key_points":
                    self._update_key_points(message["text"])
                    # Save insights to memory system when received
                    self._save_insight_to_memory(message["text"], message.get("context", ""))
                elif message["type"] == "insight":
                    self._add_insight_to_list(message["insight"])
        except queue.Empty:
            pass
        finally:
            self.after(100, self._process_messages)

    def _setup_ui(self):
        """Set up the UI with tabs including Knowledge Library"""
        # Configure the theme
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")
        
        # Main frame
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Status frame - at the top
        status_frame = ctk.CTkFrame(main_frame, fg_color="transparent", height=30)
        status_frame.pack(fill="x", pady=(0, 5))
        
        # Title
        title_label = ctk.CTkLabel(
            status_frame,
            text="ScreenMate",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title_label.pack(side="left", padx=(10, 0))
        
        # Status indicator
        self.status_indicator = ctk.CTkLabel(
            status_frame,
            text="●",
            font=ctk.CTkFont(size=16),
            text_color="red"
        )
        self.status_indicator.pack(side="left", padx=(10, 5))
        
        self.status_label = ctk.CTkLabel(
            status_frame,
            text="Inactive",
            font=ctk.CTkFont(size=12)
        )
        self.status_label.pack(side="left")
        
        # Create tabview
        self.tabview = ctk.CTkTabview(main_frame)
        self.tabview.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Add tabs
        self.tab_key_points = self.tabview.add("Key Points")
        self.tab_knowledge = self.tabview.add("Knowledge Library")
        self.tab_settings = self.tabview.add("Settings")
        
        # Set up each tab
        self._setup_key_points_tab()
        self._setup_knowledge_library_tab()
        self._setup_settings_tab()

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
        self.deiconify()
        self.lift()
    
    def _quit_app(self):
        """Quit the application"""
        if self.tray_icon:
            self.tray_icon.stop()
        self.quit()
    
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
            # Update status
            self.message_queue.put({"type": "status", "text": "Analyzing..."})
            
            # Capture screen and extract text
            screen_data = self.screen_capture.analyze_screen()
            
            if not screen_data or not screen_data["text"] or len(screen_data["text"]) < 50:
                self.message_queue.put({
                    "type": "status",
                    "text": "Not enough text to analyze" if not self.analyzing else "Active"
                })
                return
            
            # Check if content has changed significantly
            if hasattr(self, 'last_screen_text'):
                similarity = SequenceMatcher(None, self.last_screen_text, screen_data["text"]).ratio()
                
                if similarity > 0.9:
                    self.message_queue.put({
                        "type": "status",
                        "text": "Content unchanged" if not self.analyzing else "Active"
                    })
                    return
            
            # Save current text for future comparison
            self.last_screen_text = screen_data["text"]
            
            # Get key points
            use_api = not self.economy_mode_var.get()
            key_points = self.claude.get_key_points(screen_data["text"], use_api=use_api)
            
            # Update UI with results
            self.message_queue.put({
                "type": "key_points",
                "text": key_points
            })
            
            self.message_queue.put({
                "type": "status",
                "text": "Active" if self.analyzing else "Analysis complete",
                "color": "green" if self.analyzing else "blue"
            })
            
        except Exception as e:
            logging.error(f"Analysis error: {str(e)}")
            self.message_queue.put({
                "type": "status",
                "text": f"Error: {str(e)}",
                "color": "red"
            })
    
    def _update_key_points(self, text):
        """Update the key points text box"""
        self.key_points_text.configure(state="normal")
        self.key_points_text.delete("1.0", "end")
        self.key_points_text.insert("1.0", text)
        self.key_points_text.configure(state="disabled")

    def _setup_key_points_tab(self):
        """Set up the Key Points tab"""
        # Key Points section
        key_points_label = ctk.CTkLabel(
            self.key_points_tab,
            text="Key Points:",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        key_points_label.pack(anchor="w", padx=10, pady=(10, 5))
        
        self.key_points_text = ctk.CTkTextbox(self.key_points_tab, height=250)
        self.key_points_text.pack(fill="x", padx=10, pady=(0, 10))
        self.key_points_text.insert("1.0", "Key points will appear here...")
        self.key_points_text.configure(state="disabled")
        
        # Control buttons
        control_frame = ctk.CTkFrame(self.key_points_tab)
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
        settings_frame = ctk.CTkFrame(self.key_points_tab)
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

    def _setup_knowledge_library_tab(self):
        """Set up the Knowledge Library tab"""
        # Search frame
        search_frame = ctk.CTkFrame(self.tab_knowledge)
        search_frame.pack(fill="x", padx=10, pady=5)
        
        self.search_entry = ctk.CTkEntry(
            search_frame,
            placeholder_text="Search insights...",
            width=300
        )
        self.search_entry.pack(side="left", padx=5)
        
        self.search_button = ctk.CTkButton(
            search_frame,
            text="Search",
            command=self._search_insights
        )
        self.search_button.pack(side="left", padx=5)
        
        # Filter frame
        filter_frame = ctk.CTkFrame(self.tab_knowledge)
        filter_frame.pack(fill="x", padx=10, pady=5)
        
        # Category filter
        self.category_var = ctk.StringVar(value="All")
        self.category_menu = ctk.CTkOptionMenu(
            filter_frame,
            values=["All"] + self.memory_system.get_all_categories(),
            variable=self.category_var,
            command=self._filter_insights
        )
        self.category_menu.pack(side="left", padx=5)
        
        # Date filter
        self.date_var = ctk.StringVar(value="All Time")
        self.date_menu = ctk.CTkOptionMenu(
            filter_frame,
            values=["All Time", "Today", "Last Week", "Last Month"],
            variable=self.date_var,
            command=self._filter_insights
        )
        self.date_menu.pack(side="left", padx=5)
        
        # Insights list
        self.insights_frame = ctk.CTkScrollableFrame(
            self.tab_knowledge,
            width=700,
            height=400
        )
        self.insights_frame.pack(pady=10, padx=10)
        
        # Load initial insights
        self._load_insights()

    def _setup_settings_tab(self):
        """Set up the Settings tab"""
        # Economy mode
        self.economy_var = ctk.BooleanVar(value=True)
        self.economy_check = ctk.CTkCheckBox(
            self.tab_settings,
            text="Economy Mode (Use local processing when possible)",
            variable=self.economy_var
        )
        self.economy_check.pack(pady=10)
        
        # Analysis interval
        interval_frame = ctk.CTkFrame(self.tab_settings)
        interval_frame.pack(pady=10)
        
        ctk.CTkLabel(
            interval_frame,
            text="Analysis Interval (seconds):"
        ).pack(side="left", padx=5)
        
        self.interval_entry = ctk.CTkEntry(
            interval_frame,
            width=50
        )
        self.interval_entry.insert(0, str(self.analysis_interval))
        self.interval_entry.pack(side="left", padx=5)
        
        # Save button
        self.save_button = ctk.CTkButton(
            self.tab_settings,
            text="Save Settings",
            command=self._save_settings
        )
        self.save_button.pack(pady=10)

    def _load_saved_insights(self):
        """Load saved insights from the memory system"""
        # Implementation of loading saved insights
        pass

    def _save_insight_to_memory(self, insight, context):
        """Save an insight to the memory system"""
        # Implementation of saving an insight to the memory system
        pass

    def _add_insight_to_list(self, insight):
        """Add an insight to the list"""
        # Create frame for insight
        insight_frame = ctk.CTkFrame(self.insights_frame)
        insight_frame.pack(fill="x", pady=5, padx=5)
        
        # Content
        content_label = ctk.CTkLabel(
            insight_frame,
            text=insight["content"][:100] + "...",
            wraplength=600
        )
        content_label.pack(pady=5)
        
        # Metadata frame
        meta_frame = ctk.CTkFrame(insight_frame)
        meta_frame.pack(fill="x", pady=5)
        
        # Date
        date = datetime.fromtimestamp(insight["timestamp"])
        date_label = ctk.CTkLabel(
            meta_frame,
            text=date.strftime("%Y-%m-%d %H:%M")
        )
        date_label.pack(side="left", padx=5)
        
        # Source
        source_label = ctk.CTkLabel(
            meta_frame,
            text=f"Source: {insight['source']}"
        )
        source_label.pack(side="left", padx=5)
        
        # Topics
        topics = insight.get("topics", [])
        if topics:
            topics_label = ctk.CTkLabel(
                meta_frame,
                text=f"Topics: {', '.join(topics)}"
            )
            topics_label.pack(side="left", padx=5)
        
        # Action buttons
        action_frame = ctk.CTkFrame(insight_frame)
        action_frame.pack(fill="x", pady=5)
        
        edit_button = ctk.CTkButton(
            action_frame,
            text="Edit",
            command=lambda i=insight: self._edit_insight(i)
        )
        edit_button.pack(side="left", padx=5)
        
        delete_button = ctk.CTkButton(
            action_frame,
            text="Delete",
            command=lambda i=insight: self._delete_insight(i)
        )
        delete_button.pack(side="left", padx=5)

    def _search_insights(self):
        """Search insights"""
        query = self.search_entry.get()
        if query:
            insights = self.memory_system.search_memories(query)
            
            # Clear current insights
            for widget in self.insights_frame.winfo_children():
                widget.destroy()
            
            # Add search results
            for insight in insights:
                self._add_insight_to_list(insight)

    def _filter_insights(self, _=None):
        """Filter insights based on current settings"""
        self._load_insights()

    def _edit_insight(self, insight):
        """Edit an insight"""
        # Create edit window
        edit_window = ctk.CTkToplevel(self)
        edit_window.title("Edit Insight")
        edit_window.geometry("600x400")
        
        # Content
        content_label = ctk.CTkLabel(edit_window, text="Content:")
        content_label.pack(pady=5)
        
        content_text = ctk.CTkTextbox(edit_window, width=500, height=200)
        content_text.insert("1.0", insight["content"])
        content_text.pack(pady=5)
        
        # Category
        category_label = ctk.CTkLabel(edit_window, text="Category:")
        category_label.pack(pady=5)
        
        category_menu = ctk.CTkOptionMenu(
            edit_window,
            values=self.memory_system.get_all_categories()
        )
        if insight.get("topics"):
            category_menu.set(insight["topics"][0])
        category_menu.pack(pady=5)
        
        # Save button
        def save_changes():
            # Update content
            self.memory_system.update_insight_content(
                insight["id"],
                content_text.get("1.0", "end").strip()
            )
            
            # Update category
            self.memory_system.update_insight_category(
                insight["id"],
                category_menu.get()
            )
            
            # Refresh insights
            self._load_insights()
            
            # Close window
            edit_window.destroy()
        
        save_button = ctk.CTkButton(
            edit_window,
            text="Save Changes",
            command=save_changes
        )
        save_button.pack(pady=10)

    def _delete_insight(self, insight):
        """Delete an insight"""
        if self.memory_system.delete_insight(insight["id"]):
            self._load_insights()

    def _save_settings(self):
        """Save application settings"""
        try:
            # Update analysis interval
            interval = int(self.interval_entry.get())
            if interval >= 5:  # Minimum 5 seconds
                self.analysis_interval = interval
                self.status_label.configure(text="Settings saved successfully")
            else:
                self.status_label.configure(text="Interval must be at least 5 seconds")
        except ValueError:
            self.status_label.configure(text="Invalid interval value")

    def _load_insights(self):
        """Load insights into the list"""
        # Clear current insights
        for widget in self.insights_frame.winfo_children():
            widget.destroy()
        
        # Get insights based on current filters
        insights = self._get_filtered_insights()
        
        # Add insights to list
        for insight in insights:
            self._add_insight_to_list(insight)

    def _get_filtered_insights(self):
        """Get insights based on current filters"""
        # Get date range
        date_range = None
        if self.date_var.get() == "Today":
            date_range = time.time() - 86400  # 24 hours
        elif self.date_var.get() == "Last Week":
            date_range = time.time() - 604800  # 7 days
        elif self.date_var.get() == "Last Month":
            date_range = time.time() - 2592000  # 30 days
        
        # Get category
        category = None
        if self.category_var.get() != "All":
            category = self.category_var.get()
        
        # Get filtered insights
        return self.memory_system.get_filtered_insights(
            date_range=date_range,
            category=category
        )

    def _setup_journal_tab(self):
        """Setup the Journal tab"""
        # New entry frame
        new_entry_frame = ctk.CTkFrame(self.journal_tab)
        new_entry_frame.pack(fill="x", padx=10, pady=5)
        
        # Title
        title_label = ctk.CTkLabel(new_entry_frame, text="Title:")
        title_label.pack(pady=5)
        
        self.journal_title = ctk.CTkEntry(new_entry_frame, width=300)
        self.journal_title.pack(pady=5)
        
        # Content
        content_label = ctk.CTkLabel(new_entry_frame, text="Content:")
        content_label.pack(pady=5)
        
        self.journal_content = ctk.CTkTextbox(new_entry_frame, width=700, height=200)
        self.journal_content.pack(pady=5)
        
        # Mood and tags frame
        meta_frame = ctk.CTkFrame(new_entry_frame)
        meta_frame.pack(fill="x", pady=5)
        
        # Mood
        mood_label = ctk.CTkLabel(meta_frame, text="Mood:")
        mood_label.pack(side="left", padx=5)
        
        self.mood_var = ctk.StringVar(value="Neutral")
        self.mood_menu = ctk.CTkOptionMenu(
            meta_frame,
            values=["Happy", "Neutral", "Sad", "Excited", "Anxious", "Calm"],
            variable=self.mood_var
        )
        self.mood_menu.pack(side="left", padx=5)
        
        # Tags
        tags_label = ctk.CTkLabel(meta_frame, text="Tags:")
        tags_label.pack(side="left", padx=5)
        
        self.journal_tags = ctk.CTkEntry(meta_frame, width=200)
        self.journal_tags.pack(side="left", padx=5)
        
        # Save button
        self.save_journal_button = ctk.CTkButton(
            new_entry_frame,
            text="Save Entry",
            command=self._save_journal_entry
        )
        self.save_journal_button.pack(pady=10)
        
        # Entries list
        entries_label = ctk.CTkLabel(self.journal_tab, text="Recent Entries")
        entries_label.pack(pady=5)
        
        # Filter frame
        filter_frame = ctk.CTkFrame(self.journal_tab)
        filter_frame.pack(fill="x", padx=10, pady=5)
        
        # Mood filter
        self.journal_mood_filter = ctk.CTkOptionMenu(
            filter_frame,
            values=["All Moods", "Happy", "Neutral", "Sad", "Excited", "Anxious", "Calm"],
            command=self._filter_journal_entries
        )
        self.journal_mood_filter.pack(side="left", padx=5)
        
        # Tag filter
        self.journal_tag_filter = ctk.CTkEntry(
            filter_frame,
            placeholder_text="Filter by tag...",
            width=200
        )
        self.journal_tag_filter.pack(side="left", padx=5)
        
        self.journal_tag_filter.bind("<Return>", self._filter_journal_entries)
        
        # Entries list
        self.journal_entries_frame = ctk.CTkScrollableFrame(
            self.journal_tab,
            width=700,
            height=200
        )
        self.journal_entries_frame.pack(pady=10, padx=10)
        
        # Load initial entries
        self._load_journal_entries()

    def _save_journal_entry(self):
        """Save a new journal entry"""
        title = self.journal_title.get()
        content = self.journal_content.get("1.0", "end").strip()
        mood = self.mood_var.get()
        tags = [tag.strip() for tag in self.journal_tags.get().split(",") if tag.strip()]
        
        if title and content:
            entry_id = self.memory_system.add_journal_entry(
                title=title,
                content=content,
                mood=mood,
                tags=tags
            )
            
            if entry_id:
                # Clear fields
                self.journal_title.delete(0, "end")
                self.journal_content.delete("1.0", "end")
                self.journal_tags.delete(0, "end")
                
                # Refresh entries
                self._load_journal_entries()
                
                # Show success message
                self.status_label.configure(text="Journal entry saved successfully")
            else:
                self.status_label.configure(text="Error saving journal entry")

    def _load_journal_entries(self):
        """Load journal entries into the list"""
        # Clear current entries
        for widget in self.journal_entries_frame.winfo_children():
            widget.destroy()
        
        # Get entries based on current filters
        entries = self._get_filtered_journal_entries()
        
        # Add entries to list
        for entry in entries:
            self._add_journal_entry_to_list(entry)

    def _get_filtered_journal_entries(self):
        """Get journal entries based on current filters"""
        mood = None
        if self.journal_mood_filter.get() != "All Moods":
            mood = self.journal_mood_filter.get()
        
        tag = None
        tag_filter = self.journal_tag_filter.get().strip()
        if tag_filter:
            tag = tag_filter
        
        return self.memory_system.get_journal_entries(
            mood=mood,
            tag=tag
        )

    def _add_journal_entry_to_list(self, entry):
        """Add a journal entry to the list"""
        # Create frame for entry
        entry_frame = ctk.CTkFrame(self.journal_entries_frame)
        entry_frame.pack(fill="x", pady=5, padx=5)
        
        # Title and date
        header_frame = ctk.CTkFrame(entry_frame)
        header_frame.pack(fill="x", pady=5)
        
        title_label = ctk.CTkLabel(
            header_frame,
            text=entry["title"],
            font=("Helvetica", 12, "bold")
        )
        title_label.pack(side="left", padx=5)
        
        date = datetime.fromtimestamp(entry["timestamp"])
        date_label = ctk.CTkLabel(
            header_frame,
            text=date.strftime("%Y-%m-%d %H:%M")
        )
        date_label.pack(side="right", padx=5)
        
        # Preview
        preview_label = ctk.CTkLabel(
            entry_frame,
            text=entry["content"][:100] + "...",
            wraplength=600
        )
        preview_label.pack(pady=5)
        
        # Metadata frame
        meta_frame = ctk.CTkFrame(entry_frame)
        meta_frame.pack(fill="x", pady=5)
        
        # Mood
        if entry.get("mood"):
            mood_label = ctk.CTkLabel(
                meta_frame,
                text=f"Mood: {entry['mood']}"
            )
            mood_label.pack(side="left", padx=5)
        
        # Tags
        if entry.get("tags"):
            tags_label = ctk.CTkLabel(
                meta_frame,
                text=f"Tags: {', '.join(entry['tags'])}"
            )
            tags_label.pack(side="left", padx=5)
        
        # Action buttons
        action_frame = ctk.CTkFrame(entry_frame)
        action_frame.pack(fill="x", pady=5)
        
        edit_button = ctk.CTkButton(
            action_frame,
            text="Edit",
            command=lambda e=entry: self._edit_journal_entry(e)
        )
        edit_button.pack(side="left", padx=5)
        
        delete_button = ctk.CTkButton(
            action_frame,
            text="Delete",
            command=lambda e=entry: self._delete_journal_entry(e)
        )
        delete_button.pack(side="left", padx=5)

    def _edit_journal_entry(self, entry):
        """Edit a journal entry"""
        # Create edit window
        edit_window = ctk.CTkToplevel(self)
        edit_window.title("Edit Journal Entry")
        edit_window.geometry("600x400")
        
        # Title
        title_label = ctk.CTkLabel(edit_window, text="Title:")
        title_label.pack(pady=5)
        
        title_entry = ctk.CTkEntry(edit_window, width=300)
        title_entry.insert(0, entry["title"])
        title_entry.pack(pady=5)
        
        # Content
        content_label = ctk.CTkLabel(edit_window, text="Content:")
        content_label.pack(pady=5)
        
        content_text = ctk.CTkTextbox(edit_window, width=500, height=200)
        content_text.insert("1.0", entry["content"])
        content_text.pack(pady=5)
        
        # Mood
        mood_label = ctk.CTkLabel(edit_window, text="Mood:")
        mood_label.pack(pady=5)
        
        mood_menu = ctk.CTkOptionMenu(
            edit_window,
            values=["Happy", "Neutral", "Sad", "Excited", "Anxious", "Calm"]
        )
        if entry.get("mood"):
            mood_menu.set(entry["mood"])
        mood_menu.pack(pady=5)
        
        # Tags
        tags_label = ctk.CTkLabel(edit_window, text="Tags:")
        tags_label.pack(pady=5)
        
        tags_entry = ctk.CTkEntry(edit_window, width=300)
        if entry.get("tags"):
            tags_entry.insert(0, ", ".join(entry["tags"]))
        tags_entry.pack(pady=5)
        
        # Save button
        def save_changes():
            # Update entry
            self.memory_system.update_journal_entry(
                entry_id=entry["id"],
                title=title_entry.get(),
                content=content_text.get("1.0", "end").strip(),
                mood=mood_menu.get(),
                tags=[tag.strip() for tag in tags_entry.get().split(",") if tag.strip()]
            )
            
            # Refresh entries
            self._load_journal_entries()
            
            # Close window
            edit_window.destroy()
        
        save_button = ctk.CTkButton(
            edit_window,
            text="Save Changes",
            command=save_changes
        )
        save_button.pack(pady=10)

    def _delete_journal_entry(self, entry):
        """Delete a journal entry"""
        if self.memory_system.delete_journal_entry(entry["id"]):
            self._load_journal_entries()

    def _filter_journal_entries(self, _=None):
        """Filter journal entries based on current settings"""
        self._load_journal_entries()

    def run(self):
        """Start the application"""
        self.mainloop()

if __name__ == "__main__":
    app = ScreenMateApp()
    app.run() 