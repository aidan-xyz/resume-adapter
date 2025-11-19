# Resume Adapter

Stop manually tailoring your resume for every job application.

## Why?

Job hunting sucks. Tailoring your resume for each application is tedious. ATS systems are picky. Most resume builders are overpriced or produce terrible output.

I got tired of it and built this in one night.

Upload your resume + paste a job description → Get an ATS-optimized resume and cover letter in 30 seconds.

No monthly subscriptions. No usage limits. Just your API costs.

## How it works

1. Upload your current resume (PDF)
2. Paste the job description
3. Claude analyzes both and adapts your resume to highlight relevant experience
4. Generates an ATS-friendly resume PDF (one page, clean format)
5. Writes a human-sounding cover letter (not generic corporate BS)
6. Download both PDFs

## Cost per application

- Claude API: ~$0.03 per resume + cover letter
- **Total: ~$0.03 per job application**

Compare that to $30-50/month for resume builders with usage caps and terrible templates.

## Setup

### Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create `.env` file with your API key:
```bash
cp .env.example .env
# Edit .env and add your Anthropic API key
# Optionally add AUTH_USERNAME and AUTH_PASSWORD
```

3. Run the app:
```bash
python app.py
```

4. Open http://localhost:5000

### Deploy to Railway

1. Install Railway CLI:
```bash
npm i -g @railway/cli
```

2. Login and initialize:
```bash
railway login
railway init
```

3. Add environment variables in Railway dashboard:
   - `ANTHROPIC_API_KEY` (required)
   - `AUTH_USERNAME` (optional, for security)
   - `AUTH_PASSWORD` (optional, for security)

4. Deploy:
```bash
railway up
```

## Environment Variables

- `ANTHROPIC_API_KEY` - Your Anthropic API key for Claude (required)
- `AUTH_USERNAME` - Username for HTTP Basic Auth (optional)
- `AUTH_PASSWORD` - Password for HTTP Basic Auth (optional)

## Authentication

The app includes optional HTTP Basic Authentication. When you set `AUTH_USERNAME` and `AUTH_PASSWORD` environment variables, users will be prompted with a browser login dialog before accessing the app.

If these variables are not set, the app runs without authentication (useful for local development).

For production deployments, it's recommended to set these credentials to prevent unauthorized access.

## File Structure

```
resume-adapter/
├── app.py              # Main Flask application
├── templates/
│   └── index.html      # UI template
├── uploads/            # Temporary storage (auto-created)
├── outputs/            # Generated PDFs (auto-created)
├── requirements.txt    # Python dependencies
├── .env.example        # Example environment variables
└── README.md          # This file
```

## Notes

- Max file size: 10MB
- Supports PDF resumes only
- Uploaded files are deleted after processing
- Generated PDFs are stored temporarily
- Uses Claude Sonnet 4 for content adaptation
- Output is optimized for ATS (Applicant Tracking Systems)

## Contributing

PRs welcome. Keep it simple.

## License

MIT - do whatever you want with it.

## Why I built this

I was applying to jobs and got sick of:
1. Manually rewriting my resume for each application
2. Worrying about ATS compatibility
3. Writing cover letters that sound like a robot
4. Paying $30/month for resume builders that produce garbage

This does exactly what I need for pennies per application.

If you're job hunting and hate the same things, this might help.
