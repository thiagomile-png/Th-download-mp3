import os
import random
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
DURACAO_MAXIMA_SEGUNDOS = 7200
tarefas = {}


class InfoRequest(BaseModel):
    url: str


class ConvertRequest(BaseModel):
    url: str
    qualidade: str = "192"


def remover_arquivos_por_id(id_unico: str):
    for arquivo in glob.glob(f"{TEMP_DIR}/{id_unico}*"):
        if os.path.exists(arquivo):
            os.remove(arquivo)
    tarefas.pop(id_unico, None)


def obter_cookiefile_gravavel():
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


def obter_lista_proxies():
    proxies = []
    raw_list = os.environ.get("PROXY_LIST", "").strip()
    if raw_list:
        for item in raw_list.replace("\n", ",").split(","):
            p = item.strip().rstrip("/")
            if p:
                proxies.append(p)

    single_proxy = os.environ.get("PROXY_URL", "").strip().rstrip("/")
    if single_proxy and single_proxy not in proxies:
        proxies.append(single_proxy)

    if proxies:
        random.shuffle(proxies)
    return proxies


def criar_opcoes_base(usar_cookies=True, clientes=None, proxy_url=None):
    opcoes = {
        'noplaylist': True,
        'buffersize': 1024 * 16,
        'http_chunk_size': 10485760,
        'retries': 3,
        'fragment_retries': 3,
        'socket_timeout': 20,
        'quiet': True,
        'no_warnings': True,
    }
    if clientes:
        opcoes['extractor_args'] = {'youtube': {'player_client': clientes}}
    if usar_cookies:
        cookie_path = obter_cookiefile_gravavel()
        if cookie_path:
            opcoes['cookiefile'] = cookie_path
    if proxy_url:
        opcoes['proxy'] = proxy_url
    return opcoes


def traduzir_erro_youtube(erro_str):
    msg = erro_str.lower()
    if "sign in to confirm" in msg or "bot" in msg:
        return "O YouTube bloqueou temporariamente a conexão dos proxies. Tente novamente em instantes."
    if "failed to extract any player response" in msg or "403" in msg:
        return "O YouTube recusou o acesso a este vídeo (proxies bloqueados ou vídeo restrito)."
    if "video unavailable" in msg or "private video" in msg:
        return "Este vídeo está privado, indisponível ou foi removido."
    if "ultrapassa o limite" in msg or "transmissões ao vivo" in msg:
        return erro_str
    return f"Não foi possível processar este vídeo: {erro_str}"
@app.post("/info")
async def obter_info_video(dados: InfoRequest):
    proxies = obter_lista_proxies()
    lista_testes = proxies[:3] if proxies else [None]
    info = None
    ultimo_erro = None

    for proxy in lista_testes:
        opcoes = criar_opcoes_base(usar_cookies=True, clientes=None, proxy_url=proxy)
        opcoes['skip_download'] = True
        try:
            with yt_dlp.YoutubeDL(opcoes) as ydl:
                info = ydl.extract_info(dados.url, download=False)
                break
        except Exception as e:
            ultimo_erro = e

    if not info:
        raise HTTPException(status_code=400, detail=traduzir_erro_youtube(str(ultimo_erro or "Erro ao ler vídeo.")))

    duracao_seg = info.get("duration") or 0
    minutos, segundos = divmod(int(duracao_seg), 60)
    horas, minutos = divmod(minutos, 60)
    duracao_fmt = f"{horas}:{minutos:02d}:{segundos:02d}" if horas > 0 else f"{minutos}:{segundos:02d}"

    return {
        "titulo": info.get("title", "Vídeo do YouTube"),
        "thumbnail": info.get("thumbnail", ""),
        "canal": info.get("uploader", ""),
        "duracao": duracao_fmt if duracao_seg else ""
    }


def executar_download_em_segundo_plano(id_unico: str, url: str, qualidade: str):
    caminho_saida = f"{TEMP_DIR}/{id_unico}.%(ext)s"

    def hook_progresso(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            baixado = d.get('downloaded_bytes', 0)
            if total > 0:
                pct = int((baixado / total) * 75) + 5
                tarefas[id_unico]["progresso"] = min(pct, 80)
                tarefas[id_unico]["status"] = f"Baixando áudio... ({int((baixado / total) * 100)}%)"
        elif d['status'] == 'finished':
            tarefas[id_unico]["progresso"] = 85
            tarefas[id_unico]["status"] = "Convertendo para MP3 com FFmpeg..."

    def montar_opcoes_download(usar_cookies, clientes, proxy_url):
        opcoes = criar_opcoes_base(usar_cookies=usar_cookies, clientes=clientes, proxy_url=proxy_url)
        opcoes.update({
            'format': 'bestaudio/best',
            'outtmpl': caminho_saida,
            'progress_hooks': [hook_progresso],
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': qualidade,
            }],
        })
        return opcoes
    try:
        tarefas[id_unico]["status"] = "Conectando ao YouTube..."
        tarefas[id_unico]["progresso"] = 4

        proxies = obter_lista_proxies()
        estrategias = []

        if proxies:
            for idx, proxy in enumerate(proxies[:5], start=1):
                estrategias.append((f"Proxy #{idx} (com cookies)", montar_opcoes_download(True, None, proxy)))
            estrategias.append(("Proxy fallback (sem cookies)", montar_opcoes_download(False, ['tv_embedded', 'mweb'], proxies[-1])))
        else:
            estrategias.append(("Direto (com cookies)", montar_opcoes_download(True, None, None)))
            estrategias.append(("Direto (sem cookies)", montar_opcoes_download(False, ['tv_embedded', 'mweb'], None)))

        info_final = None
        ultimo_erro = None

        for nome_estrategia, opcoes_atual in estrategias:
            try:
                print(f"[INFO] Tentando {nome_estrategia} para {url}")
                with yt_dlp.YoutubeDL(opcoes_atual) as ydl:
                    info_previa = ydl.extract_info(url, download=False)
                    duracao = info_previa.get("duration") or 0

                    if duracao > DURACAO_MAXIMA_SEGUNDOS:
                        raise Exception("O vídeo ultrapassa o limite máximo de 2 horas permitido pelo servidor.")

                    if info_previa.get("is_live"):
                        raise Exception("Transmissões ao vivo em andamento não podem ser convertidas.")

                    tarefas[id_unico]["status"] = "Iniciando download do áudio..."
                    tarefas[id_unico]["progresso"] = 5

                    info_final = ydl.extract_info(url, download=True)
                    print(f"[SUCESSO] Baixado via {nome_estrategia}")
                    break
            except Exception as err:
                ultimo_erro = err
                print(f"[AVISO] {nome_estrategia} falhou: {err}")
                if "ultrapassa o limite" in str(err) or "ao vivo" in str(err):
                    raise err

        if not info_final:
            raise ultimo_erro or Exception("Falha ao baixar o vídeo.")

        titulo = info_final.get("title", "audio")
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
            "status": traduzir_erro_youtube(str(e)),
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
