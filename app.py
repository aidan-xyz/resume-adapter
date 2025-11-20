import os
from flask import Flask, render_template, request, jsonify, send_file, session
from flask_httpauth import HTTPBasicAuth
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import anthropic
import pypdf
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib import colors
import io
import secrets

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
auth = HTTPBasicAuth()

app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'outputs'
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB max file size
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}

# Create directories if they don't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

# Basic auth setup
users = {}
if os.environ.get('AUTH_USERNAME') and os.environ.get('AUTH_PASSWORD'):
    users[os.environ.get('AUTH_USERNAME')] = generate_password_hash(os.environ.get('AUTH_PASSWORD'))

@auth.verify_password
def verify_password(username, password):
    if not users:  # No auth configured
        return True
    if username in users and check_password_hash(users.get(username), password):
        return username
    return None

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def extract_text_from_pdf(pdf_path):
    """Extract text from PDF using pypdf"""
    text = ""
    with open(pdf_path, 'rb') as file:
        pdf_reader = pypdf.PdfReader(file)
        for page in pdf_reader.pages:
            text += page.extract_text()
    return text

def adapt_resume(resume_text, job_description):
    """Use Claude to adapt resume content for job description"""
    client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
    
    prompt = f"""You are helping adapt a resume for a specific job. 

Here is the original resume content:
{resume_text}

Here is the job description:
{job_description}

Please reformat this resume to be optimized for this job. Follow these rules:
1. Keep the same basic structure with sections in this EXACT order: Education, Experience, Projects, Skills
2. Emphasize experience and skills relevant to the job description
3. Use keywords from the job description where appropriate
4. Keep bullet points concise and impact-focused
5. CRITICAL: Must fit on ONE page - limit to 3-4 bullets per job, 2-3 bullets per project. Be concise.
6. Make it ATS-friendly (simple formatting, no tables, clear sections)
7. Keep the person's actual experience - don't fabricate anything
8. NEVER use em dashes (—) - use regular hyphens (-) instead

Return ONLY the adapted resume content in this exact format:

CONTACT INFO:
[Name]
[Phone] | [Email] | [LinkedIn] | [GitHub]

EDUCATION:
[School Name] - [Location]
[Degree and Major] - [Dates]

EXPERIENCE:
[Job Title] - [Dates]
[Company] - [Location]
• [Bullet point]
• [Bullet point]

PROJECTS:
[Project Name] | [Technologies] - [Dates]
• [Bullet point]

TECHNICAL SKILLS:
Languages: [list]
Frameworks: [list]
Tools: [list]

Do not include any explanations or commentary, just the formatted resume."""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3000,
        messages=[{
            "role": "user",
            "content": prompt
        }]
    )
    
    return message.content[0].text

def generate_cover_letter(resume_text, job_description):
    """Use Claude to generate a human-sounding cover letter"""
    client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
    
    # Check for graduation date vs expected start date
    graduation_note = ""
    import re
    from datetime import datetime
    
    # Look for graduation date in resume
    grad_match = re.search(r'Expected (May|June|July|August|December) (\d{4})', resume_text)
    if grad_match:
        month_str = grad_match.group(1)
        year = int(grad_match.group(2))
        
        # Convert month to number
        month_map = {'May': 5, 'June': 6, 'July': 7, 'August': 8, 'December': 12}
        grad_month = month_map.get(month_str, 5)
        
        try:
            grad_date = datetime(year, grad_month, 1)
            current_date = datetime.now()
            
            # If graduation is in the future
            if grad_date > current_date:
                graduation_note = f"\n\nIMPORTANT: The candidate's expected graduation date is {month_str} {year}. If the job posting has an immediate start date or starts before graduation, YOU MUST acknowledge this timing in the cover letter. Add a brief, professional statement that they are graduating in {month_str} {year} and are eager to discuss how the timeline could work, or if there's flexibility for a start date after graduation. Keep it positive and solution-oriented - don't make it sound like a dealbreaker."
        except:
            pass
    
    prompt = f"""You are writing a cover letter for a job application.

Here is the candidate's resume:
{resume_text}

Here is the job description:
{job_description}{graduation_note}

Write a cover letter that:
1. Sounds human and authentic, not generic or robotic
2. Is 3 paragraphs maximum
3. Highlights relevant experience from the resume
4. Shows genuine interest in the role
5. Doesn't use clichés like "I am writing to express my interest"
6. Gets straight to the point
7. If there's a graduation timing issue, address it tactfully in the closing paragraph
8. NEVER use em dashes (—) - use regular hyphens (-) instead

Format it as a proper cover letter with:
- Start with "Dear Hiring Manager," (no date, no placeholder names)
- Body paragraphs
- Professional closing with candidate's name

Return ONLY the cover letter text, no explanations."""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": prompt
        }]
    )
    
    return message.content[0].text

def generate_form_text(resume_text, job_description):
    """Extract form questions from job posting and provide answers based on resume"""
    client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
    
    # Check for graduation date
    graduation_note = ""
    import re
    from datetime import datetime
    
    grad_match = re.search(r'Expected (May|June|July|August|December) (\d{4})', resume_text)
    if grad_match:
        month_str = grad_match.group(1)
        year = int(grad_match.group(2))
        
        month_map = {'May': 5, 'June': 6, 'July': 7, 'August': 8, 'December': 12}
        grad_month = month_map.get(month_str, 5)
        
        try:
            grad_date = datetime(year, grad_month, 1)
            current_date = datetime.now()
            
            if grad_date > current_date:
                graduation_note = f"\n\nNOTE: Candidate graduates {month_str} {year}. If asked about start date availability, mention graduating {month_str} {year} and available to start shortly after, or indicate willingness to discuss flexible arrangements if needed sooner."
        except:
            pass
    
    prompt = f"""You are helping fill out job application forms that ask specific questions.

Here is the candidate's resume:
{resume_text}

Here is the job posting (may contain application questions):
{job_description}{graduation_note}

Your task:
1. Extract any application questions from the job posting (like "Why do you want to work here?", "How many years of X experience?", "Are you authorized to work in...", etc.)
2. For each question, provide a ready-to-paste answer based on the resume
3. If no specific questions are found, provide common form fields instead

Format your response EXACTLY like this:

=== APPLICATION FORM ANSWERS ===

QUESTION: [Extracted question or common field name]
ANSWER: [Your response based on resume]

QUESTION: [Next question]
ANSWER: [Your response]

=== COMMON FIELDS ===

Years of relevant experience: [X years]
Highest education level: [Degree]
Expected graduation date: [If applicable - {month_str} {year} or N/A]
Willing to relocate: [Yes/No based on resume]
Authorized to work in US: [Yes - confirm with candidate]
Expected salary: [Research market rate for this role]
Available start date: [If graduating soon, mention graduation date + availability]

Key technical skills (comma-separated): [relevant skills from resume]

Be concise and professional. Keep answers to 2-3 sentences max unless more detail is needed."""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": prompt
        }]
    )
    
    return message.content[0].text

def create_resume_pdf(adapted_resume_text, output_path):
    """Generate simple text-based PDF optimized for ATS - ONE PAGE ONLY"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.5*inch,
        leftMargin=0.5*inch,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch
    )
    
    styles = getSampleStyleSheet()
    
    # Compact text styles to fit one page
    name_style = ParagraphStyle(
        'Name',
        parent=styles['Normal'],
        fontSize=14,
        spaceAfter=4,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    contact_style = ParagraphStyle(
        'Contact',
        parent=styles['Normal'],
        fontSize=9,
        spaceAfter=8,
        alignment=TA_CENTER,
        fontName='Helvetica'
    )
    
    section_style = ParagraphStyle(
        'Section',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=3,
        spaceBefore=8,
        fontName='Helvetica-Bold'
    )
    
    text_style = ParagraphStyle(
        'Text',
        parent=styles['Normal'],
        fontSize=9,
        spaceAfter=2,
        fontName='Helvetica',
        leading=11
    )
    
    # Parse resume - just extract all text by section
    lines = adapted_resume_text.strip().split('\n')
    
    name = ""
    contact_lines = []
    current_section = None
    section_content = {'education': [], 'experience': [], 'projects': [], 'skills': []}
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if line.startswith('CONTACT INFO:'):
            current_section = 'contact'
            continue
        elif line.startswith('EDUCATION:'):
            current_section = 'education'
            continue
        elif line.startswith('EXPERIENCE:'):
            current_section = 'experience'
            continue
        elif line.startswith('PROJECTS:'):
            current_section = 'projects'
            continue
        elif line.startswith('TECHNICAL SKILLS:'):
            current_section = 'skills'
            continue
        
        if current_section == 'contact':
            if not name:
                name = line
            else:
                contact_lines.append(line)
        elif current_section:
            section_content[current_section].append(line)
    
    # Build simple text document - compact spacing for one page
    story = []
    
    # Name
    story.append(Paragraph(name, name_style))
    
    # Contact
    for contact_line in contact_lines:
        story.append(Paragraph(contact_line, contact_style))
    
    story.append(Spacer(1, 0.08*inch))
    
    # Education
    if section_content['education']:
        story.append(Paragraph('EDUCATION', section_style))
        for line in section_content['education']:
            story.append(Paragraph(line, text_style))
    
    # Experience
    if section_content['experience']:
        story.append(Paragraph('EXPERIENCE', section_style))
        for line in section_content['experience']:
            story.append(Paragraph(line, text_style))
    
    # Projects
    if section_content['projects']:
        story.append(Paragraph('PROJECTS', section_style))
        for line in section_content['projects']:
            story.append(Paragraph(line, text_style))
    
    # Skills
    if section_content['skills']:
        story.append(Paragraph('TECHNICAL SKILLS', section_style))
        for line in section_content['skills']:
            story.append(Paragraph(line, text_style))
    
    # Build PDF
    doc.build(story)
    
    # Write to file
    pdf_data = buffer.getvalue()
    buffer.close()
    
    with open(output_path, 'wb') as f:
        f.write(pdf_data)
    
    return output_path

def create_cover_letter_pdf(cover_letter_text, output_path):
    """Generate PDF from cover letter text using ReportLab"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=inch,
        leftMargin=inch,
        topMargin=inch,
        bottomMargin=inch
    )
    
    styles = getSampleStyleSheet()
    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.black,
        spaceAfter=12,
        alignment=TA_LEFT,
        fontName='Helvetica'
    )
    
    story = []
    paragraphs = cover_letter_text.strip().split('\n\n')
    
    for para in paragraphs:
        if para.strip():
            story.append(Paragraph(para.strip(), body_style))
            story.append(Spacer(1, 0.1*inch))
    
    doc.build(story)
    
    pdf_data = buffer.getvalue()
    buffer.close()
    
    with open(output_path, 'wb') as f:
        f.write(pdf_data)
    
    return output_path

@app.route('/')
@auth.login_required
def index():
    return render_template('index.html')

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'pdf_library': 'ReportLab'})

@app.route('/process', methods=['POST'])
@auth.login_required
def process_resume():
    job_description = request.form.get('job_description', '').strip()
    form_questions = request.form.get('form_questions', '').strip()
    
    if not job_description:
        return jsonify({'error': 'Job description is required'}), 400
    
    # Check if we have a resume in the session or a new upload
    resume_text = None
    
    if 'resume' in request.files and request.files['resume'].filename:
        # New resume uploaded
        file = request.files['resume']
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Please upload a PDF'}), 400
        
        try:
            # Save and extract text
            filename = secure_filename(file.filename)
            resume_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(resume_path)
            
            resume_text = extract_text_from_pdf(resume_path)
            
            # Store in session for future use
            session['original_resume_text'] = resume_text
            session['resume_filename'] = filename
            
            # Clean up uploaded file
            os.remove(resume_path)
            
        except Exception as e:
            return jsonify({'error': f'Failed to process resume: {str(e)}'}), 500
    
    elif 'original_resume_text' in session:
        # Use resume from session
        resume_text = session['original_resume_text']
        filename = session.get('resume_filename', 'resume.pdf')
    
    else:
        return jsonify({'error': 'Please upload a resume first'}), 400
    
    try:
        # Adapt resume using Claude
        adapted_resume = adapt_resume(resume_text, job_description)
        
        # Generate cover letter
        cover_letter = generate_cover_letter(resume_text, job_description)
        
        # Generate form text for manual entry (include form_questions if provided)
        combined_questions = job_description
        if form_questions:
            combined_questions = f"{job_description}\n\nADDITIONAL APPLICATION QUESTIONS:\n{form_questions}"
        form_text = generate_form_text(resume_text, combined_questions)
        
        # Create output PDFs
        resume_output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"adapted_{filename}")
        cover_letter_output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"cover_letter_{filename}")
        
        create_resume_pdf(adapted_resume, resume_output_path)
        create_cover_letter_pdf(cover_letter, cover_letter_output_path)
        
        return jsonify({
            'adapted_resume': adapted_resume,
            'cover_letter': cover_letter,
            'form_text': form_text,
            'resume_pdf_url': f'/download/resume/{filename}',
            'cover_letter_pdf_url': f'/download/cover_letter/{filename}',
            'has_resume_cached': True
        })
    
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        app.logger.error(f"Error processing resume: {str(e)}\n{error_details}")
        return jsonify({'error': str(e)}), 500

@app.route('/download/resume/<filename>')
@auth.login_required
def download_resume(filename):
    file_path = os.path.join(app.config['OUTPUT_FOLDER'], f"adapted_{filename}")
    return send_file(file_path, as_attachment=True, download_name=f"adapted_{filename}")

@app.route('/download/cover_letter/<filename>')
@auth.login_required
def download_cover_letter(filename):
    file_path = os.path.join(app.config['OUTPUT_FOLDER'], f"cover_letter_{filename}")
    return send_file(file_path, as_attachment=True, download_name=f"cover_letter_{filename}")

@app.route('/clear_resume', methods=['POST'])
@auth.login_required
def clear_resume():
    """Clear the cached resume from session"""
    session.pop('original_resume_text', None)
    session.pop('resume_filename', None)
    return jsonify({'success': True})

@app.route('/debug/<filename>')
@auth.login_required
def download_debug(filename):
    """Download debug .tex or .log files"""
    file_path = os.path.join(app.config['OUTPUT_FOLDER'], filename)
    if os.path.exists(file_path) and (filename.endswith('.tex') or filename.endswith('.log')):
        return send_file(file_path, as_attachment=True, download_name=filename)
    return jsonify({'error': 'File not found'}), 404

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
