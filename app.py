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
    """Extract form questions from job posting and provide answers based on resume"""
    client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
    
    prompt = f"""You are helping fill out job application forms that ask specific questions.

Here is the candidate's resume:
{resume_text}

Here is the job posting (may contain application questions):
{job_description}

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
Willing to relocate: [Yes/No based on resume]
Authorized to work in US: [Yes - confirm with candidate]
Expected salary: [Research market rate for this role]
Available start date: [2 weeks notice / Immediate]

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
    """Generate ATS-friendly PDF using ReportLab matching LaTeX template style"""
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
    
    # Custom styles matching LaTeX template exactly
    name_style = ParagraphStyle(
        'Name',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.black,
        spaceAfter=2,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        leading=28
    )
    
    contact_style = ParagraphStyle(
        'Contact',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.black,
        spaceAfter=12,
        alignment=TA_CENTER,
        fontName='Helvetica'
    )
    
    section_heading_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=11,
        textColor=colors.black,
        spaceAfter=4,
        spaceBefore=8,
        alignment=TA_LEFT,
        fontName='Helvetica-Bold',
        textTransform='uppercase'
    )
    
    # Job title style (bold, left-right justified with dates)
    job_title_style = ParagraphStyle(
        'JobTitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.black,
        spaceAfter=1,
        alignment=TA_LEFT,
        fontName='Helvetica-Bold'
    )
    
    # Company/institution style (italic)
    company_style = ParagraphStyle(
        'Company',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.black,
        spaceAfter=4,
        alignment=TA_LEFT,
        fontName='Helvetica-Oblique'
    )
    
    bullet_style = ParagraphStyle(
        'Bullet',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.black,
        spaceAfter=2,
        alignment=TA_LEFT,
        fontName='Helvetica',
        leftIndent=0,
        bulletIndent=6
    )
    
    # Parse resume
    lines = adapted_resume_text.strip().split('\n')
    
    name = ""
    contact = ""
    sections = {'education': [], 'experience': [], 'projects': [], 'skills': []}
    current_section = None
    current_item = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if line.startswith('CONTACT INFO:'):
            current_section = 'contact'
            continue
        elif line.startswith('EDUCATION:'):
            if current_item and current_section == 'contact':
                contact = ' | '.join(current_item)
                current_item = []
            current_section = 'education'
            continue
        elif line.startswith('EXPERIENCE:'):
            if current_item:
                sections[current_section].append('\n'.join(current_item))
                current_item = []
            current_section = 'experience'
            continue
        elif line.startswith('PROJECTS:'):
            if current_item:
                sections[current_section].append('\n'.join(current_item))
                current_item = []
            current_section = 'projects'
            continue
        elif line.startswith('TECHNICAL SKILLS:'):
            if current_item:
                sections[current_section].append('\n'.join(current_item))
                current_item = []
            current_section = 'skills'
            continue
        
        if current_section == 'contact':
            if not name:
                name = line
            else:
                current_item.append(line)
        else:
            current_item.append(line)
    
    # Handle last section
    if current_item and current_section:
        sections[current_section].append('\n'.join(current_item))
    
    # Build document
    story = []
    
    # Header - Name and Contact
    story.append(Paragraph(name, name_style))
    story.append(Paragraph(contact, contact_style))
    
    # Education Section (FIRST)
    if sections['education']:
        story.append(Spacer(1, 0.1*inch))
        story.append(Paragraph('EDUCATION', section_heading_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.black, spaceAfter=4))
        
        for item in sections['education']:
            item_lines = [l.strip() for l in item.split('\n') if l.strip()]
            if len(item_lines) >= 2:
                # Line 1: School - Location
                # Line 2: Degree - Dates
                school_location = item_lines[0]
                degree_dates = item_lines[1]
                
                # Create table for left-right alignment
                parts1 = school_location.split(' - ')
                parts2 = degree_dates.split(' - ')
                
                school = parts1[0] if parts1 else ""
                location = parts1[1] if len(parts1) > 1 else ""
                degree = parts2[0] if parts2 else ""
                dates = ' - '.join(parts2[1:]) if len(parts2) > 1 else ""
                
                # School and Location row
                data = [[Paragraph(f'<b>{school}</b>', bullet_style), Paragraph(location, bullet_style)]]
                t = Table(data, colWidths=[5*inch, 2*inch])
                t.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                    ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ]))
                story.append(t)
                
                # Degree and Dates row
                data = [[Paragraph(f'<i>{degree}</i>', bullet_style), Paragraph(f'<i>{dates}</i>', bullet_style)]]
                t = Table(data, colWidths=[5*inch, 2*inch])
                t.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                    ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ]))
                story.append(t)
                story.append(Spacer(1, 0.05*inch))
    
    # Experience Section (SECOND)
    if sections['experience']:
        story.append(Spacer(1, 0.1*inch))
        story.append(Paragraph('EXPERIENCE', section_heading_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.black, spaceAfter=4))
        
        for item in sections['experience']:
            item_lines = [l.strip() for l in item.split('\n') if l.strip()]
            if len(item_lines) >= 2:
                # Line 1: Job Title - Dates
                # Line 2: Company - Location
                title_dates = item_lines[0]
                company_location = item_lines[1]
                
                parts1 = title_dates.split(' - ')
                title = parts1[0] if parts1 else ""
                dates = ' - '.join(parts1[1:]) if len(parts1) > 1 else ""
                
                parts2 = company_location.split(' - ')
                company = parts2[0] if parts2 else ""
                location = parts2[1] if len(parts2) > 1 else ""
                
                # Title and Dates row
                data = [[Paragraph(f'<b>{title}</b>', job_title_style), Paragraph(f'<b>{dates}</b>', job_title_style)]]
                t = Table(data, colWidths=[5*inch, 2*inch])
                t.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                    ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ]))
                story.append(t)
                
                # Company and Location row
                data = [[Paragraph(f'<i>{company}</i>', company_style), Paragraph(f'<i>{location}</i>', company_style)]]
                t = Table(data, colWidths=[5*inch, 2*inch])
                t.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                    ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ]))
                story.append(t)
                
                # Bullet points
                for line in item_lines[2:]:
                    if line.startswith('•') or line.startswith('*'):
                        bullet_text = line[1:].strip()
                        story.append(Paragraph(f'• {bullet_text}', bullet_style))
                
                story.append(Spacer(1, 0.08*inch))
    
    # Projects Section (THIRD)
    if sections['projects']:
        story.append(Spacer(1, 0.1*inch))
        story.append(Paragraph('PROJECTS', section_heading_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.black, spaceAfter=4))
        
        for item in sections['projects']:
            item_lines = [l.strip() for l in item.split('\n') if l.strip()]
            if item_lines:
                # First line is project title/tech
                story.append(Paragraph(f'<b>{item_lines[0]}</b>', job_title_style))
                
                # Bullet points
                for line in item_lines[1:]:
                    if line.startswith('•') or line.startswith('*'):
                        bullet_text = line[1:].strip()
                        story.append(Paragraph(f'• {bullet_text}', bullet_style))
                
                story.append(Spacer(1, 0.08*inch))
    
    # Skills Section (FOURTH/LAST)
    if sections['skills']:
        story.append(Spacer(1, 0.1*inch))
        story.append(Paragraph('TECHNICAL SKILLS', section_heading_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.black, spaceAfter=4))
        
        for item in sections['skills']:
            for line in item.split('\n'):
                line = line.strip()
                if line:
                    story.append(Paragraph(line, bullet_style))
    
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
