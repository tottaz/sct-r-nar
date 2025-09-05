from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    send_from_directory,
    url_for,
    flash,
    send_file,
    abort,
    jsonify
)
import os
import uuid
import json
from datetime import datetime
from werkzeug.utils import secure_filename
from cryptography.fernet import Fernet

from openai import OpenAI
import ollama

signature_bp = Blueprint("signature", __name__,
                         template_folder="templates",
                         static_folder="static")

CONFIG_FILE = os.path.join(os.getcwd(), "config.json")

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

USE_OPENAI = config.get("use_openai", True)
OPENAI_API_KEY = config.get("openai_api_key")
OLLAMA_BASE_URL = config.get("ollama_base_url", "http://localhost:11434")
FERNET_KEY = config.get("fernet_key")
if not FERNET_KEY:
    raise RuntimeError("Fernet key missing from config!")

# Generate a key once and store it securely (env var or config file)
cipher = Fernet(FERNET_KEY)


UPLOADS_DIR = os.path.join(os.getcwd(), "data", "uploads")
SIGNATURES_DIR = os.path.join(os.getcwd(), "data", "signatures")

# Make sure directories exist
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(SIGNATURES_DIR, exist_ok=True)


def metadata_path_for(file_id: str) -> str:
    return os.path.join(UPLOADS_DIR, f"{file_id}.json")


def write_metadata(meta: dict):
    """Write metadata for a single file (meta must contain 'id')."""
    path = metadata_path_for(meta["id"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def read_metadata(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _create_meta_for_existing_file(filename: str) -> dict:
    """Create metadata for a raw file found in uploads (migration helper)."""
    file_id = str(uuid.uuid4())
    stored_filename = filename
    file_path = os.path.join(UPLOADS_DIR, stored_filename)
    meta = {
        "id": file_id,
        "original_filename": filename,
        "stored_filename": stored_filename,
        "filename": filename,
        "file_path": file_path,
        "type": "pdf" if filename.lower().endswith(".pdf") else "signature",
        "status": "uploaded",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    # save metadata file next to it
    write_metadata(meta)
    return meta


def load_docs() -> list:
    """
    Return a list of metadata dicts for all documents.
    Priority: read per-file JSON metadata files. If no metadata exists
    but files are present, create metadata for them (migration).
    Result is sorted by timestamp desc (newest first).
    """
    docs = []
    # find any metadata JSON files in uploads dir
    for name in os.listdir(UPLOADS_DIR):
        if name.endswith(".json"):
            try:
                meta = read_metadata(os.path.join(UPLOADS_DIR, name))
                docs.append(meta)
            except Exception:
                # skip malformed metadata files
                continue

    # If we found no metadata but there are files, create metadata for each
    if not docs:
        for name in os.listdir(UPLOADS_DIR):
            if name.lower().endswith((".pdf", ".png", ".jpg", ".jpeg")):
                docs.append(_create_meta_for_existing_file(name))

    # normalize & sort (if timestamp missing, put at end)
    def _ts(d):
        t = d.get("timestamp")
        if not t:
            return ""
        return t
    docs.sort(key=_ts, reverse=True)
    return docs


def save_metadata_for_doc_id(doc_id: str, updates: dict):
    """Load metadata for doc_id, update with `updates` dict and save."""
    path = metadata_path_for(doc_id)
    if not os.path.exists(path):
        raise FileNotFoundError("Metadata not found for id: " + doc_id)
    meta = read_metadata(path)
    meta.update(updates)
    write_metadata(meta)
    return meta


def analyze_pdfdoc(body: str, system_prompt: str) -> str:
    if USE_OPENAI:
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": body}
            ]
        )
        return response.choices[0].message.content.strip()
    else:
        # Ollama
        try:
            ollama.list()
        except Exception:
            raise Exception("Ollama server is not running. Start it with: ollama serve")
        try:
            response = ollama.chat(
                model="llama3.2:latest",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": body}
                ]
            )
            return response["message"]["content"].strip()
        except Exception as e:
            raise Exception(f"Ollama chat error: {e}")


# Default route → dashboard
@signature_bp.route("/")
def index():
    docs = load_docs()
    return render_template("docdashboard.html", docs=docs)


# View PDF
@signature_bp.route("/docupload", methods=["GET", "POST"])
def docupload():
    if request.method == "POST":
        pdf_file = request.files.get("pdf_file")

        file_id = str(uuid.uuid4())

        if pdf_file and pdf_file.filename:
            original_filename = secure_filename(pdf_file.filename)
            # store with file_id prefix to avoid collisions
            stored_filename = f"{file_id}_{original_filename}"
            file_path = os.path.join(UPLOADS_DIR, stored_filename)
            pdf_file.save(file_path)

            meta = {
                "id": file_id,
                "original_filename": original_filename,
                "stored_filename": stored_filename,
                "filename": original_filename,
                "file_path": file_path,
                "type": "pdf",
                "status": "uploaded",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            write_metadata(meta)

            flash("PDF uploaded successfully.", "success")
            return redirect(url_for("signature.docupload"))

        else:
            flash("Please provide a PDF file URL.", "danger")
            return redirect(url_for("signature.docupload"))

    # GET -> show current docs
    docs = load_docs()
    return render_template("docdashboard.html", docs=docs)


# Serve uploaded files
@signature_bp.route('/docuploaded_file/<path:filename>')
def docuploaded_file(filename):
    uploads_dir = os.path.join(os.getcwd(), "data", "uploads")

    # Loop through all .json meta files
    for f in os.listdir(uploads_dir):
        if f.endswith(".json"):
            meta_path = os.path.join(uploads_dir, f)
            with open(meta_path) as meta_file:
                meta = json.load(meta_file)

            if meta.get("original_filename") == filename:
                stored_filename = meta.get("stored_filename")
                if stored_filename and os.path.exists(os.path.join(uploads_dir, stored_filename)):
                    return send_from_directory(uploads_dir, stored_filename)

    abort(404, description=f"No stored file found for {filename}")


# Sign document (draw signature)
@signature_bp.route("/docsign/<doc_id>")
def docsign(doc_id):
    meta_path = os.path.join(UPLOADS_DIR, f"{doc_id}.json")
    if not os.path.exists(meta_path):
        flash("Document metadata not found.", "danger")
        return redirect(url_for("signature.index"))

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    file_path = meta.get("file_path")
    if not file_path or not os.path.exists(file_path):
        flash("Document file not found on disk.", "danger")
        return redirect(url_for("signature.index"))

    # Provide a URL for the iframe to display the PDF
    meta["view_url"] = url_for("signature.serve_doc", doc_id=doc_id)

    return render_template("docsignature.html", document=meta)


# View PDF
@signature_bp.route("/docview/<doc_id>")
def docview(doc_id):
    meta_path = os.path.join(UPLOADS_DIR, f"{doc_id}.json")
    if not os.path.exists(meta_path):
        flash("Document metadata not found.", "danger")
        return redirect(url_for("signature.index"))

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    if meta.get("type") == "pdf":
        meta["view_url"] = url_for("signature.serve_doc", doc_id=doc_id)
    elif meta.get("type") == "google_doc":
        meta["view_url"] = meta.get("url")
    else:
        meta["view_url"] = None

    return render_template("docview.html", doc=meta)


@signature_bp.route("/docdelete/<doc_id>", methods=["POST"])
def docdelete(doc_id):
    meta_path = os.path.join(UPLOADS_DIR, f"{doc_id}.json")
    if not os.path.exists(meta_path):
        flash("Document metadata not found.", "danger")
        return redirect(url_for("signature.index"))

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    file_path = meta.get("file_path")
    if file_path and os.path.exists(file_path):
        os.remove(file_path)

    # Delete the metadata JSON
    os.remove(meta_path)
    flash(f"Document '{meta.get('filename', doc_id)}' deleted successfully.", "success")
    return redirect(url_for("signature.index"))


@signature_bp.route("/download/<doc_id>")
def download_doc(doc_id):
    meta_path = os.path.join(UPLOADS_DIR, f"{doc_id}.json")
    if not os.path.exists(meta_path):
        flash("Document metadata not found.", "danger")
        return redirect(url_for("signature.index"))

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    file_path = meta.get("file_path")
    if not file_path or not os.path.exists(file_path):
        flash("Document file not found on disk.", "danger")
        return redirect(url_for("signature.index"))

    return send_file(file_path, as_attachment=True, download_name=meta.get("filename", doc_id))


# Analyse document (AI stub)
@signature_bp.route("/analyze_doc/<doc_id>")
def analyze_doc(doc_id):
    meta_path = os.path.join(UPLOADS_DIR, f"{doc_id}.json")
    if not os.path.exists(meta_path):
        return {"success": False, "analysis": "Document metadata not found."}

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    file_path = meta.get("file_path")
    if not file_path or not os.path.exists(file_path):
        return {"success": False, "analysis": "Document file not found."}

    # Extract text from PDF
    import pdfplumber
    text = ""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() + "\n"

    pdf_prompt = (
        "You are an AI assistant. Analyze the following resume. "
        "Extract the candidate's name, contact info, skills, education, and work experience. "
        "Provide a brief summary highlighting strengths and weaknesses, and suggest improvements. "
        "Keep the analysis concise and easy to read."
    )

    analysis = analyze_pdfdoc(text, pdf_prompt)

    # Save analysis to a .txt file
    analysis_path = os.path.join(UPLOADS_DIR, f"analysis_{doc_id}.txt")
    with open(analysis_path, "w", encoding="utf-8") as f:
        f.write(analysis)

    # Optionally, store the path in metadata
    meta['analysis_path'] = analysis_path
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return {"success": True, "analysis": analysis, "file_saved": analysis_path}


@signature_bp.route("/serve/<doc_id>")
def serve_doc(doc_id):
    meta_path = os.path.join(UPLOADS_DIR, f"{doc_id}.json")
    if not os.path.exists(meta_path):
        flash("Document metadata not found.", "danger")
        return redirect(url_for("signature.index"))

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    file_path = meta.get("file_path")
    if not file_path or not os.path.exists(file_path):
        flash("Document file not found on disk.", "danger")
        return redirect(url_for("signature.index"))

    # Serve PDF inline
    return send_file(file_path, mimetype='application/pdf')


@signature_bp.route("/download_signed/<doc_id>")
def download_signed(doc_id):
    # load your meta JSON
    meta_path = os.path.join(UPLOADS_DIR, f"{doc_id}.json")
    if not os.path.exists(meta_path):
        flash("Document not found", "danger")
        return redirect(url_for("signature.index"))

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    signed_path = meta.get("stored_filename")
    if not signed_path or not os.path.exists(os.path.join(UPLOADS_DIR, signed_path)):
        flash("Signed file not found", "danger")
        return redirect(url_for("signature.index"))

    return send_file(
        os.path.join(UPLOADS_DIR, signed_path),
        as_attachment=True,
        download_name=meta.get("filename")
    )


@signature_bp.route("/analyze_resume/<doc_id>")
def analyze_resume(doc_id):
    meta_path = os.path.join(UPLOADS_DIR, f"{doc_id}.json")
    if not os.path.exists(meta_path):
        return {"success": False, "analysis": "Resume not found."}

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    file_path = meta.get("file_path")
    if not file_path or not os.path.exists(file_path):
        return {"success": False, "analysis": "Resume file not found."}

    import pdfplumber
    text = ""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"

    resume_prompt = (
        "You are an expert HR recruiter. Analyze the following resume. "
        "Provide strengths, weaknesses, suggested improvements, "
        "and possible job roles that fit this candidate."
    )

    analysis = analyze_pdfdoc(text, resume_prompt)
    return {"success": True, "analysis": analysis}


@signature_bp.route("/generate_jobdesc", methods=["POST"])
def generate_jobdesc():
    role = request.form.get("role")
    skills = request.form.get("skills")
    experience = request.form.get("experience")

    user_prompt = f"""
    Create a professional job description for the role: {role}.
    Required skills: {skills}.
    Required experience: {experience}.
    """

    jobdesc_prompt = (
        "You are an expert HR content creator. "
        "Create a professional job description for the following role. "
        "Include responsibilities, required skills, and experience. "
        "Format it clearly and concisely."
    )
    jd_text = analyze_pdfdoc(user_prompt, jobdesc_prompt)
    return jsonify(success=True, result=jd_text)


@signature_bp.route("/generate_resume", methods=["POST"])
def generate_resume():
    name = request.form.get("name")
    contact = request.form.get("contact")
    education = request.form.get("education")
    experience = request.form.get("experience")
    skills = request.form.get("skills")

    user_prompt = f"""
    Create a professional resume for:
    Name: {name}
    Contact: {contact}
    Education: {education}
    Experience: {experience}
    Skills: {skills}
    Format it in a clean ATS-friendly style.
    """

    resume_prompt = (
        "You are an expert HR recruiter and resume writer. "
        "Create a professional, ATS-friendly resume from the following information: "
        "Include sections for contact info, education, experience, skills, and achievements. "
        "Format it clearly and concisely."
    )

    resume_text = analyze_pdfdoc(user_prompt, resume_prompt)

    # Optionally save as PDF (using reportlab or similar)
    return jsonify(success=True, result=resume_text)
