FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instala FFmpeg, Node.js e npm
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg nodejs npm && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instala o provedor de PO Token diretamente pelo registro oficial do npm (sem URL do GitHub)
RUN npm install -g bgutil-ytdlp-pot-provider

# Instala as dependências Python, o yt-dlp atualizado e o plugin conector
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -U yt-dlp bgutil-ytdlp-pot-provider

COPY . .

# Inicia o servidor de PO Token em segundo plano e o Uvicorn na porta do Render
CMD ["sh", "-c", "bgutil-pot-server & uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-keep-alive 300"]
