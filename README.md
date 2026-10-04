# Beaver

A personal knowledge base assistant: a multi-agent backend with a browser UI.

## Features

- **Chat with an agent that acts.** The agent calls tools for notes, reminders, preferences,
  sessions and the knowledge base, and can hand off to expert agents — including creating new ones.
- **Knowledge base.** Upload documents and ask questions answered from their content, with retrieval
  scoped to each user. Supported: `.md` `.txt` `.pdf` `.docx` `.xlsx` `.xls` `.csv` `.pptx`.
- **Confirmations.** Creating, updating and deleting anything asks you first, and your reason for
  declining is fed back to the model.
- **Streaming UI.** Token-by-token output over WebSocket, with every tool call shown as a card.

## Requirements

- Python 3.11+
- Node.js 18+

## Setup

```bash
git clone https://github.com/kira9339/beaver_agent.git
cd beaver_agent

uv sync --all-extras --no-extra mineru
source .venv/bin/activate        # Windows: .venv\Scripts\activate

python scripts/init_db.py        # SQLite
python scripts/init_chroma.py    # vector store (recreates the directory)

cd src/beaver_web/frontend
npm install
npm run build:h5                 # build the web UI
```

## Configure

Copy the sample config and fill in your credentials:

```bash
cp config.yaml.example ~/.beaver/config.yaml
```

```yaml
user:
  username: <username>
model_provider:
  provider: openai               # any OpenAI-compatible endpoint
  model: deepseek-chat
  api_key: <your-api-key>
  base_url: https://api.deepseek.com/v1
embedding:
  provider: local                # openai | local | mock_embedding_provider
  model: BAAI/bge-m3
  model_path: D:/hf_cache/hub    # HuggingFace cache dir, for provider: local
```

The chat model works with any OpenAI-compatible API (DeepSeek, Kimi, Zhipu, …).
For embeddings, `openai` calls a compatible embedding API, `local` runs a sentence-transformers
model from your HuggingFace cache with no API key (`pip install 'beaver[local]'`), and
`mock_embedding_provider` is for tests only — it cannot index documents.

You can also edit the configuration from the settings page in the browser.

## Run

```bash
beaver-web                                    # http://127.0.0.1:8000
```

Or without the entry point:

```bash
PYTHONPATH=src python -m uvicorn beaver_web.app:app --port 8000
```

For frontend development, run the backend as above and in another terminal:

```bash
cd src/beaver_web/frontend
npm run dev:h5                                # http://localhost:5173
```

Open the page and enter any username — the account is created on first use.

Environment variables: `BEAVER_HOST`, `BEAVER_PORT`, `BEAVER_RELOAD`.

> **Don't run with `--reload` while chatting.** The CreatorAgent writes new expert agents into
> `src/beaver_agent/`; a reloader watching the source tree would restart the server mid-conversation
> and drop the session. `beaver-web` keeps reload off unless `BEAVER_RELOAD=1` is set.

## Data

Everything lives outside the repository:

| | |
|---|---|
| `~/.beaver/config.yaml` | model and embedding configuration |
| `beaver_assistant.db` | conversations, messages, notes, reminders, preferences, users |
| `chroma_db/` | document embeddings |
| `uploads/` | uploaded documents, per user |

## Layout

```
src/
├── beaver_web/       FastAPI app, WebSocket runtime, REST API, uni-app H5 frontend
├── beaver_agent/     agent definitions, prompts, native tool registry
├── beaver_client/    BeaverCoreClient facade over the service layer
├── beaver_core/      domain services, context management, document parsing
├── beaver_models/    LLM and embedding providers
└── beaver_storage/   SQLAlchemy models, repositories, Chroma connection
```

## Notes

- The server binds to `127.0.0.1` by default. Sign-in is username-only with no password, so put it
  behind your own authentication before exposing it.
- After the server starts, the local embedding model loads in the background (~20s for
  `BAAI/bge-m3`). The app is usable immediately, but the first document upload may wait for it.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
