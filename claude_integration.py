import os
import time
import logging
from typing import Dict, Any, Optional, List
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

class ClaudeIntegration:
    def __init__(self, daily_budget: int = 20):
        """Initialize Claude integration with API budget tracking"""
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment variables")
        
        self.client = Anthropic(api_key=self.api_key)
        self.context = []  # Store recent interactions for context
        
        # API budget tracking
        self.daily_budget = daily_budget
        self.api_calls_today = 0
        self.last_budget_reset = time.time()
        
        # Configure logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
        # Cost tracking
        self.daily_cost = 0.0
        self.total_cost = 0.0
        self.cost_per_call = 0.00001  # $0.00001 per token (approximate)
        self.max_daily_cost = 1.0  # $1.00 maximum daily cost
    
    def _check_api_budget(self) -> bool:
        """Check if API budget is exceeded and reset if needed"""
        current_time = time.time()
        
        # Reset counter if it's a new day
        if current_time - self.last_budget_reset > 86400:  # 24 hours
            self.api_calls_today = 0
            self.daily_cost = 0.0
            self.last_budget_reset = current_time
        
        return self.api_calls_today < self.daily_budget
    
    def _increment_api_counter(self, tokens_used: int = 1000):
        """Increment the API call counter and cost tracking"""
        self.api_calls_today += 1
        call_cost = tokens_used * self.cost_per_call
        self.daily_cost += call_cost
        self.total_cost += call_cost
        
        # Log cost information
        self.logger.info(f"API call cost: ${call_cost:.6f}, Daily total: ${self.daily_cost:.6f}, Total: ${self.total_cost:.6f}")
        
        # Check if we've exceeded the daily cost limit
        if self.daily_cost >= self.max_daily_cost:
            self.logger.warning(f"Daily cost limit of ${self.max_daily_cost} reached. Switching to local processing.")
            return False
        return True
    
    def get_insights(self, screen_text):
        """Get insights from Claude based on screen text"""
        if not screen_text or len(screen_text.strip()) < 10:
            return "Not enough text on screen to analyze."
        
        prompt = f"""
        I'm looking at my screen which contains the following text:
        
        {screen_text}
        
        Based on this information, what are 1-3 key insights or helpful observations you can provide? 
        Focus on what might be most helpful to know right now given what I'm working on.
        Keep your response brief and focused.
        """
        
        try:
            response = self.client.messages.create(
                model="claude-3-sonnet-20240229",
                max_tokens=300,  # Keep responses brief
                system="You are ScreenMate, an AI assistant that helps users understand what they're working on. Provide brief, focused insights that would be most helpful given what's visible on screen. Don't explain what ScreenMate is - just provide the insights directly.",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            insight = response.content[0].text
            
            # Add to context for future reference
            if len(self.context) >= 5:  # Keep only last 5 interactions
                self.context.pop(0)
            self.context.append({
                "screen_text": screen_text,
                "insight": insight
            })
            
            # Track API usage and cost
            self._increment_api_counter(300)  # Approximate token count
            
            return insight
        
        except Exception as e:
            return f"Error getting insights: {str(e)}"
    
    def get_insights_with_context(self, screen_text: str, input_context: Dict[str, Any], use_api: bool = True) -> str:
        """Get insights from Claude with context, respecting API budget"""
        if not screen_text or len(screen_text) < 50:
            return "Not enough content to analyze."
            
        # Check if we should use the API
        if not use_api or not self._check_api_budget():
            self.logger.info("API budget exceeded or economy mode enabled, using local processing")
            return self._generate_local_insight(screen_text, input_context)
            
        try:
            # Prepare the prompt with context
            prompt = f"""
            Analyze this screen content and user context to provide insights:
            
            Screen Content:
            {screen_text[:1000]}  # Limit content length
            
            User Context:
            Current App: {input_context.get('current_app', {}).get('name', 'Unknown')}
            Recent Activity: {input_context.get('recent_activity', [])}
            
            Provide a brief, actionable insight about what the user is doing and any relevant suggestions.
            Focus on productivity and workflow improvements.
            """
            
            # Get response from Claude
            response = self.client.messages.create(
                model="claude-3-sonnet-20240229",
                max_tokens=150,
                temperature=0.7,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Track API usage and cost
            if not self._increment_api_counter(150):  # Approximate token count
                return self._generate_local_insight(screen_text, input_context)
                
            return response.content[0].text
            
        except Exception as e:
            self.logger.error(f"Error getting insights: {e}")
            return self._generate_local_insight(screen_text, input_context)
            
    def _generate_local_insight(self, screen_text: str, input_context: Dict[str, Any]) -> str:
        """Generate a simple insight without using the API"""
        app_name = input_context.get('current_app', {}).get('name', 'Unknown')
        
        # Extract key phrases (simple implementation)
        words = screen_text.lower().split()
        word_freq = {}
        for word in words:
            if len(word) > 3:  # Skip short words
                word_freq[word] = word_freq.get(word, 0) + 1
                
        # Get most common words
        common_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]
        
        # Generate simple insight
        insight = f"Working in {app_name}. "
        if common_words:
            insight += f"Focused on: {', '.join(word for word, _ in common_words)}. "
            
        # Add activity-based insight
        recent_activity = input_context.get('recent_activity', [])
        if recent_activity:
            insight += f"Recent activity suggests {recent_activity[-1]}."
            
        return insight
        
    def get_answer(self, question, screen_text):
        """Get a specific answer to a question about the screen content"""
        prompt = f"""
        Based on the following screen content:
        
        {screen_text}
        
        Please answer this question: {question}
        
        Keep your response brief and focused on the question.
        """
        
        try:
            response = self.client.messages.create(
                model="claude-3-sonnet-20240229",
                max_tokens=300,
                system="You are ScreenMate, an AI assistant that helps users understand what they're working on. Provide clear, concise answers to questions about the screen content.",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Track API usage and cost
            if not self._increment_api_counter(300):  # Approximate token count
                return "API cost limit reached. Please try again later."
                
            return response.content[0].text
        
        except Exception as e:
            return f"Error getting answer: {str(e)}"
    
    def generate_daily_summary(self, memories: List[Dict[str, Any]], use_api: bool = True) -> str:
        """Generate a summary of daily insights with budget awareness"""
        if not memories:
            return "No insights collected today."
            
        # Check if we should use the API
        if not use_api or not self._check_api_budget():
            return self._generate_local_summary(memories)
            
        try:
            # Group memories by topic
            topics_to_memories = {}
            for memory in memories:
                for topic in memory.get('topics', []):
                    if topic not in topics_to_memories:
                        topics_to_memories[topic] = []
                    topics_to_memories[topic].append(memory)
                    
            # Create compact representation
            summary_points = []
            for topic, topic_memories in topics_to_memories.items():
                topic_summary = f"Topic: {topic} ({len(topic_memories)} insights)"
                key_points = [m['content'].split('.')[0] + '.' for m in topic_memories[:3]]
                topic_summary += "\n - " + "\n - ".join(key_points)
                summary_points.append(topic_summary)
                
            all_memory_text = "\n\n".join(summary_points)
            
            # Generate summary with Claude
            prompt = f"""
            Please create a concise summary of today's insights, already grouped by topic:
            
            {all_memory_text}
            
            Create a well-organized summary that:
            1. Highlights the most important information from each topic
            2. Presents any action items or key takeaways
            3. Is brief but comprehensive
            
            Format the summary with clear headings and bullet points.
            """
            
            response = self.client.messages.create(
                model="claude-3-sonnet-20240229",
                max_tokens=500,
                temperature=0.7,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Track API usage and cost
            if not self._increment_api_counter(500):  # Approximate token count
                return self._generate_local_summary(memories)
                
            return response.content[0].text
            
        except Exception as e:
            self.logger.error(f"Error generating summary: {e}")
            return self._generate_local_summary(memories)
            
    def _generate_local_summary(self, memories: List[Dict[str, Any]]) -> str:
        """Generate a simple summary without API calls"""
        # Group by topic
        topics_to_memories = {}
        for memory in memories:
            for topic in memory.get('topics', []):
                if topic not in topics_to_memories:
                    topics_to_memories[topic] = []
                topics_to_memories[topic].append(memory)
                
        # Generate summary text
        summary = "# Today's Insights Summary\n\n"
        
        # Add date
        summary += f"Date: {time.strftime('%Y-%m-%d', time.localtime())}\n\n"
        
        # Add topics sections
        for topic, topic_memories in topics_to_memories.items():
            summary += f"## {topic.title()} ({len(topic_memories)} insights)\n\n"
            
            # Add key points
            for memory in topic_memories[:5]:  # Limit to 5 per topic
                timestamp = time.strftime("%H:%M", time.localtime(memory['timestamp']))
                summary += f"- [{timestamp}] {memory['content'].split('.')[0]}.\n"
            
            summary += "\n"
            
        return summary
        
    def get_api_usage_stats(self) -> Dict[str, Any]:
        """Get API usage statistics"""
        return {
            "api_calls_today": self.api_calls_today,
            "daily_cost": self.daily_cost,
            "total_cost": self.total_cost,
            "daily_budget": self.max_daily_cost,
            "remaining_budget": max(0, self.max_daily_cost - self.daily_cost)
        }
    
    def get_key_points(self, screen_text, use_api=True):
        """Extract key points from screen text with cost control"""
        if not screen_text or len(screen_text.strip()) < 50:
            return "Not enough text to extract key points."
        
        # Enforce character limit to control costs
        screen_text = screen_text[:2000] if len(screen_text) > 2000 else screen_text
        
        # Check budget before making API call
        if not use_api or not self._check_api_budget():
            return self._extract_key_points_local(screen_text)
        
        prompt = f"""
        Extract the 3-5 most important points and any action items from this content:
        
        {screen_text}
        
        Format your response as a bulleted list. For action items, add "(ACTION ITEM)" at the end.
        Focus on deadlines, key decisions, important facts, and required actions.
        Be concise and clear.
        """
        
        try:
            response = self.client.messages.create(
                model="claude-3-haiku-20240307",  # Use cheaper model for MVP
                max_tokens=200,  # Limit token usage
                system="You extract key points from text. Be concise and highlight only the most important information.",
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Track API usage and cost
            self._increment_api_counter(200)  # Approximate token count
            
            return response.content[0].text
        except Exception as e:
            self.logger.error(f"Error getting key points: {e}")
            return self._extract_key_points_local(screen_text)
    
    def _extract_key_points_local(self, text):
        """Extract key points without API calls"""
        # Simple rule-based extraction
        sentences = text.split('.')
        key_points = []
        
        # Keywords that suggest importance
        important_keywords = ['must', 'important', 'critical', 'deadline', 'required', 
                            'key', 'essential', 'urgent', 'necessary', 'vital']
        
        # Action verbs that suggest tasks
        action_verbs = ['submit', 'complete', 'send', 'prepare', 'review', 'update', 
                       'create', 'finish', 'deliver', 'schedule']
        
        # Check each sentence for importance
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
                
            # Check if sentence contains important keywords
            if any(keyword in sentence.lower() for keyword in important_keywords):
                key_points.append(f"• {sentence}.")
                continue
                
            # Check if sentence contains action verbs
            if any(verb in sentence.lower() for verb in action_verbs):
                key_points.append(f"• {sentence}. (ACTION ITEM)")
                continue
        
        # If we couldn't find important sentences, take the first few
        if not key_points and len(sentences) > 3:
            for i in range(min(3, len(sentences))):
                if sentences[i].strip():
                    key_points.append(f"• {sentences[i].strip()}.")
        
        if not key_points:
            return "No key points identified."
            
        return "\n".join(key_points) 