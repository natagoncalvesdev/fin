# Fin — Controle Residencial

Aplicação full-stack para controle financeiro e de veículos.

- **Frontend:** HTML/CSS/JS (interface original)
- **Backend:** Python + FastAPI
- **Banco:** PostgreSQL (sem Firebase)

## Estrutura

```
fin/
├── backend/                 # API REST
│   ├── app/
│   └── scripts/             # SQL de criação do banco
├── frontend/                # Páginas web
│   └── js/fin-sdk.js        # Comunicação com a API (substitui Firebase)
└── docker-compose.yml       # Postgres + API
```

## Opção 1 — Docker (recomendado)

Sobe PostgreSQL e a API juntos:

```bash
docker compose up --build
```

- App: http://localhost:8000
- PostgreSQL: `localhost:5432` (usuário `fin`, senha `fin`, banco `fin`)

As tabelas são criadas automaticamente na primeira execução.

## Opção 2 — PostgreSQL local + Python

### 1. Criar o banco PostgreSQL

Instale o PostgreSQL e execute:

```bash
psql -U postgres -f backend/scripts/init_postgres.sql
```

Ou manualmente:

```sql
CREATE USER fin WITH PASSWORD 'fin';
CREATE DATABASE fin OWNER fin;
```

### 2. Configurar o backend

```bash
cd backend
copy .env.example .env   # Windows
# cp .env.example .env   # Linux/macOS
```

Edite o `.env` se necessário:

```env
DATABASE_URL=postgresql://fin:fin@localhost:5432/fin
SECRET_KEY=sua-chave-secreta-forte
```

### 3. Instalar e rodar

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS

pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Acesse: http://localhost:8000

## Primeiro acesso

1. Cadastro em `/register.html`
2. Login em `/login.html`
3. Use financeiro, veículos e relatórios normalmente

## Banco de dados

Todos os dados ficam no **PostgreSQL**:

| Tabela | Conteúdo |
|--------|----------|
| `users` | Usuários e autenticação |
| `meses_financeiros` | Período (usuário + ano + mês + status do cartão) |
| `contas` | Contas fixas do mês (`user_id` + `mes_id`) |
| `adicionais` | Entradas / receitas extras (`user_id` + `mes_id`) |
| `debitos` | Compras no débito (`user_id` + `mes_id`) |
| `reservados` | Valores reservados (`user_id` + `mes_id`) |
| `compras_cartao` | Compras no cartão (`user_id` + `mes_id`) |
| `vale_cargas` | Carga mensal dos cartões vale (`user_id` + `mes_id`) |
| `categorias` | Categorias de despesas |
| `cartoes` | Cartões cadastrados |
| `veiculos` | Veículos |
| `abastecimentos` | Histórico de abastecimentos |
| `manutencoes` | Histórico de manutenções |

O Firebase **não é mais usado**. O frontend fala com a API Python, que persiste tudo no Postgres.

## API

Documentação Swagger: http://localhost:8000/docs

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/api/auth/register` | Cadastro |
| POST | `/api/auth/login` | Login |
| GET | `/api/financeiro/anos/{ano}/meses/{mes}` | Dados do mês |
| GET | `/api/veiculos` | Listar veículos |
| GET | `/api/categorias` | Listar categorias |
