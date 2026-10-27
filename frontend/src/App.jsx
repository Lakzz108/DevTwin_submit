import { useMemo, useRef, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
const NODE_TYPES = ["PROJECT", "FOLDER", "FILE", "CLASS", "INTERFACE", "FUNCTION", "METHOD", "PACKAGE", "MODULE", "API"];
const COLORS = { PROJECT: "#3f6540", FOLDER: "#859b62", FILE: "#527b39", CLASS: "#5876ad", INTERFACE: "#728ac0", FUNCTION: "#ba8436", METHOD: "#a15b8e", PACKAGE: "#9d7849", MODULE: "#4b8987", API: "#bd6652", CODE_CHUNK: "#657078" };
const DEPENDENCY_RELATIONSHIPS = new Set(["IMPORTS", "CALLS", "USES", "DEPENDS_ON", "EXTENDS", "IMPLEMENTS", "HANDLED_BY", "EXPORTS"]);

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, headers: { "Content-Type": "application/json", ...options.headers } });
  } catch {
    throw new Error("Backend is unavailable. Please start the DevTwin backend.");
  }
  let body = null;
  try { body = await response.json(); } catch { /* Handle non-JSON responses below. */ }
  if (!response.ok) {
    if (response.status === 503) throw new Error(body?.detail || "Neo4j is unavailable. Start Neo4j and try again.");
    if (response.status >= 500) throw new Error(body?.detail || "DevTwin could not complete this request. Check the repository and Neo4j, then try again.");
    throw new Error(body?.detail || `Request failed (${response.status}). Check the URL and try again.`);
  }
  if (body === null) throw new Error("DevTwin received an unexpected response. Please retry.");
  return body;
}

function App() {
  const [sourceMode, setSourceMode] = useState("github");
  const [repositoryInput, setRepositoryInput] = useState("");
  const [repositoryId, setRepositoryId] = useState("");
  const [ingestion, setIngestion] = useState(null);
  const [overview, setOverview] = useState(null);
  const [graph, setGraph] = useState(null);
  const [selectedNode, setSelectedNode] = useState(null);
  const [fileSummary, setFileSummary] = useState(null);
  const [question, setQuestion] = useState("");
  const [topK, setTopK] = useState(5);
  const [queryResult, setQueryResult] = useState(null);
  const [dependencyResult, setDependencyResult] = useState(null);
  const [impactResult, setImpactResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [busyMessage, setBusyMessage] = useState("");
  const [error, setError] = useState("");

  async function runAction(action, message = "Working…") {
    setBusy(true); setBusyMessage(message); setError("");
    try { await action(); } catch (caught) { setError(caught.message); }
    finally { setBusy(false); setBusyMessage(""); }
  }

  function clearResults() {
    setRepositoryId(""); setIngestion(null); setOverview(null); setGraph(null);
    setSelectedNode(null); setFileSummary(null); setQueryResult(null);
    setDependencyResult(null); setImpactResult(null);
  }

  async function receiveRepository(result) {
    const savedGraph = result.graph || await request(`/repositories/${encodeURIComponent(result.repository_id)}/graph?limit=500`);
    setRepositoryId(result.repository_id); setIngestion(result);
    setOverview(result.project_understanding || null); setGraph(savedGraph);
    setSelectedNode(null); setFileSummary(null); setQueryResult(null);
    setDependencyResult(null); setImpactResult(null);
  }

  function analyzeRepository() {
    const value = repositoryInput.trim();
    if (!value) return;
    return runAction(async () => {
      const github = sourceMode === "github";
      const result = await request(github ? "/repositories/github" : "/repositories", {
        method: "POST", body: JSON.stringify(github ? { url: value } : { path: value }),
      });
      await receiveRepository(result);
    }, "Fetching, analyzing, and indexing repository…");
  }

  function openSavedRepository() {
    const value = repositoryInput.trim();
    if (!value) return;
    return runAction(async () => {
      const github = sourceMode === "github";
      const result = await request(github ? "/repositories/github/open" : "/repositories/open", {
        method: "POST", body: JSON.stringify(github ? { url: value } : { path: value }),
      });
      await receiveRepository(result);
    }, "Fetching repository and opening saved graph…");
  }

  function askQuestion(event) {
    event.preventDefault();
    if (!repositoryId || !question.trim()) return;
    return runAction(async () => {
      const result = await request(`/repositories/${encodeURIComponent(repositoryId)}/query`, {
        method: "POST", body: JSON.stringify({ question: question.trim(), top_k: Number(topK) }),
      });
      setQueryResult(result);
    }, "Retrieving semantic matches and graph context…");
  }

  async function selectGraphNode(node) {
    setSelectedNode(node); setFileSummary(null);
    setDependencyResult(null); setImpactResult(null);
    if (node?.type !== "FILE" || !ingestion?.repository_path) return;
    await runAction(async () => {
      const summary = await request("/repositories/file-summary", {
        method: "POST",
        body: JSON.stringify({ repository_path: ingestion.repository_path, file: node.file || node.name }),
      });
      setFileSummary(summary);
    }, "Reading selected file…");
  }

  async function lookup(kind) {
    if (!repositoryId || !fileSummary?.file) return;
    return runAction(async () => {
      const params = new URLSearchParams({ file: fileSummary.file, max_depth: kind === "impact" ? "3" : "1" });
      const result = await request(`/repositories/${encodeURIComponent(repositoryId)}/${kind}?${params}`);
      if (kind === "impact") setImpactResult(result); else setDependencyResult(result);
    }, "Exploring graph relationships…");
  }

  const ready = Boolean(repositoryId && graph);
  const githubMode = sourceMode === "github";
  return (
    <main className="page-shell">
      <header className="topbar"><a className="brand" href="#top" aria-label="DevTwin home"><span className="brand-mark">D</span><span>dev<span className="brand-light">twin</span></span></a><span className="product-label">SOFTWARE REPOSITORY UNDERSTANDING</span><span className="local-badge"><i /> LOCAL ANALYSIS</span></header>
      <section className="hero" id="top">
        <div className="eyebrow"><span /> CODEBASE COMPANION</div><h1>Understand the<br /><em>whole picture.</em></h1><p className="hero-copy">Explore what a project does, what each file contributes, and how repository components connect.</p>
        <section className="panel repository-panel"><div className="panel-heading"><div className="step-number">01</div><div><h2>Connect a repository</h2><p>Public GitHub URL is the primary input. Local folders are available for development.</p></div></div>
          <div className="source-tabs" role="tablist" aria-label="Repository source"><button type="button" className={githubMode ? "source-tab active" : "source-tab"} onClick={() => { setSourceMode("github"); clearResults(); }}>GitHub URL</button><button type="button" className={!githubMode ? "source-tab active" : "source-tab"} onClick={() => { setSourceMode("local"); clearResults(); }}>Local folder</button></div>
          <form className="repository-form" onSubmit={(event) => { event.preventDefault(); analyzeRepository(); }}>
            <label className="sr-only" htmlFor="repository-input">{githubMode ? "GitHub repository URL" : "Local repository path"}</label>
            <input id="repository-input" type={githubMode ? "url" : "text"} value={repositoryInput} onChange={(event) => { setRepositoryInput(event.target.value); if (ready) clearResults(); }} placeholder={githubMode ? "https://github.com/owner/repository" : "/Users/you/Projects/my-app"} disabled={busy} required />
            <div className="repository-actions"><button className="button button-primary" type="submit" disabled={busy || !repositoryInput.trim()}>{busy ? busyMessage : "Analyze repository"}<span aria-hidden="true">↗</span></button><button className="button button-outline" type="button" onClick={openSavedRepository} disabled={busy || !repositoryInput.trim()}>Open saved analysis</button>{ready && <button className="button button-outline" type="button" onClick={analyzeRepository} disabled={busy}>Re-analyze</button>}</div>
          </form>
          {ingestion && <div className="ingestion-summary" role="status"><span className="success-dot" /><strong>{ingestion.repository_name || overview?.repository_name || "Repository ready"}</strong><span>{ingestion.files_analyzed} files analyzed</span>{ingestion.source === "github" && <span>Fetched from GitHub</span>}<button className="clear-repository" type="button" onClick={() => { clearResults(); setRepositoryInput(""); }} disabled={busy}>Clear</button></div>}
        </section>
      </section>
      {error && <div className="error-banner" role="alert">{error}</div>}
      {!ready && <section className="empty-workspace" aria-live="polite"><span className="step-number">02</span><div><h2>No repository selected</h2><p>Enter a public GitHub URL to begin. DevTwin fetches and analyzes it only after you select Analyze repository.</p></div></section>}
      {ready && <>
        {overview && <ProjectOverview overview={overview} onReanalyze={analyzeRepository} busy={busy} />}
        <GraphExplorer graph={graph} selectedNodeId={selectedNode?.id} onSelectNode={selectGraphNode} />
        <SelectedComponent node={selectedNode} summary={fileSummary} busy={busy} onDependencies={() => lookup("dependencies")} onImpact={() => lookup("impact")} dependencyResult={dependencyResult} impactResult={impactResult} />
        <section className="workspace is-ready"><div className="workspace-header"><div className="step-number">04</div><div><h2>Ask DevTwin</h2><p>Retrieve code evidence and expand it with connected knowledge-graph context.</p></div></div>
          <section className="panel query-panel"><form onSubmit={askQuestion}><label className="sr-only" htmlFor="question">Ask about this repository</label><textarea id="question" rows="3" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Find code related to authentication or user login" disabled={!ready || busy} required />
            <div className="example-prompts"><span>Try:</span>{["Find code related to authentication", "Find code related to database connections", "Where is login implemented?"].map((prompt) => <button type="button" key={prompt} onClick={() => setQuestion(prompt)} disabled={busy}>{prompt}</button>)}</div>
            <div className="query-controls"><label className="top-k-label" htmlFor="top-k">Evidence chunks</label><select id="top-k" value={topK} onChange={(event) => setTopK(event.target.value)} disabled={!ready || busy}>{[3, 5, 8, 10].map((number) => <option key={number} value={number}>{number}</option>)}</select><button className="button button-dark" disabled={!ready || busy || !question.trim()}>Retrieve evidence <span aria-hidden="true">→</span></button></div>
          </form>{queryResult && <QueryResults result={queryResult} />}</section>
        </section>
      </>}
      <footer className="footer"><span>DevTwin <span className="footer-muted">· repository understanding prototype</span></span><span>LOCAL EMBEDDINGS · NEO4J KNOWLEDGE GRAPH · GRAPH CONTEXT</span></footer>
    </main>
  );
}

function ProjectOverview({ overview, onReanalyze, busy }) {
  const stats = overview.statistics || {};
  const statItems = [["Files", stats.files], ["Classes", stats.classes], ["Interfaces", stats.interfaces], ["Functions", stats.functions], ["Methods", stats.methods], ["API endpoints", stats.apis], ["Graph nodes", stats.graph_nodes], ["Relationships", stats.relationships], ["Calls", stats.calls], ["Code chunks", stats.code_chunks]];
  return <section className="overview-section"><div className="overview-heading"><div><div className="section-kicker">PROJECT OVERVIEW</div><h2>{overview.project_name || overview.repository_name}</h2>{overview.project_type && <span className="info-tag project-type-tag">{overview.project_type}</span>}<p>Repository-level facts with evidence sources shown.</p></div><button className="button button-outline" type="button" onClick={onReanalyze} disabled={busy}>Re-analyze repository</button></div>
    <div className="overview-grid"><article className="panel overview-card overview-purpose"><div className="section-kicker">WHAT THIS PROJECT DOES</div><p>{overview.summary || overview.purpose}</p><small>{overview.purpose_evidence ? `Source: ${overview.purpose_evidence}` : "No purpose statement found in README or project metadata"}</small></article><article className="panel overview-card"><div className="section-kicker">HIGH-LEVEL ARCHITECTURE</div><p>{overview.architecture_summary || overview.how_it_works}</p><small>{overview.architecture_note}</small><small className="scope-note">{overview.analysis_scope}</small></article></div>
    <div className="overview-grid overview-lists"><article className="panel overview-card"><div className="section-kicker">LANGUAGES, FRAMEWORKS & DEPENDENCIES</div><div className="tag-list">{(overview.languages || []).map((item) => <span className="info-tag" key={item.name}>{item.name} · {item.files}</span>)}{(overview.frameworks || []).map((item) => <span className="info-tag framework-tag" key={item.name}>{item.name}</span>)}{(overview.dependencies || overview.technologies || []).slice(0, 12).map((item) => <span className="info-tag tech-tag" key={item}>{item}</span>)}</div>{!overview.languages?.length && !overview.frameworks?.length && !overview.dependencies?.length && !overview.technologies?.length && <p className="empty-state">No language or package evidence found.</p>}</article>
      <article className="panel overview-card"><div className="section-kicker">MAIN COMPONENTS & DIRECTORIES</div>{overview.main_components?.length ? <div className="component-summary-list">{overview.main_components.slice(0, 8).map((component, index) => <div key={`${component.file || component.name}-${index}`}><strong>{component.name}</strong>{component.file && <code>{component.file}</code>}<p>{component.description}</p><small>{component.evidence}</small></div>)}</div> : <p className="empty-state">No major source directories or documented components were identified.</p>}{overview.entry_points?.length > 0 && <div className="compact-list entry-list">{overview.entry_points.slice(0, 8).map((entry, index) => <span key={`${entry.file}-${entry.name}-${index}`}><code>{entry.file} · {entry.name}</code><small>{entry.evidence}</small></span>)}</div>}</article>
      <article className="panel overview-card"><div className="section-kicker">REPOSITORY STATISTICS</div><div className="stats-grid overview-stats">{statItems.map(([label, value]) => <div className="panel stat-card" key={label}><strong>{value ?? 0}</strong><span>{label}</span></div>)}</div></article>
      <article className="panel overview-card"><div className="section-kicker">IMPORT ANALYSIS · STATIC SOURCE IMPORTS</div><div className="import-count-grid">{[["Total", overview.import_analysis?.total], ["Internal", overview.import_analysis?.internal], ["External", overview.import_analysis?.external], ["Unresolved", overview.import_analysis?.unresolved]].map(([label, value]) => <span key={label}><strong>{value ?? 0}</strong>{label}</span>)}</div><p className="import-explainer">Internal imports resolve to repository files or packages. External packages are supported by manifests or language rules. Unresolved imports need more project context.</p></article></div>
    {overview.documented_components?.length > 0 && <article className="panel overview-card"><div className="section-kicker">COMPONENT DOCUMENTATION FOUND IN SOURCE</div><div className="documented-components">{overview.documented_components.slice(0, 8).map((component, index) => <div key={`${component.file}-${component.name}-${index}`}><code>{component.file} · {component.name}</code><p>{component.purpose}</p></div>)}</div></article>}
    {overview.documentation_evidence?.length > 0 && <article className="panel overview-card"><div className="section-kicker">DOCUMENTATION EXCERPTS</div><div className="documented-components">{overview.documentation_evidence.map((item) => <div key={item.file}><code>{item.file}</code><p>{item.excerpt}</p></div>)}</div></article>}
      {overview.most_connected_files?.length > 0 && <article className="panel overview-card"><div className="section-kicker">MOST CONNECTED FILES · STATIC IMPORT EDGES</div><div className="tag-list">{overview.most_connected_files.slice(0, 6).map((item) => <span className="info-tag" key={item.file}>{item.file} · {item.connections}</span>)}</div></article>}
      <article className="panel overview-card architecture-card"><div className="section-kicker">STATIC IMPORT ANALYSIS</div><p>Imports come from parsed source statements. Calls and API links are shown in the knowledge graph; runtime control flow is not inferred.</p>{overview.architecture_edges?.length ? <details className="overview-disclosure"><summary>Show {overview.architecture_edges.length} sample import edges · {overview.import_analysis?.internal || 0} internal resolved</summary><div className="architecture-links">{overview.architecture_edges.map((edge, index) => <span key={`${edge.source}-${edge.target}-${index}`}><code>{edge.source}</code><b>imports</b><code>{edge.target}</code></span>)}</div></details> : overview.import_analysis?.total ? <p className="empty-state">{overview.import_analysis.total} imports were detected, but none resolved to a displayed graph edge. Check unresolved imports and graph storage.</p> : <p className="empty-state">No source imports were detected in this repository.</p>}</article>
  </section>;
}

function GraphExplorer({ graph, selectedNodeId, onSelectNode }) {
  const [mode, setMode] = useState("overview");
  const [typeFilter, setTypeFilter] = useState("ALL");
  const [relationshipFilter, setRelationshipFilter] = useState("ALL");
  const [search, setSearch] = useState("");
  const [view, setView] = useState({ x: 0, y: 0, scale: 1 });
  const drag = useRef(null);
  const nodesById = useMemo(() => new Map(graph.nodes.map((node) => [node.id, node])), [graph.nodes]);
  const relationshipTypes = useMemo(() => [...new Set(graph.relationships.map((edge) => edge.relationship))].sort(), [graph.relationships]);
  let nodes = graph.nodes.filter((node) => node.type !== "CODE_CHUNK");
  let edges = graph.relationships;
  if (mode === "overview") {
    nodes = nodes.filter((node) => ["PROJECT", "FOLDER", "FILE"].includes(node.type));
    edges = edges.filter((edge) => edge.relationship === "CONTAINS");
  } else if (selectedNodeId) {
    if (mode === "neighborhood") edges = edges.filter((edge) => edge.source === selectedNodeId || edge.target === selectedNodeId);
    if (mode === "dependencies" || mode === "impact") {
      const discovered = new Set([selectedNodeId]);
      const traversalEdges = new Map();
      let frontier = new Set([selectedNodeId]);
      for (let depth = 0; depth < 3 && frontier.size; depth += 1) {
        const next = new Set();
        graph.relationships.forEach((edge) => {
          if (!DEPENDENCY_RELATIONSHIPS.has(edge.relationship)) return;
          const matches = mode === "dependencies" ? frontier.has(edge.source) : frontier.has(edge.target);
          if (!matches) return;
          const related = mode === "dependencies" ? edge.target : edge.source;
          if (related === selectedNodeId || related.startsWith("chunk:")) return;
          traversalEdges.set(`${edge.source}|${edge.relationship}|${edge.target}`, edge);
          if (!discovered.has(related)) { discovered.add(related); next.add(related); }
        });
        frontier = next;
      }
      nodes = nodes.filter((node) => discovered.has(node.id));
      edges = [...traversalEdges.values()];
    }
    const visibleIds = new Set([selectedNodeId]);
    edges.forEach((edge) => { visibleIds.add(edge.source); visibleIds.add(edge.target); });
    nodes = nodes.filter((node) => visibleIds.has(node.id));
  } else {
    nodes = [];
    edges = [];
  }
  const query = search.trim().toLowerCase();
  if (query) nodes = nodes.filter((node) => `${node.name} ${node.file || ""} ${node.type}`.toLowerCase().includes(query));
  if (typeFilter !== "ALL") nodes = nodes.filter((node) => node.type === typeFilter);
  const matchCount = nodes.length;
  nodes = nodes.slice(0, mode === "overview" ? 100 : 60);
  const ids = new Set(nodes.map((node) => node.id));
  edges = edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target) && (relationshipFilter === "ALL" || edge.relationship === relationshipFilter)).slice(0, 120);
  const coords = new Map();
  nodes.forEach((node, index) => {
    if (mode === "overview") {
      const level = node.type === "PROJECT" ? 0 : node.type === "FOLDER" ? 1 : 2;
      const sameLevel = nodes.filter((candidate) => (candidate.type === "PROJECT" ? 0 : candidate.type === "FOLDER" ? 1 : 2) === level);
      const position = sameLevel.findIndex((candidate) => candidate.id === node.id);
      coords.set(node.id, { x: 75 + level * 320, y: 50 + position * 54 });
    } else {
      const angle = 2 * Math.PI * index / Math.max(nodes.length, 1) - Math.PI / 2;
      const radius = nodes.length < 2 ? 0 : nodes.length <= 8 ? 125 : 195;
      const center = node.id === selectedNodeId;
      coords.set(node.id, center ? { x: 400, y: 250 } : { x: 400 + Math.cos(angle) * radius, y: 250 + Math.sin(angle) * radius });
    }
  });
  const graphHeight = mode === "overview"
    ? Math.max(500, ...Array.from(coords.values(), (point) => point.y + 80))
    : 500;
  const selected = nodesById.get(selectedNodeId);
  function pointerDown(event) {
    if (event.target.closest?.(".graph-node")) return;
    drag.current = { x: event.clientX, y: event.clientY, viewX: view.x, viewY: view.y };
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function pointerMove(event) {
    if (drag.current) setView((old) => ({ ...old, x: drag.current.viewX + event.clientX - drag.current.x, y: drag.current.viewY + event.clientY - drag.current.y }));
  }
  return <section className="panel repository-graph" aria-label="Interactive repository relationship graph"><div className="graph-title-row"><div><div className="section-kicker">KNOWLEDGE GRAPH</div><h2>Explore repository relationships</h2><p>Choose a focused view, then drag to pan, zoom, and select a component.</p></div><div className="graph-total-badges"><span><strong>{graph.total_nodes}</strong> nodes</span><span><strong>{graph.total_relationships}</strong> relationships</span></div></div>
    <div className="source-tabs graph-view-tabs" role="tablist" aria-label="Graph view"><button type="button" className={mode === "overview" ? "source-tab active" : "source-tab"} onClick={() => { setMode("overview"); setTypeFilter("ALL"); setRelationshipFilter("ALL"); }}>Project structure</button><button type="button" className={mode === "neighborhood" ? "source-tab active" : "source-tab"} onClick={() => { setMode("neighborhood"); setTypeFilter("ALL"); setRelationshipFilter("ALL"); }} disabled={!selectedNodeId}>Component links</button><button type="button" className={mode === "dependencies" ? "source-tab active" : "source-tab"} onClick={() => { setMode("dependencies"); setTypeFilter("ALL"); setRelationshipFilter("ALL"); }} disabled={!selectedNodeId}>Depends on · 3 hops</button><button type="button" className={mode === "impact" ? "source-tab active" : "source-tab"} onClick={() => { setMode("impact"); setTypeFilter("ALL"); setRelationshipFilter("ALL"); }} disabled={!selectedNodeId}>Used by / impact · 3 hops</button></div>
    <div className="graph-controls"><label htmlFor="node-type-filter">Node type</label><select id="node-type-filter" value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}><option value="ALL">All visible</option>{(mode === "overview" ? ["PROJECT", "FOLDER", "FILE"] : NODE_TYPES.filter((type) => type !== "CODE_CHUNK")).map((type) => <option value={type} key={type}>{type.replaceAll("_", " ")}</option>)}</select><label htmlFor="relationship-filter">Relationship</label><select id="relationship-filter" value={relationshipFilter} onChange={(event) => setRelationshipFilter(event.target.value)}><option value="ALL">All visible</option>{(mode === "overview" ? ["CONTAINS"] : relationshipTypes).map((type) => <option value={type} key={type}>{type.replaceAll("_", " ")}</option>)}</select><input aria-label="Search graph nodes" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search files and symbols" /><div className="zoom-actions"><button type="button" onClick={() => setView((v) => ({ ...v, scale: Math.min(2.2, v.scale + 0.2) }))} aria-label="Zoom in">+</button><button type="button" onClick={() => setView((v) => ({ ...v, scale: Math.max(0.55, v.scale - 0.2) }))} aria-label="Zoom out">−</button><button type="button" onClick={() => setView({ x: 0, y: 0, scale: 1 })}>Reset view</button></div></div>
    <div className="graph-legend">{NODE_TYPES.map((type) => <span key={type}><i style={{ backgroundColor: COLORS[type] }} />{type.toLowerCase()}</span>)}</div>
    <div className="svg-graph-wrap">{nodes.length === 0 ? <p className="empty-state graph-empty">{selectedNodeId ? "No relationships match this view and filter." : "Select a node to see its links, dependencies, or potential impact."}</p> : <svg className="knowledge-svg" viewBox={`0 0 800 ${graphHeight}`} role="img" aria-label="Node-link view of repository files and relationships" onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}>
      <defs><marker id="edge-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#a6b29e" /></marker></defs><g transform={`translate(${view.x} ${view.y}) translate(400 250) scale(${view.scale}) translate(-400 -250)`}>
        {edges.map((edge, index) => { const from = coords.get(edge.source); const to = coords.get(edge.target); if (!from || !to) return null; const mx = (from.x + to.x) / 2; const my = (from.y + to.y) / 2; return <g key={`${edge.source}-${edge.relationship}-${edge.target}-${index}`}><line x1={from.x} y1={from.y} x2={to.x} y2={to.y} className="graph-edge" markerEnd="url(#edge-arrow)" />{edges.length < 35 && <text x={mx} y={my - 4} className="graph-edge-label">{edge.relationship.replaceAll("_", " ")}</text>}</g>; })}
        {nodes.map((node) => { const point = coords.get(node.id); const label = node.name || node.file || node.id; return <g key={node.id} className={`graph-node ${selectedNodeId === node.id ? "selected" : ""}`} role="button" tabIndex="0" aria-label={`${node.type}: ${label}`} onClick={() => onSelectNode(node)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") onSelectNode(node); }}><title>{node.type}: {label}</title><circle cx={point.x} cy={point.y} r={selectedNodeId === node.id ? 22 : 18} fill={COLORS[node.type] || COLORS.MODULE} /><text x={point.x} y={point.y + 3} className="graph-node-type">{node.type === "FUNCTION" ? "FN" : node.type === "METHOD" ? "M" : node.type.slice(0, 3)}</text><text x={point.x} y={point.y + (mode === "overview" ? 27 : 34)} className="graph-node-label">{label.length > 22 ? `${label.slice(0, 20)}…` : label}</text></g>; })}
      </g></svg>}</div>
    <div className="graph-footer"><span>{nodes.length} shown{matchCount > nodes.length ? ` of ${matchCount} matching nodes` : ""}{graph.truncated ? " · graph result is truncated" : ""}</span>{selected && <button type="button" className="clear-selection" onClick={() => onSelectNode(null)}>Clear selection</button>}</div>
  </section>;
}

function SelectedComponent({ node, summary, busy, onDependencies, onImpact, dependencyResult, impactResult }) {
  if (!node) return <section className="panel selected-component"><div className="section-kicker">SELECTED COMPONENT</div><p className="empty-state">Select a node in the graph to inspect source facts and relationships.</p></section>;
  const displayName = summary?.file || node.file || node.name;
  return <section className="panel selected-component"><div className="component-heading"><div><div className="section-kicker">SELECTED COMPONENT</div><h2>{displayName}</h2></div><span className={`node-type node-type-${node.type.toLowerCase()}`}>{node.type}</span></div>
    {node.type === "FILE" ? busy && !summary ? <p className="empty-state">Reading selected file…</p> : summary && <><p className="component-purpose">{summary.purpose}</p><small className="evidence-note">{summary.explanation_basis}</small>{summary.documented_components?.length > 0 && <div className="documented-components">{summary.documented_components.map((component) => <div key={`${component.kind}-${component.name}`}><code>{component.kind} · {component.name}</code><p>{component.purpose}</p></div>)}</div>}<div className="component-facts"><FactList title="Language" values={[summary.language]} /><FactList title="Classes" values={summary.classes} /><FactList title="Interfaces" values={summary.interfaces} /><FactList title="Functions" values={summary.functions} /><FactList title="Methods" values={summary.methods} /><FactList title="Imports / dependencies" values={summary.dependencies} /><FactList title="Used by" values={summary.used_by} /><FactList title="Exports" values={summary.exports} /><FactList title="API endpoints" values={(summary.api_endpoints || []).map((item) => `${item.method} ${item.path}${item.handler ? ` → ${item.handler}` : ""}`)} /><FactList title="Resolved static call links" values={summary.calls} /></div><div className="graph-actions"><button className="button button-outline" type="button" onClick={onDependencies} disabled={busy}>Dependencies</button><button className="button button-outline" type="button" onClick={onImpact} disabled={busy}>Potential impact</button></div>{dependencyResult && <NodeList title="Dependencies" items={dependencyResult.dependencies} empty="No outgoing dependencies found." />}{impactResult && <NodeList title="Potentially affected" items={impactResult.impacted_components} empty="No incoming dependents found." />}</> : <><p className="component-purpose">This node was extracted as a <strong>{node.type.toLowerCase()}</strong> named <strong>{node.name}</strong>. Its source path and direct relationships are available in the graph views.</p><div className="component-facts"><FactList title="Source file" values={node.file ? [node.file] : []} /><FactList title="Folder or package path" values={node.path ? [node.path] : []} /><FactList title="Language" values={node.language ? [node.language] : []} /></div></>}
  </section>;
}

function FactList({ title, values = [] }) { return <div className="fact-list"><h3>{title}</h3>{values.length ? <ul>{values.map((value, index) => <li key={`${value}-${index}`}><code>{value}</code></li>)}</ul> : <p>None extracted</p>}</div>; }

function QueryResults({ result }) {
  const chunks = result.semantic_chunks || [];
  const graph = result.graph_context || { nodes: [], relationships: [] };
  const nodesById = new Map(graph.nodes.map((node) => [node.id, node]));
  const friendlyName = (id) => { const node = nodesById.get(id); return node?.file || node?.name || id.split(":").slice(1).join(":"); };
  return <div className="results" aria-live="polite"><div className="answer-honesty"><div className="section-kicker">REPOSITORY EVIDENCE</div><p>No generative LLM is connected. These are retrieved source matches and graph context, not an AI-written answer.</p></div><div className="results-heading"><div><div className="section-kicker">SEMANTIC MATCHES</div><h3>{chunks.length} relevant code {chunks.length === 1 ? "chunk" : "chunks"}</h3></div><span className="graph-count">{graph.nodes.length} graph nodes</span></div>
    {chunks.length === 0 ? <p className="empty-state">No matching code chunks were found for this question.</p> : chunks.map((chunk) => <article className="evidence-card" key={chunk.id}><div className="evidence-meta"><code>{chunk.file}</code><span>{chunk.kind || "CODE"}{chunk.symbol ? ` · ${chunk.symbol}` : ""}</span><span>{Math.round(chunk.score * 100)}% match</span></div><pre>{chunk.content}</pre></article>)}
    <div className="graph-context"><div className="section-kicker">GRAPH CONTEXT</div>{graph.relationships.length === 0 ? <p className="empty-state">No direct graph relationships for these matches.</p> : graph.relationships.map((edge, index) => <div className="edge-row" key={`${edge.source}-${edge.relationship}-${edge.target}-${index}`}><code>{friendlyName(edge.source)}</code><span>{edge.relationship.replaceAll("_", " ")}</span><code>{friendlyName(edge.target)}</code></div>)}</div>
  </div>;
}

function NodeList({ title, items, empty }) { return <div className="node-list"><div className="section-kicker">{title.toUpperCase()}</div>{items.length === 0 ? <p className="empty-state">{empty}</p> : items.map((item) => <div className="node-row" key={item.id}><span className={`node-type node-type-${String(item.type || "unknown").toLowerCase()}`}>{item.type}</span><code>{item.file || item.name || item.id}</code>{item.depth && <span className="node-depth">depth {item.depth}</span>}</div>)}</div>; }

export default App;
