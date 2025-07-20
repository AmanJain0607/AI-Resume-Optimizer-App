# AI-Resume-Optimizer-App# 🧠 AI Resume Optimizer App

A full-stack AI-powered web application that analyzes, scores, and optimizes resumes using Google's Gemini 1.5 API. Users can generate ATS-compliant LaTeX-based resumes, evaluate them against job descriptions, receive feedback, and export polished PDF documents.

## 🚀 Features

- 🔐 **Login-protected** web app with session management
- 📄 **Resume Parsing** and LaTeX-based formatting
- 🤖 **Gemini 1.5 API Integration** for:
  - Resume evaluation and scoring
  - Feedback generation
  - Skill analysis and gap detection
  - Resume optimization
- 📈 **Summary PDF Reports** with score and suggestions
- 📝 **Skill Section Generator** from Gemini-based analysis
- 📥 **Downloadable ATS-friendly PDF resumes**
- 📂 Support for multiple resume sessions using UUIDs

---

## 🛠️ Built With

- **Python** + **Flask** – Backend web framework
- **Google Generative AI (Gemini 1.5)** – AI-powered content generation
- **LaTeX** – High-quality resume formatting
- **PyPDF2** + **ReportLab** – PDF generation and merging
- **HTML + Jinja2** – Frontend templating

---

## 📦 Requirements

Install dependencies from `requirements.txt`:

```bash
pip install -r requirements.txt
requirements.txt
nginx
Copy
Edit
Flask
google-generativeai
PyPDF2
reportlab
🔑 Setup
Clone the repository:

bash
Copy
Edit
git clone https://github.com/your-username/ai-resume-optimizer.git
cd ai-resume-optimizer
Set your Gemini API key:

You can either:

Set it as an environment variable:

bash
Copy
Edit
export GENAI_API_KEY=your-key-here
Or enter it in the web app manually during resume generation.

Run the app:

bash
Copy
Edit
python app.py
Then go to http://127.0.0.1:5000 in your browser.

🔐 Authentication
Use the hardcoded passcode (PASSCODE = "aman") to log in. You can change this in app.py.

📁 Project Structure
bash
Copy
Edit
.
├── app.py                      # Main Flask application
├── requirements.txt            # Python dependencies
├── templates/
│   ├── index.html              # Homepage UI
│   ├── login.html              # Login page UI
│   └── latex_template.tex      # LaTeX resume template
├── prompts/
│   ├── resume_formatter.txt    # Prompt to convert resume to LaTeX
│   ├── resume_evaluator.txt    # Prompt to score and give feedback
│   └── resume_optimizer.txt    # Prompt to improve resume
📄 Output
✅ LaTeX Resume Code – Gemini fills a template with user content

✅ PDF Output – Includes summary page + resume

✅ Score & Feedback – Gemini evaluates job match

✅ Skills Analysis – Detects gaps and missing certifications

