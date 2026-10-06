import { useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: { "Content-Type": "application/json", ...options.headers },
    });
  } catch {
    throw new Error("Backend is unavailable. Please start the DevTwin backend.");
  }

  let body = null;
  try {
    body = await response.json();
  } catch {
    // A proxy or server may return an empty/non-JSON error page.
  }
  if (!response.ok) {
    if (response.status === 503) {
      throw new Error(body?.detail || "Neo4j is unavailable. Start Neo4j and try again.");
    }
    if (response.status >= 500) {
      throw new Error(body?.detail || "DevTwin could not complete this request. Check the repository and Neo4j, then try again.");
    }
    throw new Error(body?.detail || `Request failed (${response.status}). Check the repository path and try again.`);
  }
  if (body === null) throw new Error("DevTwin received an unexpected response. Please retry.");
  return body;
}

function App() {
  const [repositoryPath, setRepositoryPath] = useState("");
  const [repositoryId, setRepositoryId] = useState("");
  const [question, setQuestion] = useState("");
  const [file, setFile] = useState("");
  const [topK, setTopK] = useState(5);
  const [ingestion, setIngestion] = useState(null);
  const [graphData, setGraphData] = useState(null);
  const [queryResult, setQueryResult] = useState(null);
  const [dependencyResult, setDependencyResult] = useState(null);
  const [impactResult, setImpactResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function runAction(action) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (caught) {
      setError(caught.message);
    } finally {
      setBusy(false);
    }
  }

  function ingest() {
    return runAction(async () => {
      const result = await request("/repositories", {
        method: "POST",
        body: JSON.stringify({ path: repositoryPath.trim() }),
      });
      const savedGraph = await request(
        `/repositories/${encodeURIComponent(result.repository_id)}/graph?limit=300`,
      );
      setIngestion(result);
      setRepositoryId(result.repository_id);
      setGraphData(savedGraph);
      setQueryResult(null);
      setDependencyResult(null);
      setImpactResult(null);
    });
  }

  function loadExistingGraph(event) {
    event?.preventDefault?.();
    return runAction(async () => {
      const result = await request("/repositories/open", {
        method: "POST",
        body: JSON.stringify({ path: repositoryPath.trim() }),
      });
      const id = result.repository_id;
      const storedSummary = {
        repository_id: id,
        files_analyzed: result.files_analyzed,
        nodes_processed: result.graph.total_nodes,
        relationships_processed: result.graph.total_relationships,
      };
      setRepositoryId(id);
      setIngestion(storedSummary);
      setGraphData(result.graph);
      setQueryResult(null);
      setDependencyResult(null);
      setImpactResult(null);
    });
  }

  function resetRepository() {
    clearSelectedRepository();
    setRepositoryPath("");
  }

  function clearSelectedRepository() {
    setRepositoryId("");
    setIngestion(null);
    setGraphData(null);
    setQueryResult(null);
    setDependencyResult(null);
    setImpactResult(null);
    setQuestion("");
    setFile("");
    setError("");
  }

  function changeRepositoryPath(value) {
    setRepositoryPath(value);
    if (repositoryId) clearSelectedRepository();
  }

  function askQuestion(event) {
    event.preventDefault();
    return runAction(async () => {
      const result = await request(
        `/repositories/${encodeURIComponent(repositoryId)}/query`,
        {
          method: "POST",
          body: JSON.stringify({ question, top_k: Number(topK) }),
        },
      );
      setQueryResult(result);
    });
  }

  function lookupGraph(kind) {
    return runAction(async () => {
      const params = new URLSearchParams({ file, max_depth: kind === "impact" ? "3" : "1" });
      const result = await request(
        `/repositories/${encodeURIComponent(repositoryId)}/${kind}?${params}`,
      );
      if (kind === "impact") setImpactResult(result);
      else setDependencyResult(result);
    });
  }

  function toggleCodeChunks(includeChunks) {
    return runAction(async () => {
      const params = new URLSearchParams({
        limit: "500",
        include_chunks: String(includeChunks),
      });
      const result = await request(
        `/repositories/${encodeURIComponent(repositoryId)}/graph?${params}`,
      );
      setGraphData(result);
    });
  }

  const ready = Boolean(repositoryId);

  return (
    <main className="page-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="DevTwin home">
          <span className="brand-mark">D</span>
          <span>dev<span className="brand-light">twin</span></span>
        </a>
        <span className="product-label">REPOSITORY INTELLIGENCE</span>
        <span className="local-badge"><i /> LOCAL ANALYSIS</span>
      </header>

      <section className="hero" id="top">
        <div className="eyebrow"><span /> CODEBASE COMPANION</div>
        <h1>Understand the<br /><em>whole picture.</em></h1>
        <p className="hero-copy">
          Connect code meaning with the relationships between files,
          symbols, and components.
        </p>

        <section className="panel repository-panel">
          <div className="panel-heading">
            <div className="step-number">01</div>
            <div>
              <h2>Connect a repository</h2>
              <p>Enter a folder path that the DevTwin backend can access.</p>
            </div>
          </div>
          <form
            className="repository-form"
            onSubmit={(event) => { event.preventDefault(); ingest(); }}
          >
            <label className="sr-only" htmlFor="repository-path">Repository folder path</label>
            <input
              id="repository-path"
              value={repositoryPath}
              onChange={(event) => changeRepositoryPath(event.target.value)}
              placeholder="/Users/you/Projects/my-app"
              disabled={busy}
              required
            />
            <div className="repository-actions">
              <button className="button button-primary" type="submit" disabled={busy || !repositoryPath.trim()}>
                {busy ? "Working…" : "Analyze repository"}
                <span aria-hidden="true">↗</span>
              </button>
              <button
                className="button button-outline"
                type="button"
                onClick={loadExistingGraph}
                disabled={busy || !repositoryPath.trim()}
                title="Open the saved analysis for this folder without analyzing it again"
              >
                Open saved analysis
              </button>
            </div>
          </form>
          {ingestion && (
            <div className="ingestion-summary" role="status">
              <span className="success-dot" />
              <strong>Repository ready</strong>
              {ingestion.files_analyzed != null && <span>{ingestion.files_analyzed} files</span>}
              {ingestion.chunks_embedded != null && <span>{ingestion.chunks_embedded} code chunks</span>}
              {ingestion.nodes_processed != null && <span>{ingestion.nodes_processed} graph nodes</span>}
              {ingestion.relationships_processed != null && <span>{ingestion.relationships_processed} relationships</span>}
              <button className="clear-repository" type="button" onClick={resetRepository} disabled={busy}>
                Clear repository
              </button>
            </div>
          )}
        </section>
        {graphData && (
          <GraphExplorer graph={graphData} onIncludeChunksChange={toggleCodeChunks} />
        )}
      </section>

      {error && <div className="error-banner" role="alert">{error}</div>}

      {ready ? <section className="workspace is-ready">
        <div className="workspace-header">
          <div className="step-number">02</div>
          <div>
            <h2>Ask your codebase</h2>
            <p>Semantic matches are expanded with connected knowledge-graph context.</p>
          </div>
        </div>

        <div className="workspace-grid">
          <section className="panel query-panel">
            <div className="section-kicker">REPOSITORY QUESTION</div>
            <form onSubmit={askQuestion}>
              <label className="sr-only" htmlFor="question">Ask a question</label>
              <textarea
                id="question"
                rows="4"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Where is authentication implemented?"
                disabled={!ready}
                required
              />
              <div className="query-controls">
                <label className="top-k-label" htmlFor="top-k">Evidence chunks</label>
                <select id="top-k" value={topK} onChange={(event) => setTopK(event.target.value)} disabled={!ready}>
                  {[3, 5, 8, 10].map((number) => <option key={number} value={number}>{number}</option>)}
                </select>
                <button className="button button-dark" disabled={!ready || busy || !question.trim()}>
                  Retrieve context <span aria-hidden="true">→</span>
                </button>
              </div>
            </form>
            {queryResult && <QueryResults result={queryResult} />}
          </section>

          <aside className="panel graph-panel">
            <div className="section-kicker">DEPENDENCY EXPLORER</div>
            <label htmlFor="file-path">Repository-relative file</label>
            <input
              id="file-path"
              value={file}
              onChange={(event) => setFile(event.target.value)}
              placeholder="src/auth/login.py"
              disabled={!ready}
            />
            <div className="graph-actions">
              <button className="button button-outline" onClick={() => lookupGraph("dependencies")} disabled={!ready || busy || !file.trim()}>
                Dependencies
              </button>
              <button className="button button-outline" onClick={() => lookupGraph("impact")} disabled={!ready || busy || !file.trim()}>
                Change impact
              </button>
            </div>
            {dependencyResult && (
              <NodeList title="Dependencies" items={dependencyResult.dependencies} empty="No outgoing dependencies found." />
            )}
            {impactResult && (
              <NodeList title="Potentially affected" items={impactResult.impacted_components} empty="No incoming dependents found." />
            )}
            {!dependencyResult && !impactResult && (
              <p className="helper-copy">Enter a file and explore its connected components.</p>
            )}
          </aside>
        </div>
      </section> : (
        <section className="empty-workspace" aria-live="polite">
          <span className="step-number">02</span>
          <div>
            <h2>Your repository workspace will appear here</h2>
            <p>Select a folder and analyze it to explore its structure and retrieve related code.</p>
          </div>
        </section>
      )}

      <footer className="footer">
        <span>DevTwin <span className="footer-muted">· AI-powered software repository understanding</span></span>
        <span>LOCAL EMBEDDINGS · NEO4J KNOWLEDGE GRAPH</span>
      </footer>
    </main>
  );
}

function QueryResults({ result }) {
  const chunks = result.semantic_chunks || [];
  const graph = result.graph_context || { nodes: [], relationships: [] };
  const nodesById = new Map(graph.nodes.map((node) => [node.id, node]));
  const friendlyName = (id) => {
    const node = nodesById.get(id);
    if (!node) return id.split(":").slice(1).join(":");
    return node.file || node.name || id.split(":").slice(1).join(":");
  };

  return (
    <div className="results" aria-live="polite">
      <div className="results-heading">
        <div>
          <div className="section-kicker">SEMANTIC MATCHES</div>
          <h3>{chunks.length} relevant code {chunks.length === 1 ? "chunk" : "chunks"}</h3>
        </div>
        <span className="graph-count">{graph.nodes.length} graph nodes</span>
      </div>
      {chunks.length === 0 ? (
        <p className="empty-state">No matching code chunks were found for this question.</p>
      ) : chunks.map((chunk) => (
        <article className="evidence-card" key={chunk.id}>
          <div className="evidence-meta">
            <code>{chunk.file}</code>
            <span>{chunk.kind || "CODE"}{chunk.symbol ? ` · ${chunk.symbol}` : ""}</span>
            <span>{Math.round(chunk.score * 100)}% match</span>
          </div>
          <pre>{chunk.content}</pre>
        </article>
      ))}
      <div className="graph-context">
        <div className="section-kicker">GRAPH CONTEXT</div>
        {graph.relationships.length === 0 ? (
          <p className="empty-state">No direct graph relationships for these matches.</p>
        ) : graph.relationships.map((edge, index) => (
          <div className="edge-row" key={`${edge.source}-${edge.relationship}-${edge.target}-${index}`}>
            <code>{friendlyName(edge.source)}</code><span>{edge.relationship.replaceAll("_", " ")}</span><code>{friendlyName(edge.target)}</code>
          </div>
        ))}
      </div>
      <p className="retrieval-note">This view shows retrieved evidence and graph context. A generated natural-language answer is not connected yet.</p>
    </div>
  );
}

function NodeList({ title, items, empty }) {
  return (
    <div className="node-list">
      <div className="section-kicker">{title.toUpperCase()}</div>
      {items.length === 0 ? <p className="empty-state">{empty}</p> : items.map((item) => (
        <div className="node-row" key={item.id}>
          <span className={`node-type node-type-${String(item.type || "unknown").toLowerCase()}`}>{item.type}</span>
          <code>{item.file || item.name || item.id}</code>
          {item.depth && <span className="node-depth">depth {item.depth}</span>}
        </div>
      ))}
    </div>
  );
}

function GraphExplorer({ graph, onIncludeChunksChange }) {
  const [selectedFileId, setSelectedFileId] = useState("");
  const [search, setSearch] = useState("");
  const nodesById = new Map(graph.nodes.map((node) => [node.id, node]));
  const files = graph.nodes
    .filter((node) => node.type === "FILE")
    .sort((left, right) => left.name.localeCompare(right.name));
  const normalizedSearch = search.trim().toLowerCase();
  const visibleFiles = files.filter((file) => {
    if (selectedFileId && file.id !== selectedFileId) return false;
    if (!normalizedSearch) return true;
    const relatedSymbols = graph.relationships
      .filter((edge) => edge.source === file.id && edge.relationship === "DEFINES")
      .map((edge) => nodesById.get(edge.target)?.name || "");
    const relatedImports = graph.relationships
      .filter((edge) => edge.source === file.id && edge.relationship === "IMPORTS")
      .map((edge) => nodesById.get(edge.target)?.name || "");
    return [file.name, ...relatedSymbols, ...relatedImports]
      .some((value) => value.toLowerCase().includes(normalizedSearch));
  });

  function labelFor(id) {
    const node = nodesById.get(id);
    if (!node) return id;
    if (node.type === "FILE") return node.file || node.name;
    if (node.type === "MODULE") return node.name;
    return node.name || node.symbol || node.id;
  }

  function edgesFrom(sourceId, relationship) {
    return graph.relationships.filter(
      (edge) => edge.source === sourceId && edge.relationship === relationship,
    );
  }

  function RelationshipGroup({ title, edges }) {
    if (!edges.length) return null;
    return (
      <div className="file-relation-group">
        <div className="file-relation-title">{title}</div>
        <ul>
          {edges.map((edge) => (
            <li key={`${edge.source}-${edge.relationship}-${edge.target}`}>
              <span className="relation-arrow">{edge.relationship} →</span>
              <span className="relation-target">
                {labelFor(edge.target)}
                {nodesById.get(edge.target)?.type && (
                  <small>{nodesById.get(edge.target).type.toLowerCase()}</small>
                )}
              </span>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <section className="panel repository-graph" aria-label="Repository graph">
      <div className="graph-title-row">
        <div>
          <div className="section-kicker">REPOSITORY MAP</div>
          <h2>How the code is connected</h2>
          <p>Relationships are grouped by file so you can follow them without crossing lines.</p>
        </div>
        <div className="graph-total-badges">
          <span><strong>{graph.total_nodes}</strong> nodes</span>
          <span><strong>{graph.total_relationships}</strong> relationships</span>
        </div>
      </div>

      {graph.truncated && (
        <p className="graph-truncated" role="status">
          This saved graph contains more relationships than are shown here. Increase the graph result limit from the API to view all of them.
        </p>
      )}

      <div className="graph-controls">
        <label htmlFor="graph-file-select">Focus on one file</label>
        <select
          id="graph-file-select"
          value={selectedFileId}
          onChange={(event) => setSelectedFileId(event.target.value)}
        >
          <option value="">All files</option>
          {files.map((node) => <option key={node.id} value={node.id}>{node.name}</option>)}
        </select>
        <label className="sr-only" htmlFor="graph-search">Search files, symbols, or imports</label>
        <input
          id="graph-search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search files, symbols, or imports"
        />
        <label className="chunk-toggle">
          <input
            type="checkbox"
            checked={Boolean(graph.include_chunks)}
            onChange={(event) => onIncludeChunksChange(event.target.checked)}
          />
          Show code chunks
        </label>
      </div>

      {visibleFiles.length === 0 ? (
        <p className="empty-state">No files match that search.</p>
      ) : (
        <div className="file-graph-list">
          {visibleFiles.map((file, index) => {
            const imports = edgesFrom(file.id, "IMPORTS");
            const definitions = edgesFrom(file.id, "DEFINES");
            const definedIds = definitions.map((edge) => edge.target);
            const methods = graph.relationships.filter(
              (edge) => edge.relationship === "HAS_METHOD" && definedIds.includes(edge.source),
            );
            const chunks = edgesFrom(file.id, "CONTAINS_CHUNK");

            return (
              <details
                className="file-graph-card"
                key={file.id}
                open={selectedFileId === file.id || (!selectedFileId && index === 0)}
              >
                <summary>
                  <span className="file-summary-main">
                    <span className="file-node-icon">FILE</span>
                    <code>{file.name}</code>
                  </span>
                  <span className="file-summary-counts">
                    <span>{imports.length} imports</span>
                    <span>{definitions.length} symbols</span>
                    <span>{methods.length} methods</span>
                    {graph.include_chunks && <span>{chunks.length} chunks</span>}
                  </span>
                </summary>
                <div className="file-graph-content">
                  <RelationshipGroup
                    title="IMPORTS"
                    edges={imports}
                  />
                  <div className="file-relation-group">
                    <div className="file-relation-title">DEFINES</div>
                    {definitions.length === 0 ? (
                      <p className="empty-state">No classes or functions were extracted from this file.</p>
                    ) : (
                      <ul className="defined-symbol-list">
                        {definitions.map((edge) => {
                          const symbol = nodesById.get(edge.target);
                          const symbolMethods = methods.filter((method) => method.source === edge.target);
                          const describedChunks = graph.relationships.filter(
                            (relationship) => relationship.relationship === "DESCRIBES"
                              && relationship.target === edge.target,
                          );
                          return (
                            <li key={edge.target}>
                              <div className="defined-symbol">
                                <span className={`node-type node-type-${String(symbol?.type || "symbol").toLowerCase()}`}>{symbol?.type || "SYMBOL"}</span>
                                <strong>{labelFor(edge.target)}</strong>
                              </div>
                              {symbolMethods.length > 0 && (
                                <div className="method-branch">
                                  <span>HAS_METHOD</span>
                                  {symbolMethods.map((method) => (
                                    <code key={method.target}>{labelFor(method.target)}</code>
                                  ))}
                                </div>
                              )}
                              {graph.include_chunks && describedChunks.length > 0 && (
                                <div className="method-branch chunk-branch">
                                  <span>DESCRIBED BY</span>
                                  {describedChunks.map((chunkEdge) => (
                                    <code key={chunkEdge.source}>{labelFor(chunkEdge.source)}</code>
                                  ))}
                                </div>
                              )}
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </div>
                  {graph.include_chunks && (
                    <RelationshipGroup
                      title="CONTAINS CODE CHUNKS"
                      edges={chunks}
                    />
                  )}
                </div>
              </details>
            );
          })}
        </div>
      )}
      <p className="graph-explainer">
        Each row is a FILE node. Expand it to follow IMPORTS, DEFINES, and HAS_METHOD relationships. Imported modules are shown even when they are outside this repository.
      </p>
    </section>
  );
}

export default App;
