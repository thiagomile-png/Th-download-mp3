FROM python:3.11-slim

# Evita geração de arquivos .pyc e ativa logs em tempo real no painel do Render
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instala o FFmpeg e o Node.js (necessário para o yt-dlp decifrar links do YouTube)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg nodejs && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instala as dependências e força a atualização do yt-dlp para a versão mais recente
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -U yt-dlp

# Copia o restante do seu código (server.py, index.html, etc.)
COPY . .

# Inicia o Uvicorn apontando para server:app com 1 worker (economiza RAM) e timeout alto
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-keep-alive 300"]
