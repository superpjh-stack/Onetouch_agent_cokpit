FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OPENAI_MODEL=gpt-5.6

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py cockpit_runtime.py ./
COPY onetouch_agent ./onetouch_agent
COPY sample_docs ./sample_docs
COPY scripts ./scripts
COPY data/onetouch_demo.db ./data/onetouch_demo.db

EXPOSE 8501
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
