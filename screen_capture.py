import mss
import mss.tools
import pytesseract
import io
from PIL import Image, ImageEnhance, ImageFilter
import time
import os
import platform
import logging
import base64

class ScreenCapture:
    def __init__(self):
        """Initialize screen capture with platform-specific settings"""
        self.sct = mss.mss()
        
        # Configure Tesseract path for Windows
        if platform.system() == "Windows":
            pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        
        # Configure logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
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
        """Extract text with improved OCR settings"""
        try:
            # Add preprocessing for better OCR results
            # Enhance contrast
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(1.5)
            
            # Apply sharpening
            image = image.filter(ImageFilter.SHARPEN)
            
            # Use better OCR configuration
            custom_config = r'--oem 3 --psm 6 -l eng'
            text = pytesseract.image_to_string(image, config=custom_config)
            return text
        except Exception as e:
            self.logger.error(f"Error extracting text: {e}")
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
        """Capture and analyze the current screen content"""
        try:
            # Capture the primary monitor
            screenshot = self.sct.grab(self.sct.monitors[1])
            
            # Convert to PIL Image
            img = Image.frombytes('RGB', screenshot.size, screenshot.rgb)
            
            # Extract text
            text = self.extract_text(img)
            
            # Convert image to base64 for storage
            buffered = io.BytesIO()
            img.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()
            
            return {
                "text": text,
                "image": img_str,
                "timestamp": time.time()
            }
            
        except Exception as e:
            self.logger.error(f"Error analyzing screen: {e}")
            return None 