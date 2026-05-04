/**
 * graph.js — D3 v7 force-directed graph for CodeGrapher viewer.
 *
 * Expects a global GRAPH_DATA variable injected by run.py.
 * No external network requests; works fully offline.
 */

(function () {
  "use strict";

  const RELATION_COLORS = {
    defines:    "#4a90d9",
    imports:    "#777777",
    calls:      "#5cb85c",
    contains:   "#9b59b6",
    uses_type:  "#e67e22",
    produces:   "#17a89e",  // teal  — data-producing edges
    consumes:   "#e8a020",  // amber — data-consuming edges
    typedef_of: "#888888",
    depends_on: "#aaaaaa",
    entry_of:   "#cc88ff",
  };

  // Color used when a consumes/calls edge has role:"control" (overrides default)
  const ROLE_CONTROL_COLOR = "#9b3dcc";  // violet/purple

  // -----------------------------------------------------------------------
  // Mermaid diagram overlay — 3 tabs: Flowchart | Data Flow | State
  // -----------------------------------------------------------------------
  mermaid.initialize({ startOnLoad: false, theme: "dark", securityLevel: "loose", maxEdges: 2000, zoom: false });

  // Per-tab lazy loaders: { flowchart: fn, dataflow: fn, state: fn }
  // Each fn fetches and calls showDiagramPanel if the pane hasn't been loaded yet.
  const _diagLoaders = { flowchart: null, dataflow: null, state: null };

  function _splitDiagrams(mermaidText) {
    const chunks = [];
    let current = [];
    for (const line of mermaidText.split("\n")) {
      const trimmed = line.trimStart();
      if ((trimmed === "stateDiagram-v2" || trimmed === "classDiagram") && current.length > 0) {
        chunks.push(current.join("\n"));
        current = [];
      }
      current.push(line);
    }
    if (current.length > 0) chunks.push(current.join("\n"));
    return chunks.filter(c => /stateDiagram-v2|classDiagram|flowchart/.test(c));
  }

  // Show the diagram overlay and render mermaidText in the given tab.
  // tabId: "flowchart" | "dataflow" | "state"
  function showDiagramPanel(tabId, title, mermaidText) {
    const panel = document.getElementById("diagram-panel");
    panel.style.display = "flex";
    panel.classList.remove("minimized");
    _switchDiagTab(tabId);

    const pane    = document.getElementById(`pane-${tabId}`);
    const content = pane.querySelector(".diag-content");
    const zoomSlider = document.getElementById("diagram-zoom");
    const zoomVal    = document.getElementById("diagram-zoom-val");
    zoomSlider.value = 100;
    zoomVal.textContent = "100%";
    content.style.transform = "scale(1)";

    // For flowchart/dataflow: single diagram block, no sub-tabs needed
    // For state: may have multiple stateDiagram-v2 blocks (File Level / Symbol Level)
    const diagrams = tabId === "state" ? _splitDiagrams(mermaidText) : [mermaidText];

    if (diagrams.length === 0) {
      content.innerHTML = `<pre style="color:oklch(0.60 0.12 30);font-size:10px;padding:12px;background:var(--bg-deep);border-radius:2px;border:1px solid var(--border-muted);">no diagram found.\n\n${esc(mermaidText)}</pre>`;
      return;
    }

    content.innerHTML = '<div style="color:var(--text-dim);font-size:10px;padding:20px;letter-spacing:0.08em;">rendering…</div>';

    const ts = Date.now();
    let tabBar = "";
    if (diagrams.length > 1) {
      const labels = diagrams.map((d, i) => /stateDiagram-v2/.test(d) ? (i === 0 ? "File Level" : "Symbol Level") : `Diagram ${i+1}`);
      tabBar = `<div class="diag-subtabs" style="display:flex;gap:4px;margin-bottom:10px;">` +
        labels.map((lbl, i) =>
          `<button class="diag-subtab" data-idx="${i}" style="background:${i===0?"oklch(0.14 0.04 220)":"var(--bg-raised)"};color:${i===0?"#4a8fd0":"var(--text-muted)"};border:1px solid ${i===0?"oklch(0.35 0.07 220)":"var(--border)"};padding:2px 9px;border-radius:2px;cursor:pointer;font-family:inherit;font-size:10px;">${lbl}</button>`
        ).join("") + `</div>`;
    }
    const pageDivs = diagrams.map((d, i) =>
      `<div class="diag-subpage" data-idx="${i}" style="display:${i===0?"block":"none"};"><div class="mermaid" id="mermaid-${ts}-${i}">${d}</div></div>`
    ).join("");
    content.innerHTML = tabBar + pageDivs;

    const rendered = new Set();
    function renderDiagram(i) {
      if (rendered.has(i)) return;
      rendered.add(i);
      const el = document.getElementById(`mermaid-${ts}-${i}`);
      if (!el) return;
      mermaid.run({ nodes: [el] }).catch(err => {
        el.outerHTML = `<div style="color:oklch(0.65 0.10 80);font-size:10px;margin-bottom:6px;">[warn] render error: ${esc(err.message)}</div><pre style="color:var(--text-muted);font-size:10px;background:var(--bg-deep);padding:10px;border-radius:2px;overflow:auto;white-space:pre;border:1px solid var(--border-muted);">${esc(diagrams[i])}</pre>`;
      });
    }

    content.querySelectorAll(".diag-subtab").forEach(btn => {
      btn.addEventListener("click", () => {
        const idx = +btn.dataset.idx;
        content.querySelectorAll(".diag-subtab").forEach(b => {
          b.style.background  = b.dataset.idx == idx ? "oklch(0.14 0.04 220)" : "var(--bg-raised)";
          b.style.color       = b.dataset.idx == idx ? "#4a8fd0" : "var(--text-muted)";
          b.style.borderColor = b.dataset.idx == idx ? "oklch(0.35 0.07 220)" : "var(--border)";
        });
        content.querySelectorAll(".diag-subpage").forEach(p => {
          p.style.display = p.dataset.idx == idx ? "block" : "none";
        });
        renderDiagram(idx);
      });
    });
    renderDiagram(0);
  }

  function _switchDiagTab(tabId) {
    document.querySelectorAll(".diag-tab").forEach(btn => {
      btn.classList.toggle("active", btn.dataset.tab === tabId);
    });
    document.querySelectorAll(".diag-pane").forEach(pane => {
      pane.classList.toggle("active", pane.id === `pane-${tabId}`);
    });
    // Lazy-load the tab if it hasn't been fetched yet for the current node
    const pane = document.getElementById(`pane-${tabId}`);
    const content = pane && pane.querySelector(".diag-content");
    const isEmpty = content && content.innerHTML.trim() === "";
    if (isEmpty && _diagLoaders[tabId]) {
      _diagLoaders[tabId]();
    }
  }

  function hideDiagramPanel() {
    document.getElementById("diagram-panel").style.display = "none";
  }

  // Open panel to a tab without triggering lazy load (inspector buttons call their own loader)
  function _openDiagramPanel(tabId) {
    const panel = document.getElementById("diagram-panel");
    panel.style.display = "flex";
    panel.classList.remove("minimized");
    document.querySelectorAll(".diag-tab").forEach(btn => {
      btn.classList.toggle("active", btn.dataset.tab === tabId);
    });
    document.querySelectorAll(".diag-pane").forEach(pane => {
      pane.classList.toggle("active", pane.id === `pane-${tabId}`);
    });
  }

  // Wire diagram panel controls once DOM is ready
  document.addEventListener("DOMContentLoaded", () => {
    const panel      = document.getElementById("diagram-panel");
    const zoomSlider = document.getElementById("diagram-zoom");
    const zoomVal    = document.getElementById("diagram-zoom-val");

    // Tab switching
    document.querySelectorAll(".diag-tab").forEach(btn => {
      btn.addEventListener("click", () => _switchDiagTab(btn.dataset.tab));
    });

    // Active pane zoom target (whichever pane is .active)
    function activeContent() {
      const pane = document.querySelector(".diag-pane.active");
      return pane ? pane.querySelector(".diag-content") : null;
    }

    zoomSlider.addEventListener("input", () => {
      const pct = zoomSlider.value;
      zoomVal.textContent = pct + "%";
      const c = activeContent(); if (c) c.style.transform = `scale(${pct/100})`;
    });
    document.getElementById("diagram-zoom-reset").addEventListener("click", () => {
      zoomSlider.value = 100; zoomVal.textContent = "100%";
      const c = activeContent(); if (c) c.style.transform = "scale(1)";
    });

    // Scroll-to-zoom — attach to each pane's scroll area
    document.querySelectorAll(".diag-scroll").forEach(scrollEl => {
      scrollEl.addEventListener("wheel", e => {
        e.preventDefault();
        const step = e.deltaY < 0 ? 10 : -10;
        const next = Math.max(20, Math.min(+zoomSlider.max, +zoomSlider.value + step));
        zoomSlider.value = next; zoomVal.textContent = next + "%";
        const c = scrollEl.querySelector(".diag-content");
        if (c) c.style.transform = `scale(${next/100})`;
      }, { passive: false });

      // Drag-to-pan
      let _pan = false, _px = 0, _py = 0;
      scrollEl.addEventListener("mousedown", e => {
        if (e.button !== 0) return;
        _pan = true; _px = e.clientX + scrollEl.scrollLeft; _py = e.clientY + scrollEl.scrollTop;
        e.preventDefault();
      });
      document.addEventListener("mousemove", e => {
        if (!_pan) return;
        scrollEl.scrollLeft = _px - e.clientX; scrollEl.scrollTop = _py - e.clientY;
      });
      document.addEventListener("mouseup", () => { _pan = false; });
    });

    // Minimize / restore
    document.getElementById("diagram-minimize").addEventListener("click", () => {
      panel.classList.toggle("minimized");
    });
    panel.addEventListener("click", e => {
      if (panel.classList.contains("minimized") && e.target === panel) {
        panel.classList.remove("minimized");
      }
    });

    // Full-width toggle
    document.getElementById("diagram-fullscreen").addEventListener("click", () => {
      panel.style.width = panel.style.width === "100%" ? "55%" : "100%";
    });

    // Close
    document.getElementById("diagram-close").addEventListener("click", hideDiagramPanel);

    // Drag-resize handle
    const resizeHandle = document.getElementById("diagram-resize");
    let _drag = false;
    resizeHandle.addEventListener("mousedown", e => { _drag = true; e.preventDefault(); });
    document.addEventListener("mousemove", e => {
      if (!_drag) return;
      const w = window.innerWidth - e.clientX;
      panel.style.width = Math.max(300, Math.min(window.innerWidth - 100, w)) + "px";
    });
    document.addEventListener("mouseup", () => { _drag = false; });
  });

  // -----------------------------------------------------------------------
  // BFS Trace
  // -----------------------------------------------------------------------
  function bfsFromNode(startId, nodes, links) {
    const visited = new Set([startId]);
    const queue = [startId];
    while (queue.length > 0) {
      const current = queue.shift();
      for (const link of links) {
        const srcId = typeof link.source === 'object' ? link.source.id : link.source;
        const tgtId = typeof link.target === 'object' ? link.target.id : link.target;
        if (srcId === current && !visited.has(tgtId)) {
          visited.add(tgtId);
          queue.push(tgtId);
        }
      }
    }
    return visited;
  }

  // -----------------------------------------------------------------------
  // Boot — supports both standalone (GRAPH_DATA) and LOD server (GRAPH_DATA=null)
  // -----------------------------------------------------------------------
  document.addEventListener("DOMContentLoaded", () => {
    if (typeof GRAPH_DATA !== "undefined" && GRAPH_DATA !== null) {
      // Standalone mode: data baked in
      hideLoading();
      init(GRAPH_DATA);
    } else {
      // LOD server mode: fetch tier_directory.json as the first load
      fetchAndInit();
    }
  });

  function hideLoading() {
    const el = document.getElementById("loading");
    if (!el) return;
    el.style.transition = "opacity 0.4s";
    el.style.opacity = "0";
    setTimeout(() => { el.style.display = "none"; }, 420);
  }

  async function fetchAndInit() {
    try {
      const [tocResp, dirResp] = await Promise.all([
        fetch("/graphs/toc.json"),
        fetch("/graphs/tier_directory.json"),
      ]);
      if (!tocResp.ok || !dirResp.ok) throw new Error("Failed to load graph data");
      const toc = await tocResp.json();
      const dirData = await dirResp.json();
      hideLoading();
      // Store toc globally for LOD fetches later
      window._cg_toc = toc;
      init(dirData);
    } catch (err) {
      const statusEl = document.getElementById("loading-status");
      if (statusEl) { statusEl.textContent = "error: " + err.message; statusEl.style.color = "oklch(0.60 0.12 30)"; }
    }
  }

  // -----------------------------------------------------------------------
  // init
  // -----------------------------------------------------------------------
  function init(data) {
    // Deep-copy nodes so D3 can attach x/y freely
    const nodes = data.nodes.map(d => ({ ...d }));

    // Build id → node map BEFORE touching edges
    const nodeById = new Map(nodes.map(n => [n.id, n]));

    // Remap edges: use "source"/"target" (D3 convention) pointing at node objects.
    // Drop any edge whose endpoint isn't in nodeById (avoids "node not found").
    const links = [];
    for (const e of data.edges) {
      const src = nodeById.get(e.from);
      const tgt = nodeById.get(e.to);
      if (src && tgt) {
        links.push({
          source: src, target: tgt, relation: e.relation,
          unresolved: !!e.unresolved,
          relay: e.relay || false,
          role:  e.role  || null,
          seq:   e.seq   != null ? e.seq : null,
          via:   e.via   || null,
        });
      }
    }

    // Relation filter state — Set of relation names currently hidden
    const hiddenRelations = new Set();

    // Adjacency maps (built from the valid links only)
    const neighbors  = new Map(nodes.map(n => [n.id, new Set()]));
    const edgesByNode = new Map(nodes.map(n => [n.id, []]));
    for (const lk of links) {
      neighbors.get(lk.source.id).add(lk.target.id);
      neighbors.get(lk.target.id).add(lk.source.id);
      edgesByNode.get(lk.source.id).push({ link: lk, dir: "out" });
      edgesByNode.get(lk.target.id).push({ link: lk, dir: "in"  });
    }

    // -----------------------------------------------------------------------
    // Stats + title
    // -----------------------------------------------------------------------
    const statsEl = document.getElementById("stats");
    if (statsEl) statsEl.textContent = `${nodes.length} nodes · ${links.length} edges`;
    const titleEl = document.getElementById("feature-title");
    if (titleEl) titleEl.textContent = `feature: ${data.feature}`;

    // -----------------------------------------------------------------------
    // SVG
    // -----------------------------------------------------------------------
    const svgEl  = document.getElementById("graph");
    const width  = svgEl.clientWidth  || window.innerWidth - 320;
    const height = svgEl.clientHeight || window.innerHeight;

    const svg = d3.select(svgEl);
    svg.selectAll("*").remove();

    // Arrow markers — two sets:
    // "arrow-{rel}"       refX=18  for <line> elements (force graph edges)
    // "arrow-trace-{rel}" refX=8   for <path> elements (flowchart trace)
    const defs = svg.append("defs");
    Object.entries(RELATION_COLORS).forEach(([rel, color]) => {
      defs.append("marker")
        .attr("id",          `arrow-${rel}`)
        .attr("viewBox",     "0 -4 8 8")
        .attr("refX",        18)
        .attr("refY",        0)
        .attr("markerWidth",  5)
        .attr("markerHeight", 5)
        .attr("orient",      "auto")
        .append("path")
          .attr("d",    "M0,-4L8,0L0,4")
          .attr("fill", color)
          .attr("fill-opacity", 0.7);
      defs.append("marker")
        .attr("id",          `arrow-trace-${rel}`)
        .attr("viewBox",     "0 -4 8 8")
        .attr("refX",        8)
        .attr("refY",        0)
        .attr("markerWidth",  6)
        .attr("markerHeight", 6)
        .attr("orient",      "auto")
        .append("path")
          .attr("d",    "M0,-4L8,0L0,4")
          .attr("fill", color)
          .attr("fill-opacity", 0.9);
    });
    // Extra trace markers for role:control color
    defs.append("marker")
      .attr("id",          "arrow-trace-control")
      .attr("viewBox",     "0 -4 8 8")
      .attr("refX",        8)
      .attr("refY",        0)
      .attr("markerWidth",  6)
      .attr("markerHeight", 6)
      .attr("orient",      "auto")
      .append("path")
        .attr("d",    "M0,-4L8,0L0,4")
        .attr("fill", ROLE_CONTROL_COLOR)
        .attr("fill-opacity", 0.9);

    const g = svg.append("g");

    // Zoom / pan
    const zoom = d3.zoom()
      .scaleExtent([0.03, 6])
      .on("zoom", ev => {
        g.attr("transform", ev.transform);
      });
    svg.call(zoom);

    // -----------------------------------------------------------------------
    // LOD state
    // -----------------------------------------------------------------------
    let lodState = "DIR_ONLY";       // DIR_ONLY | FILE_LEVEL | SYMBOL_LEVEL
    let fileDataLoaded = false;
    let zoomFetchPending = false;
    let loadedSubGraphs = new Set(); // slugs already fetched

    // Per-directory expansion state: Set of dir node IDs that have been expanded.
    // In DIR_ONLY mode, files whose path prefix matches an expanded dir are shown.
    const expandedDirs = new Set();

    // VS Code-style tree panel path filter. null = show all.
    let activePathFilter = null;

    // Extract the directory path from a dir node ID: "feat::dir::a/b/c" → "a/b/c"
    function dirPathFromId(nodeId) {
      const marker = "::dir::";
      const idx = nodeId.indexOf(marker);
      return idx >= 0 ? nodeId.slice(idx + marker.length) : null;
    }

    // Return true if a file node (with node.file path) belongs to the given dir path.
    function fileIsUnderDir(filePath, dirPath) {
      if (!filePath || !dirPath) return false;
      return filePath === dirPath || filePath.startsWith(dirPath + "/");
    }

    function getViewportNodeIds(transform) {
      const svgW = svgEl.clientWidth  || window.innerWidth - 320;
      const svgH = svgEl.clientHeight || window.innerHeight;
      const x0 = -transform.x / transform.k - svgW * 0.2;
      const x1 = (svgW - transform.x) / transform.k + svgW * 0.2;
      const y0 = -transform.y / transform.k - svgH * 0.2;
      const y1 = (svgH - transform.y) / transform.k + svgH * 0.2;
      return nodes
        .filter(n => n.type === "file" && n.x != null && n.x >= x0 && n.x <= x1 && n.y != null && n.y >= y0 && n.y <= y1)
        .map(n => n.id);
    }

    function mergeGraphData(newData) {
      // Add new nodes (skip duplicates by id)
      const existingPositioned = nodes.filter(n => n.x != null && n.y != null);
      const cx = existingPositioned.length > 0 ? existingPositioned.reduce((s, n) => s + n.x, 0) / existingPositioned.length : width / 2;
      const cy = existingPositioned.length > 0 ? existingPositioned.reduce((s, n) => s + n.y, 0) / existingPositioned.length : height / 2;
      const newNodes = (newData.nodes || []).filter(nd => !nodeById.has(nd.id)).map(nd => ({
        ...nd,
        x: nd.x != null ? nd.x : cx + (Math.random() - 0.5) * 200,
        y: nd.y != null ? nd.y : cy + (Math.random() - 0.5) * 200,
      }));
      const newEdgeRaw = (newData.edges || []);

      newNodes.forEach(n => {
        nodes.push(n);
        nodeById.set(n.id, n);
        neighbors.set(n.id, new Set());
        edgesByNode.set(n.id, []);
      });

      // Add new links (skip if both endpoints already linked)
      const newLinks = [];
      for (const e of newEdgeRaw) {
        const src = nodeById.get(e.from);
        const tgt = nodeById.get(e.to);
        if (src && tgt) {
          const lk = {
            source: src, target: tgt, relation: e.relation,
            unresolved: !!e.unresolved,
            relay: e.relay || false,
            role:  e.role  || null,
            seq:   e.seq   != null ? e.seq : null,
            via:   e.via   || null,
          };
          links.push(lk);
          newLinks.push(lk);
          neighbors.get(src.id).add(tgt.id);
          neighbors.get(tgt.id).add(src.id);
          edgesByNode.get(src.id).push({ link: lk, dir: "out" });
          edgesByNode.get(tgt.id).push({ link: lk, dir: "in"  });
        }
      }

      if (newNodes.length === 0 && newLinks.length === 0) return;

      // Re-bind simulation data
      simulation.nodes(nodes);
      simulation.force("link").links(links);

      // Re-render: add new node elements
      nodeSel2 = g.select(".nodes").selectAll("g")
        .data(nodes, d => d.id)
        .join(
          enter => {
            const grp = enter.append("g")
              .attr("class", d => {
                let c = `node ${d.type || "symbol"}`;
                if (d.is_test)                    c += " test";
                if (d.type === "file" && !d.file) c += " stdlib";
                if (d.type === "directory" && (d.count === 0 || d.count == null)) c += " empty-dir";
                return c;
              })
              .call(d3.drag()
                .on("start", (ev, d) => { if (!ev.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
                .on("drag",  (ev, d) => { d.fx = ev.x; d.fy = ev.y; })
                .on("end",   (ev, d) => { if (!ev.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; })
              )
              .on("click", (ev, d) => { ev.stopPropagation(); selectNode(d); })
              .on("dblclick", (ev, d) => {
                ev.stopPropagation();
                if (d.type === "directory") toggleDirExpansion(d);
              });
            grp.append("circle").attr("r", d => nodeR(d));
            grp.append("text").attr("dy", d => nodeR(d) + 3).text(d => trunc(d.label, 20));
            return grp;
          },
          update => update,
          exit => exit
        );

      // Re-bind links
      linkSel2 = g.select(".links").selectAll("line")
        .data(links, (d, i) => i)
        .join("line")
          .attr("class",            d => `link ${d.relation}${d.unresolved ? " unresolved" : ""}${d.relay ? " relay" : ""}`)
          .attr("stroke-width",     1.2)
          .attr("stroke-dasharray", d => d.relay ? "6,3" : null)
          .attr("stroke",           d => d.role === "control" ? ROLE_CONTROL_COLOR : (RELATION_COLORS[d.relation] || "#888"))
          .attr("marker-end",       d => d.unresolved ? null : `url(#arrow-${d.relation})`);

      // Update tick to use updated selections
      simulation.on("tick", tickFn);

      // Gentle reheat
      simulation.alpha(0.1).restart();

      // Update stats
      if (statsEl) statsEl.textContent = `${nodes.length} nodes · ${links.length} edges`;

      applyLodVisibility();
    }

    function applyLodVisibility() {
      // Precompute which dir paths are expanded (avoids repeated work per node)
      const expandedPaths = new Set();
      for (const id of expandedDirs) {
        const p = dirPathFromId(id);
        if (p) expandedPaths.add(p);
      }

      // Decide whether a given node is visible under the current LOD + expansion state
      function nodeVisible(d) {
        if (lodState === "DIR_ONLY") {
          // Directory and repo nodes always visible regardless of path filter
          if (d.type === "directory" || d.type === "repo") return true;
          // File nodes visible only if their parent dir is expanded AND under the path filter
          if (d.type === "file") {
            if (activePathFilter && !fileIsUnderDir(d.file || "", activePathFilter)) return false;
            for (const dp of expandedPaths) {
              if (fileIsUnderDir(d.file, dp)) return true;
            }
          }
          return false;
        } else if (lodState === "FILE_LEVEL") {
          if (d.type === "symbol" || d.type === "type") return false;
          // Path filter applies to file/dir nodes at file level
          if (activePathFilter) {
            if (d.type === "directory") {
              const dp = dirPathFromId(d.id || "") || "";
              return dp === activePathFilter || dp.startsWith(activePathFilter + "/") ||
                     activePathFilter.startsWith(dp + "/");
            }
            return fileIsUnderDir(d.file || "", activePathFilter);
          }
          return true;
        }
        // SYMBOL_LEVEL: path filter applies, directories always visible
        if (activePathFilter) {
          if (d.type === "directory" || d.type === "repo") return true;
          return fileIsUnderDir(d.file || "", activePathFilter);
        }
        return true;
      }

      const allNodeSel = g.select(".nodes").selectAll("g");
      // Cache visibility per node id so link filtering doesn't recompute per edge
      const visibilityCache = new Map();
      allNodeSel
        .style("display", d => {
          const v = nodeVisible(d);
          visibilityCache.set(d.id, v);
          return v ? null : "none";
        })
        // Expanded dir nodes: solid bright stroke, no dash, to show they are open
        .select("circle")
          .style("stroke-width", d =>
            (d.type === "directory" && expandedDirs.has(d.id)) ? "2.5px" : null
          )
          .style("stroke", d =>
            (d.type === "directory" && expandedDirs.has(d.id)) ? "#00d060" : null
          )
          .style("stroke-dasharray", d =>
            (d.type === "directory" && expandedDirs.has(d.id)) ? "none" : null
          );

      // Boundary-aware context (Option D): classify nodes as local/external, hide unrelated
      if (activePathFilter) {
        const localNodeIds = new Set();
        const externalNodeIds = new Set();

        // First pass: mark LOCAL nodes (file under filter OR dir/repo nodes)
        allNodeSel.each(d => {
          if (visibilityCache.get(d.id)) {
            if (d.type === "directory" || d.type === "repo") {
              localNodeIds.add(d.id);
            } else if (fileIsUnderDir(d.file || "", activePathFilter)) {
              localNodeIds.add(d.id);
            }
          }
        });

        // Second pass: mark EXTERNAL nodes (visible, not local, but connected to local)
        allNodeSel.each(d => {
          if (visibilityCache.get(d.id) && !localNodeIds.has(d.id)) {
            const nb = neighbors.get(d.id) || new Set();
            for (const neighborId of nb) {
              if (localNodeIds.has(neighborId)) {
                externalNodeIds.add(d.id);
                break;
              }
            }
          }
        });

        // Third pass: hide unrelated nodes (visible but neither local nor external), apply styling
        allNodeSel
          .style("display", d => {
            if (!visibilityCache.get(d.id)) return "none";
            if (localNodeIds.has(d.id) || externalNodeIds.has(d.id)) return null;
            return "none";
          })
          .classed("external-node", d => externalNodeIds.has(d.id))
          .style("opacity", d => externalNodeIds.has(d.id) ? 0.45 : null)
          .select("circle")
            .style("stroke", d => externalNodeIds.has(d.id) ? "var(--border)" : null)
            .style("stroke-dasharray", d => externalNodeIds.has(d.id) ? "3 2" : null)
          .each(function(d) {
            if (externalNodeIds.has(d.id)) {
              d3.select(this.parentNode).select("text").style("opacity", 0.35);
            }
          });
      } else {
        // No filter: clear all boundary classes and inline styles
        allNodeSel
          .classed("external-node", false)
          .style("opacity", null)
          .select("circle")
            .style("stroke", null)
            .style("stroke-dasharray", null)
          .each(function(d) {
            d3.select(this.parentNode).select("text").style("opacity", null);
          });
      }

      const allLinkSel = g.select(".links").selectAll("line");
      allLinkSel.style("display", d => {
        if (!d || !d.source || !d.target) return null;
        if (hiddenRelations.has(d.relation)) return "none";
        if (!visibilityCache.get(d.source.id) || !visibilityCache.get(d.target.id)) return "none";
        return null;
      });

      // Tag boundary-crossing edges (activePathFilter non-null, one local + one external endpoint)
      if (activePathFilter) {
        const localNodeIds = new Set();
        const externalNodeIds = new Set();
        // Two-pass: local first, then external (avoids order-dependency in single pass)
        allNodeSel.each(d => {
          if (visibilityCache.get(d.id) &&
              (d.type === "directory" || d.type === "repo" || fileIsUnderDir(d.file || "", activePathFilter))) {
            localNodeIds.add(d.id);
          }
        });
        allNodeSel.each(d => {
          if (visibilityCache.get(d.id) && !localNodeIds.has(d.id)) {
            const nb = neighbors.get(d.id) || new Set();
            for (const neighborId of nb) {
              if (localNodeIds.has(neighborId)) { externalNodeIds.add(d.id); break; }
            }
          }
        });

        allLinkSel.classed("boundary-cross", d => {
          if (!d || !d.source || !d.target) return false;
          const srcLocal = localNodeIds.has(d.source.id);
          const tgtLocal = localNodeIds.has(d.target.id);
          const srcExt   = externalNodeIds.has(d.source.id);
          const tgtExt   = externalNodeIds.has(d.target.id);
          return (srcLocal && tgtExt) || (tgtLocal && srcExt);
        });
      } else {
        allLinkSel.classed("boundary-cross", false);
      }

      if (window._cg_updateLodBtns) window._cg_updateLodBtns();
    }

    // -----------------------------------------------------------------------
    // Relation filter toggles
    // -----------------------------------------------------------------------
    function setupLodButtons() {
      const controlsEl = document.getElementById("controls");
      if (!controlsEl) return;

      const wrap = document.createElement("div");
      wrap.id = "lod-buttons";
      wrap.style.cssText = "display:flex;align-items:center;gap:4px;padding:3px 0 0 0;width:100%;";

      const label = document.createElement("span");
      label.textContent = "lod:";
      label.style.cssText = "font-size:9px;color:var(--text-dim);margin-right:2px;text-transform:uppercase;letter-spacing:0.1em;font-family:inherit;";
      wrap.appendChild(label);

      const levels = [
        { id: "lod-dir",    label: "dirs",    state: "DIR_ONLY" },
        { id: "lod-file",   label: "files",   state: "FILE_LEVEL" },
        { id: "lod-symbol", label: "symbols", state: "SYMBOL_LEVEL" },
      ];

      function updateButtonStyles(activeState) {
        levels.forEach(({ id, state }) => {
          const b = document.getElementById(id);
          if (!b) return;
          if (state === activeState) {
            b.style.background = "oklch(0.14 0.04 220)";
            b.style.color = "#4a8fd0";
            b.style.borderColor = "oklch(0.35 0.07 220)";
          } else {
            b.style.background = "var(--bg-raised)";
            b.style.color = "var(--text-muted)";
            b.style.borderColor = "var(--border)";
          }
        });
      }

      levels.forEach(({ id, label: btnLabel, state }) => {
        const btn = document.createElement("button");
        btn.id = id;
        btn.textContent = btnLabel;
        btn.style.cssText = "padding:2px 7px;font-size:10px;border-radius:2px;border:1px solid var(--border);background:var(--bg-raised);color:var(--text-muted);cursor:pointer;font-family:inherit;box-shadow:var(--shadow-sm);";

        btn.addEventListener("click", () => {
          if (state === "DIR_ONLY") {
            lodState = "DIR_ONLY";
            applyLodVisibility();
            updateButtonStyles("DIR_ONLY");
          } else if (state === "FILE_LEVEL") {
            if (!fileDataLoaded && !zoomFetchPending) {
              zoomFetchPending = true;
              fetch("/graphs/tier_file.json")
                .then(r => r.json())
                .then(fileData => {
                  fileDataLoaded = true;
                  zoomFetchPending = false;
                  lodState = "FILE_LEVEL";
                  mergeGraphData(fileData);
                  updateButtonStyles("FILE_LEVEL");
                })
                .catch(() => { zoomFetchPending = false; });
            } else {
              lodState = "FILE_LEVEL";
              applyLodVisibility();
              updateButtonStyles("FILE_LEVEL");
            }
          } else if (state === "SYMBOL_LEVEL") {
            lodState = "SYMBOL_LEVEL";
            applyLodVisibility();
            updateButtonStyles("SYMBOL_LEVEL");
            loadVisibleSubGraphs(d3.zoomTransform(svgEl));
          }
        });

        wrap.appendChild(btn);
      });

      controlsEl.appendChild(wrap);

      // Highlight the initial active state
      updateButtonStyles(lodState);
    }

    function setupRelationFilters() {
      const controlsEl = document.getElementById("controls");
      if (!controlsEl) return;

      const wrap = document.createElement("div");
      wrap.id = "relation-filters";
      wrap.style.cssText = "display:flex;flex-wrap:wrap;align-items:center;gap:3px;padding:3px 0 0 0;width:100%;";

      const label = document.createElement("span");
      label.textContent = "edges:";
      label.style.cssText = "font-size:9px;color:var(--text-dim);margin-right:2px;text-transform:uppercase;letter-spacing:0.1em;font-family:inherit;";
      wrap.appendChild(label);

      Object.entries(RELATION_COLORS).forEach(([rel, color]) => {
        const btn = document.createElement("button");
        btn.dataset.relation = rel;
        btn.title = `Toggle ${rel} edges`;
        btn.style.cssText = "display:inline-flex;align-items:center;gap:3px;padding:2px 6px;font-size:10px;border-radius:2px;border:1px solid var(--border);background:var(--bg-raised);color:var(--text-muted);cursor:pointer;transition:opacity 0.15s;font-family:inherit;box-shadow:var(--shadow-sm);";

        const dot = document.createElement("span");
        dot.style.cssText = `display:inline-block;width:6px;height:6px;border-radius:50%;background:${color};flex-shrink:0;opacity:0.7;`;
        btn.appendChild(dot);
        btn.appendChild(document.createTextNode(rel));

        btn.addEventListener("click", () => {
          if (hiddenRelations.has(rel)) {
            hiddenRelations.delete(rel);
            btn.style.opacity = "1";
            btn.style.textDecoration = "none";
          } else {
            hiddenRelations.add(rel);
            btn.style.opacity = "0.35";
            btn.style.textDecoration = "line-through";
          }
          applyLodVisibility();
        });

        wrap.appendChild(btn);
      });

      controlsEl.appendChild(wrap);
    }

    // -----------------------------------------------------------------------
    // -----------------------------------------------------------------------
    // VS Code-style directory tree panel
    // -----------------------------------------------------------------------
    function resetPathFilter(breadcrumbEl, resetBtn) {
      activePathFilter = null;
      if (breadcrumbEl) breadcrumbEl.textContent = "All files";
      if (resetBtn) resetBtn.style.display = "none";
      applyLodVisibility();
    }

    function buildTreePanel() {
      const toc = window._cg_toc;
      const contentEl = document.getElementById("tree-content");
      const breadcrumbEl = document.getElementById("tree-breadcrumb");
      const resetBtn = document.getElementById("tree-reset");
      if (!contentEl) return;

      // Build dir tree from toc.dirs array or derive from toc.files keys
      // toc.dirs is an array of dir path strings (relative), or we derive from files
      let dirs = [];
      if (toc && toc.dirs) {
        dirs = toc.dirs.slice().sort();
      } else if (toc && toc.files) {
        const dirSet = new Set();
        Object.keys(toc.files).forEach(fp => {
          const parts = fp.split("/");
          for (let i = 1; i < parts.length; i++) {
            dirSet.add(parts.slice(0, i).join("/"));
          }
        });
        dirs = Array.from(dirSet).sort();
      }

      // Track collapsed dirs (collapsed = children hidden)
      const collapsedDirs = new Set();

      function isChildPath(child, parent) {
        return child !== parent && (child.startsWith(parent + "/"));
      }

      function renderTree() {
        contentEl.innerHTML = "";

        // "All files" root entry
        const rootItem = document.createElement("div");
        rootItem.className = "tree-item" + (activePathFilter === null ? " active" : "");
        rootItem.innerHTML = `<span class="tree-icon" style="color:var(--text-dim);font-size:10px;">&#x2302;</span><span class="tree-label">all files</span>`;
        rootItem.addEventListener("click", () => {
          resetPathFilter(breadcrumbEl, resetBtn);
          renderTree();
        });
        contentEl.appendChild(rootItem);

        dirs.forEach(dirPath => {
          // Compute depth and parent
          const depth = dirPath.split("/").length - 1;
          const parentPath = depth > 0 ? dirPath.split("/").slice(0, -1).join("/") : null;

          // Hide if any ancestor is collapsed
          if (parentPath && collapsedDirs.has(parentPath)) return;
          // Also hide if a grandparent is collapsed
          const parts = dirPath.split("/");
          for (let i = 1; i < parts.length - 1; i++) {
            if (collapsedDirs.has(parts.slice(0, i).join("/"))) return;
          }

          const hasChildren = dirs.some(d => isChildPath(d, dirPath));
          const isCollapsed = collapsedDirs.has(dirPath);
          const dirName = dirPath.split("/").pop();
          const isActive = activePathFilter === dirPath;

          const item = document.createElement("div");
          item.className = "tree-item" + (isActive ? " active" : "");
          item.style.paddingLeft = (8 + depth * 14) + "px";

          const toggleIcon = hasChildren ? (isCollapsed ? "▶" : "▼") : " ";
          item.innerHTML = `<span class="tree-icon" style="font-size:9px;width:10px;text-align:center;color:var(--text-dim);">${toggleIcon}</span><span class="tree-icon" style="color:var(--text-dim);font-size:10px;">&#x25A1;</span><span class="tree-label" title="${dirPath}">${dirName}</span>`;

          // Click on toggle arrow: collapse/expand subtree
          const iconEl = item.querySelector(".tree-icon");
          if (hasChildren && iconEl) {
            iconEl.style.cursor = "pointer";
            iconEl.addEventListener("click", (ev) => {
              ev.stopPropagation();
              if (collapsedDirs.has(dirPath)) {
                collapsedDirs.delete(dirPath);
              } else {
                collapsedDirs.add(dirPath);
              }
              renderTree();
            });
          }

          // Click on row: set path filter
          item.addEventListener("click", () => {
            activePathFilter = dirPath;
            if (breadcrumbEl) breadcrumbEl.textContent = dirPath;
            if (resetBtn) resetBtn.style.display = "";
            // In server mode, ensure file-level data is loaded before filtering
            const isServerMode = (typeof GRAPH_DATA === "undefined" || GRAPH_DATA === null);
            if (lodState === "DIR_ONLY") {
              if (isServerMode && !fileDataLoaded && !zoomFetchPending) {
                zoomFetchPending = true;
                fetch("/graphs/tier_file.json")
                  .then(r => r.json())
                  .then(fileData => {
                    fileDataLoaded = true;
                    zoomFetchPending = false;
                    lodState = "FILE_LEVEL";
                    mergeGraphData(fileData);
                    renderTree();
                  })
                  .catch(() => { zoomFetchPending = false; });
              } else {
                lodState = "FILE_LEVEL";
                applyLodVisibility();
                if (window._cg_updateLodBtns) window._cg_updateLodBtns();
              }
            } else {
              applyLodVisibility();
            }
            renderTree();
          });

          contentEl.appendChild(item);
        });
      }

      if (resetBtn) {
        resetBtn.addEventListener("click", () => {
          resetPathFilter(breadcrumbEl, resetBtn);
          renderTree();
        });
      }

      renderTree();
    }

    buildTreePanel();

    setupRelationFilters();
    setupLodButtons();

    // Reset-view button — resets D3 zoom/pan to identity
    {
      const controlsEl = document.getElementById("controls");
      if (controlsEl) {
        const btn = document.createElement("button");
        btn.title = "Reset view";
        btn.textContent = "⌖ reset view";
        btn.style.cssText = "padding:3px 7px;font-size:10px;border-radius:2px;border:1px solid var(--border);background:var(--bg-raised);color:var(--text-muted);cursor:pointer;font-family:inherit;white-space:nowrap;box-shadow:var(--shadow-sm);";
        btn.addEventListener("click", () => {
          svg.transition().duration(400).call(zoom.transform, d3.zoomIdentity);
        });
        controlsEl.appendChild(btn);
      }
    }

    // Toggle expansion of a directory node.
    // Ensures file data is loaded, then flips the expanded state and re-applies visibility.
    function toggleDirExpansion(dirNode) {
      if (expandedDirs.has(dirNode.id)) {
        expandedDirs.delete(dirNode.id);
        applyLodVisibility();
        return;
      }

      expandedDirs.add(dirNode.id);

      // In standalone mode all data is already loaded; just re-apply visibility.
      const isServerMode = (typeof GRAPH_DATA === "undefined" || GRAPH_DATA === null);
      if (isServerMode && !fileDataLoaded && !zoomFetchPending) {
        zoomFetchPending = true;
        fetch("/graphs/tier_file.json")
          .then(r => r.json())
          .then(fileData => {
            fileDataLoaded = true;
            zoomFetchPending = false;
            mergeGraphData(fileData);
            // mergeGraphData calls applyLodVisibility at the end
          })
          .catch(() => { zoomFetchPending = false; expandedDirs.delete(dirNode.id); applyLodVisibility(); });
      } else {
        applyLodVisibility();
      }
    }

    function loadVisibleSubGraphs(transform) {
      if (!window._cg_toc) return;
      const visibleFileIds = getViewportNodeIds(transform);
      const toc = window._cg_toc;
      // files map: filePath -> {slug, graph} — covers all files, not just entry points
      const filesMap = toc.files || {};
      // Fallback: entry_points array (legacy)
      const eps = toc.entry_points || [];

      let anyMatched = false;
      visibleFileIds.forEach(fileNodeId => {
        // Extract file path from node id: feature::path/to/file.py
        const parts = fileNodeId.split("::");
        const filePath = parts[1] || "";

        // Prefer per-file sub-graph from toc.files, fall back to entry_points
        let entry = filesMap[filePath];
        if (!entry) {
          const ep = eps.find(e => e.file === filePath);
          if (ep) entry = ep;
        }
        if (!entry || loadedSubGraphs.has(entry.slug)) return;
        anyMatched = true;
        loadedSubGraphs.add(entry.slug);

        fetch(`/graphs/${entry.graph}`)
          .then(r => r.json())
          .then(subData => { mergeGraphData(subData); })
          .catch(() => {});
      });

      // Fallback: if no per-file sub-graphs available, load tier_symbol.json once
      if (!anyMatched && !loadedSubGraphs.has("__tier_symbol__")) {
        loadedSubGraphs.add("__tier_symbol__");
        fetch("/graphs/tier_symbol.json")
          .then(r => r.json())
          .then(symData => { mergeGraphData(symData); })
          .catch(() => {});
      }
    }

    // Initial LOD state is set after render blocks (below)
    // (applyLodVisibility needs .nodes/.links groups to exist first)

    // -----------------------------------------------------------------------
    // Force simulation
    // -----------------------------------------------------------------------
    const simulation = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(links)
        .id(d => d.id)
        .distance(d => {
          if (d.relation === "contains") return 60;
          if (d.relation === "defines")  return 90;
          return 120;
        })
        .strength(d => {
          if (d.relation === "contains") return 1.0;
          if (d.relation === "defines")  return 0.7;
          return 0.25;
        })
      )
      .force("charge", d3.forceManyBody()
        .strength(d => {
          if (d.type === "file")   return -400;
          if (d.type === "type")   return -200;
          return -80;
        })
        .distanceMax(600)
      )
      .force("center", d3.forceCenter(width / 2, height / 2).strength(0.08))
      .force("gravityX", d3.forceX(width / 2).strength(0.04))
      .force("gravityY", d3.forceY(height / 2).strength(0.04))
      .force("collision", d3.forceCollide().radius(d => nodeR(d) + 14))
      .alphaDecay(0.028);

    // -----------------------------------------------------------------------
    // Render edges
    // -----------------------------------------------------------------------
    g.append("g").attr("class", "links");
    let linkSel = g.select(".links")
      .selectAll("line")
      .data(links)
      .join("line")
        .attr("class",            d => `link ${d.relation}${d.unresolved ? " unresolved" : ""}${d.relay ? " relay" : ""}`)
        .attr("stroke-width",     1.2)
        .attr("stroke-dasharray", d => d.relay ? "6,3" : null)
        .attr("stroke",           d => d.role === "control" ? ROLE_CONTROL_COLOR : (RELATION_COLORS[d.relation] || "#888"))
        .attr("marker-end",       d => d.unresolved ? null : `url(#arrow-${d.relation})`);
    let linkSel2 = linkSel;

    // -----------------------------------------------------------------------
    // Render nodes
    // -----------------------------------------------------------------------
    g.append("g").attr("class", "nodes");
    let nodeSel = g.select(".nodes")
      .selectAll("g")
      .data(nodes, d => d.id)
      .join("g")
        .attr("class", d => {
          let c = `node ${d.type || "symbol"}`;
          if (d.is_test)                      c += " test";
          if (d.type === "file" && !d.file)   c += " stdlib";
          if (d.type === "directory" && (d.count === 0 || d.count == null)) c += " empty-dir";
          return c;
        })
        .call(d3.drag()
          .on("start", (ev, d) => { if (!ev.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
          .on("drag",  (ev, d) => { d.fx = ev.x; d.fy = ev.y; })
          .on("end",   (ev, d) => { if (!ev.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; })
        )
        .on("click", (ev, d) => { ev.stopPropagation(); selectNode(d); })
        .on("dblclick", (ev, d) => {
          ev.stopPropagation();
          if (d.type === "directory") toggleDirExpansion(d);
        });
    let nodeSel2 = nodeSel;

    nodeSel.append("circle").attr("r", d => nodeR(d));
    nodeSel.append("text")
      .attr("dy", d => nodeR(d) + 3)
      .text(d => trunc(d.label, 20));

    svg.on("click", () => clearSel());

    // Apply initial LOD visibility now that .nodes/.links groups exist
    if (data.nodes && data.nodes.some(n => n.type === "symbol")) {
      lodState = "SYMBOL_LEVEL"; // Standalone mode: show everything
    }
    applyLodVisibility();

    // -----------------------------------------------------------------------
    // Tick
    // -----------------------------------------------------------------------
    function tickFn() {
      linkSel2
        .attr("x1", d => d.source.x)
        .attr("y1", d => d.source.y)
        .attr("x2", d => d.target.x)
        .attr("y2", d => d.target.y);
      nodeSel2.attr("transform", d => `translate(${d.x},${d.y})`);
    }
    simulation.on("tick", tickFn);

    // Zoom-to-fit after layout settles
    function zoomFitSafe() {
      zoomFit();
    }
    simulation.on("end", () => zoomFitSafe());
    setTimeout(zoomFitSafe, 3000);

    // -----------------------------------------------------------------------
    // Selection
    // -----------------------------------------------------------------------
    let selId = null;

    function selectNode(d) {
      if (selId === d.id) { clearSel(); return; }
      selId = d.id;
      const nb = neighbors.get(d.id) || new Set();

      nodeSel2
        .classed("dimmed",      n => n.id !== d.id && !nb.has(n.id))
        .classed("highlighted", n => n.id === d.id ||  nb.has(n.id));
      linkSel2
        .classed("dimmed",      lk => lk.source.id !== d.id && lk.target.id !== d.id)
        .classed("highlighted", lk => lk.source.id === d.id || lk.target.id === d.id);

      renderSidebar(d, edgesByNode.get(d.id) || [], nodeById, () => toggleDirExpansion(d), () => expandedDirs.has(d.id));
    }

    function clearSel() {
      selId = null;
      nodeSel2.classed("dimmed", false).classed("highlighted", false);
      linkSel2.classed("dimmed", false).classed("highlighted", false);
      document.getElementById("sidebar-content").innerHTML = "";
    }

    // Esc: close diagram panel
    document.addEventListener("keydown", ev => {
      if (ev.key !== "Escape") return;
      hideDiagramPanel();
    });



    // -----------------------------------------------------------------------
    // Search
    // -----------------------------------------------------------------------
    document.getElementById("search").addEventListener("input", function () {
      const q = this.value.trim().toLowerCase();
      if (!q) {
        // Clear search highlighting
        nodeSel2.classed("search-highlight", false)
                .classed("dimmed", false);
        linkSel2.classed("dimmed", false);
        document.getElementById("sidebar-content").innerHTML = "";
        return;
      }
      const hits = new Set(nodes.filter(n => {
        const label = (n.label || "").toLowerCase();
        const id = (n.id || "").toLowerCase();
        return label.includes(q) || id.includes(q);
      }).map(n => n.id));

      // Dim non-matching nodes to 25% opacity
      nodeSel2.classed("search-highlight", n => hits.has(n.id))
              .classed("dimmed", n => !hits.has(n.id))
              .style("opacity", n => hits.has(n.id) ? 1 : 0.25);

      // Dim edges that don't connect matching nodes
      linkSel2.classed("dimmed", lk => !hits.has(lk.source.id) && !hits.has(lk.target.id))
              .style("opacity", lk => {
                if (hits.has(lk.source.id) || hits.has(lk.target.id)) return 1;
                return 0.05;
              });

      // If exactly 1 match, pan/zoom to center on it
      if (hits.size === 1) {
        const matchId = Array.from(hits)[0];
        const matchNode = nodeById.get(matchId);
        if (matchNode && matchNode.x != null && matchNode.y != null) {
          const pad = 100;
          const sc = 2.0;  // zoom in 2x on the node
          const tx = width / 2 - matchNode.x * sc;
          const ty = height / 2 - matchNode.y * sc;
          svg.transition().duration(600)
             .call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(sc));
        }
      }

      document.getElementById("sidebar-content").innerHTML =
        `<div class="sb-label">Search</div><div class="sb-value">${hits.size} match(es)</div>`;
    });

    // -----------------------------------------------------------------------
    // Filter buttons — node type filters
    // -----------------------------------------------------------------------
    document.querySelectorAll(".filter-btn[data-type]").forEach(btn => {
      btn.addEventListener("click", () => {
        btn.classList.toggle("active");
        const hidden = new Set(
          Array.from(document.querySelectorAll(".filter-btn[data-type].active"))
               .map(b => b.dataset.type)
        );
        nodeSel2.style("display", d => hidden.has(d.type) ? "none" : null);
        linkSel2.style("display", lk => {
          const st = lk.source.type, tt = lk.target.type;
          return (hidden.has(st) || hidden.has(tt)) ? "none" : null;
        });
      });
    });

    // -----------------------------------------------------------------------
    // Filter buttons — edge relation filters
    // -----------------------------------------------------------------------
    const hiddenEdgeRelations = new Set();
    document.querySelectorAll(".filter-btn[data-relation]").forEach(btn => {
      btn.addEventListener("click", () => {
        btn.classList.toggle("active");
        const relation = btn.dataset.relation;
        if (btn.classList.contains("active")) {
          hiddenEdgeRelations.add(relation);
        } else {
          hiddenEdgeRelations.delete(relation);
        }
        // Just hide/show the edges, don't remove from DOM
        linkSel2.style("display", lk => {
          if (hiddenEdgeRelations.has(lk.relation)) return "none";
          return null;
        });
      });
    });

    // -----------------------------------------------------------------------
    // Helpers
    // -----------------------------------------------------------------------
    function zoomFit() {
      try {
        const b = g.node().getBBox();
        if (!b.width || !b.height) return;
        const pad = 50;
        const sc  = Math.min((width - pad*2) / b.width, (height - pad*2) / b.height, 1.5);
        const tx  = (width  - b.width  * sc) / 2 - b.x * sc;
        const ty  = (height - b.height * sc) / 2 - b.y * sc;
        svg.transition().duration(700)
           .call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(sc));
      } catch (_) {}
    }
  }

  // -----------------------------------------------------------------------
  // Sidebar
  // -----------------------------------------------------------------------
  function renderSidebar(node, edgeEntries, nodeById, onDirToggle, isDirExpanded) {
    const el = document.getElementById("sidebar-content");
    const isStdlib = node.type === "file" && !node.file;
    const badge = isStdlib ? "stdlib" : (node.type || "symbol");

    let h = `
      <div class="sb-label">Type</div>
      <div><span class="sb-badge ${badge}">${badge}${node.is_dataclass?" · dataclass":""}${node.is_test?" · test":""}</span></div>
      <div class="sb-label">Label</div>
      <div class="sb-value">${esc(node.label)}</div>
      <div class="sb-label">ID</div>
      <div class="sb-value id">${esc(node.id)}</div>
    `;
    if (node.file)  h += `<div class="sb-label">File</div><div class="sb-value">${esc(node.file)}</div>`;
    if (node.line)  h += `<div class="sb-label">Line</div><div class="sb-value">${node.line}</div>`;

    if (edgeEntries.length) {
      h += `<div class="sb-label">Edges (${edgeEntries.length})</div><div class="sb-edge-list">`;
      for (const { link: lk, dir } of edgeEntries) {
        const other = dir === "out" ? lk.target : lk.source;
        const lbl   = other ? other.label : "?";
        const arrow = dir === "out" ? "&rarr;" : "&larr;";
        // Show file basename to disambiguate .h vs .cc symbols with the same name
        const otherFile = other && other.file ? other.file.split("/").pop() : null;
        let meta = "";
        if (otherFile)                 meta += ` <span style="color:var(--text-dim);font-size:9px;">${esc(otherFile)}</span>`;
        if (lk.seq  != null)           meta += ` <span style="color:var(--text-dim);">[seq:${lk.seq}]</span>`;
        if (lk.role === "control")     meta += ` <span style="color:${ROLE_CONTROL_COLOR}">[ctrl]</span>`;
        if (lk.relay)                  meta += ` <span style="color:var(--text-muted);">[relay]</span>`;
        if (lk.via)                    meta += ` <span style="color:var(--text-muted);">[via:${esc(lk.via)}]</span>`;
        h += `<div class="sb-edge${lk.unresolved?" unresolved":""}">
                <span class="relation">${lk.relation}</span> ${arrow} ${esc(lbl)}${meta}
              </div>`;
      }
      h += "</div>";
    }

    // Type structure tree (only for type nodes with outgoing contains edges)
    if (node.type === "type") {
      const containsOut = edgeEntries.filter(e => e.dir === "out" && e.link.relation === "contains");
      if (containsOut.length > 0) {
        h += `<div class="sb-label" style="margin-top:8px;">Type Structure</div>`;
        h += `<div style="font-family:'JetBrains Mono',Consolas,monospace;font-size:10px;line-height:1.8;padding:4px 8px;background:var(--bg-deep);border-radius:2px;margin-bottom:4px;border:1px solid var(--border-muted);box-shadow:var(--shadow-sm);">`;
        h += `<span style="color:#9050d8;font-weight:600;">${esc(node.label)}</span> <span style="color:var(--text-dim);">{</span><br>`;
        for (const { link: lk } of containsOut) {
          const fieldLabel = lk.target ? (lk.target.label || "?") : "?";
          const pDepth = lk.ptr_depth != null ? lk.ptr_depth : 0;
          const stars = "*".repeat(pDepth);
          h += `&nbsp;&nbsp;<span style="color:var(--text-muted);">${esc(fieldLabel)}</span><span style="color:var(--text-dim);">${stars}</span>`;
          if (pDepth > 0) h += ` <span style="color:var(--text-dim);font-size:9px;">ptr:${pDepth}</span>`;
          h += `<br>`;
        }
        h += `<span style="color:var(--text-dim);">}</span>`;
        h += `</div>`;
      }
    }

    if (node.type === "directory" && onDirToggle) {
      const expanded = isDirExpanded && isDirExpanded();
      const btnLabel = expanded ? "&#x25B4; Collapse files" : "&#x25BE; Expand files";
      h += `<button id="dir-expand-btn" style="font-family:'JetBrains Mono',Consolas,monospace;font-size:10px;background:var(--bg-raised);color:var(--text-muted);border:1px solid var(--border);padding:5px 10px;border-radius:2px;cursor:pointer;margin-top:5px;width:100%;box-sizing:border-box;text-align:left;box-shadow:var(--shadow-sm);">${btnLabel}</button>`;
    }

    const SB_BTN = "font-family:'JetBrains Mono',Consolas,monospace;font-size:10px;background:var(--bg-raised);color:var(--text-muted);border:1px solid var(--border);padding:5px 10px;border-radius:2px;cursor:pointer;margin-top:5px;width:100%;box-sizing:border-box;text-align:left;transition:border-color 0.12s,color 0.12s;box-shadow:var(--shadow-sm);";
    h += `<div style="border-top:1px solid var(--border-muted);margin-top:10px;padding-top:6px;">`;
    h += `<button id="flowchart-btn" style="${SB_BTN}">&#x21AA; Flowchart</button>`;
    h += `<button id="dataflow-btn" style="${SB_BTN}">&#x21C6; Data Flow</button>`;
    if (node.type === "file" || node.type === "symbol") {
      h += `<button id="state-diag-btn" style="${SB_BTN}">&#x25A6; State diagram</button>`;
    }
    if (node.type === "type") {
      h += `<button id="type-diag-btn" style="${SB_BTN}">&#x25A6; Type diagram</button>`;
    }
    h += `</div>`;

    el.innerHTML = h;

    // Wire diagram buttons
    // Clear per-tab loaders and pane contents whenever a new node is inspected
    _diagLoaders.flowchart = null;
    _diagLoaders.dataflow = null;
    _diagLoaders.state = null;
    ["flowchart", "dataflow", "state"].forEach(tab => {
      const p = document.getElementById(`pane-${tab}`);
      if (p) p.querySelector(".diag-content").innerHTML = "";
    });

    function _fetchDiagram(tabId, url, labelFn, mermaidKey) {
      const pane = document.getElementById(`pane-${tabId}`);
      const content = pane && pane.querySelector(".diag-content");
      if (content && content.innerHTML.trim() !== "") return; // already loaded
      if (content) content.innerHTML = '<div style="color:var(--text-dim);font-size:10px;padding:20px;letter-spacing:0.08em;">loading…</div>';
      fetch(url)
        .then(r => r.json())
        .then(data => {
          const text = data.error ? "Error: " + data.error : (data[mermaidKey] || data.output || "");
          showDiagramPanel(tabId, labelFn(data), text);
        })
        .catch(err => showDiagramPanel(tabId, "Error", "Fetch failed: " + err.message));
    }

    const flowchartBtn = document.getElementById("flowchart-btn");
    if (flowchartBtn) {
      const loadFlowchart = () => _fetchDiagram(
        "flowchart",
        `/api/diagram/flowchart?node=${encodeURIComponent(node.id)}`,
        () => node.label,
        "mermaid"
      );
      _diagLoaders.flowchart = loadFlowchart;
      flowchartBtn.addEventListener("click", () => {
        _openDiagramPanel("flowchart");
        loadFlowchart();
      });
    }

    const dataflowBtn = document.getElementById("dataflow-btn");
    if (dataflowBtn) {
      const loadDataflow = () => _fetchDiagram(
        "dataflow",
        `/api/diagram/dataflow?node=${encodeURIComponent(node.id)}`,
        () => node.label,
        "mermaid"
      );
      _diagLoaders.dataflow = loadDataflow;
      dataflowBtn.addEventListener("click", () => {
        _openDiagramPanel("dataflow");
        loadDataflow();
      });
    }

    const stateDiagBtn = document.getElementById("state-diag-btn");
    if (stateDiagBtn) {
      const entryFile = node.file || node.id.split("::").slice(1, -1).join("/") || node.id;
      const loadState = () => _fetchDiagram(
        "state",
        `/api/diagram/flow?entry=${encodeURIComponent(entryFile)}`,
        data => data.error ? "Error" : "State — " + entryFile,
        "mermaid"
      );
      _diagLoaders.state = loadState;
      stateDiagBtn.addEventListener("click", () => {
        _openDiagramPanel("state");
        loadState();
      });
    }

    const typeDiagBtn = document.getElementById("type-diag-btn");
    if (typeDiagBtn) {
      const typeName = node.label;
      const loadType = () => _fetchDiagram(
        "state",
        `/api/diagram/type?type=${encodeURIComponent(typeName)}&format=mermaid`,
        data => data.error ? "Error" : "Class — " + typeName,
        "output"
      );
      _diagLoaders.state = loadType;
      typeDiagBtn.addEventListener("click", () => {
        _openDiagramPanel("state");
        loadType();
      });
    }

    // Directory expand/collapse button
    const dirExpandBtn = document.getElementById("dir-expand-btn");
    if (dirExpandBtn && onDirToggle) {
      dirExpandBtn.addEventListener("click", onDirToggle);
    }
  }

  function nodeR(d) {
    if (d.type === "file") return d.file ? 10 : 5;
    if (d.type === "type") return 8;
    return 6;
  }
  function trunc(s, n) { return s && s.length > n ? s.slice(0, n-1) + "…" : (s || ""); }
  function esc(s)       { return (s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

})();
