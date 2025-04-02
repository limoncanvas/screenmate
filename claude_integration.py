import os
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

class ClaudeIntegration:
    def __init__(self):
        """Initialize Claude integration"""
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment variables")
        
        self.client = Anthropic(api_key=self.api_key)
        self.context = []  # Store recent interactions for context
    
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
            
            return insight
        
        except Exception as e:
            return f"Error getting insights: {str(e)}"
    
    def get_insights_with_context(self, screen_text, input_context):
        """Get insights from Claude based on screen text and input context"""
        if not screen_text or len(screen_text.strip()) < 10:
            return "Not enough text on screen to analyze."
        
        # Convert input context to a readable string
        context_str = ""
        
        # Add current application context
        current_app = input_context.get("current_app", {})
        if current_app:
            context_str += f"You are currently using: {current_app.get('name')} - {current_app.get('title')}\n"
            context_str += f"You've been in this application for about {int(current_app.get('time_spent', 0))} seconds.\n\n"
        
        # Add recent application switches
        recent_apps = input_context.get("recent_apps", [])
        if recent_apps:
            context_str += "Recently used applications:\n"
            for app in recent_apps[-3:]:  # Just show the last 3
                context_str += f"- {app.get('name')} ({app.get('title')})\n"
            context_str += "\n"
        
        # Add recent text input
        recent_input = input_context.get("recent_input", [])
        if recent_input:
            context_str += "Recent input you've typed:\n"
            for input_item in recent_input[-5:]:  # Just the last 5 inputs
                context_str += f"- In {input_item.get('app')}: \"{input_item.get('text')}\"\n"
            context_str += "\n"
        
        # Create the prompt with both screen content and input context
        prompt = f"""
        I'm looking at my screen which contains the following text:
        
        {screen_text}
        
        Additional context about what I'm doing:
        {context_str}
        
        Based on this information, what are 1-3 key insights or helpful observations you can provide? 
        Focus on what might be most helpful to know right now given what I'm working on.
        Keep your response brief and focused.
        """
        
        try:
            response = self.client.messages.create(
                model="claude-3-sonnet-20240229",
                max_tokens=300,  # Keep responses brief
                system="You are ScreenMate, an AI assistant that helps users understand what they're working on. Provide brief, focused insights that would be most helpful given what's visible on screen and the user's recent activity. Don't explain what ScreenMate is - just provide the insights directly.",
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
                "input_context": input_context,
                "insight": insight
            })
            
            return insight
        
        except Exception as e:
            return f"Error getting insights: {str(e)}"
    
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
            
            return response.content[0].text
        
        except Exception as e:
            return f"Error getting answer: {str(e)}" 