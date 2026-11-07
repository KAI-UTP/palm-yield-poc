# Palm Yield Optimization POC: web app (default) or REST API, from one image.
#   docker build -t palm-yield .
#   docker run -p 8501:8501 -e GEMINI_API_KEY=... palm-yield                    -> app on http://localhost:8501
#   docker run -p 8000:8000 palm-yield uvicorn api:app --host 0.0.0.0 --port 8000  -> API on http://localhost:8000/docs
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt fastapi uvicorn

COPY . .
RUN useradd --create-home palm && chown -R palm /app
USER palm

EXPOSE 8501 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
