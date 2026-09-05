FROM python:3.12-slim

WORKDIR /app

# System deps needed by some Python packages (e.g. audio handling)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# data/ holds the vector DB, tokens, audit log, api keys — persist this
# as a volume in production, don't bake user data into the image
RUN mkdir -p data/chroma data/drive_tokens

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
