"""Local FastAPI interface for DevTwin repository analysis and retrieval."""

import hashlib
import logging
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from neo4j.exceptions import Neo4jError
from pydantic import BaseModel, Field, field_validator


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PARSER_PATH = PROJECT_ROOT / "parser"
if str(PARSER_PATH) not in sys.path:
    sys.path.insert(0, str(PARSER_PATH))

from repository_analyzer import analyze_repository  # noqa: E402
from github_repository import (  # noqa: E402
    GitHubRepositoryError,
    fetch_public_repository,
)
from repository_chunker import build_repository_chunks  # noqa: E402
from repository_understanding import (  # noqa: E402
    build_project_understanding,
    summarize_file,
)
from graph.chunk_graph import add_chunks_to_graph  # noqa: E402
from graph.neo4j_queries import Neo4jGraphReader  # noqa: E402
from graph.neo4j_writer import Neo4jGraphWriter  # noqa: E402
from graph_builder import build_graph_data  # noqa: E402
from rag.embedding_service import FastEmbedEmbeddingProvider  # noqa: E402
from rag.graphrag_retriever import GraphRAGRetriever  # noqa: E402
from rag.neo4j_vector_store import Neo4jVectorStore  # noqa: E402


app = FastAPI(
    title="DevTwin API",
    description=(
        "Repository graph and GraphRAG retrieval API. Retrieval results include "
        "code evidence and graph context; they are not generated LLM answers."
    ),
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

_embedding_provider = None
_repository_cache = {}
logger = logging.getLogger(__name__)


class RepositoryRequest(BaseModel):
    path: str = Field(..., min_length=1, description="Path to a local repository")
    repository_id: str | None = Field(
        default=None,
        min_length=1,
        description="Optional stable ID; defaults to a hash of the resolved path",
    )


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value):
        if not value.strip():
            raise ValueError("question must not be blank")
        return value.strip()


class GitHubRepositoryRequest(BaseModel):
    url: str = Field(..., min_length=1, description="Public GitHub repository URL")


class FileSummaryRequest(BaseModel):
    repository_path: str = Field(..., min_length=1)
    file: str = Field(..., min_length=1)


def get_embedding_provider():
    """Load the small local embedding model once per API process."""

    global _embedding_provider
    if _embedding_provider is None:
        _embedding_provider = FastEmbedEmbeddingProvider()
    return _embedding_provider


def make_repository_id(repository_path):
    """Create a stable ID without exposing a user's full local path."""

    canonical_path = str(Path(repository_path).resolve())
    digest = hashlib.sha256(canonical_path.encode("utf-8")).hexdigest()[:12]
    return f"local-{digest}"


def open_writer():
    try:
        return Neo4jGraphWriter.from_env()
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=(
                "Neo4j is unavailable. Start Neo4j and check the connection "
                "settings in the project .env file."
            ),
        ) from error


@app.exception_handler(RequestValidationError)
async def invalid_request_handler(request, error):
    """Return a small, readable validation message without internal details."""

    invalid_fields = {
        str(item.get("loc", ())[-1])
        for item in error.errors()
        if item.get("loc")
    }
    if "question" in invalid_fields:
        message = "Please enter a question first."
    elif "path" in invalid_fields:
        message = "Please provide a repository folder path."
    elif "url" in invalid_fields:
        message = "Please provide a public GitHub repository URL."
    else:
        message = "One or more request values are invalid. Check them and try again."

    return JSONResponse(
        status_code=422,
        content={"detail": message},
    )


@app.exception_handler(Neo4jError)
async def neo4j_error_handler(request, error):
    """Turn database errors into a safe service-unavailable response."""

    logger.warning("Neo4j request failed: %s", type(error).__name__)
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Neo4j is unavailable. Start Neo4j and try again.",
        },
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request, error):
    """Keep internal tracebacks in backend logs, never in the API response."""

    logger.exception("Unhandled DevTwin API error")
    return JSONResponse(
        status_code=500,
        content={
            "detail": (
                "DevTwin could not complete this request. Check the repository "
                "and Neo4j, then try again."
            ),
        },
    )


@app.get("/health")
def health():
    """Report whether the local API process is responding."""

    return {"status": "ok", "embedding_model": "BAAI/bge-small-en-v1.5"}


@app.post("/repositories")
def ingest_repository(request: RepositoryRequest):
    """Analyze a local repository and write its graph and code vectors."""

    repository_path = Path(request.path).expanduser().resolve()
    if not repository_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Repository folder was not found. Check the path and try again.",
        )
    if not repository_path.is_dir():
        raise HTTPException(
            status_code=400,
            detail="Repository path must point to a folder.",
        )

    repository_id = request.repository_id or make_repository_id(repository_path)
    return _ingest_repository(repository_path, repository_id)


@app.post("/repositories/github")
def ingest_github_repository(request: GitHubRepositoryRequest):
    """Clone/fetch a public GitHub repository, then run the existing pipeline."""

    try:
        repository_path, repository_name = fetch_public_repository(request.url)
    except GitHubRepositoryError as error:
        message = str(error)
        status_code = 422 if message.startswith(("Enter ", "Use ", "The GitHub")) else 400
        raise HTTPException(status_code=status_code, detail=message) from error
    result = _ingest_repository(
        repository_path,
        make_repository_id(repository_path),
        repository_name=repository_name,
    )
    result.setdefault("repository_name", repository_name)
    if isinstance(result.get("project_understanding"), dict):
        result["project_understanding"].setdefault("repository_name", repository_name)
    result["source"] = "github"
    return result


def _ingest_repository(repository_path, repository_id, repository_name=None):
    """Run analysis, graph construction, embeddings and persistence."""

    try:
        analysis = analyze_repository(repository_path)
        analysis["repository_name"] = repository_name or Path(repository_path).name
        if not analysis["files"]:
            raise HTTPException(
                status_code=422,
                detail="No supported source files were found in this repository.",
            )
        chunks = build_repository_chunks(
            repository_path,
            repository_id=repository_id,
            analysis_result=analysis,
        )
        graph_data = add_chunks_to_graph(build_graph_data(analysis), chunks)
        _repository_cache[str(Path(repository_path).resolve())] = {
            "analysis": analysis,
            "graph_data": graph_data,
            "chunks": chunks,
        }
        project_understanding = build_project_understanding(
            repository_path,
            analysis,
            graph_data,
            chunks,
        )
        provider = get_embedding_provider()
        embeddings = provider.embed_chunks(chunks)
    except HTTPException:
        raise
    except (OSError, UnicodeError, ValueError) as error:
        raise HTTPException(
            status_code=400,
            detail="Could not read repository source files. Check the folder and permissions.",
        ) from error

    writer = open_writer()
    try:
        graph_result = writer.write_graph(repository_id, graph_data)
        vector_store = Neo4jVectorStore(writer.driver, writer.database)
        vector_store.ensure_index()
        embedding_count = vector_store.store_embeddings(repository_id, embeddings)
    finally:
        writer.close()

    return {
        "repository_id": repository_id,
        "repository_path": str(repository_path),
        "repository_name": project_understanding["repository_name"],
        "project_understanding": project_understanding,
        "files_analyzed": len(analysis["files"]),
        "chunks_embedded": embedding_count,
        **graph_result,
    }


@app.post("/repositories/open")
def open_existing_repository(request: RepositoryRequest):
    """Open a previously analyzed repository using its folder path."""

    repository_path = Path(request.path).expanduser().resolve()
    if not repository_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Repository folder was not found. Check the path and try again.",
        )
    if not repository_path.is_dir():
        raise HTTPException(
            status_code=400,
            detail="Repository path must point to a folder.",
        )

    return _open_repository(repository_path)


@app.post("/repositories/github/open")
def open_existing_github_repository(request: GitHubRepositoryRequest):
    """Fetch the public repository and open its saved graph by its URL."""

    try:
        repository_path, repository_name = fetch_public_repository(request.url, refresh=False)
    except GitHubRepositoryError as error:
        message = str(error)
        status_code = 422 if message.startswith(("Enter ", "Use ", "The GitHub")) else 400
        raise HTTPException(status_code=status_code, detail=message) from error
    result = _open_repository(repository_path)
    result["repository_name"] = repository_name
    result["project_understanding"]["repository_name"] = repository_name
    result["source"] = "github"
    return result


def _open_repository(repository_path):
    """Open saved graph data and rebuild source-grounded overview facts."""

    repository_path = Path(repository_path).resolve()
    repository_id = make_repository_id(repository_path)
    writer = open_writer()
    try:
        graph = Neo4jGraphReader(
            writer.driver,
            writer.database,
        ).get_repository_graph(repository_id, limit=300)
    finally:
        writer.close()

    if graph["total_nodes"] == 0:
        raise HTTPException(
            status_code=404,
            detail="This folder has not been analyzed by DevTwin yet.",
        )

    analysis = analyze_repository(repository_path)
    chunks = build_repository_chunks(
        repository_path,
        repository_id=repository_id,
        analysis_result=analysis,
    )
    graph_data = add_chunks_to_graph(build_graph_data(analysis), chunks)
    _repository_cache[str(repository_path)] = {
        "analysis": analysis,
        "graph_data": graph_data,
        "chunks": chunks,
    }
    project_understanding = build_project_understanding(
        repository_path,
        analysis,
        graph_data,
        chunks,
    )

    return {
        "repository_id": repository_id,
        "repository_path": str(repository_path),
        "repository_name": project_understanding["repository_name"],
        "project_understanding": project_understanding,
        "files_analyzed": sum(node["type"] == "FILE" for node in graph["nodes"]),
        "graph": graph,
    }


@app.post("/repositories/file-summary")
def repository_file_summary(request: FileSummaryRequest):
    """Return source/docstring facts for one file inside an analyzed folder."""

    root = Path(request.repository_path).expanduser().resolve()
    if not root.is_dir():
        raise HTTPException(status_code=404, detail="Repository folder was not found.")
    try:
        cached = _repository_cache.get(str(root))
        if cached is None:
            analysis = analyze_repository(root)
            chunks = build_repository_chunks(root, analysis_result=analysis)
            graph_data = add_chunks_to_graph(build_graph_data(analysis), chunks)
            cached = {"analysis": analysis, "graph_data": graph_data, "chunks": chunks}
            _repository_cache[str(root)] = cached
        return summarize_file(root, request.file, cached["analysis"], cached["graph_data"])
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except (OSError, UnicodeError) as error:
        raise HTTPException(status_code=400, detail="Could not read the selected source file.") from error


@app.post("/repositories/{repository_id}/query")
def query_repository(repository_id: str, request: QueryRequest):
    """Return semantic code matches with their connected graph context."""

    writer = open_writer()
    try:
        retriever = GraphRAGRetriever(
            get_embedding_provider(),
            Neo4jVectorStore(writer.driver, writer.database),
            Neo4jGraphReader(writer.driver, writer.database),
        )
        try:
            return retriever.retrieve(
                repository_id,
                request.question,
                top_k=request.top_k,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
    finally:
        writer.close()


@app.get("/repositories/{repository_id}/graph")
def repository_graph(
    repository_id: str,
    limit: int = Query(default=300, ge=1, le=500),
    include_chunks: bool = False,
):
    """Return repository nodes and relationships for the graph explorer."""

    writer = open_writer()
    try:
        try:
            return Neo4jGraphReader(
                writer.driver,
                writer.database,
            ).get_repository_graph(
                repository_id,
                limit=limit,
                include_chunks=include_chunks,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
    finally:
        writer.close()


@app.get("/repositories/{repository_id}/dependencies")
def repository_dependencies(
    repository_id: str,
    file: str,
    max_depth: int = 1,
):
    """List files/components reachable through outgoing graph edges."""

    writer = open_writer()
    try:
        try:
            dependencies = Neo4jGraphReader(
                writer.driver,
                writer.database,
            ).find_dependencies(
                repository_id,
                f"file:{file}",
                max_depth=max_depth,
            )
            # A file's DEFINES and CONTAINS_CHUNK edges are structural details,
            # not file dependencies. Keep this view focused on imported files
            # and external modules.
            dependencies = [
                node for node in dependencies
                if node.get("type") in {"FILE", "MODULE"}
                and node.get("file") != file
            ]
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {
            "repository_id": repository_id,
            "file": file,
            "dependencies": dependencies,
        }
    finally:
        writer.close()


@app.get("/repositories/{repository_id}/impact")
def repository_impact(
    repository_id: str,
    file: str,
    max_depth: int = 3,
):
    """List graph nodes that may be affected by a file change."""

    writer = open_writer()
    try:
        try:
            impacted = Neo4jGraphReader(
                writer.driver,
                writer.database,
            ).find_impact(
                repository_id,
                f"file:{file}",
                max_depth=max_depth,
            )
            impacted = [
                node for node in impacted
                if node.get("type") != "CODE_CHUNK"
            ]
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {
            "repository_id": repository_id,
            "file": file,
            "impacted_components": impacted,
        }
    finally:
        writer.close()
