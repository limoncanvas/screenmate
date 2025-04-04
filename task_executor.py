import os
import subprocess
import pyautogui
import time
from typing import Dict, List, Optional
import json
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

class TaskExecutor:
    def __init__(self):
        self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.supported_actions = {
            "open_app": self._open_application,
            "click": self._click,
            "type": self._type_text,
            "press": self._press_key,
            "wait": self._wait,
            "search": self._search,
            "navigate": self._navigate,
            "copy": self._copy,
            "paste": self._paste,
            "scroll": self._scroll
        }
        
    def execute_task(self, task_description: str) -> Dict:
        """
        Execute a task based on the user's description
        Returns a dictionary with the execution status and results
        """
        try:
            # Get AI-generated action plan
            action_plan = self._get_action_plan(task_description)
            
            # Execute the plan
            results = []
            for action in action_plan:
                action_type = action.get("action")
                if action_type in self.supported_actions:
                    result = self.supported_actions[action_type](**action.get("params", {}))
                    results.append(result)
                    time.sleep(0.5)  # Small delay between actions
                else:
                    results.append({"status": "error", "message": f"Unsupported action: {action_type}"})
            
            return {
                "status": "success",
                "results": results,
                "task_description": task_description
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "task_description": task_description
            }
    
    def _get_action_plan(self, task_description: str) -> List[Dict]:
        """Get AI-generated action plan for the task"""
        prompt = f"""
        Given the following task: "{task_description}"
        
        Generate a sequence of computer actions to accomplish this task. Each action should be one of:
        {list(self.supported_actions.keys())}
        
        Return the actions as a JSON array of objects, where each object has:
        - action: the type of action
        - params: parameters for the action
        
        Example format:
        [
            {{"action": "open_app", "params": {{"app_name": "Safari"}}}},
            {{"action": "wait", "params": {{"seconds": 2}}}},
            {{"action": "type", "params": {{"text": "https://google.com"}}}},
            {{"action": "press", "params": {{"key": "enter"}}}}
        ]
        """
        
        response = self.client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        try:
            return json.loads(response.content[0].text)
        except json.JSONDecodeError:
            return []
    
    def _open_application(self, app_name: str) -> Dict:
        """Open an application"""
        try:
            if os.name == 'posix':  # macOS
                subprocess.run(['open', '-a', app_name])
            else:  # Windows
                subprocess.run(['start', app_name], shell=True)
            return {"status": "success", "action": "open_app", "app": app_name}
        except Exception as e:
            return {"status": "error", "action": "open_app", "message": str(e)}
    
    def _click(self, x: int, y: int) -> Dict:
        """Click at specific coordinates"""
        try:
            pyautogui.click(x, y)
            return {"status": "success", "action": "click", "coordinates": (x, y)}
        except Exception as e:
            return {"status": "error", "action": "click", "message": str(e)}
    
    def _type_text(self, text: str) -> Dict:
        """Type text"""
        try:
            pyautogui.write(text)
            return {"status": "success", "action": "type", "text": text}
        except Exception as e:
            return {"status": "error", "action": "type", "message": str(e)}
    
    def _press_key(self, key: str) -> Dict:
        """Press a key"""
        try:
            pyautogui.press(key)
            return {"status": "success", "action": "press", "key": key}
        except Exception as e:
            return {"status": "error", "action": "press", "message": str(e)}
    
    def _wait(self, seconds: float) -> Dict:
        """Wait for specified seconds"""
        try:
            time.sleep(seconds)
            return {"status": "success", "action": "wait", "seconds": seconds}
        except Exception as e:
            return {"status": "error", "action": "wait", "message": str(e)}
    
    def _search(self, query: str) -> Dict:
        """Search for text on screen"""
        try:
            location = pyautogui.locateOnScreen(query)
            if location:
                return {"status": "success", "action": "search", "found": True, "location": location}
            return {"status": "success", "action": "search", "found": False}
        except Exception as e:
            return {"status": "error", "action": "search", "message": str(e)}
    
    def _navigate(self, direction: str) -> Dict:
        """Navigate in a direction"""
        try:
            if direction == "up":
                pyautogui.press("up")
            elif direction == "down":
                pyautogui.press("down")
            elif direction == "left":
                pyautogui.press("left")
            elif direction == "right":
                pyautogui.press("right")
            return {"status": "success", "action": "navigate", "direction": direction}
        except Exception as e:
            return {"status": "error", "action": "navigate", "message": str(e)}
    
    def _copy(self) -> Dict:
        """Copy selected text"""
        try:
            pyautogui.hotkey('command', 'c') if os.name == 'posix' else pyautogui.hotkey('ctrl', 'c')
            return {"status": "success", "action": "copy"}
        except Exception as e:
            return {"status": "error", "action": "copy", "message": str(e)}
    
    def _paste(self) -> Dict:
        """Paste text"""
        try:
            pyautogui.hotkey('command', 'v') if os.name == 'posix' else pyautogui.hotkey('ctrl', 'v')
            return {"status": "success", "action": "paste"}
        except Exception as e:
            return {"status": "error", "action": "paste", "message": str(e)}
    
    def _scroll(self, amount: int) -> Dict:
        """Scroll up or down"""
        try:
            pyautogui.scroll(amount)
            return {"status": "success", "action": "scroll", "amount": amount}
        except Exception as e:
            return {"status": "error", "action": "scroll", "message": str(e)} 