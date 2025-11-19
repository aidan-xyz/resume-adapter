import os
from flask import Flask, render_template, request, jsonify, send_file, session
from flask_httpauth import HTTPBasicAuth
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import anthropic
import pypdf
import io
import secrets
import subprocess
import tempfile
import shutil

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

def escape_latex(text):
    """Escape special LaTeX characters"""
    replacements = {
        '&': r'\&',
        '%': r'\%',
        '$': r'\$',
        '#': r'\#',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
        '~': r'\textasciitilde{}',
        '^': r'\^{}',
        '\\': r'\textbackslash{}',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text

def create_resume_pdf(adapted_resume_text, output_path):
    """Generate ATS-friendly PDF using LaTeX"""
    # Parse the adapted resume text
    lines = adapted_resume_text.strip().split('\n')
    
    # Extract sections
    name = ""
    contact = ""
    education_items = []
    experience_items = []
    projects_items = []
    skills_text = ""
    
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
                contact = ' $|$ '.join(current_item)
                current_item = []
            current_section = 'education'
            continue
        elif line.startswith('EXPERIENCE:'):
            if current_item and current_section == 'education':
                education_items.append('\n'.join(current_item))
                current_item = []
            current_section = 'experience'
            continue
        elif line.startswith('PROJECTS:'):
            if current_item and current_section == 'experience':
                experience_items.append('\n'.join(current_item))
                current_item = []
            current_section = 'projects'
            continue
        elif line.startswith('TECHNICAL SKILLS:'):
            if current_item and current_section == 'projects':
                projects_items.append('\n'.join(current_item))
                current_item = []
            current_section = 'skills'
            continue
        
        # Add content to current section
        if current_section == 'contact':
            if not name:
                name = line
            else:
                current_item.append(line)
        else:
            current_item.append(line)
    
    # Handle last section
    if current_section == 'skills' and current_item:
        skills_text = '\n'.join(current_item)
    elif current_section == 'projects' and current_item:
        projects_items.append('\n'.join(current_item))
    
    # Build LaTeX document
    latex_content = r'''\documentclass[letterpaper,11pt]{article}

\usepackage{latexsym}
\usepackage[empty]{fullpage}
\usepackage{titlesec}
\usepackage{marvosym}
\usepackage[usenames,dvipsnames]{color}
\usepackage{verbatim}
\usepackage{enumitem}
\usepackage[hidelinks]{hyperref}
\usepackage{fancyhdr}
\usepackage[english]{babel}
\usepackage{tabularx}

\pagestyle{fancy}
\fancyhf{}
\fancyfoot{}
\renewcommand{\headrulewidth}{0pt}
\renewcommand{\footrulewidth}{0pt}

\addtolength{\oddsidemargin}{-0.5in}
\addtolength{\evensidemargin}{-0.5in}
\addtolength{\textwidth}{1in}
\addtolength{\topmargin}{-.5in}
\addtolength{\textheight}{1.0in}

\urlstyle{same}
\raggedbottom
\raggedright
\setlength{\tabcolsep}{0in}

\titleformat{\section}{
  \vspace{-4pt}\scshape\raggedright\large
}{}{0em}{}[\color{black}\titlerule \vspace{-5pt}]

\newcommand{\resumeItem}[1]{
  \item\small{
    {#1 \vspace{-2pt}}
  }
}

\newcommand{\resumeSubheading}[4]{
  \vspace{-2pt}\item
    \begin{tabular*}{0.97\textwidth}[t]{l@{\extracolsep{\fill}}r}
      \textbf{#1} & #2 \\
      \textit{\small#3} & \textit{\small #4} \\
    \end{tabular*}\vspace{-7pt}
}

\newcommand{\resumeProjectHeading}[2]{
    \item
    \begin{tabular*}{0.97\textwidth}{l@{\extracolsep{\fill}}r}
      \small#1 & #2 \\
    \end{tabular*}\vspace{-7pt}
}

\renewcommand\labelitemii{$\vcenter{\hbox{\tiny$\bullet$}}$}

\newcommand{\resumeSubHeadingListStart}{\begin{itemize}[leftmargin=0.15in, label={}]}
\newcommand{\resumeSubHeadingListEnd}{\end{itemize}}
\newcommand{\resumeItemListStart}{\begin{itemize}}
\newcommand{\resumeItemListEnd}{\end{itemize}\vspace{-5pt}}

\begin{document}

\begin{center}
    \textbf{\Huge \scshape ''' + escape_latex(name) + r'''} \\ \vspace{1pt}
    \small ''' + escape_latex(contact) + r'''
\end{center}

'''
    
    # Add Education
    if education_items:
        latex_content += r'''\section{Education}
  \resumeSubHeadingListStart
'''
        for item in education_items:
            # Parse education item
            item_lines = item.split('\n')
            if len(item_lines) >= 2:
                school_loc = item_lines[0].split(' - ')
                school = school_loc[0] if school_loc else item_lines[0]
                location = school_loc[1] if len(school_loc) > 1 else ""
                degree_dates = item_lines[1].split(' - ')
                degree = degree_dates[0] if degree_dates else item_lines[1]
                dates = degree_dates[1] if len(degree_dates) > 1 else ""
                
                latex_content += f'''    \\resumeSubheading
      {{{escape_latex(school)}}}{{{escape_latex(location)}}}
      {{{escape_latex(degree)}}}{{{escape_latex(dates)}}}
'''
        latex_content += r'''  \resumeSubHeadingListEnd

'''
    
    # Add Experience
    if experience_items:
        latex_content += r'''\section{Experience}
  \resumeSubHeadingListStart
'''
        for item in experience_items:
            item_lines = [l for l in item.split('\n') if l.strip()]
            if len(item_lines) >= 2:
                # First line: job title - dates
                title_dates = item_lines[0].split(' - ')
                title = title_dates[0] if title_dates else item_lines[0]
                dates = ' - '.join(title_dates[1:]) if len(title_dates) > 1 else ""
                
                # Second line: company - location
                company_loc = item_lines[1].split(' - ')
                company = company_loc[0] if company_loc else item_lines[1]
                location = company_loc[1] if len(company_loc) > 1 else ""
                
                latex_content += f'''    \\resumeSubheading
      {{{escape_latex(title)}}}{{{escape_latex(dates)}}}
      {{{escape_latex(company)}}}{{{escape_latex(location)}}}
      \\resumeItemListStart
'''
                # Add bullet points
                for line in item_lines[2:]:
                    if line.strip().startswith('•'):
                        bullet_text = line.strip()[1:].strip()
                        latex_content += f'''        \\resumeItem{{{escape_latex(bullet_text)}}}
'''
                latex_content += r'''      \resumeItemListEnd
'''
        latex_content += r'''  \resumeSubHeadingListEnd

'''
    
    # Add Projects
    if projects_items:
        latex_content += r'''\section{Projects}
    \resumeSubHeadingListStart
'''
        for item in projects_items:
            item_lines = [l for l in item.split('\n') if l.strip()]
            if item_lines:
                # First line: project name | tech - dates
                first_line = item_lines[0]
                latex_content += f'''      \\resumeProjectHeading
          {{{escape_latex(first_line)}}}{{}}
          \\resumeItemListStart
'''
                for line in item_lines[1:]:
                    if line.strip().startswith('•'):
                        bullet_text = line.strip()[1:].strip()
                        latex_content += f'''            \\resumeItem{{{escape_latex(bullet_text)}}}
'''
                latex_content += r'''          \resumeItemListEnd
'''
        latex_content += r'''    \resumeSubHeadingListEnd

'''
    
    # Add Skills
    if skills_text:
        latex_content += r'''\section{Technical Skills}
 \begin{itemize}[leftmargin=0.15in, label={}]
    \small{\item{
'''
        for line in skills_text.split('\n'):
            if line.strip():
                latex_content += f'''     {escape_latex(line)} \\\\
'''
        latex_content += r'''    }}
 \end{itemize}
'''
    
    latex_content += r'''\end{document}'''
    
    # Compile LaTeX to PDF
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = os.path.join(tmpdir, 'resume.tex')
        with open(tex_path, 'w', encoding='utf-8') as f:
            f.write(latex_content)
        
        # Compile with pdflatex
        try:
            result = subprocess.run(
                ['pdflatex', '-interaction=nonstopmode', '-output-directory', tmpdir, tex_path],
                capture_output=True,
                timeout=60,
                text=True
            )
            
            # Check if PDF was created
            pdf_path = os.path.join(tmpdir, 'resume.pdf')
            if not os.path.exists(pdf_path):
                # Save debug files
                debug_tex = output_path.replace('.pdf', '.tex')
                debug_log = output_path.replace('.pdf', '.log')
                with open(debug_tex, 'w', encoding='utf-8') as f:
                    f.write(latex_content)
                log_path = os.path.join(tmpdir, 'resume.log')
                if os.path.exists(log_path):
                    shutil.copy(log_path, debug_log)
                raise Exception(f"LaTeX failed to generate PDF. Check {debug_tex} and {debug_log}. Output: {result.stderr[:500]}")
            
            # Copy PDF to output path
            shutil.copy(pdf_path, output_path)
            
        except subprocess.TimeoutExpired:
            raise Exception("LaTeX compilation timed out after 60 seconds")
        except FileNotFoundError:
            raise Exception("pdflatex not found. Please install LaTeX (texlive-full on Linux, MacTeX on Mac, MiKTeX on Windows)")
    
    return output_path

def create_cover_letter_pdf(cover_letter_text, output_path):
    """Generate PDF from cover letter text using LaTeX"""
    latex_content = r'''\documentclass[letterpaper,11pt]{article}

\usepackage{latexsym}
\usepackage[empty]{fullpage}
\usepackage[hidelinks]{hyperref}
\usepackage[english]{babel}

\usepackage[margin=1in]{geometry}

\begin{document}

''' + escape_latex(cover_letter_text) + r'''

\end{document}'''
    
    # Compile LaTeX to PDF
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_path = os.path.join(tmpdir, 'cover_letter.tex')
        with open(tex_path, 'w', encoding='utf-8') as f:
            f.write(latex_content)
        
        try:
            result = subprocess.run(
                ['pdflatex', '-interaction=nonstopmode', '-output-directory', tmpdir, tex_path],
                capture_output=True,
                timeout=60,
                text=True
            )
            
            pdf_path = os.path.join(tmpdir, 'cover_letter.pdf')
            if not os.path.exists(pdf_path):
                debug_path = output_path.replace('.pdf', '.tex')
                with open(debug_path, 'w', encoding='utf-8') as f:
                    f.write(latex_content)
                raise Exception(f"Cover letter LaTeX failed. Check {debug_path}. Error: {result.stderr[:500]}")
            
            shutil.copy(pdf_path, output_path)
            
        except subprocess.TimeoutExpired:
            raise Exception("Cover letter compilation timed out after 60 seconds")
        except FileNotFoundError:
            raise Exception("pdflatex not found. Please install LaTeX")
    
    return output_path

@app.route('/')
@auth.login_required
def index():
    return render_template('index.html')

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
