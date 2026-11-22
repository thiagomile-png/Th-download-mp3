FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instala FFmpeg, unzip e curl para instalar o Deno
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl unzip ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Instala o Deno (runtime JS oficial recomendado pelo yt-dlp para YouTube)
RUN curl -fsSL https://deno.land | DENO_INSTALL=/usr/local sh

WORKDIR /app

# Instala as dependências Python e o yt-dlp mais recente com extras
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -U "yt-dlp[default]"

COPY . .

# Inicia o Uvicorn na porta do Render
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-keep-alive 300"]
