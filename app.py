import os
import re
import uuid
import logging
from flask import Flask, Response, request, render_template, redirect, url_for, session, jsonify
from functools import wraps
import subprocess
import tempfile
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from PyPDF2 import PdfMerger

# ✅ Logging configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ✅ Create Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)  # Needed for session management

# ✅ Static passcode (change later if needed)
PASSCODE = "aman"

# ✅ Try importing Gemini
try:
    import google.generativeai as genai
    HAS_GENAI = True
    print("✅ google.generativeai imported successfully")
except ImportError:
    HAS_GENAI = False
    print("❌ google.generativeai not found — using fallback or mock")

# ✅ Set API key from env (or leave empty, user can enter it manually)
DEFAULT_GENAI_API_KEY = os.environ.get("GENAI_API_KEY", "")

# ✅ Configure Gemini model
if HAS_GENAI and DEFAULT_GENAI_API_KEY:
    genai.configure(api_key=DEFAULT_GENAI_API_KEY)
    default_model = genai.GenerativeModel("gemini-1.5-flash")
else:
    default_model = None

# ✅ Load helper files (prompts + LaTeX)
def load_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logging.error(f"❌ Error loading file {path}: {e}")
        return ""

# Load template + prompts
LATEX_TEMPLATE = load_file("templates/latex_template.tex")
PROMPT_FORMATTER = load_file("prompts/resume_formatter.txt")
PROMPT_EVALUATOR = load_file("prompts/resume_evaluator.txt")
PROMPT_OPTIMIZER = load_file("prompts/resume_optimizer.txt")

# ✅ In-memory resume store (cache by resume_id)
resume_store = {}

# ✅ Login required decorator
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

# ✅ Login route
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("passcode") == PASSCODE:
            session["authenticated"] = True
            return redirect(url_for("index"))
        return render_template("login.html", error="Invalid passcode")
    return render_template("login.html")

# ✅ Logout route
@app.route("/logout")
def logout():
    session.pop("authenticated", None)
    return redirect(url_for("login"))

# ✅ Homepage route
@app.route("/")
@login_required
def index():
    return render_template("index.html")

# ✅ Route to generate resume
@app.route("/generate_resume", methods=["POST"])
@login_required
def generate_resume():
    try:
        # 🌐 Get user input from the form
        resume_text = request.form.get("resume_content", "").strip()
        job_description = request.form.get("job_description", "").strip()
        user_api_key = request.form.get("api_key", "").strip()
        company_name = request.form.get("company_name", "").strip()

        if not resume_text or not job_description:
            return jsonify({"error": "Resume and Job Description are required."}), 400

        # ⚙️ Configure Gemini based on provided API key
        if HAS_GENAI:
            try:
                if user_api_key:
                    genai.configure(api_key=user_api_key)
                    model = genai.GenerativeModel("gemini-1.5-flash")
                    logging.info("🔑 Using user-provided Gemini key")
                else:
                    model = default_model
                    logging.info("🧠 Using default Gemini model")
            except Exception as e:
                logging.warning(f"❗ Failed to configure Gemini: {e}")
                model = default_model
        else:
            model = None

        if not model:
            return jsonify({"error": "Gemini model not available."}), 500

        logging.info("📤 Sending data to Gemini to fill LaTeX template")

        # 🧠 Prompt: Resume formatting using LaTeX template with placeholders
        format_prompt = PROMPT_FORMATTER.replace("<RESUME_TEXT>", resume_text).replace("<LATEX_TEMPLATE>", LATEX_TEMPLATE)

        response = model.generate_content(format_prompt)

        if not response.text:
            return jsonify({"error": "Gemini failed to generate resume."}), 500

        latex_resume = response.text.strip()
        # 🧽 Clean LaTeX if wrapped in markdown
        if latex_resume.startswith("```latex") and latex_resume.endswith("```"):
                latex_resume = latex_resume.replace("```latex", "").replace("```", "").strip()

        # 🧠 Evaluate the resume using the evaluator prompt
        evaluator_prompt = PROMPT_EVALUATOR.replace("<LATEX_CODE>", latex_resume).replace("<JOB_DESCRIPTION>", job_description)
        eval_response = model.generate_content(evaluator_prompt)
        score = 7  # Default fallback score
        feedback = "No feedback available"
        optimization_message = ""  # ✅ Declare in outer scope

        if eval_response and eval_response.text:
            raw_feedback = eval_response.text.strip()

    # Extract score robustly
            score_patterns = [
                r"score[:\- ]*(\d{1,2})/10",         
                r"overall score[:= ]*(\d{1,2})/10",  
                r"(\d{1,2})[\s]*/[\s]*10"            
                ]
            score = 7  # fallback
            for pattern in score_patterns:
                match = re.search(pattern, raw_feedback, re.IGNORECASE)
                if match:
                    score = int(match.group(1))
                    break

            feedback = enforce_line_breaks(raw_feedback)

    # 🧠 AUTO-OPTIMIZE the resume using feedback
            optimized_latex = optimize_resume_for_job(model, latex_resume, job_description, feedback)

    # Store optimization message if changed
            
            if optimized_latex != latex_resume:
                optimization_message = "Resume improved based on feedback and job description."
                latex_resume = optimized_latex  # ✅ Replace with improved version






        # 🪪 Generate a unique ID for this resume session
        resume_id = str(uuid.uuid4())

        # ⏳ Save initial data
        resume_store[resume_id] = {
            "latex_code": latex_resume,
            "company_name": company_name,
            "api_key": user_api_key or None,
            "resume_text": resume_text,
            "job_description": job_description,
            "score": score,
            "feedback": feedback,
            "optimization_message": optimization_message
        }



        logging.info(f"✅ Resume generated and stored with ID: {resume_id}")

        return jsonify({
            "message": "Resume LaTeX generated",
            "resume_id": resume_id,
            "latex_code": latex_resume,
            "score": score,
            "feedback": feedback
        }), 200

    except Exception as e:
        logging.exception("❌ Error in generate_resume route")
        return jsonify({"error": "Server error occurred during resume generation."}), 500

# ✅ Evaluate resume match against job description using Gemini
def evaluate_resume_job_match(model, latex_resume, job_description):
    try:
        logging.info("📊 Evaluating resume against job description...")

        prompt = PROMPT_EVALUATOR \
            .replace("<LATEX_CODE>", latex_resume) \
            .replace("<JOB_DESCRIPTION>", job_description)

        response = model.generate_content(prompt)

        if not response.text:
            return (0, "No feedback received from Gemini.")

        # 🎯 Assume Gemini returns something like:
        # Score: 7/10
        # Feedback: <reason here>
        raw = response.text.strip()
        score = 0
        for line in raw.splitlines():
            if "Score" in line:
                try:
                    score = int(line.split(":")[1].strip().split("/")[0])
                    break
                except:
                    continue

        # ✅ FORMAT the feedback here before returning
        formatted_feedback = enforce_line_breaks(raw)
        return (score, formatted_feedback)

    except Exception as e:
        logging.warning(f"⚠️ Resume evaluation failed: {e}")
        return (0, "Unable to evaluate resume-job match due to an error.")

def enforce_line_breaks(feedback_text):
    import re

    # Add double newlines before sections
    feedback_text = re.sub(r"(?<!\n)(- \*\*[^\n]+?:)", r"\n\n\1", feedback_text)

    # Add newlines before sub-bullets if needed
    feedback_text = re.sub(r"(?<!\n)(- [^-*\n].+)", r"\n\1", feedback_text)

    # Clean up excess spaces
    return feedback_text.strip()



# ✅ Re-evaluate route or optional optimization call can go here
@app.route("/evaluate_resume", methods=["POST"])
@login_required
def evaluate_resume():
    try:
        resume_id = request.form.get("resume_id")

        if not resume_id or resume_id not in resume_store:
            return jsonify({"error": "Invalid resume ID"}), 400

        entry = resume_store[resume_id]
        model = default_model
        if entry.get("api_key"):
            genai.configure(api_key=entry["api_key"])
            model = genai.GenerativeModel("gemini-1.5-flash")

        score, feedback = evaluate_resume_job_match(model, entry["latex_code"], entry["job_description"])

        # Save to store
        resume_store[resume_id]["score"] = score
        resume_store[resume_id]["feedback"] = feedback

        return jsonify({
            "resume_id": resume_id,
            "score": score,
            "feedback": feedback
        }), 200

    except Exception as e:
        logging.exception("❌ Error in evaluate_resume route")
        return jsonify({"error": "Failed to evaluate resume"}), 500

# ✅ Optimize resume for job based on feedback using Gemini
def optimize_resume_for_job(model, latex_resume, job_description, feedback):
    try:
        logging.info("🛠️ Optimizing resume for better job match...")

        prompt = PROMPT_OPTIMIZER \
            .replace("<LATEX_CODE>", latex_resume) \
            .replace("<JOB_DESCRIPTION>", job_description) \
            .replace("<FEEDBACK>", feedback)

        response = model.generate_content(prompt)

        if not response.text:
            logging.warning("⚠️ Gemini returned empty response for optimization.")
            return latex_resume  # fallback

        new_latex = response.text.strip()

        # Remove markdown if present
        if new_latex.startswith("```latex") and new_latex.endswith("```"):
            new_latex = new_latex.replace("```latex", "").replace("```", "").strip()

        # Optional: prevent returning same as before
        if new_latex == latex_resume:
            logging.warning("⚠️ Gemini returned unchanged resume.")
            return latex_resume + "\n\n% Note: Gemini returned unchanged LaTeX"

        return new_latex

    except Exception as e:
        logging.warning(f"⚠️ Resume optimization failed: {e}")
        return latex_resume


# ✅ Route to auto-optimize if needed
@app.route("/optimize_resume", methods=["POST"])
@login_required
def optimize_resume():
    try:
        resume_id = request.form.get("resume_id")
        if not resume_id or resume_id not in resume_store:
            return jsonify({"error": "Invalid resume ID"}), 400

        entry = resume_store[resume_id]
        model = default_model
        if entry.get("api_key"):
            genai.configure(api_key=entry["api_key"])
            model = genai.GenerativeModel("gemini-1.5-flash")

        score = entry.get("score", 0)
        feedback = entry.get("feedback", "")
        original_latex = entry.get("latex_code", "")
        job_description = entry.get("job_description", "")

        if score >= 8:
            return jsonify({
                "message": "Resume already has a good score. No optimization needed.",
                "latex_code": original_latex,
                "score": score
            }), 200

        # ✨ Optimize it
        new_latex = optimize_resume_for_job(model, original_latex, job_description, feedback)
        entry["latex_code"] = new_latex

        # 🔁 Re-evaluate
        new_score, new_feedback = evaluate_resume_job_match(model, new_latex, job_description)
        entry["score"] = new_score
        entry["feedback"] = new_feedback

        return jsonify({
            "message": "Resume optimized successfully.",
            "resume_id": resume_id,
            "latex_code": new_latex,
            "score": new_score,
            "feedback": new_feedback
        }), 200

    except Exception as e:
        logging.exception("❌ Error during resume optimization")
        return jsonify({"error": "Resume optimization failed"}), 500

# ✅ Analyze resume skills vs job description using Gemini
def analyze_skills(model, latex_resume, job_description):
    try:
        logging.info("🧠 Analyzing skills and certifications...")

        analysis_prompt = f"""
You are a resume analyzer. Extract and evaluate skills from the given LaTeX resume and compare them with the job description.

Tasks:
1. Identify profession type
2. Extract current skills (grouped by category)
3. List current certifications (if any)
4. Compare with job description to find missing or recommended skills
5. Format clearly and consistently

Return result in this format:
PROFESSION_TYPE:
SKILL_CATEGORIES:
CURRENT_SKILLS:
  Technical Skills:
  Security Skills:
  Other Skills:
CURRENT_CERTIFICATIONS:
MISSING_SKILLS:
RECOMMENDED_SKILLS:
RECOMMENDED_CERTIFICATIONS:

Resume:
{latex_resume}

Job Description:
{job_description}
"""

        response = model.generate_content(analysis_prompt)

        if not response.text:
            return {
                "current_skills": ["Error: No skills returned"],
                "missing_skills": [],
                "recommended_skills": [],
                "current_skills_by_category": {},
                "recommended_skills_by_category": {},
                "latex_skills_section": ""
            }

        return parse_skills_response(response.text.strip())

    except Exception as e:
        logging.warning(f"⚠️ Skill analysis failed: {e}")
        return {
            "current_skills": ["Error analyzing skills"],
            "missing_skills": [],
            "recommended_skills": [],
            "current_skills_by_category": {},
            "recommended_skills_by_category": {},
            "latex_skills_section": ""
        }

# ✅ Placeholder for parsing logic
def parse_skills_response(response_text):
    import re
    from collections import defaultdict

    def extract_section(label):
        pattern = rf"{label}:\s*(.*?)(?=\n[A-Z_]+:|\Z)"
        match = re.search(pattern, response_text, re.DOTALL)
        return match.group(1).strip() if match else ""

    def extract_skills_list(text):
        return [s.strip() for s in re.split(r",|\n", text) if s.strip()]

    def extract_skills_by_category(section):
        categories = {}
        lines = section.splitlines()
        for line in lines:
            if ":" in line:
                key, val = line.split(":", 1)
                categories[key.strip()] = extract_skills_list(val)
        return categories

    # Extract all sections
    profession = extract_section("PROFESSION_TYPE")
    current_skills_block = extract_section("CURRENT_SKILLS")
    current_certs = extract_skills_list(extract_section("CURRENT_CERTIFICATIONS"))
    missing_skills = extract_skills_list(extract_section("MISSING_SKILLS"))
    recommended_skills = extract_skills_list(extract_section("RECOMMENDED_SKILLS"))
    recommended_certs = extract_skills_list(extract_section("RECOMMENDED_CERTIFICATIONS"))

    return {
        "profession_type": profession,
        "current_skills": sum(extract_skills_by_category(current_skills_block).values(), []),
        "missing_skills": missing_skills,
        "recommended_skills": recommended_skills,
        "current_skills_by_category": extract_skills_by_category(current_skills_block),
        "recommended_skills_by_category": {},  # you can parse if needed
        "current_certifications": current_certs,
        "recommended_certifications": recommended_certs,
        "latex_skills_section": ""  # will be filled later
    }


# ✅ Analyze skills route
@app.route("/analyze_skills", methods=["POST"])
@login_required
def analyze_skills_route():
    try:
        resume_id = request.form.get("resume_id")
        if not resume_id or resume_id not in resume_store:
            return jsonify({"error": "Invalid resume ID"}), 400

        entry = resume_store[resume_id]
        model = default_model
        if entry.get("api_key"):
            genai.configure(api_key=entry["api_key"])
            model = genai.GenerativeModel("gemini-1.5-flash")

        skills_data = analyze_skills(model, entry["latex_code"], entry["job_description"])
        resume_store[resume_id]["skills_analysis"] = skills_data

        return jsonify({
            "resume_id": resume_id,
            "skills_analysis": skills_data
        }), 200

    except Exception as e:
        logging.exception("❌ Error in analyze_skills_route")
        return jsonify({"error": "Skill analysis failed"}), 500




# ✅ Generate summary page (page 1)
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit

def create_summary_pdf(score, feedback, optimization_note, company_name):
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=A4)
    width, height = A4

    # Header
    c.setFont("Helvetica-Bold", 14)
    c.drawString(100, height - 40, "Resume Evaluation Summary")

    c.setFont("Helvetica", 12)
    c.drawString(100, height - 70, f"Company: {company_name or 'N/A'}")
    c.drawString(100, height - 90, f"Score: {score}/10")

    # Setup feedback text
    y_position = height - 120
    max_width = width - 140
    c.setFont("Helvetica", 11)

    wrapped_lines = []
    for line in feedback.splitlines():
        # Use simpleSplit to wrap each line to fit the page
        wrapped = simpleSplit(line, "Helvetica", 11, max_width)
        wrapped_lines.extend(wrapped)

    if optimization_note:
        wrapped_lines.append("")
        wrapped_lines.append("Note: " + optimization_note)

    # Draw wrapped lines safely
    for line in wrapped_lines:
        if y_position < 50:
            c.showPage()
            y_position = height - 50
            c.setFont("Helvetica", 11)
        c.drawString(100, y_position, line)
        y_position -= 15  # line spacing

    c.showPage()
    c.save()
    packet.seek(0)
    return packet


# ✅ Compile LaTeX to PDF
def compile_latex_to_pdf(latex_code):
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_path = os.path.join(tmpdir, "resume.tex")
            with open(tex_path, "w", encoding="utf-8") as f:
                f.write(latex_code)

            result = subprocess.run(
                ["xelatex", "-interaction=nonstopmode", tex_path],
                cwd=tmpdir, capture_output=True, text=True
            )

            pdf_path = os.path.join(tmpdir, "resume.pdf")
            if not os.path.exists(pdf_path):
                # ✅ Log error output for debugging
                logging.error("❌ LaTeX Compilation Error:\n" + result.stdout + "\n" + result.stderr)
                return None

            with open(pdf_path, "rb") as f:
                return io.BytesIO(f.read())

    except Exception as e:
        logging.error(f"❌ LaTeX PDF generation failed: {e}")
        return None

# ✅ Serve combined final PDF (auto download)
@app.route("/download_pdf/<resume_id>", methods=["GET"])
@login_required
def download_pdf(resume_id):
    try:
        # ✅ Validate resume existence
        if resume_id not in resume_store:
            return "Invalid resume ID", 404

        data = resume_store[resume_id]

        # ✅ Create summary PDF (first page)
        summary_pdf = create_summary_pdf(
            score=data.get("score", 0),
            feedback=data.get("feedback", "No feedback available."),
            optimization_note=data.get("optimization_message", ""),
            company_name=data.get("company_name", "")
        )

        # ✅ Create resume PDF (second page onward)
        latex_code = data.get("latex_code", "")
        resume_pdf = compile_latex_to_pdf(latex_code)
        if not resume_pdf:
            return "Failed to compile resume LaTeX.", 500

        # ✅ Merge summary + resume into one PDF
        merger = PdfMerger()
        merger.append(summary_pdf)
        merger.append(resume_pdf)

        final_pdf = io.BytesIO()
        merger.write(final_pdf)
        merger.close()
        final_pdf.seek(0)

        # ✅ Prepare filename
        filename = f"Resume_{resume_id[:8]}.pdf"

        # ✅ Return downloadable response
        return Response(final_pdf, mimetype='application/pdf', headers={
            "Content-Disposition": f"attachment;filename={filename}"
        })

    except Exception as e:
        logging.exception("❌ Error generating final PDF")
        return "Error generating final PDF.", 500

# ✅ Generate new LaTeX for skills section from analyzed data
def generate_skills_latex(skills_data):
    try:
        section_lines = []

        for category, skills in skills_data.get("current_skills_by_category", {}).items():
            if skills:
                section_lines.append(f"\\textbf{{{category}}}{{: {', '.join(skills)}}} \\\\")

        for category, skills in skills_data.get("recommended_skills_by_category", {}).items():
            if skills:
                section_lines.append(f"\\textbf{{{category}}}{{: {', '.join(skills)}}} \\\\")

        certs = skills_data.get("current_certifications", []) + skills_data.get("recommended_certifications", [])
        certs_text = ", ".join(certs) if certs else "No current certifications"

        full_block = f"""%-----------SKILLS and CERTIFICATIONS-----------
\\section{{Professional Skills \\& Certifications}}
 \\begin{{itemize}}[leftmargin=0.15in, label={{}}]
    \\small{{\\item{{
{chr(10).join(section_lines)}
     \\textbf{{Certifications}}{{: {certs_text}}}
    }}
 \\end{{itemize}}"""

        return full_block

    except Exception as e:
        logging.error(f"❌ Error building LaTeX skills section: {e}")
        return ""

# ✅ Route to regenerate + update LaTeX resume with new skills section
@app.route("/regenerate_skills_latex", methods=["POST"])
@login_required
def regenerate_skills_latex():
    try:
        resume_id = request.form.get("resume_id")
        if not resume_id or resume_id not in resume_store:
            return jsonify({"error": "Invalid resume ID"}), 400

        entry = resume_store[resume_id]
        skills_data = entry.get("skills_analysis", {})

        if not skills_data:
            return jsonify({"error": "No skills analysis found"}), 400

        new_skills_section = generate_skills_latex(skills_data)

        # Find and replace old skills section
        old_latex = entry["latex_code"]
        old_skills_section = skills_data.get("latex_skills_section", "")
        if old_skills_section and old_skills_section in old_latex:
            updated_latex = old_latex.replace(old_skills_section, new_skills_section)
        else:
            updated_latex = old_latex + "\n\n" + new_skills_section  # fallback: just append

        # Update store
        resume_store[resume_id]["latex_code"] = updated_latex
        resume_store[resume_id]["skills_analysis"]["latex_skills_section"] = new_skills_section

        return jsonify({
            "resume_id": resume_id,
            "latex_skills_section": new_skills_section,
            "message": "Skills section updated successfully"
        }), 200

    except Exception as e:
        logging.exception("❌ Error regenerating skills section")
        return jsonify({"error": "Failed to regenerate skills section"}), 500

if __name__ == "__main__":
    print("🚀 Starting Flask App at http://127.0.0.1:5000")
    app.run(debug=True)
