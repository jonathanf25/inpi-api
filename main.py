"""
INPI Brand Search API
Microservico para consulta de marcas no INPI (pePI)
Compativel com Lovable, Next.js, React, ou qualquer frontend.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
from typing import Optional, List
import re

app = FastAPI(
    title="INPI Marcas API",
    description="Consulta de marcas registradas no INPI sem necessidade de login",
    version="1.0.0",
)

# CORS: permite chamadas do Lovable e outros frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# URLs do sistema pePI
BASE_URL    = "https://busca.inpi.gov.br/pePI"
LOGIN_URL   = f"{BASE_URL}/servlet/LoginController"
SEARCH_URL  = f"{BASE_URL}/servlet/MarcasServletController"

# Modelos de resposta
class MarcaResultado(BaseModel):
    numero: str
    prioridade: str
    marca: str
    situacao: str
    titular: str
    classe: str

class PesquisaResponse(BaseModel):
    total: int
    marca_pesquisada: str
    tipo_pesquisa: str
    resultados: List[MarcaResultado]

# Funcao principal de scraping
def buscar_marcas_inpi(nome: str, tipo: str = "E") -> List[MarcaResultado]:
    """
    Busca marcas no INPI via scraping do pePI.

    Args:
        nome:  Nome da marca a pesquisar
        tipo:  "E" = Exata | "R" = Radical (busca ampla)

    Returns:
        Lista de MarcaResultado
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; INPI-API/1.0)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9",
    })

    # PASSO 1: Acesso anonimo - bate no LoginController sem credenciais
    try:
        resp = session.post(
            LOGIN_URL,
            data={"submission": "continuar"},
            timeout=15,
            allow_redirects=True,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Erro ao conectar no INPI: {str(e)}")

    # PASSO 2: Pesquisa por nome da marca
    try:
        resp = session.post(
            SEARCH_URL,
            data={
                "Action":          "SearchBasic",
                "tipoConsulta":    "marcas",
                "comboTipoMarca":  tipo,
                "marcaNome":       nome,
                "classeNice":      "",
                "qtdRow":          "50",
            },
            timeout=20,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Erro na pesquisa INPI: {str(e)}")

    # PASSO 3: Parse do HTML
    soup = BeautifulSoup(resp.text, "html.parser")
    tabela = soup.find("table", {"class": "tabelaResultado"})

    # Fallback: tenta encontrar qualquer tabela com dados de marca
    if not tabela:
        tabelas = soup.find_all("table")
        for t in tabelas:
            headers = [th.get_text(strip=True).lower() for th in t.find_all("th")]
            if "marca" in headers and "titular" in headers:
                tabela = t
                break

    if not tabela:
        return []

    resultados: List[MarcaResultado] = []
    linhas = tabela.find_all("tr")[1:]  # pula o cabecalho

    for linha in linhas:
        cols = linha.find_all("td")
        if len(cols) < 6:
            continue
        resultados.append(MarcaResultado(
            numero     = cols[0].get_text(strip=True),
            prioridade = cols[1].get_text(strip=True),
            marca      = cols[3].get_text(strip=True),
            situacao   = cols[5].get_text(strip=True),
            titular    = cols[6].get_text(strip=True) if len(cols) > 6 else "",
            classe     = cols[7].get_text(strip=True) if len(cols) > 7 else "",
        ))

    return resultados


# ENDPOINTS

@app.get("/")
def root():
    return {
        "servico": "INPI Marcas API",
        "versao": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "GET /marcas?nome=suamarca":         "Busca exata",
            "GET /marcas?nome=suamarca&tipo=radical": "Busca radical (variacoes)",
        }
    }


@app.get("/marcas", response_model=PesquisaResponse)
def pesquisar_marca(
    nome: str = Query(..., description="Nome da marca a pesquisar", example="registraja"),
    tipo: str = Query("exata", description="Tipo de busca: 'exata' ou 'radical'", example="exata"),
):
    """
    Pesquisa uma marca na base de dados do INPI.

    - **nome**: Nome da marca (obrigatorio)
    - **tipo**: exata (padrao) ou radical (encontra variacoes)
    """
    tipo_codigo = "R" if tipo.lower() == "radical" else "E"
    resultados = buscar_marcas_inpi(nome, tipo_codigo)

    return PesquisaResponse(
        total=len(resultados),
        marca_pesquisada=nome,
        tipo_pesquisa=tipo,
        resultados=resultados,
    )


@app.get("/health")
def health_check():
    """Verifica se o servico esta online."""
    return {"status": "ok"}
