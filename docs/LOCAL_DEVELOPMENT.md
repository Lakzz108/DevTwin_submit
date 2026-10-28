# Running DevTwin locally

DevTwin uses Neo4j for its repository graph/vector index and a local FastEmbed
model for semantic retrieval. It does not require an OpenAI key or send
repository source to a paid API. Optional natural-language answers use a local
Ollama server; answer generation is disabled unless enabled in `.env`.

## Start the backend

1. Start the DevTwin database in Neo4j Desktop and ensure it is **Running**.
2. From the DevTwin project directory, run:

   ```sh
   .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
   ```

3. Keep that terminal open. API docs are at
   [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

If port 8000 is already in use, a backend is probably still running. Use it or
press Control+C in its terminal before starting another copy.

## Start the web interface

1. In a second terminal, run:

   ```sh
   cd frontend
   npm run dev
   ```

2. Open the Vite URL, normally
   [http://127.0.0.1:5173](http://127.0.0.1:5173).
3. Paste a public GitHub repository URL and select **Analyze repository**.
   DevTwin clones/fetches it into `data/repositories/`, ignored by Git, then
   runs the current analysis, graph, and embedding pipeline. Select **Local
   folder** to analyze a directory already accessible to the backend.

DevTwin starts with no repository selected and sends no analysis request on
page load. To reopen a saved analysis after refresh, enter the same URL/path
and choose **Open saved analysis**. Choose **Re-analyze** to fetch the latest
public GitHub revision and replace the Neo4j graph snapshot for that checkout.

## What the current analysis explains

The dashboard uses README/project metadata, package manifests, source
docstrings, extracted entities, imports, and graph counts as evidence. When a
purpose is not documented, the UI says there is not enough information rather
than guessing from a filename. Folder rows show source-file counts; they do not
claim a folder's purpose based on its name.

Tree-sitter structural extraction is enabled for Python, JavaScript, JSX,
TypeScript, TSX, Java, C, C++, C#, and Go. It extracts declarations and common
imports for these grammars; extraction is syntax-aware, not a complete compiler
or runtime analyzer. Internal imports resolve to files or packages when the
repository layout makes the target unambiguous. Static calls link only when a
unique in-repository target can be identified. API route detection currently
covers common FastAPI/Flask decorators and Express route calls. Import counts
separate internal, external, and unresolved references.

The graph includes project/folder/file containment, declarations, methods,
imports, exports, inheritance/implementation, unambiguous static calls, API
handlers, and code-chunk links. The UI offers project-structure,
selected-component, dependency, and impact views with filters, search, zoom,
pan, and component facts. Relationship edges are static evidence; runtime
control flow is not inferred. File explanations use source comments/docstrings
and parsed facts.

Question retrieval uses local embeddings to find code chunks and expands from
those chunk nodes through a bounded two-hop Neo4j graph neighborhood. When
enabled and a local Ollama server is running, DevTwin generates an answer from
only those retrieved chunks and graph relationships; the response still
includes the evidence separately. To enable it, set
`DEVTWIN_LLM_ENABLED=true` in `.env` and optionally set
`DEVTWIN_LLM_MODEL` and `DEVTWIN_LLM_BASE_URL`. DevTwin never downloads the
model. If Ollama is unavailable, retrieval results are still returned with a
clear answer-generation status. Private GitHub repositories are not supported. Cloned
repositories persist under the ignored `data/repositories/` directory until
manually removed.

## If Neo4j is unavailable

Confirm the Neo4j Desktop instance is running and the URI, username, and
password in the project-root `.env` match it. Keep `.env` private; never commit
it.
