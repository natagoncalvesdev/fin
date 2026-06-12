from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, engine
from app.migrations import run_migrations
from app.routers import auth_router, cartoes, categorias, financeiro, users, veiculos

Base.metadata.create_all(bind=engine)
run_migrations(engine)

app = FastAPI(title="Fin - Controle Residencial", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(users.router)
app.include_router(financeiro.router)
app.include_router(categorias.router)
app.include_router(cartoes.router)
app.include_router(veiculos.router)


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
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")


@app.get("/api/health")
def health():
    return {"status": "ok", "database": "postgresql"}
