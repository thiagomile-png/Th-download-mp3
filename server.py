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

# Armazena o progresso de cada conversão em andamento
tarefas = {}

class ConvertRequest(BaseModel):
    url: str
    qualidade: str = "192"

def remover_arquivos_por_id(id_unico: str):
    for arquivo in glob.glob(f"{TEMP_DIR}/{id_unico}*"):
        if os.path.exists(arquivo):
            os.remove(arquivo)
    tarefas.pop(id_unico, None)

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

def executar_download_em_segundo_plano(id_unico: str, url: str, qualidade: str):
    caminho_saida = f"{TEMP_DIR}/{id_unico}.%(ext)s"

    def hook_progresso(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            baixado = d.get('downloaded_bytes', 0)
            if total > 0:
                # O download representa de 5% a 80% do processo total
                pct = int((baixado / total) * 75) + 5
                tarefas[id_unico]["progresso"] = min(pct, 80)
                tarefas[id_unico]["status"] = f"Baixando áudio do YouTube... ({int((baixado / total) * 100)}%)"
        elif d['status'] == 'finished':
            tarefas[id_unico]["progresso"] = 85
            tarefas[id_unico]["status"] = "Convertendo para MP3 com FFmpeg..."

    opcoes_ytdlp = {
        'format': 'bestaudio/best',
        'outtmpl': caminho_saida,
        'noplaylist': True,
        'buffersize': 1024 * 16,
        'quiet': True,
        'progress_hooks': [hook_progresso],
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': qualidade,
        }],
    }

    cookie_path = obter_cookiefile_gravavel()
    if cookie_path:
        opcoes_ytdlp['cookiefile'] = cookie_path

    try:
        tarefas[id_unico]["status"] = "Conectando ao YouTube..."
        tarefas[id_unico]["progresso"] = 5

        with yt_dlp.YoutubeDL(opcoes_ytdlp) as ydl:
            info = ydl.extract_info(url, download=True)
            titulo = info.get("title", "audio")
            titulo_limpo = "".join(c for c in titulo if c.isalnum() or c in " -_").strip() or "audio"

        arquivo_final = f"{TEMP_DIR}/{id_unico}.mp3"
        if not os.path.exists(arquivo_final):
            raise Exception("Falha na conversão do áudio pelo FFmpeg.")

        tarefas[id_unico]["arquivo"] = arquivo_final
        tarefas[id_unico]["nome_download"] = f"{titulo_limpo} ({qualidade}kbps).mp3"
        tarefas[id_unico]["progresso"] = 100
        tarefas[id_unico]["status"] = "Concluído!"
        tarefas[id_unico]["concluido"] = True

    except Exception as e:
        remover_arquivos_por_id(id_unico)
        tarefas[id_unico] = {
            "progresso": 0,
            "status": str(e),
            "erro": True,
            "concluido": False
        }

@app.post("/iniciar-conversao")
async def iniciar_conversao(dados: ConvertRequest, background_tasks: BackgroundTasks):
    qualidade = dados.qualidade if dados.qualidade in ["128", "192", "320"] else "192"
    id_unico = str(uuid.uuid4())

    tarefas[id_unico] = {
        "progresso": 2,
        "status": "Iniciando...",
        "concluido": False,
        "erro": False
    }

    background_tasks.add_task(executar_download_em_segundo_plano, id_unico, dados.url, qualidade)
    return {"job_id": id_unico}

@app.get("/progresso/{job_id}")
async def consultar_progresso(job_id: str):
    tarefa = tarefas.get(job_id)
    if not tarefa:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    return {
        "progresso": tarefa["progresso"],
        "status": tarefa["status"],
        "concluido": tarefa["concluido"],
        "erro": tarefa.get("erro", False)
    }

@app.get("/baixar/{job_id}")
async def baixar_arquivo(job_id: str, background_tasks: BackgroundTasks):
    tarefa = tarefas.get(job_id)
    if not tarefa or not tarefa.get("concluido"):
        raise HTTPException(status_code=404, detail="Arquivo ainda não está pronto.")

    background_tasks.add_task(remover_arquivos_por_id, job_id)
    return FileResponse(
        path=tarefa["arquivo"],
        media_type="audio/mpeg",
        filename=tarefa["nome_download"]
    )

app.mount("/", StaticFiles(directory=".", html=True), name="site")
