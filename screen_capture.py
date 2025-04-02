import mss
import mss.tools
import pytesseract
import io
from PIL import Image
import time
import os

class ScreenCapture:
    def __init__(self):
        """Initialize the screen capture module"""
        # Set the path to tesseract if needed (example for Windows)
        if os.name == 'nt':  # Windows
            pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
            
    def capture_screen(self):
        """Capture the entire screen"""
        with mss.mss() as sct:
            # Get the entire screen
            monitor = sct.monitors[1]  # Primary monitor
            screenshot = sct.grab(monitor)
            
            # Convert to PIL Image
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            return img
            
    def extract_text(self, image):
        """Extract text from the image using OCR"""
        try:
            text = pytesseract.image_to_string(image)
            return text
        except Exception as e:
            print(f"Error extracting text: {e}")
            return ""
    
    def capture_active_window(self):
        """Capture the active window (simplified version)"""
        # In a full implementation, you would detect the active window
        # For MVP, we'll just capture the middle portion of the screen
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # Primary monitor
            
            # Capture the middle 60% of the screen as an approximation
            width = monitor["width"]
            height = monitor["height"]
            
            left = int(width * 0.2)
            top = int(height * 0.2)
            right = int(width * 0.8)
            bottom = int(height * 0.8)
            
            region = {"left": left, "top": top, "width": right - left, "height": bottom - top}
            screenshot = sct.grab(region)
            
            # Convert to PIL Image
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            return img

    def analyze_screen(self):
        """Capture screen and extract text"""
        img = self.capture_active_window()
        text = self.extract_text(img)
        return {
            "image": img,
            "text": text,
            "timestamp": time.time()
        } 