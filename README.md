# ScreenMate MVP

ScreenMate is an AI assistant that analyzes your screen and provides relevant insights using Claude AI.

## Prerequisites

- Python 3.9 or higher
- Tesseract OCR installed on your system
  - Windows: Download and install from [https://github.com/UB-Mannheim/tesseract/wiki](https://github.com/UB-Mannheim/tesseract/wiki)
  - Mac: `brew install tesseract`
  - Linux: `sudo apt install tesseract-ocr`
- Anthropic API key

## Installation

1. Clone this repository or download the files
2. Create a virtual environment:
   ```bash
   python -m venv venv
   # Activate on Windows:
   venv\Scripts\activate
   # Activate on Mac/Linux:
   source venv/bin/activate
   ```
3. Install the required packages:
   ```bash
   pip install -r requirements.txt
   ```
4. Create a `.env` file in the project root and add your Anthropic API key:
   ```
   ANTHROPIC_API_KEY=your_api_key_here
   ```

## Usage

1. Run the application:
   ```bash
   python main.py
   ```

2. The application window will open with the following features:
   - Screen preview showing what's being captured
   - Status indicator showing if analysis is active
   - AI insights display
   - Question input field
   - Control buttons for starting/stopping analysis and performing one-time analysis

3. To use ScreenMate:
   - Click "Analyze Now" for a one-time screen analysis
   - Click "Start Analysis" to begin continuous analysis (every 10 seconds)
   - Type questions in the input field to ask about what's on your screen
   - Click "Ask" to get AI-powered answers about your screen content

## Features

- Real-time screen capture and analysis
- OCR text extraction from screen content
- AI-powered insights using Claude
- Question-answering about screen content
- Continuous or one-time analysis modes
- Modern, responsive UI using CustomTkinter

## Troubleshooting

1. If OCR doesn't work:
   - Ensure Tesseract is installed correctly
   - For Windows users, verify the Tesseract path in `screen_capture.py`

2. If Claude API calls fail:
   - Check your API key in the `.env` file
   - Verify your internet connection

3. If the UI looks wrong:
   - Try changing the appearance mode in `app.py`:
     ```python
     ctk.set_appearance_mode("Light")  # or "Dark"
     ```

## Contributing

Feel free to submit issues and enhancement requests! 