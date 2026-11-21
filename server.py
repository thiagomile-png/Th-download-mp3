import os
import uuid
from urllib.parse import quote
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import yt_dlp

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"]
)

os.makedirs("downloads_temp", exist_ok=True)

class ConvertRequest(BaseModel):
    url: str
    qualidade: str = "192"

def remover_arquivo(caminho: str):
    if os.path.exists(caminho):
        try:
            os.remove(caminho)
        except Exception:
            pass

# 1º: Rota da conversão (tem que vir antes do StaticFiles)
@app.post("/converter-mp3")
async def converter_mp3(dados: ConvertRequest, background_tasks: BackgroundTasks):
    qualidade = dados.qualidade if dados.qualidade in ["128", "192", "320"] else "192"
    id_unico = str(uuid.uuid4())
    caminho_saida = f"downloads_temp/{id_unico}.%(ext)s"

    opcoes_ytdlp = {
        'format': 'bestaudio/best',
        'outtmpl': caminho_saida,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': qualidade,
        }],
    }

    try:
        with yt_dlp.YoutubeDL(opcoes_ytdlp) as ydl:
            info = ydl.extract_info(dados.url, download=True)
            titulo = info.get("title", "audio_th_download")
            titulo_limpo = "".join(c for c in titulo if c.isalnum() or c in " -_()").strip()
            if not titulo_limpo:
                titulo_limpo = "audio_convertido"

        arquivo_final = f"downloads_temp/{id_unico}.mp3"
        
        if not os.path.exists(arquivo_final):
            raise Exception("Falha ao gerar o arquivo MP3.")

        with open(arquivo_final, "rb") as f:
            conteudo_mp3 = f.read()

        background_tasks.add_task(remover_arquivo, arquivo_final)

        nome_arquivo = f"{titulo_limpo} ({qualidade}kbps).mp3"
        nome_codificado = quote(nome_arquivo)

        return Response(
            content=conteudo_mp3,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{nome_codificado}"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# 2º: Carrega index.html e todas as suas outras páginas automaticamente
app.mount("/", StaticFiles(directory=".", html=True), name="site")
