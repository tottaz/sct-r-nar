# Rúnar ⚡

**Rúnar** is an AI-powered Resume and Job Description platform inspired by the wisdom of the Norse runes.  
It helps candidates and recruiters craft, analyze, and improve resumes and job descriptions with the strength of AI.  

## ✨ Features
- 📂 Upload and analyze resumes (PDF) with AI insights  
- 🧾 Generate professional job descriptions from structured input  
- 🛠️ Create ATS-friendly resumes from form data  
- 🔍 AI-powered resume analysis: strengths, weaknesses, and fit for roles  
- ⚔️ Norse-inspired design philosophy: turning career journeys into sagas  

## 🚀 Getting Started

### Prerequisites
- Python 3.10+  
- Flask  
- OpenAI API key **or** Ollama running locally  
- A valid `config.json` with:
  ```json
  {
    "use_openai": true,
    "openai_api_key": "your-api-key-here",
    "ollama_base_url": "http://localhost:11434",
    "fernet_key": "your-generated-fernet-key"
  }

Installation
```bash
git clone https://github.com/yourusername/runar.git
cd runar
pip install -r requirements.txt
```
Run the App
```bash
python app.py
```

Open http://localhost:5000
 in your browser.

# Usage

Upload Resume (PDF): Upload a candidate resume and get an AI-powered analysis.

Analyze Resume: View strengths, weaknesses, and job role suggestions.

Generate Job Description: Fill a form with role, skills, and experience to create a polished JD.

Build Resume: Enter structured data to generate a professional ATS-friendly resume.

# Tech Stack

Backend: Python, Flask

Frontend: Jinja, Bootstrap 5

AI: OpenAI GPT models or Ollama (local LLMs)

PDF Handling: pdfplumber, reportlab

# Name

The name Rúnar comes from Old Norse rúnar meaning runes, secret writings.
Just as runes held wisdom and stories of the past, Rúnar helps capture and shape the story of a career.

# License

MIT License – feel free to use, modify, and share.

“Write your career in runes, and let AI forge your path.”
