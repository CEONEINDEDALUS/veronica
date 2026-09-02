<div align="center">

# Veronica

**Private, local-first RAG assistant for your own documents.**

Point it at your files, connect it to a local [Ollama](https://ollama.com) server,
and ask questions grounded in your data. Nothing leaves your machine.

[Features](#features) · [Screenshots](#screenshots) · [Setup](#setup) · [Usage](#using-it) · [Project Layout](#project-layout)

</div>

---

## Features

- **Any number of uploads** — multi-file picker or whole-folder ingestion, batched embeddings, background thread so the UI never freezes.
- **Multiple knowledge bases** — create, switch, and delete separate document collections (e.g. "Work", "Legal", "Research").
- **Broad file support** — PDF, DOCX, TXT/MD, CSV/TSV, XLSX/XLS, HTML, JSON, and common source-code files.
- **Ollama backend** — native Ollama API for both chat and embeddings. Fully local.
- **Two embedding backends** — Ollama embedding models (e.g. `nomic-embed-text`) or local `sentence-transformers` (no server needed).
- **Streaming chat** with source attribution and live retrieval diagnostics (chunks used, overflow, whether compression kicked in, context window size).
- **Persistent storage** — ChromaDB-backed, survives restarts.
- **Polished dark UI** — PyQt6, custom theme, sidebar navigation.

## Why Veronica handles small context windows well

Local models frequently run with modest context windows (many quantized 7B–8B GGUF models default to 2k–8k tokens in Ollama). Most simple RAG demos just stuff the top-k chunks into the prompt and hope it fits — which silently truncates and breaks answers on exactly these models.

Veronica instead:

1. **Detects the real context window** of the selected model (`/api/show` in Ollama), and computes an honest token budget:
   `budget = context_window − reserved_output − reserved_system_prompt − chat_history`.
2. **Greedily fits the most similar chunks** into that budget (fast path, works for the vast majority of queries).
3. If more *relevant* chunks exist than fit, and compression is enabled, it **hierarchically summarizes the overflow** (map → reduce, batched to fit the model's own context, recursively condensed) using the same local model — so highly relevant material gets compressed rather than dropped.
4. As an absolute last resort (context smaller than even one chunk), it truncates a single best-matching chunk rather than failing outright.

All of this is tunable in **Settings**: reserved tokens, compression on/off, compression aggressiveness, chat history length, chunk size/overlap, top-k, similarity floor, etc.

## Screenshots

<table>
  <tr>
    <td width="33.33%" align="center"><b>Chat</b></td>
    <td width="33.33%" align="center"><b>Documents</b></td>
    <td width="33.33%" align="center"><b>Settings</b></td>
  </tr>
  <tr>
    <td width="33.33%" align="center"><img src="https://github.com/user-attachments/assets/845306f3-081b-492d-9031-e72dba812318" alt="Chat interface" width="100%"/></td>
    <td width="33.33%" align="center"><img src="https://github.com/user-attachments/assets/06929b73-1a43-485c-b965-d1e424bd0b54" alt="Documents interface" width="100%"/></td>
    <td width="33.33%" align="center"><img src="https://github.com/user-attachments/assets/bf06da0e-edeb-4951-b5a3-0d36de3c6c1c" alt="Settings interface" width="100%"/></td>
  </tr>
</table>

> Click any screenshot to view it at full resolution.

## Setup

```bash
pip install -r requirements.txt
```

If you want the `sentence_transformers` embedding backend instead of Ollama embeddings, also run:

```bash
pip install sentence-transformers
```

You'll need [Ollama](https://ollama.com) installed and running, with at least one chat model and one embedding model pulled, e.g.:

```bash
ollama pull llama3.1
ollama pull nomic-embed-text
```

## Run

```bash
python main.py
```

## Using it

1. **Documents tab** — create a knowledge base, then "Add files..." or "Add folder..." to ingest as many documents as you want.
2. **Chat tab** — pick your knowledge base and model, then ask away. Each answer shows how many chunks were used and whether context compression was triggered.
3. **Settings tab** — point at a different backend, tune chunking, retrieval, and context-budget behavior.

## Project layout

```
veronica_rag/
├── main.py                  entry point
├── core/
│   ├── config.py             settings model + persistence (~/.veronica_rag/config.json)
│   ├── tokenizer.py          token counting (tiktoken, with heuristic fallback)
│   ├── document_loader.py    PDF/DOCX/CSV/XLSX/HTML/text extraction
│   ├── chunker.py            boundary-aware recursive text splitter
│   ├── embeddings.py         Ollama / sentence-transformers embedding backends
│   ├── vector_store.py       ChromaDB persistent wrapper (per-knowledge-base)
│   ├── llm_client.py         Ollama chat client, context detection
│   ├── context_manager.py    token budgeting + hierarchical overflow summarization
│   └── rag_engine.py         ties ingestion & query together
└── ui/
    ├── style.py              dark violet QSS theme
    ├── main_window.py        sidebar + page stack
    ├── chat_widget.py        streaming chat page
    ├── documents_widget.py   knowledge base & upload management
    ├── settings_widget.py    all tunable options
    └── workers.py            QThread workers (ingest, query, model listing)
```

## Notes on speed

- Embeddings are batched (32 chunks/request) during ingestion.
- All ingestion and generation happens on background `QThread`s — the UI stays responsive while large uploads or long generations run.
- ChromaDB's persistent HNSW index keeps retrieval fast even with large knowledge bases.
