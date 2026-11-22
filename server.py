import os
import shutil
import uuid
import glob
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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

TEMP_DIR = "/tmp/downloads_temp"
os.makedirs(TEMP_DIR, exist_ok=True)

class ConvertRequest(BaseModel):
    url: str
    qualidade: str = "192"

def remover_arquivos_por_id(id_unico: str):
    for arquivo in glob.glob(f"{TEMP_DIR}/{id_unico}*"):
        if os.path.exists(arquivo):
            os.remove(arquivo)

def obter_cookiefile_gravavel() -> str | None:
    origem = None
    if os.path.exists("/etc/secrets/cookies.txt"):
        origem = "/etc/secrets/cookies.txt"
    elif os.path.exists("cookies.txt"):
        origem = "cookies.txt"

    if origem:
        destino = "/tmp/cookies_yt.txt"
        shutil.copyfile(origem, destino)
        return destino
    return None

@app.post("/converter-mp3")
async def converter_mp3(dados: ConvertRequest, background_tasks: BackgroundTasks):
    qualidade = dados.qualidade if dados.qualidade in ["128", "192", "320"] else "192"
    id_unico = str(uuid.uuid4())
    caminho_saida = f"{TEMP_DIR}/{id_unico}.%(ext)s"

    opcoes_ytdlp = {
        'format': 'ba/b',
        'outtmpl': caminho_saida,
        'noplaylist': True,
        'buffersize': 1024 * 16,
        'quiet': False,
        'verbose': False,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': qualidade,
        }],
    }

    cookie_path = obter_cookiefile_gravavel()
    if cookie_path:
        opcoes_ytdlp['cookiefile'] = cookie_path
        print(f"[INFO] Usando cookies de: {cookie_path}")

    try:
        with yt_dlp.YoutubeDL(opcoes_ytdlp) as ydl:
            info = ydl.extract_info(dados.url, download=True)
            titulo = info.get("title", "audio")
            titulo_limpo = "".join(c for c in titulo if c.isalnum() or c in " -_").strip() or "audio"

        arquivo_final = f"{TEMP_DIR}/{id_unico}.mp3"

        if not os.path.exists(arquivo_final):
            raise Exception("Falha na conversão do áudio pelo FFmpeg.")

        background_tasks.add_task(remover_arquivos_por_id, id_unico)

        return FileResponse(
            path=arquivo_final,
            media_type="audio/mpeg",
            filename=f"{titulo_limpo} ({qualidade}kbps).mp3"
        )
    except Exception as e:
        remover_arquivos_por_id(id_unico)
        raise HTTPException(status_code=400, detail=str(e))

app.mount("/", StaticFiles(directory=".", html=True), name="site")
