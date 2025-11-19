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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.enums import TA_LEFT
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
1. Keep the same basic structure (Education, Experience, Projects, Skills)
2. Emphasize experience and skills relevant to the job description
3. Use keywords from the job description where appropriate
4. Keep bullet points concise and impact-focused
5. Ensure it fits on ONE page worth of content
6. Make it ATS-friendly (simple formatting, no tables, clear sections)
7. Keep the person's actual experience - don't fabricate anything

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
    
    prompt = f"""You are writing a cover letter for a job application.

Here is the candidate's resume:
{resume_text}

Here is the job description:
{job_description}

Write a cover letter that:
1. Sounds human and authentic, not generic or robotic
2. Is 3 paragraphs maximum
3. Highlights relevant experience from the resume
4. Shows genuine interest in the role
5. Doesn't use clichés like "I am writing to express my interest"
6. Gets straight to the point

Format it as a proper cover letter with:
- Date (use [DATE])
- Hiring Manager section (use [HIRING MANAGER NAME] and [COMPANY NAME])
- Body paragraphs
- Professional closing

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
    """Generate plaintext formatted for copy-pasting into job application forms"""
    client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
    
    prompt = f"""You are helping format resume content for those annoying job application forms that make you manually re-enter everything.

Here is the resume:
{resume_text}

Here is the job description:
{job_description}

Create a plaintext version optimized for copy-pasting into web forms. Format it like this:

WORK EXPERIENCE:

[Job Title] at [Company Name]
[Start Date] - [End Date]
• [Achievement/responsibility]
• [Achievement/responsibility]
• [Achievement/responsibility]

[Next Job Title] at [Company Name]
[Start Date] - [End Date]
• [Achievement/responsibility]
• [Achievement/responsibility]

EDUCATION:

[Degree] in [Major]
[University Name]
[Graduation Date]
GPA: [if mentioned]

SKILLS:

[Comma-separated list of relevant technical skills from the job description]

PROJECTS (if applicable):

[Project Name]
[Brief description]
Technologies: [list]

Keep it concise and relevant to the job. Focus on what matters for this specific role.
Return ONLY the formatted text, no explanations."""

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
    """Generate ATS-friendly PDF from adapted resume text"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75*inch,
        leftMargin=0.75*inch,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch
    )
    
    # Styles
    styles = getSampleStyleSheet()
    
    # Custom styles for ATS-friendly resume
    name_style = ParagraphStyle(
        'Name',
        parent=styles['Heading1'],
        fontSize=18,
        textColor='black',
        spaceAfter=6,
        alignment=TA_LEFT
    )
    
    contact_style = ParagraphStyle(
        'Contact',
        parent=styles['Normal'],
        fontSize=10,
        textColor='black',
        spaceAfter=12,
        alignment=TA_LEFT
    )
    
    heading_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=12,
        textColor='black',
        spaceAfter=6,
        spaceBefore=8,
        alignment=TA_LEFT,
        bold=True
    )
    
    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontSize=10,
        textColor='black',
        spaceAfter=4,
        alignment=TA_LEFT
    )
    
    # Parse the adapted resume text
    story = []
    lines = adapted_resume_text.strip().split('\n')
    
    current_section = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check for section headers
        if line.startswith('CONTACT INFO:'):
            current_section = 'contact'
            continue
        elif line.startswith('EDUCATION:'):
            story.append(Paragraph('EDUCATION', heading_style))
            current_section = 'education'
            continue
        elif line.startswith('EXPERIENCE:'):
            story.append(Paragraph('EXPERIENCE', heading_style))
            current_section = 'experience'
            continue
        elif line.startswith('PROJECTS:'):
            story.append(Paragraph('PROJECTS', heading_style))
            current_section = 'projects'
            continue
        elif line.startswith('TECHNICAL SKILLS:'):
            story.append(Paragraph('TECHNICAL SKILLS', heading_style))
            current_section = 'skills'
            continue
        
        # Handle content based on section
        if current_section == 'contact':
            if not story:  # First line is the name
                story.append(Paragraph(line, name_style))
            else:
                story.append(Paragraph(line, contact_style))
        else:
            # Regular content
            story.append(Paragraph(line, body_style))
    
    # Build PDF
    doc.build(story)
    
    # Write to file
    pdf_data = buffer.getvalue()
    buffer.close()
    
    with open(output_path, 'wb') as f:
        f.write(pdf_data)
    
    return output_path

def create_cover_letter_pdf(cover_letter_text, output_path):
    """Generate PDF from cover letter text"""
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
        textColor='black',
        spaceAfter=12,
        alignment=TA_LEFT
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

@app.route('/process', methods=['POST'])
@auth.login_required
def process_resume():
    job_description = request.form.get('job_description', '').strip()
    
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
        
        # Generate form text for manual entry
        form_text = generate_form_text(resume_text, job_description)
        
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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
