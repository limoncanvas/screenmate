import os
import json
import time
import sqlite3
import datetime
from pathlib import Path
import re
from anthropic import Anthropic
from dotenv import load_dotenv
import threading
import queue
from collections import Counter
import logging
from typing import List, Dict, Any, Optional

load_dotenv()

class SmartMemorySystem:
    def __init__(self, db_path="./memory.db", relevance_threshold=0.6):
        """Initialize the memory system
        
        Args:
            db_path: Path to SQLite database file
            relevance_threshold: Threshold for relevance (0.0-1.0)
        """
        self.db_path = db_path
        self.relevance_threshold = relevance_threshold
        self.claude_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        
        # Initialize threading lock
        self.lock = threading.Lock()
        
        # Processing queue for async operations
        self.processing_queue = queue.Queue()
        
        # Initialize database
        self._init_db()
        
        # Start processing thread
        self.processing_thread = threading.Thread(target=self._process_queue)
        self.processing_thread.daemon = True
        self.processing_thread.start()
        
        # Track recent content to avoid duplicates
        self.recent_content_hashes = set()
        
        # Load user interests and common tasks (will be updated over time)
        self.user_interests = []
        self.common_tasks = []
        self._load_user_profile()
        
        self.stopwords = set([
            'the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have', 'i',
            'it', 'for', 'not', 'on', 'with', 'he', 'as', 'you', 'do', 'at',
            'this', 'but', 'his', 'by', 'from', 'they', 'we', 'say', 'her', 'she',
            'or', 'an', 'will', 'my', 'one', 'all', 'would', 'there', 'their', 'what'
        ])

    def _init_db(self):
        """Initialize the SQLite database"""
        with self.lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create tables if they don't exist
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                source TEXT,
                timestamp REAL,
                relevance_score REAL,
                context TEXT,
                app_name TEXT,
                topics TEXT,
                is_consolidated BOOLEAN DEFAULT 0,
                access_count INTEGER DEFAULT 0,
                last_accessed REAL
            )
            ''')
            
            # Table for consolidated memories (summaries of related memories)
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS consolidated_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                source_ids TEXT,
                timestamp REAL,
                topics TEXT,
                access_count INTEGER DEFAULT 0,
                last_accessed REAL
            )
            ''')
            
            # Table for user profile to track interests and preferences
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_profile (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                interests TEXT,
                common_tasks TEXT,
                frequent_apps TEXT,
                last_updated REAL
            )
            ''')
            
            # Table for journal entries
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS journal_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                mood TEXT,
                tags TEXT,
                timestamp REAL,
                last_modified REAL
            )
            ''')
            
            # Index for faster topic search
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_memories_topics ON memories (topics)')
            
            conn.commit()
            conn.close()
    
    def store_insight(self, content, source=None, context=None, app_name=None, analyze_now=False, topics=None):
        """Store an insight or notification with optional immediate analysis
        
        Args:
            content: The text content of the insight
            source: Source of the insight (e.g., "screen_analysis", "proactive_suggestion")
            context: Additional context (e.g., screen text that triggered this)
            app_name: The application the user was using
            analyze_now: If True, analyze synchronously; otherwise queue for async
            topics: Optional predefined topics to use instead of extracting them
        
        Returns:
            memory_id if stored, None if rejected as irrelevant or duplicate
        """
        # Generate a simple hash of the content to check for near-duplicates
        content_hash = hash(content[:100])  # First 100 chars for approximate matching
        
        # Skip if we've seen very similar content recently
        if content_hash in self.recent_content_hashes:
            return None
            
        # Add to recent hashes
        self.recent_content_hashes.add(content_hash)
        if len(self.recent_content_hashes) > 100:  # Limit set size
            self.recent_content_hashes.pop()
        
        # Apply immediate quick relevance checks
        if not self._quick_relevance_check(content, app_name):
            return None
        
        # Package the memory data
        memory_data = {
            "content": content,
            "source": source,
            "timestamp": time.time(),
            "context": context,
            "app_name": app_name
        }
        
        # If topics are provided, use them directly
        if topics:
            # Store in database with provided topics
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Calculate a default relevance score
            relevance_score = 0.8  # High relevance for manually tagged content
            
            cursor.execute('''
            INSERT INTO memories 
            (content, source, timestamp, relevance_score, context, app_name, topics) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                content, 
                source, 
                memory_data.get("timestamp"), 
                relevance_score,
                context,
                app_name,
                json.dumps(topics)
            ))
            
            memory_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return memory_id
        
        if analyze_now:
            # Analyze synchronously
            return self._analyze_and_store(memory_data)
        else:
            # Queue for async processing
            self.processing_queue.put(("store", memory_data))
            return "queued"
    
    def _quick_relevance_check(self, content, app_name=None):
        """Perform rapid client-side relevance checks before deeper analysis
        
        This runs locally without API calls to quickly filter obvious irrelevant content
        """
        # 1. Length check - very short insights often lack value
        if len(content) < 15:
            return False
            
        # 2. Common filler phrase check
        filler_phrases = [
            "i don't have enough information",
            "i don't know enough",
            "i cannot determine",
            "it's unclear from the information",
            "based on the image provided",
            "without more context"
        ]
        
        for phrase in filler_phrases:
            if phrase in content.lower():
                return False
        
        # 3. Check for known low-value app contexts
        low_value_apps = ["system preferences", "settings", "file explorer", "finder"]
        if app_name and app_name.lower() in low_value_apps:
            # More strict for these apps
            return len(content) > 50  # Higher bar for these contexts
            
        # 4. Check if it contains actionable language or insights
        actionable_indicators = ["should", "could", "might want to", "try", "consider", "important", "deadline", "remember", "key", "critical"]
        has_actionable = any(indicator in content.lower() for indicator in actionable_indicators)
        
        # If the content passes basic checks or has actionable language, proceed with deeper analysis
        return has_actionable or len(content) > 30
    
    def _analyze_and_store(self, memory_data):
        """Analyze content relevance and store if sufficiently relevant"""
        content = memory_data["content"]
        context = memory_data.get("context", "")
        app_name = memory_data.get("app_name", "")
        
        # Calculate relevance score through multiple methods
        relevance_score = self._calculate_relevance(content, context, app_name)
        
        # Only store if relevance meets threshold
        if relevance_score >= self.relevance_threshold:
            # Extract topics
            topics = self._extract_topics(content, context)
            
            # Store in database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
            INSERT INTO memories 
            (content, source, timestamp, relevance_score, context, app_name, topics) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                content, 
                memory_data.get("source"), 
                memory_data.get("timestamp"), 
                relevance_score,
                context,
                app_name,
                json.dumps(topics)
            ))
            
            memory_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            # If we have enough memories, trigger consolidation (but not too often)
            self._maybe_trigger_consolidation()
            
            return memory_id
        else:
            # Content not relevant enough to store
            return None
    
    def _calculate_relevance(self, content, context=None, app_name=None):
        """Calculate a relevance score using multiple strategies
        
        Returns: Float between 0.0 and 1.0
        """
        score = 0.0
        
        # 1. Rule-based scoring (fast, no API calls)
        rule_score = 0.0
        
        # Check for task-related keywords
        task_keywords = ["task", "todo", "deadline", "project", "remember", "important", "meeting", "call", "email"]
        if any(keyword in content.lower() for keyword in task_keywords):
            rule_score += 0.2
        
        # Check for specificity (specific details tend to be more useful)
        specificity_indicators = [
            r'\b\d+[\/\-\.]\d+[\/\-\.]\d+\b',  # dates
            r'\b\d{1,2}:\d{2}\b',               # times
            r'\$\d+',                           # dollar amounts
            r'\b[A-Z][a-z]+ [A-Z][a-z]+\b'      # proper names
        ]
        
        for pattern in specificity_indicators:
            if re.search(pattern, content):
                rule_score += 0.15
                break
        
        # Check for personal references
        if "you" in content.lower() or "your" in content.lower():
            rule_score += 0.1
        
        # 2. Interest matching (medium complexity)
        interest_score = 0.0
        
        # Check if content matches user interests
        for interest in self.user_interests:
            if interest.lower() in content.lower():
                interest_score += 0.3
                break
        
        # 3. Historical engagement (weighted by how much the user has engaged with similar content)
        historical_score = 0.0
        
        # Extract potential topics
        potential_topics = self._simple_topic_extraction(content)
        
        # Check if these topics have high engagement
        if potential_topics:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            topic_placeholders = ', '.join(['?'] * len(potential_topics))
            query = f'''
            SELECT AVG(access_count) FROM memories 
            WHERE topics LIKE '%' || ? || '%'
            '''
            
            total_engagement = 0
            for topic in potential_topics:
                cursor.execute(query, (topic,))
                result = cursor.fetchone()
                if result[0]:
                    total_engagement += result[0]
            
            conn.close()
            
            # Normalize historical score
            if potential_topics:
                avg_engagement = total_engagement / len(potential_topics)
                historical_score = min(0.3, avg_engagement * 0.1)  # Cap at 0.3
        
        # 4. Application context relevance
        app_score = 0.0
        if app_name:
            # Check if this is a frequently used or important app
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT COUNT(*) FROM memories WHERE app_name = ?
            ''', (app_name,))
            
            app_memory_count = cursor.fetchone()[0]
            conn.close()
            
            # More memories from this app suggests it's important
            app_score = min(0.2, app_memory_count * 0.02)
        
        # Calculate final score with weighted components
        final_score = (rule_score * 0.4) + (interest_score * 0.3) + (historical_score * 0.2) + (app_score * 0.1)
        
        # Ensure score is between 0 and 1
        return min(1.0, max(0.0, final_score))
    
    def _simple_topic_extraction(self, text):
        """Extract potential topics without API calls"""
        # Simple method to extract nouns and noun phrases
        # This is a simplified version - in a full implementation you might use NLP
        words = text.lower().split()
        stopwords = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "with", "by"}
        
        # Filter out stopwords and short words
        filtered_words = [word for word in words if word not in stopwords and len(word) > 3]
        
        # Take most frequent words as topics
        topics = list(set(filtered_words))[:5]  # Limit to 5 topics
        return topics
    
    def _extract_topics(self, content, context=None):
        """Extract topics from the content using Claude
        
        This is more expensive but gives better topics for retrieval
        """
        # Use local topic extraction by default
        return self.extract_topics_local(content)
        
        # The following code is commented out to avoid API calls
        # try:
        #     prompt = f"""
        #     Please analyze this text and extract 3-5 key topics or themes:
        #     
        #     {content}
        #     
        #     Return ONLY a comma-separated list of topics, with no additional text or explanation.
        #     For example: "project management, deadline, client meeting"
        #     """
        #     
        #     response = self.claude_client.messages.create(
        #         model="claude-3-sonnet-20240229",
        #         max_tokens=100,
        #         system="You extract key topics from text. Return only a comma-separated list of topics, no other text.",
        #         messages=[
        #             {"role": "user", "content": prompt}
        #         ]
        #     )
        #     
        #     topics_text = response.content[0].text.strip()
        #     topics = [topic.strip() for topic in topics_text.split(',')]
        #     return topics
        #     
        # except Exception as e:
        #     print(f"Error extracting topics: {e}")
        #     # Fall back to simple extraction
        #     return self._simple_topic_extraction(content)
    
    def _process_queue(self):
        """Process the queue of memory operations"""
        while True:
            try:
                operation, data = self.processing_queue.get(timeout=1.0)
                
                if operation == "store":
                    self._analyze_and_store(data)
                elif operation == "consolidate":
                    self._consolidate_memories(data)
                elif operation == "update_profile":
                    self._update_user_profile()
                
                # Mark task as done
                self.processing_queue.task_done()
                
            except queue.Empty:
                # Queue is empty, sleep briefly
                time.sleep(0.1)
            except Exception as e:
                print(f"Error processing memory operation: {e}")
    
    def _maybe_trigger_consolidation(self):
        """Check if consolidation should be triggered"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Count unconsolidated memories
        cursor.execute('SELECT COUNT(*) FROM memories WHERE is_consolidated = 0')
        unconsolidated_count = cursor.fetchone()[0]
        
        conn.close()
        
        # Trigger consolidation if we have enough unconsolidated memories
        if unconsolidated_count >= 10:  # Adjust threshold as needed
            self.processing_queue.put(("consolidate", None))
    
    def _consolidate_memories(self, _=None):
        """Consolidate related memories into summaries"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get unconsolidated memories
        cursor.execute('''
        SELECT id, content, topics FROM memories 
        WHERE is_consolidated = 0
        ORDER BY timestamp DESC
        ''')
        
        memories = cursor.fetchall()
        
        # Group by topic similarity
        topic_groups = {}
        
        for memory_id, content, topics_json in memories:
            try:
                topics = json.loads(topics_json)
                
                # Find a matching group or create new
                assigned = False
                for group_key, group in topic_groups.items():
                    group_topics = group["topics"]
                    # Check for topic overlap
                    if any(topic in group_topics for topic in topics):
                        group["memories"].append((memory_id, content))
                        # Update group topics with any new ones
                        group["topics"] = list(set(group["topics"] + topics))
                        assigned = True
                        break
                
                if not assigned:
                    # Create new group
                    topic_groups[f"group_{len(topic_groups)}"] = {
                        "topics": topics,
                        "memories": [(memory_id, content)]
                    }
            except json.JSONDecodeError:
                # Skip memories with invalid topic data
                continue
        
        # For each group with multiple memories, create a consolidated summary
        for group_key, group in topic_groups.items():
            if len(group["memories"]) >= 3:  # Only consolidate groups with multiple memories
                memory_ids = [m[0] for m in group["memories"]]
                memory_contents = [m[1] for m in group["memories"]]
                
                # Generate summary using Claude
                summary = self._generate_summary(memory_contents, group["topics"])
                
                if summary:
                    # Store consolidated memory
                    cursor.execute('''
                    INSERT INTO consolidated_memories
                    (content, source_ids, timestamp, topics)
                    VALUES (?, ?, ?, ?)
                    ''', (
                        summary,
                        json.dumps(memory_ids),
                        time.time(),
                        json.dumps(group["topics"])
                    ))
                    
                    # Mark source memories as consolidated
                    id_placeholders = ', '.join(['?'] * len(memory_ids))
                    cursor.execute(f'''
                    UPDATE memories 
                    SET is_consolidated = 1
                    WHERE id IN ({id_placeholders})
                    ''', memory_ids)
        
        conn.commit()
        conn.close()
        
        # After consolidation, update user profile
        self.processing_queue.put(("update_profile", None))
    
    def _generate_summary(self, memory_contents, topics):
        """Generate a summary of related memories using Claude"""
        try:
            all_content = "\n\n---\n\n".join(memory_contents)
            
            prompt = f"""
            Please summarize these related notes into a concise, useful summary:
            
            {all_content}
            
            These notes relate to the following topics: {', '.join(topics)}
            
            Create a summary that preserves the most important information, action items, 
            and insights while eliminating redundancy and low-value content.
            """
            
            response = self.claude_client.messages.create(
                model="claude-3-sonnet-20240229",
                max_tokens=300,
                system="You create concise, useful summaries that preserve key information and eliminate redundancy.",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            return response.content[0].text.strip()
            
        except Exception as e:
            print(f"Error generating summary: {e}")
            return None
    
    def _update_user_profile(self):
        """Update the user's profile based on memory patterns"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Extract frequent topics (interests)
        cursor.execute('''
        SELECT topics FROM memories
        ORDER BY timestamp DESC LIMIT 100
        ''')
        
        all_topics = []
        for topics_json, in cursor.fetchall():
            try:
                topics = json.loads(topics_json)
                all_topics.extend(topics)
            except json.JSONDecodeError:
                continue
        
        # Count occurrences of each topic
        topic_counts = {}
        for topic in all_topics:
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
        
        # Get most frequent topics
        self.user_interests = [topic for topic, count in sorted(
            topic_counts.items(), key=lambda x: x[1], reverse=True
        )[:10]]  # Top 10 interests
        
        # Get frequently used apps
        cursor.execute('''
        SELECT app_name, COUNT(*) as count
        FROM memories
        WHERE app_name IS NOT NULL
        GROUP BY app_name
        ORDER BY count DESC
        LIMIT 5
        ''')
        
        frequent_apps = [app for app, _ in cursor.fetchall()]
        
        # Store updated profile
        cursor.execute('''
        INSERT OR REPLACE INTO user_profile
        (id, interests, common_tasks, frequent_apps, last_updated)
        VALUES (1, ?, ?, ?, ?)
        ''', (
            json.dumps(self.user_interests),
            json.dumps(self.common_tasks),
            json.dumps(frequent_apps),
            time.time()
        ))
        
        conn.commit()
        conn.close()
    
    def _load_user_profile(self):
        """Load the user's profile from the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT interests, common_tasks FROM user_profile WHERE id = 1')
        result = cursor.fetchone()
        
        if result:
            interests_json, tasks_json = result
            try:
                self.user_interests = json.loads(interests_json)
                self.common_tasks = json.loads(tasks_json)
            except json.JSONDecodeError:
                # Initialize with empty lists if JSON is invalid
                self.user_interests = []
                self.common_tasks = []
        else:
            # No profile exists yet
            self.user_interests = []
            self.common_tasks = []
        
        conn.close()
    
    def retrieve_relevant_memories(self, query=None, context=None, app_name=None, limit=5):
        """Retrieve memories relevant to the current context
        
        Args:
            query: Optional search query
            context: Current context (e.g., screen text)
            app_name: Current application name
            limit: Maximum number of memories to return
            
        Returns:
            List of relevant memories
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Return rows as dictionaries
        cursor = conn.cursor()
        
        # Build query based on available information
        if query:
            # Direct search query (highest priority)
            sql = '''
            SELECT * FROM memories
            WHERE content LIKE ?
            ORDER BY relevance_score DESC
            LIMIT ?
            '''
            cursor.execute(sql, (f"%{query}%", limit))
        elif context:
            # Extract potential topics from context
            topics = self._simple_topic_extraction(context)
            
            if topics and len(topics) > 0:
                # Search by extracted topics
                topic_conditions = ' OR '.join(['topics LIKE ?' for _ in topics])
                params = [f"%{topic}%" for topic in topics]
                params.append(limit)
                
                sql = f'''
                SELECT * FROM memories
                WHERE {topic_conditions}
                ORDER BY relevance_score DESC
                LIMIT ?
                '''
                cursor.execute(sql, params)
            else:
                # Fallback to app context
                sql = '''
                SELECT * FROM memories
                WHERE app_name = ?
                ORDER BY timestamp DESC
                LIMIT ?
                '''
                cursor.execute(sql, (app_name, limit))
        else:
            # Just return recent high-relevance memories
            sql = '''
            SELECT * FROM memories
            ORDER BY relevance_score DESC, timestamp DESC
            LIMIT ?
            '''
            cursor.execute(sql, (limit,))
        
        memories = [dict(row) for row in cursor.fetchall()]
        
        # If we have few memory results, also check consolidated memories
        if len(memories) < limit:
            remaining = limit - len(memories)
            
            if query:
                sql = '''
                SELECT * FROM consolidated_memories
                WHERE content LIKE ?
                ORDER BY last_accessed DESC
                LIMIT ?
                '''
                cursor.execute(sql, (f"%{query}%", remaining))
            else:
                sql = '''
                SELECT * FROM consolidated_memories
                ORDER BY last_accessed DESC
                LIMIT ?
                '''
                cursor.execute(sql, (remaining,))
            
            consolidated = [dict(row) for row in cursor.fetchall()]
            memories.extend(consolidated)
        
        # Update access counts for retrieved memories
        for memory in memories:
            if 'id' in memory:
                if 'source_ids' in memory:  # This is a consolidated memory
                    cursor.execute('''
                    UPDATE consolidated_memories
                    SET access_count = access_count + 1, last_accessed = ?
                    WHERE id = ?
                    ''', (time.time(), memory['id']))
                else:
                    cursor.execute('''
                    UPDATE memories
                    SET access_count = access_count + 1, last_accessed = ?
                    WHERE id = ?
                    ''', (time.time(), memory['id']))
        
        conn.commit()
        conn.close()
        
        return memories
    
    def clear_old_memories(self, days_threshold=30):
        """Clear memories older than the threshold
        
        Args:
            days_threshold: Remove memories older than this many days
        """
        threshold_time = time.time() - (days_threshold * 86400)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get count before deletion
        cursor.execute('SELECT COUNT(*) FROM memories WHERE timestamp < ?', (threshold_time,))
        count_to_delete = cursor.fetchone()[0]
        
        # Delete old memories that have low relevance and few accesses
        cursor.execute('''
        DELETE FROM memories 
        WHERE timestamp < ? AND relevance_score < 0.7 AND access_count < 3
        ''', (threshold_time,))
        
        # Delete old consolidated memories
        cursor.execute('''
        DELETE FROM consolidated_memories 
        WHERE timestamp < ? AND access_count < 2
        ''', (threshold_time,))
        
        conn.commit()
        conn.close()
        
        return count_to_delete
    
    def get_memory_stats(self):
        """Get statistics about the memory system"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        stats = {}
        
        # Total memories
        cursor.execute('SELECT COUNT(*) FROM memories')
        stats['total_memories'] = cursor.fetchone()[0]
        
        # Consolidated memories
        cursor.execute('SELECT COUNT(*) FROM consolidated_memories')
        stats['consolidated_memories'] = cursor.fetchone()[0]
        
        # Average relevance score
        cursor.execute('SELECT AVG(relevance_score) FROM memories')
        stats['avg_relevance'] = cursor.fetchone()[0]
        
        # Most common topics
        cursor.execute('SELECT topics FROM memories')
        all_topics = []
        for topics_json, in cursor.fetchall():
            try:
                topics = json.loads(topics_json)
                all_topics.extend(topics)
            except:
                continue
        
        topic_counts = {}
        for topic in all_topics:
            topic_counts[topic] = topic_counts.get(topic, 0) + 1
        
        stats['top_topics'] = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        conn.close()
        return stats
    
    def get_all_topics(self):
        """Get all topics and their memory counts"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get all topics from memories
            cursor.execute('''
            SELECT topics, COUNT(*) as count 
            FROM memories 
            WHERE topics IS NOT NULL 
            GROUP BY topics
            ''')
            
            results = cursor.fetchall()
            conn.close()
            
            # Process the JSON-encoded topics
            topic_counts = {}
            for topics_json, count in results:
                try:
                    topics = json.loads(topics_json)
                    for topic in topics:
                        topic_counts[topic] = topic_counts.get(topic, 0) + count
                except json.JSONDecodeError:
                    continue
            
            return topic_counts
            
        except Exception as e:
            print(f"Error getting topics: {e}")
            return {}

    def extract_topics_local(self, text: str, max_topics: int = 3) -> List[str]:
        """Extract topics using only local processing (no API calls)"""
        if not text or len(text) < 20:
            return []
            
        # Remove punctuation and convert to lowercase
        text = re.sub(r'[^\w\s]', '', text.lower())
        
        # Remove stopwords
        words = [word for word in text.split() if word not in self.stopwords and len(word) > 2]
        
        # Count word frequencies
        word_counts = Counter(words)
        
        # Extract multi-word phrases (potential names, projects)
        original_text = text
        phrases = []
        phrase_pattern = re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b')
        for match in phrase_pattern.finditer(original_text):
            phrases.append(match.group(1).lower())
        
        # Add phrases to counts with higher weight
        for phrase in phrases:
            word_counts[phrase] = word_counts.get(phrase, 0) + 5
        
        # Get most common words/phrases
        return [topic for topic, _ in word_counts.most_common(max_topics)] 

    def retrieve_recent_insights(self, limit=50):
        """Retrieve recent insights from the memory system
        
        Args:
            limit: Maximum number of insights to return
            
        Returns:
            List of recent insights
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Return rows as dictionaries
        cursor = conn.cursor()
        
        # Get recent insights ordered by timestamp
        cursor.execute('''
        SELECT * FROM memories
        ORDER BY timestamp DESC
        LIMIT ?
        ''', (limit,))
        
        insights = [dict(row) for row in cursor.fetchall()]
        
        # Process each insight
        for insight in insights:
            # Parse topics from JSON
            if 'topics' in insight and insight['topics']:
                try:
                    insight['topics'] = json.loads(insight['topics'])
                except json.JSONDecodeError:
                    insight['topics'] = []
        
        conn.close()
        return insights
    
    def get_insight_by_id(self, insight_id):
        """Get a specific insight by ID
        
        Args:
            insight_id: The ID of the insight to retrieve
            
        Returns:
            Insight dictionary or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Return rows as dictionaries
        cursor = conn.cursor()
        
        # Get the insight by ID
        cursor.execute('''
        SELECT * FROM memories
        WHERE id = ?
        ''', (insight_id,))
        
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            return None
        
        insight = dict(row)
        
        # Parse topics from JSON
        if 'topics' in insight and insight['topics']:
            try:
                insight['topics'] = json.loads(insight['topics'])
            except json.JSONDecodeError:
                insight['topics'] = []
        
        conn.close()
        return insight
    
    def get_all_categories(self):
        """Get all unique categories from insights
        
        Returns:
            List of unique categories
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get all topics from memories
        cursor.execute('SELECT topics FROM memories')
        results = cursor.fetchall()
        
        conn.close()
        
        # Extract categories from topics
        categories = set()
        for topics_json, in results:
            if topics_json:
                try:
                    topics = json.loads(topics_json)
                    for topic in topics:
                        # Add categories (we could filter to only include user-added categories)
                        categories.add(topic)
                except json.JSONDecodeError:
                    continue
        
        # Always include a "General" category
        categories.add("General")
        
        return sorted(list(categories))
    
    def update_insight_category(self, insight_id, new_category):
        """Update the category of an insight
        
        Args:
            insight_id: The ID of the insight to update
            new_category: The new category to assign
            
        Returns:
            Boolean indicating success
        """
        try:
            # First get the current insight
            insight = self.get_insight_by_id(insight_id)
            if not insight:
                return False
            
            # Get current topics
            topics = insight.get('topics', [])
            if isinstance(topics, str):
                try:
                    topics = json.loads(topics)
                except json.JSONDecodeError:
                    topics = []
            
            # Remove any existing categories (simplistic approach)
            # In a more robust implementation, you might maintain a separate categories field
            
            # Add the new category
            if new_category not in topics:
                topics.append(new_category)
            
            # Update in database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
            UPDATE memories
            SET topics = ?
            WHERE id = ?
            ''', (json.dumps(topics), insight_id))
            
            conn.commit()
            conn.close()
            
            return True
        except Exception as e:
            logging.error(f"Error updating insight category: {e}")
            return False
    
    def update_insight_content(self, insight_id, new_content):
        """Update the content of an insight
        
        Args:
            insight_id: The ID of the insight to update
            new_content: The new content for the insight
            
        Returns:
            Boolean indicating success
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
            UPDATE memories
            SET content = ?
            WHERE id = ?
            ''', (new_content, insight_id))
            
            conn.commit()
            conn.close()
            
            return True
        except Exception as e:
            logging.error(f"Error updating insight content: {e}")
            return False
    
    def delete_insight(self, insight_id):
        """Delete an insight from the memory system
        
        Args:
            insight_id: The ID of the insight to delete
            
        Returns:
            Boolean indicating success
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
            DELETE FROM memories
            WHERE id = ?
            ''', (insight_id,))
            
            conn.commit()
            conn.close()
            
            return True
        except Exception as e:
            logging.error(f"Error deleting insight: {e}")
            return False
    
    def get_filtered_insights(self, date_range=None, category=None, limit=50):
        """Get insights filtered by date and/or category
        
        Args:
            date_range: Unix timestamp for the start date (None for all time)
            category: Category to filter by (None for all categories)
            limit: Maximum number of insights to return
            
        Returns:
            List of insights matching the filters
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM memories"
        params = []
        
        where_clauses = []
        
        # Add date filter
        if date_range:
            where_clauses.append("timestamp >= ?")
            params.append(date_range)
        
        # Add category filter
        if category:
            where_clauses.append("topics LIKE ?")
            params.append(f"%{category}%")
        
        # Add WHERE clause if we have any filters
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        
        # Add ordering and limit
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        # Execute query
        cursor.execute(query, params)
        
        insights = [dict(row) for row in cursor.fetchall()]
        
        # Process each insight
        for insight in insights:
            # Parse topics from JSON
            if 'topics' in insight and insight['topics']:
                try:
                    insight['topics'] = json.loads(insight['topics'])
                except json.JSONDecodeError:
                    insight['topics'] = []
        
        conn.close()
        return insights
    
    def search_memories(self, query, limit=20):
        """Search insights by content
        
        Args:
            query: Search query
            limit: Maximum number of results
            
        Returns:
            List of matching insights
        """
        if not query or len(query) < 3:
            return []
            
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Search in content and context
        cursor.execute('''
        SELECT * FROM memories 
        WHERE content LIKE ? OR context LIKE ?
        ORDER BY timestamp DESC 
        LIMIT ?
        ''', (f'%{query}%', f'%{query}%', limit))
        
        insights = [dict(row) for row in cursor.fetchall()]
        
        # Process each insight
        for insight in insights:
            # Parse topics from JSON
            if 'topics' in insight and insight['topics']:
                try:
                    insight['topics'] = json.loads(insight['topics'])
                except json.JSONDecodeError:
                    insight['topics'] = []
        
        conn.close()
        return insights
    
    def _calculate_similarity(self, text1, text2):
        """Calculate similarity between two texts
        
        Args:
            text1: First text
            text2: Second text
            
        Returns:
            Similarity score between 0 and 1
        """
        # Simple word overlap similarity
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) 

    def add_journal_entry(self, title, content, mood=None, tags=None):
        """Add a new journal entry
        
        Args:
            title: Title of the journal entry
            content: Content of the journal entry
            mood: Optional mood associated with the entry
            tags: Optional list of tags
            
        Returns:
            ID of the created entry or None if failed
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            current_time = time.time()
            
            cursor.execute('''
            INSERT INTO journal_entries (title, content, mood, tags, timestamp, last_modified)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                title,
                content,
                mood,
                json.dumps(tags) if tags else None,
                current_time,
                current_time
            ))
            
            entry_id = cursor.lastrowid
            
            # Extract topics from content for context
            topics = self.extract_topics_local(content)
            
            # Store as a memory for context
            self.store_insight(
                content=f"Journal Entry: {title}\n{content[:200]}...",
                source="journal",
                context=content,
                app_name="journal",
                topics=topics
            )
            
            conn.commit()
            conn.close()
            
            return entry_id
        except Exception as e:
            logging.error(f"Error adding journal entry: {e}")
            return None
    
    def get_journal_entries(self, limit=50, offset=0, mood=None, tag=None):
        """Get journal entries with optional filtering
        
        Args:
            limit: Maximum number of entries to return
            offset: Number of entries to skip
            mood: Filter by mood
            tag: Filter by tag
            
        Returns:
            List of journal entries
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM journal_entries"
        params = []
        
        where_clauses = []
        
        if mood:
            where_clauses.append("mood = ?")
            params.append(mood)
        
        if tag:
            where_clauses.append("tags LIKE ?")
            params.append(f"%{tag}%")
        
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        
        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        
        entries = [dict(row) for row in cursor.fetchall()]
        
        # Parse tags from JSON
        for entry in entries:
            if entry.get('tags'):
                try:
                    entry['tags'] = json.loads(entry['tags'])
                except json.JSONDecodeError:
                    entry['tags'] = []
        
        conn.close()
        return entries
    
    def get_journal_entry(self, entry_id):
        """Get a specific journal entry by ID
        
        Args:
            entry_id: ID of the entry to retrieve
            
        Returns:
            Journal entry dictionary or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT * FROM journal_entries
        WHERE id = ?
        ''', (entry_id,))
        
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            return None
        
        entry = dict(row)
        
        # Parse tags from JSON
        if entry.get('tags'):
            try:
                entry['tags'] = json.loads(entry['tags'])
            except json.JSONDecodeError:
                entry['tags'] = []
        
        conn.close()
        return entry
    
    def update_journal_entry(self, entry_id, title=None, content=None, mood=None, tags=None):
        """Update a journal entry
        
        Args:
            entry_id: ID of the entry to update
            title: New title (optional)
            content: New content (optional)
            mood: New mood (optional)
            tags: New tags (optional)
            
        Returns:
            Boolean indicating success
        """
        try:
            # First get the current entry
            entry = self.get_journal_entry(entry_id)
            if not entry:
                return False
            
            # Prepare update query
            updates = []
            params = []
            
            if title is not None:
                updates.append("title = ?")
                params.append(title)
            
            if content is not None:
                updates.append("content = ?")
                params.append(content)
            
            if mood is not None:
                updates.append("mood = ?")
                params.append(mood)
            
            if tags is not None:
                updates.append("tags = ?")
                params.append(json.dumps(tags))
            
            if not updates:
                return True  # Nothing to update
            
            updates.append("last_modified = ?")
            params.append(time.time())
            
            params.append(entry_id)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(f'''
            UPDATE journal_entries
            SET {", ".join(updates)}
            WHERE id = ?
            ''', params)
            
            conn.commit()
            conn.close()
            
            return True
        except Exception as e:
            logging.error(f"Error updating journal entry: {e}")
            return False
    
    def delete_journal_entry(self, entry_id):
        """Delete a journal entry
        
        Args:
            entry_id: ID of the entry to delete
            
        Returns:
            Boolean indicating success
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
            DELETE FROM journal_entries
            WHERE id = ?
            ''', (entry_id,))
            
            conn.commit()
            conn.close()
            
            return True
        except Exception as e:
            logging.error(f"Error deleting journal entry: {e}")
            return False
    
    def get_journal_stats(self):
        """Get statistics about journal entries
        
        Returns:
            Dictionary containing journal statistics
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get total number of entries
            cursor.execute('SELECT COUNT(*) FROM journal_entries')
            total_entries = cursor.fetchone()[0]
            
            # Get mood distribution
            cursor.execute('SELECT mood, COUNT(*) FROM journal_entries GROUP BY mood')
            mood_counts = dict(cursor.fetchall())
            
            # Get tag distribution
            cursor.execute('SELECT tags FROM journal_entries')
            all_tags = []
            for tags_json, in cursor.fetchall():
                if tags_json:
                    try:
                        tags = json.loads(tags_json)
                        all_tags.extend(tags)
                    except json.JSONDecodeError:
                        continue
            
            tag_counts = Counter(all_tags).most_common(10)
            
            conn.close()
            
            return {
                'total_entries': total_entries,
                'mood_distribution': mood_counts,
                'top_tags': tag_counts
            }
        except Exception as e:
            logging.error(f"Error getting journal stats: {e}")
            return None 