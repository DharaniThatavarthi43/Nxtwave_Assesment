# NxtWave GenAI Lesson Studio

NxtWave GenAI Lesson Studio creates beginner-friendly lessons, checks each lesson against six evaluation checkpoints, retries a failed lesson up to two times with correction feedback, and saves approved notes and rejection history in SQLite. It has two generation modes:

- **NxtWave GPT** generates directly with the configured language model.
- **NxtWave RAG** retrieves relevant content from the Knowledge Base first, then uses the same generation and evaluation workflow. Add a document or webpage in the Generate page before using RAG.

Both modes use the same six checkpoints (C1–C6). Approved lessons appear in Notes and can be downloaded as Markdown or text. Rejected attempts appear in Rejection Logs.

## Prerequisites

Install these before setup:

- **Git** to clone the repository.
- **Python 3.10 or newer** (Python 3.11 or 3.12 recommended). Include the Python launcher (`py`) on Windows.
- **Node.js 20 or newer** and npm (npm is included with Node.js).
- An API key from a supported model provider: [GroqCloud](https://console.groq.com/keys) or [Google AI Studio](https://aistudio.google.com/apikey).

The Python dependencies are listed in `requirements.txt` and the frontend dependencies and exact versions are listed in `frontend/package.json` and `frontend/package-lock.json`. Installing the requirements installs FastAPI/Uvicorn, LangChain provider adapters, Pydantic, SQLite support from Python, PDF parsing, and the test tools. `npm ci` installs React, Vite, TypeScript, Tailwind CSS, charts, and the UI libraries from the lockfile. You do not need to install SQLite separately.

## 1. Clone the repository

Open PowerShell (Windows), Terminal (macOS/Linux), or a shell with Git installed:

```sh
git clone <GITHUB_REPOSITORY_URL>
cd NxtWave_GenAI_Assessment
```

Replace `<GITHUB_REPOSITORY_URL>` with the repository's Code → HTTPS URL. If you download a ZIP instead, extract it and open a terminal in the extracted `NxtWave_GenAI_Assessment` directory.

## 2. Install backend packages

### Windows PowerShell

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks virtual environment activation, run the Python executable directly instead (for example, `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`) or use Command Prompt with `.venv\Scripts\activate.bat`.

### macOS or Linux

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 3. Configure the language model

Create your private local configuration file from the example:

### Windows PowerShell

```powershell
Copy-Item .env.example .env
notepad .env
```

### macOS or Linux

```sh
cp .env.example .env
${EDITOR:-nano} .env
```

Set the provider, model, and API key together. Example for GroqCloud:

```dotenv
LLM_PROVIDER=groq
LLM_MODEL=openai/gpt-oss-120b
LLM_API_KEY=paste_your_GroqCloud_key_here
```

For Google Gemini, set `LLM_PROVIDER=google`, set `LLM_MODEL` to a Gemini model available to your account, and set `LLM_API_KEY` to your Google AI Studio key. The values in `.env.example` are blank placeholders; the application will not generate lessons until valid provider settings are configured. Keep `.env` private. It is ignored by Git; never commit or share a real API key.

Other optional settings are already documented in `.env.example`: `DATABASE_PATH`, `MAX_RETRIES` (0–2 for the command-line workflow), `EVALUATOR_MAX_RETRY_AFTER_SECONDS`, and `FRONTEND_ORIGINS`. The web generation modes use up to two lesson retries. The default SQLite database is created automatically at `data/database/lesson_generator.db`; generated reports are saved below `outputs/`.

## 4. Install frontend packages

Open a **second terminal** in the repository root, then run:

```sh
cd frontend
npm ci
```

`npm ci` uses the checked-in lockfile for a repeatable installation. No global Vite or TypeScript installation is needed.

## 5. Start the backend

In the first terminal, from the repository root with the virtual environment active, start FastAPI:

```sh
python -m uvicorn app.api.app:app --reload --host 127.0.0.1 --port 8000
```

Keep this terminal open. Confirm the API is healthy by opening <http://127.0.0.1:8000/api/health>; the response should show `"status":"ok"` and `"database_connected":true`. Interactive API documentation is at <http://127.0.0.1:8000/api/docs>.

## 6. Start the frontend

In the second terminal, with the current directory set to `frontend`, run:

```sh
npm run dev
```

Open the URL printed by Vite, normally <http://127.0.0.1:5173>. The frontend sends API calls to the same origin by default; during local development Vite forwards `/api` requests to `http://127.0.0.1:8000`. Keep both terminals running while using the system.

## 7. Use the system

1. Open **Generate lesson**.
2. Enter a lesson topic and choose **NxtWave GPT** or **NxtWave RAG**.
3. For RAG, add a webpage URL or upload a PDF, TXT, or Markdown file, then select a knowledge-base document.
4. Start generation. Follow the A–D progress bar from preparation through the evaluation decision; hover or focus each step for details.
5. The lesson is checked against all six mandatory checkpoints. A failed evaluation can trigger up to two retries with correction guidance.
6. An approved lesson is saved in **Notes**, where it can be viewed and downloaded as Markdown or text. Rejection details and retry history appear in **Rejection Logs**. Dashboard, Evaluation Lab, Execution History, Learning Memory, Knowledge Base, and Settings read the same backend data and configuration.

## Optional: run the command-line workflow

With the virtual environment active and `.env` configured, run from the repository root:

```sh
python -m app.main
```

The CLI prompts for a topic. To provide it directly:

```sh
python -m app.main --topic "Introduction to RAG"
```

## Optional: run deterministic examples

These examples use scripted model responses and do not make paid provider API calls:

```sh
python -m app.demo --scenario corrected
python -m app.demo --scenario rejected
```

They write clearly marked mock demonstration reports below `outputs/examples/`.

## Optional: run checks

From the repository root, with Python dependencies installed:

```sh
python -m pytest
python -m compileall -q app tests
python -m pip check
```

To compile the frontend for deployment:

```sh
cd frontend
npm run build
```

## Troubleshooting

- **“Cannot connect to the API”**: make sure the backend terminal is still running and `http://127.0.0.1:8000/api/health` responds. Restart the API after changing `.env`.
- **“Request failed (500)”**: check the backend terminal for the error and restart the backend after pulling code or changing dependencies.
- **LLM is not configured**: check `LLM_PROVIDER`, `LLM_MODEL`, and `LLM_API_KEY` in the root `.env`; all three must be set to use the same provider.
- **RAG has no sources**: add a webpage or upload a supported file on the Generate page, then select it before starting the RAG run.
- **Address already in use**: another process is using port 8000 (backend) or 5173 (frontend). Stop that process or choose a free port; if you change the backend port, set `VITE_API_PROXY_TARGET` before starting Vite.
- **Python version or install errors**: verify `python --version` is at least 3.10, activate the intended virtual environment, and rerun `python -m pip install -r requirements.txt`.
- **Node package errors**: verify `node --version` is at least 20, then run `npm ci` from inside `frontend/`.

## Deployment notes

The commands above start a local development instance. To host the app for other people, build the frontend with `npm run build`, deploy the built `frontend/dist/` directory, and deploy the FastAPI application on a reachable host. Set `VITE_API_BASE_URL` to the public API base URL when UI and API use different origins; set the API environment variable `FRONTEND_ORIGINS` to the exact comma-separated UI origins (scheme and hostname, with no path). Use HTTPS, keep provider keys in the deployment platform's secret store, and persist `DATABASE_PATH` and `outputs/` on durable storage. The in-memory job queue and progress events are for a single API process; this repository does not provide a multi-worker durable queue or multi-user authentication. Do not expose the development server or API publicly as-is.




