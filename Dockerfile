FROM python:3.11-slim

# Install LaTeX and required tools
RUN apt-get update && apt-get install -y \
    texlive-latex-base \
    texlive-fonts-recommended \
    texlive-latex-extra \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create necessary directories
RUN mkdir -p uploads outputs

EXPOSE 8080

CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]
