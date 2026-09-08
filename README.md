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
| `registro_peso` | Histórico de peso (kg + data) |
| `registro_medidas` | Histórico de medidas corporais (cm + data) |
| `meta_peso` | Metas de peso e histórico (ativa / atingida / arquivada) |
| `cofrinho` | Metas de economia ("guardar dinheiro") |
| `aporte_cofrinho` | Depósitos num cofrinho (cada um também vira um débito) |
| `conquista` | Medalhas (marcos de peso, metas, cofrinhos) |

O Firebase **não é mais usado**. O frontend fala com a API Python, que persiste tudo no Postgres.

## API

Documentação Swagger: http://localhost:8000/docs

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/api/auth/register` | Cadastro |
| POST | `/api/auth/login` | Login |
| GET | `/api/financeiro/anos/{ano}/meses/{mes}` | Dados do mês |
| GET | `/api/financeiro/anos/{ano}/resumo` | Ano inteiro numa requisição (relatório / resumo anual) |
| GET | `/api/veiculos` | Listar veículos |
| GET | `/api/categorias` | Listar categorias |
| GET | `/api/saude/peso?dias=7\|30\|365` | Registros de peso na janela |
| GET | `/api/saude/medidas` | Registros de medidas corporais |
| GET | `/api/saude/metas` | Metas de peso (com histórico) |
| GET | `/api/cofrinhos` | Metas de economia (saldo, plano mensal, aportes) |
| GET | `/api/conquistas` | Medalhas (peso + cofrinhos) |

## Produção (Supabase + Render + Netlify, planos free)

Notas de desempenho para o ambiente hospedado:

- **Região do banco × backend:** o projeto Supabase e o serviço do Render
  **devem estar na mesma região** (ex.: ambos em US East). Cada query paga a
  latência de rede entre os dois; com regiões diferentes, uma tela que faz
  ~6 queries fica visivelmente lenta.
- **Connection string:** use o *connection pooler* do Supabase (o host
  `...pooler.supabase.com`, porta `6543`, modo *transaction*) no
  `DATABASE_URL`, não a conexão direta.
- **Cold start do Render:** o plano free hiberna após ~15 min sem tráfego e o
  próximo acesso leva 30-50s. O workflow `.github/workflows/keep-warm.yml`
  faz um ping a cada ~12 min. Para algo mais confiável, configure o
  [cron-job.org](https://cron-job.org) apontando para
  `https://<app>.onrender.com/api/health` a cada 10 min.
- **Relatório / resumo anual:** carregam o ano inteiro em **uma** requisição
  (`/anos/{ano}/resumo`, ~6 queries) em vez de 12 requisições em série.
- **Polling:** as telas do financeiro revalidam a cada 20s (antes 2,5-4s).
