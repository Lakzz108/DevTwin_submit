# Running DevTwin locally

DevTwin uses a small local embedding model and your local Neo4j instance. It
does not need an OpenAI API key or send repository code to a paid AI API.

## Start the backend

1. Start the DevTwin database in Neo4j Desktop and make sure its status is
   **Running**.
2. Open Terminal in the DevTwin project folder and run:

   ```sh
   .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
   ```

3. Leave this Terminal window running. The API documentation is available at
   [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

## Start the web interface

1. Open a second Terminal window in the DevTwin project folder.
2. Run:

   ```sh
   cd frontend
   npm run dev
   ```

3. Open the local address printed by Vite, normally
   [http://127.0.0.1:5173](http://127.0.0.1:5173).
4. Enter the repository folder path on the computer running the backend, then
   select **Analyze repository**. When it finishes, ask a question or explore a
   file's dependencies and potential impact.

DevTwin starts with no repository selected. After a browser refresh, enter the
folder path again and select **Open saved analysis** to reopen the graph without
re-running analysis or embeddings. This keeps an old repository from appearing
automatically when the app opens.

The repository map appears below the ingestion summary. Expand a file row to
see its imports, classes/functions, and class methods. Use **Focus on one file**
to reduce the list to a single component. Turn on **Show code chunks** only when
you also need to inspect retrieval chunk relationships. If the repository was
already analyzed, enter the same folder path and select **Open saved analysis**;
DevTwin finds its saved graph from the path, without asking you for an ID or
repeating analysis and embedding.

The first analysis embeds Python source chunks locally. Later questions also
run locally and return semantically relevant chunks with neighboring graph
entities and relationships. The current interface displays retrieved evidence;
natural-language answer generation by an LLM has not been connected yet.

Tree-sitter entity extraction and semantic code chunking currently support
Python. The repository scanner also recognizes JavaScript, TypeScript, Java,
and C/C++ file extensions, but those files are currently represented as files
only; their language-specific symbols and code chunks are not extracted yet.

## If the database connection fails

Check that Neo4j Desktop shows the instance as **Running**, and confirm that
the URI, username, and password in the project-root `.env` file match that
instance. Keep `.env` private; it must not be committed.
