from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, engine
from app.migrations import run_migrations
from app.routers import (
    auth_router,
    cartoes,
    categorias,
    cofrinhos,
    conquistas,
    financeiro,
    grupos,
    saude,
    users,
    veiculos,
)

Base.metadata.create_all(bind=engine)
run_migrations(engine)

app = FastAPI(title="Fin - Controle Residencial", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=3600,
)

# Cabeçalhos de segurança em toda resposta da API. O frontend (servido pela
# Netlify) tem os seus próprios em frontend/_headers — este bloco cobre as
# respostas JSON e o /docs. A API só devolve JSON, então uma CSP estrita não
# quebra nada (exceto o Swagger, que precisa carregar assets).
_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if not request.url.path.startswith(_DOCS_PATHS):
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        )
    return response

app.include_router(auth_router.router)
app.include_router(users.router)
app.include_router(financeiro.router)
app.include_router(categorias.router)
app.include_router(cartoes.router)
app.include_router(veiculos.router)
app.include_router(saude.router)
app.include_router(cofrinhos.router)
app.include_router(conquistas.router)
app.include_router(grupos.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "database": "postgresql"}


def _frontend_dir() -> Path | None:
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "frontend",
        Path("/frontend"),
    ]
    for path in candidates:
        if path.is_dir():
            return path
    return None


frontend_dir = _frontend_dir()
if frontend_dir:
    # Precisa ser o último mount: StaticFiles("/") captura qualquer caminho,
    # então qualquer rota de API registrada depois dele seria inalcançável.
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
