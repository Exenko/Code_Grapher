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
  // Mermaid diagram panel
  // -----------------------------------------------------------------------
  mermaid.initialize({ startOnLoad: false, theme: "dark", securityLevel: "loose" });

  // Split mermaid text (which may contain multiple diagrams) into individual chunks
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
    return chunks.filter(c => /stateDiagram-v2|classDiagram/.test(c));
  }

  function showDiagramPanel(title, mermaidText) {
    const panel   = document.getElementById("diagram-panel");
    const content = document.getElementById("diagram-content");
    const titleEl = document.getElementById("diagram-title");
    titleEl.textContent = title;
    panel.style.display = "flex";  // flex column layout

    const diagrams = _splitDiagrams(mermaidText);
    if (diagrams.length === 0) {
      content.innerHTML = `<pre style="color:#e74c3c;font-size:11px;">No diagram found in output.\n\n${mermaidText}</pre>`;
      return;
    }

    content.innerHTML = '<div style="color:#8899bb;font-family:monospace;padding:20px;">Rendering...</div>';

    // Build tab bar if there are multiple diagrams (File Level / Symbol Level)
    const labels = diagrams.map((d, i) => {
      if (/stateDiagram-v2/.test(d)) return i === 0 ? "File Level" : "Symbol Level";
      return `Diagram ${i + 1}`;
    });

    const ts = Date.now();
    let tabBar = "";
    if (diagrams.length > 1) {
      tabBar = `<div id="diag-tabs" style="display:flex;gap:4px;margin-bottom:12px;">` +
        labels.map((lbl, i) =>
          `<button class="diag-tab" data-idx="${i}" style="background:${i===0?"#6a3aaf":"#1e2236"};color:${i===0?"#fff":"#8899bb"};border:1px solid #2a3050;padding:4px 10px;border-radius:3px;cursor:pointer;font-family:monospace;font-size:11px;">${lbl}</button>`
        ).join("") +
        `</div>`;
    }

    const diagramDivs = diagrams.map((d, i) =>
      `<div class="diag-page" data-idx="${i}" style="display:${i===0?"block":"none"};"><div class="mermaid" id="mermaid-${ts}-${i}">${d}</div></div>`
    ).join("");

    content.innerHTML = tabBar + diagramDivs;

    // Wire tab switching
    content.querySelectorAll(".diag-tab").forEach(btn => {
      btn.addEventListener("click", () => {
        const idx = +btn.dataset.idx;
        content.querySelectorAll(".diag-tab").forEach(b => {
          b.style.background = b.dataset.idx == idx ? "#6a3aaf" : "#1e2236";
          b.style.color      = b.dataset.idx == idx ? "#fff"    : "#8899bb";
        });
        content.querySelectorAll(".diag-page").forEach(p => {
          p.style.display = p.dataset.idx == idx ? "block" : "none";
        });
      });
    });

    // Render each diagram independently so one failure doesn't block the others
    diagrams.forEach((diagSrc, i) => {
      const el = document.getElementById(`mermaid-${ts}-${i}`);
      if (!el) return;
      mermaid.run({ nodes: [el] }).catch(err => {
        // Replace failed render with copyable source text
        el.outerHTML = `<div style="margin-bottom:24px;">
          <div style="color:#e6a817;font-family:monospace;font-size:11px;margin-bottom:4px;">
            ⚠ Mermaid render error: ${esc(err.message)} — raw source below (copy to <a href="https://mermaid.live" target="_blank" style="color:#6a9eff;">mermaid.live</a>)
          </div>
          <pre style="color:#ccd;font-size:11px;background:#111420;padding:10px;border-radius:4px;overflow:auto;white-space:pre;">${esc(diagSrc)}</pre>
        </div>`;
      });
    });
  }

  function hideDiagramPanel() {
    document.getElementById("diagram-panel").style.display = "none";
  }

  // Wire up diagram panel controls — DOM is already parsed when this script runs
  {
    // Close button
    document.getElementById("diagram-close").addEventListener("click", hideDiagramPanel);

    // Zoom slider
    const zoomSlider = document.getElementById("diagram-zoom");
    const zoomVal    = document.getElementById("diagram-zoom-val");
    const content    = document.getElementById("diagram-content");
    zoomSlider.addEventListener("input", () => {
      const pct = zoomSlider.value;
      zoomVal.textContent = pct + "%";
      content.style.transform = `scale(${pct / 100})`;
    });

    // Zoom reset
    document.getElementById("diagram-zoom-reset").addEventListener("click", () => {
      zoomSlider.value = 100;
      zoomVal.textContent = "100%";
      content.style.transform = "scale(1)";
    });

    // Full-width toggle
    const panel = document.getElementById("diagram-panel");
    document.getElementById("diagram-fullscreen").addEventListener("click", () => {
      panel.style.width = panel.style.width === "100%" ? "75%" : "100%";
    });

    // Drag-resize handle
    const resizeHandle = document.getElementById("diagram-resize");
    let _dragging = false;
    resizeHandle.addEventListener("mousedown", e => { _dragging = true; e.preventDefault(); });
    document.addEventListener("mousemove", e => {
      if (!_dragging) return;
      const newWidth = window.innerWidth - e.clientX;
      panel.style.width = Math.max(300, Math.min(window.innerWidth - 100, newWidth)) + "px";
    });
    document.addEventListener("mouseup", () => { _dragging = false; });
  }

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
    if (GRAPH_DATA !== null && typeof GRAPH_DATA !== "undefined") {
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
    if (el) el.style.display = "none";
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
      const el = document.getElementById("loading");
      if (el) el.textContent = "Error loading graph: " + err.message;
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

    // Trace mode state
    let traceMode = false;
    let traceFromNodeId = null;

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
      const newNodes = (newData.nodes || []).filter(nd => !nodeById.has(nd.id)).map(nd => ({ ...nd }));
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
                return c;
              })
              .call(d3.drag()
                .on("start", (ev, d) => { if (!ev.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
                .on("drag",  (ev, d) => { d.fx = ev.x; d.fy = ev.y; })
                .on("end",   (ev, d) => { if (!ev.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; })
              )
              .on("click", (ev, d) => { ev.stopPropagation(); selectNode(d); });
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
      // Hide/show nodes by type based on current LOD state
      // Uses CSS display toggling — never removes nodes from memory
      const allNodeSel = g.select(".nodes").selectAll("g");
      allNodeSel.style("display", d => {
        if (lodState === "DIR_ONLY") {
          return (d.type === "directory" || d.type === "repo") ? null : "none";
        } else if (lodState === "FILE_LEVEL") {
          return (d.type === "symbol" || d.type === "type") ? "none" : null;
        }
        return null; // SYMBOL_LEVEL: show all
      });
      const allLinkSel = g.select(".links").selectAll("line");
      allLinkSel.style("display", d => {
        if (!d || !d.source || !d.target) return null;
        if (hiddenRelations.has(d.relation)) return "none";
        const st = d.source.type, tt = d.target.type;
        if (lodState === "DIR_ONLY") {
          return (st === "directory" || st === "repo") && (tt === "directory" || tt === "repo") ? null : "none";
        } else if (lodState === "FILE_LEVEL") {
          return (st === "symbol" || st === "type" || tt === "symbol" || tt === "type") ? "none" : null;
        }
        return null;
      });
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
      wrap.style.cssText = "display:flex;align-items:center;gap:4px;padding:3px 6px;border-top:1px solid #2a2a3a;background:#181820;";

      const label = document.createElement("span");
      label.textContent = "LOD:";
      label.style.cssText = "font-size:10px;color:#555;margin-right:2px;";
      wrap.appendChild(label);

      const levels = [
        { id: "lod-dir",    label: "Directories", state: "DIR_ONLY" },
        { id: "lod-file",   label: "Files",        state: "FILE_LEVEL" },
        { id: "lod-symbol", label: "Symbols",      state: "SYMBOL_LEVEL" },
      ];

      function updateButtonStyles(activeState) {
        levels.forEach(({ id, state }) => {
          const b = document.getElementById(id);
          if (!b) return;
          if (state === activeState) {
            b.style.background = "#2a3a5a";
            b.style.color = "#8ab4f8";
            b.style.borderColor = "#4a6090";
          } else {
            b.style.background = "#252530";
            b.style.color = "#bbb";
            b.style.borderColor = "#444";
          }
        });
      }

      levels.forEach(({ id, label: btnLabel, state }) => {
        const btn = document.createElement("button");
        btn.id = id;
        btn.textContent = btnLabel;
        btn.style.cssText = "padding:2px 8px;font-size:10px;border-radius:3px;border:1px solid #444;background:#252530;color:#bbb;cursor:pointer;";

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
      wrap.style.cssText = "display:flex;flex-wrap:wrap;align-items:center;gap:3px;padding:3px 6px;border-top:1px solid #2a2a3a;background:#181820;";

      const label = document.createElement("span");
      label.textContent = "edges:";
      label.style.cssText = "font-size:10px;color:#555;margin-right:2px;";
      wrap.appendChild(label);

      Object.entries(RELATION_COLORS).forEach(([rel, color]) => {
        const btn = document.createElement("button");
        btn.dataset.relation = rel;
        btn.title = `Toggle ${rel} edges`;
        btn.style.cssText = "display:inline-flex;align-items:center;gap:3px;padding:2px 6px;font-size:10px;border-radius:3px;border:1px solid #444;background:#252530;color:#bbb;cursor:pointer;transition:opacity 0.15s;";

        const dot = document.createElement("span");
        dot.style.cssText = `display:inline-block;width:7px;height:7px;border-radius:50%;background:${color};flex-shrink:0;`;
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
    setupRelationFilters();
    setupLodButtons();

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
        .id(d => d.id)          // not strictly needed since we pass objects, but safe
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
          if (d.type === "file")   return -600;
          if (d.type === "type")   return -300;
          return -120;
        })
      )
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide().radius(d => nodeR(d) + 18))
      .alphaDecay(0.025);

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
          return c;
        })
        .call(d3.drag()
          .on("start", (ev, d) => { if (!ev.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
          .on("drag",  (ev, d) => { d.fx = ev.x; d.fy = ev.y; })
          .on("end",   (ev, d) => { if (!ev.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; })
        )
        .on("click", (ev, d) => { ev.stopPropagation(); selectNode(d); });
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

      renderSidebar(d, edgesByNode.get(d.id) || [], nodeById, () => applyTrace(d.id), () => applyDataFlowTrace(d.id));
    }

    function clearSel() {
      selId = null;
      nodeSel2.classed("dimmed", false).classed("highlighted", false);
      linkSel2.classed("dimmed", false).classed("highlighted", false);
      document.getElementById("sidebar-content").innerHTML = "";
    }

    function applyTrace(nodeId) {
      traceMode = true;
      traceFromNodeId = nodeId;

      // BFS to get reachable nodes and assign depth levels
      const depth = new Map();
      depth.set(nodeId, 0);
      const queue = [nodeId];
      while (queue.length > 0) {
        const cur = queue.shift();
        for (const lk of links) {
          const srcId = typeof lk.source === 'object' ? lk.source.id : lk.source;
          const tgtId = typeof lk.target === 'object' ? lk.target.id : lk.target;
          if (srcId === cur && !depth.has(tgtId)) {
            depth.set(tgtId, depth.get(cur) + 1);
            queue.push(tgtId);
          }
        }
      }

      const reachableIds = new Set(depth.keys());

      // Group nodes by depth level
      const byDepth = new Map();
      for (const [id, d] of depth) {
        if (!byDepth.has(d)) byDepth.set(d, []);
        byDepth.get(d).push(id);
      }

      const maxDepth = Math.max(...byDepth.keys());
      const svgEl = document.getElementById("graph");
      const W = svgEl.clientWidth || window.innerWidth - 320;
      const H = svgEl.clientHeight || window.innerHeight;
      // Use fixed row height and fixed min column spacing — layout can exceed viewport (user can pan)
      const ROW_H   = 160;
      const MIN_COL = 160;
      const nodeMap = new Map(nodes.map(n => [n.id, n]));

      // Assign x/y positions
      for (const [d, ids] of byDepth) {
        // Sort ids by label for stable ordering
        ids.sort((a, b) => {
          const la = nodeMap.get(a)?.label || a;
          const lb = nodeMap.get(b)?.label || b;
          return la < lb ? -1 : la > lb ? 1 : 0;
        });
        const colW = Math.max(W / (ids.length + 1), MIN_COL);
        const totalW = colW * (ids.length + 1);
        const offsetX = totalW > W ? 0 : (W - totalW) / 2;  // center if fits, else start at 0
        ids.forEach((id, i) => {
          const n = nodeMap.get(id);
          if (n) {
            n.fx = offsetX + colW * (i + 1);
            n.fy = 40 + d * ROW_H;
          }
        });
      }

      // Stop simulation and reposition
      simulation.stop();
      simulation.alpha(0);

      // Snap nodes into position immediately (use nodeSel2 — includes merged nodes)
      nodeSel2.attr("transform", d => `translate(${d.fx !== null ? d.fx : d.x},${d.fy !== null ? d.fy : d.y})`);

      // Fade out non-reachable nodes
      nodeSel2.style("opacity", d => reachableIds.has(d.id) ? 1 : 0.05);

      // Switch links from <line> to curved <path> with labels
      // We rebuild the link layer in trace mode
      linkSel2.style("opacity", 0); // hide original lines

      // Draw trace edges as curved paths
      const traceEdges = links.filter(lk => {
        const s = typeof lk.source === 'object' ? lk.source.id : lk.source;
        const t = typeof lk.target === 'object' ? lk.target.id : lk.target;
        return reachableIds.has(s) && reachableIds.has(t);
      });

      // Remove any previous trace layer
      g.selectAll(".trace-layer").remove();
      const traceLayer = g.insert("g", ".nodes").attr("class", "trace-layer");

      traceEdges.forEach(lk => {
        const sn = typeof lk.source === 'object' ? lk.source : nodeMap.get(lk.source);
        const tn = typeof lk.target === 'object' ? lk.target : nodeMap.get(lk.target);
        if (!sn || !tn) return;

        const sx = sn.fx !== null ? sn.fx : sn.x;
        const sy = sn.fy !== null ? sn.fy : sn.y;
        const tx = tn.fx !== null ? tn.fx : tn.x;
        const ty = tn.fy !== null ? tn.fy : tn.y;

        const isCycle = (depth.get(sn.id) || 0) >= (depth.get(tn.id) || 0);
        let pathD;
        if (isCycle) {
          // back-edge: arc out to the side
          const mx = Math.max(sx, tx) + 80;
          const my = (sy + ty) / 2;
          pathD = `M${sx},${sy} Q${mx},${my} ${tx},${ty}`;
        } else {
          // forward edge: gentle curve
          const cy = (sy + ty) / 2;
          pathD = `M${sx},${sy} C${sx},${cy} ${tx},${cy} ${tx},${ty}`;
        }

        const color = RELATION_COLORS[lk.relation] || "#888";
        const traceColor = (lk.role === "control") ? ROLE_CONTROL_COLOR : color;
        const traceDash  = lk.relay ? "6,3" : (isCycle ? "5,3" : null);
        const edgeId = `trace-edge-${Math.random().toString(36).slice(2)}`;

        traceLayer.append("path")
          .attr("id", edgeId)
          .attr("d", pathD)
          .attr("fill", "none")
          .attr("stroke", traceColor)
          .attr("stroke-width", isCycle ? 1.2 : 1.8)
          .attr("stroke-dasharray", traceDash)
          .attr("marker-end", lk.role === "control" ? "url(#arrow-trace-control)" : `url(#arrow-trace-${lk.relation})`);

        // Edge label along path
        traceLayer.append("text")
          .attr("dy", -3)
          .attr("font-size", "9px")
          .attr("fill", traceColor)
          .attr("opacity", 0.85)
          .append("textPath")
            .attr("href", `#${edgeId}`)
            .attr("startOffset", "40%")
            .text(lk.seq != null ? `${lk.relation} [${lk.seq}]` : lk.relation);
      });

      // Zoom to fit the trace subgraph
      try {
        const traceNodes = nodes.filter(n => reachableIds.has(n.id));
        const xs = traceNodes.map(n => n.fx !== null ? n.fx : n.x);
        const ys = traceNodes.map(n => n.fy !== null ? n.fy : n.y);
        const x0 = Math.min(...xs) - 60, x1 = Math.max(...xs) + 60;
        const y0 = Math.min(...ys) - 60, y1 = Math.max(...ys) + 60;
        const sc = Math.min(W / (x1 - x0), H / (y1 - y0), 1.5);
        const tx2 = (W - (x1 - x0) * sc) / 2 - x0 * sc;
        const ty2 = (H - (y1 - y0) * sc) / 2 - y0 * sc;
        svg.transition().duration(600)
           .call(zoom.transform, d3.zoomIdentity.translate(tx2, ty2).scale(sc));
      } catch (_) {}

      // Update sidebar
      const sidebarEl = document.getElementById("sidebar-content");
      if (sidebarEl) {
        const html = sidebarEl.innerHTML;
        const btn = document.createElement("button");
        btn.textContent = "Back to full graph";
        btn.style.cssText = "background: #666; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; margin-top: 8px; width: 100%; box-sizing: border-box;";
        btn.onclick = () => resetTrace();
        sidebarEl.innerHTML = html;
        sidebarEl.appendChild(btn);
      }
    }

    function resetTrace() {
      traceMode = false;
      traceFromNodeId = null;

      // Unfix all node positions so force sim can take over again
      nodes.forEach(n => { n.fx = null; n.fy = null; });

      // Remove trace layer, restore original links
      g.selectAll(".trace-layer").remove();
      linkSel2.style("opacity", 1);
      nodeSel2.style("opacity", 1);

      // Restart simulation
      simulation.alpha(0.3).restart();

      if (selId) {
        selectNode(nodeById.get(selId));
      } else {
        clearSel();
      }
    }

    // -----------------------------------------------------------------------
    // Data-flow trace — directed walk via produces/consumes/calls/defines in seq order
    // -----------------------------------------------------------------------
    function applyDataFlowTrace(nodeId) {
      const DATA_FLOW_RELS = new Set(["produces", "consumes", "calls", "defines"]);
      const MAX_DEPTH = 3;

      const depth = new Map();
      const seqOrder = new Map();

      const seedNode = nodes.find(n => n.id === nodeId);
      const seedType = seedNode ? seedNode.type : "symbol";

      // For type nodes: show what symbols produce/consume this type (reverse BFS inward),
      // plus the type's own fields (contains children). Outward BFS from fields is useless
      // since field stubs have no data-flow edges.
      if (seedType === "type") {
        depth.set(nodeId, 1);
        seqOrder.set(nodeId, 0);

        // Collect contains children (fields) at depth 2
        links.forEach(lk => {
          const srcId = typeof lk.source === 'object' ? lk.source.id : lk.source;
          const tgtId = typeof lk.target === 'object' ? lk.target.id : lk.target;
          if (srcId === nodeId && lk.relation === "contains") {
            if (!depth.has(tgtId)) { depth.set(tgtId, 2); seqOrder.set(tgtId, 9999); }
          }
        });

        // Walk inward: symbols that produce/consume this type go at depth 0
        // Then walk one more level back from those symbols (their callers, depth -1 → use depth 0 for callers, 1 for type)
        const producerIds = [];
        links.forEach(lk => {
          const srcId = typeof lk.source === 'object' ? lk.source.id : lk.source;
          const tgtId = typeof lk.target === 'object' ? lk.target.id : lk.target;
          if (tgtId === nodeId && (lk.relation === "produces" || lk.relation === "consumes")) {
            if (!depth.has(srcId)) { depth.set(srcId, 0); seqOrder.set(srcId, lk.seq ?? 9999); producerIds.push(srcId); }
          }
        });

        // One level further back: who calls the producers
        producerIds.forEach(pid => {
          links.forEach(lk => {
            const srcId = typeof lk.source === 'object' ? lk.source.id : lk.source;
            const tgtId = typeof lk.target === 'object' ? lk.target.id : lk.target;
            if (tgtId === pid && DATA_FLOW_RELS.has(lk.relation)) {
              if (!depth.has(srcId)) { depth.set(srcId, -1); seqOrder.set(srcId, lk.seq ?? 9999); }
            }
          });
        });

        // Re-normalise depths so minimum is 0
        const minD = Math.min(...depth.values());
        for (const [id, d] of depth) depth.set(id, d - minD);

      } else {
        // For file/symbol nodes: forward BFS on data-flow edges
        const expandRel = seedType === "file" ? "defines" : null;
        let seeds = [nodeId];
        if (expandRel) {
          const childIds = links
            .filter(lk => {
              const srcId = typeof lk.source === 'object' ? lk.source.id : lk.source;
              return srcId === nodeId && lk.relation === expandRel;
            })
            .map(lk => typeof lk.target === 'object' ? lk.target.id : lk.target);
          if (childIds.length > 0) seeds = childIds;
        }

        depth.set(nodeId, 0);
        seqOrder.set(nodeId, 0);
        seeds.forEach((sid, i) => {
          if (!depth.has(sid)) { depth.set(sid, 0); seqOrder.set(sid, i); }
        });

        const queue = seeds.map(sid => ({ id: sid, d: 0 }));
        while (queue.length > 0) {
          const { id: cur, d } = queue.shift();
          if (d >= MAX_DEPTH) continue;
          const outEdges = links
            .filter(lk => {
              const srcId = typeof lk.source === 'object' ? lk.source.id : lk.source;
              return srcId === cur && DATA_FLOW_RELS.has(lk.relation);
            })
            .sort((a, b) => (a.seq != null ? a.seq : 9999) - (b.seq != null ? b.seq : 9999));
          for (const lk of outEdges) {
            const tgtId = typeof lk.target === 'object' ? lk.target.id : lk.target;
            if (!depth.has(tgtId)) {
              depth.set(tgtId, d + 1);
              seqOrder.set(tgtId, lk.seq != null ? lk.seq : 9999);
              queue.push({ id: tgtId, d: d + 1 });
            }
          }
        }
      }

      const reachableIds = new Set(depth.keys());
      const byDepth = new Map();
      for (const [id, d] of depth) {
        if (!byDepth.has(d)) byDepth.set(d, []);
        byDepth.get(d).push(id);
      }

      const svgEl2 = document.getElementById("graph");
      const W = svgEl2.clientWidth || window.innerWidth - 320;
      const H = svgEl2.clientHeight || window.innerHeight;
      const ROW_H = 160, MIN_COL = 160;
      const nodeMap = new Map(nodes.map(n => [n.id, n]));

      for (const [d, ids] of byDepth) {
        ids.sort((a, b) => {
          const sa = seqOrder.get(a) ?? 9999, sb = seqOrder.get(b) ?? 9999;
          if (sa !== sb) return sa - sb;
          return (nodeMap.get(a)?.label || a) < (nodeMap.get(b)?.label || b) ? -1 : 1;
        });
        const colW = Math.max(W / (ids.length + 1), MIN_COL);
        const totalW = colW * (ids.length + 1);
        const offsetX = totalW > W ? 0 : (W - totalW) / 2;
        ids.forEach((id, i) => {
          const n = nodeMap.get(id);
          if (n) { n.fx = offsetX + colW * (i + 1); n.fy = 40 + d * ROW_H; }
        });
      }

      simulation.stop();
      simulation.alpha(0);
      nodeSel2.attr("transform", d => `translate(${d.fx !== null ? d.fx : d.x},${d.fy !== null ? d.fy : d.y})`);
      nodeSel2.style("opacity", d => reachableIds.has(d.id) ? 1 : 0.05);
      linkSel2.style("opacity", 0);

      const traceEdges = links.filter(lk => {
        const s = typeof lk.source === 'object' ? lk.source.id : lk.source;
        const t = typeof lk.target === 'object' ? lk.target.id : lk.target;
        return reachableIds.has(s) && reachableIds.has(t) && DATA_FLOW_RELS.has(lk.relation);
      });

      g.selectAll(".trace-layer").remove();
      const traceLayer = g.insert("g", ".nodes").attr("class", "trace-layer");

      traceEdges.forEach(lk => {
        const sn = typeof lk.source === 'object' ? lk.source : nodeMap.get(lk.source);
        const tn = typeof lk.target === 'object' ? lk.target : nodeMap.get(lk.target);
        if (!sn || !tn) return;

        const sx = sn.fx !== null ? sn.fx : sn.x;
        const sy = sn.fy !== null ? sn.fy : sn.y;
        const tx = tn.fx !== null ? tn.fx : tn.x;
        const ty = tn.fy !== null ? tn.fy : tn.y;

        const isCycle = (depth.get(sn.id) || 0) >= (depth.get(tn.id) || 0);
        let pathD;
        if (isCycle) {
          const mx = Math.max(sx, tx) + 80, my = (sy + ty) / 2;
          pathD = `M${sx},${sy} Q${mx},${my} ${tx},${ty}`;
        } else {
          const cy = (sy + ty) / 2;
          pathD = `M${sx},${sy} C${sx},${cy} ${tx},${cy} ${tx},${ty}`;
        }

        const color = RELATION_COLORS[lk.relation] || "#888";
        const traceColor = lk.role === "control" ? ROLE_CONTROL_COLOR : color;
        const edgeId = `df-edge-${Math.random().toString(36).slice(2)}`;

        traceLayer.append("path")
          .attr("id", edgeId)
          .attr("d", pathD)
          .attr("fill", "none")
          .attr("stroke", traceColor)
          .attr("stroke-width", isCycle ? 1.5 : 2.2)
          .attr("stroke-dasharray", lk.relay ? "6,3" : (isCycle ? "5,3" : null))
          .attr("marker-end", lk.role === "control" ? "url(#arrow-trace-control)" : `url(#arrow-trace-${lk.relation})`);

        const labelParts = [lk.relation];
        if (lk.seq  != null)       labelParts.push(`[${lk.seq}]`);
        if (lk.via)                labelParts.push(`via:${lk.via}`);
        if (lk.relay)              labelParts.push("relay");
        if (lk.role === "control") labelParts.push("control");

        traceLayer.append("text")
          .attr("dy", -4)
          .attr("font-size", "9px")
          .attr("fill", traceColor)
          .attr("opacity", 0.9)
          .append("textPath")
            .attr("href", `#${edgeId}`)
            .attr("startOffset", "35%")
            .text(labelParts.join(" "));
      });

      try {
        const traceNodes = nodes.filter(n => reachableIds.has(n.id));
        const xs = traceNodes.map(n => n.fx !== null ? n.fx : n.x);
        const ys = traceNodes.map(n => n.fy !== null ? n.fy : n.y);
        const x0 = Math.min(...xs) - 60, x1 = Math.max(...xs) + 60;
        const y0 = Math.min(...ys) - 60, y1 = Math.max(...ys) + 60;
        const sc = Math.min(W / (x1 - x0), H / (y1 - y0), 1.5);
        svg.transition().duration(600)
           .call(zoom.transform, d3.zoomIdentity
             .translate((W - (x1 - x0) * sc) / 2 - x0 * sc, (H - (y1 - y0) * sc) / 2 - y0 * sc)
             .scale(sc));
      } catch (_) {}

      const sidebarEl = document.getElementById("sidebar-content");
      if (sidebarEl) {
        const html = sidebarEl.innerHTML;
        const btn = document.createElement("button");
        btn.textContent = "Back to full graph";
        btn.style.cssText = "background:#666;color:white;border:none;padding:6px 12px;border-radius:4px;cursor:pointer;margin-top:8px;width:100%;box-sizing:border-box;";
        btn.onclick = () => resetTrace();
        sidebarEl.innerHTML = html;
        sidebarEl.appendChild(btn);
      }
    }

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
  function renderSidebar(node, edgeEntries, nodeById, onTraceClick, onDataFlowClick) {
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
        if (otherFile)                 meta += ` <span style="color:#556;font-size:10px;">${esc(otherFile)}</span>`;
        if (lk.seq  != null)           meta += ` <span style="color:#aaa">[seq:${lk.seq}]</span>`;
        if (lk.role === "control")     meta += ` <span style="color:${ROLE_CONTROL_COLOR}">[control]</span>`;
        if (lk.relay)                  meta += ` <span style="color:#aaa">[relay]</span>`;
        if (lk.via)                    meta += ` <span style="color:#aaa">[via:${esc(lk.via)}]</span>`;
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
        h += `<div style="font-family:monospace;font-size:11px;line-height:1.8;padding:3px 6px;background:#1a1a24;border-radius:3px;margin-bottom:4px;">`;
        h += `<span style="color:#9b59b6;font-weight:bold;">${esc(node.label)}</span> {<br>`;
        for (const { link: lk } of containsOut) {
          const fieldLabel = lk.target ? (lk.target.label || "?") : "?";
          const pDepth = lk.ptr_depth != null ? lk.ptr_depth : 0;
          const stars = "*".repeat(pDepth);
          h += `&nbsp;&nbsp;<span style="color:#e67e22;">${esc(fieldLabel)}</span><span style="color:#aaa;">${stars}</span>`;
          if (pDepth > 0) h += ` <span style="color:#555;font-size:9px;">ptr_depth:${pDepth}</span>`;
          h += `<br>`;
        }
        h += `}`;
        h += `</div>`;
      }
    }

    h += `<button id="trace-btn" style="background: #4a9eff; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; margin-top: 8px; width: 100%; box-sizing: border-box;">Flowchart from here</button>`;
    if (node.type === "type" || node.type === "symbol" || node.type === "file") {
      h += `<button id="df-trace-btn" style="background: #17a89e; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; margin-top: 4px; width: 100%; box-sizing: border-box;">Data flow trace</button>`;
    }

    // State diagram button — for file nodes only (entry points have main())
    if (node.type === "file" || node.type === "symbol") {
      h += `<button id="state-diag-btn" style="background: #6a3aaf; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; margin-top: 4px; width: 100%; box-sizing: border-box;">State Diagram</button>`;
    }
    // Type diagram button — for type nodes
    if (node.type === "type") {
      h += `<button id="type-diag-btn" style="background: #6a3aaf; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; margin-top: 4px; width: 100%; box-sizing: border-box;">Type Diagram</button>`;
    }

    el.innerHTML = h;

    // Attach trace button click handler
    const traceBtn = document.getElementById("trace-btn");
    if (traceBtn && onTraceClick) {
      traceBtn.addEventListener("click", onTraceClick);
    }
    const dfTraceBtn = document.getElementById("df-trace-btn");
    if (dfTraceBtn && onDataFlowClick) {
      dfTraceBtn.addEventListener("click", onDataFlowClick);
    }

    // State diagram button
    const stateDiagBtn = document.getElementById("state-diag-btn");
    if (stateDiagBtn) {
      stateDiagBtn.addEventListener("click", () => {
        // entry param: use node.file (rel path) if available, else parse from node.id
        const entryFile = node.file || node.id.split("::").slice(1, -1).join("/") || node.id;
        stateDiagBtn.textContent = "Loading...";
        stateDiagBtn.disabled = true;
        fetch(`/api/diagram/flow?entry=${encodeURIComponent(entryFile)}`)
          .then(r => r.json())
          .then(data => {
            stateDiagBtn.textContent = "State Diagram";
            stateDiagBtn.disabled = false;
            if (data.error) {
              showDiagramPanel("Error", "Error: " + data.error);
            } else {
              showDiagramPanel("State Diagram — " + entryFile, data.mermaid);
            }
          })
          .catch(err => {
            stateDiagBtn.textContent = "State Diagram";
            stateDiagBtn.disabled = false;
            showDiagramPanel("Error", "Fetch failed: " + err.message);
          });
      });
    }

    // Type diagram button
    const typeDiagBtn = document.getElementById("type-diag-btn");
    if (typeDiagBtn) {
      typeDiagBtn.addEventListener("click", () => {
        const typeName = node.label;
        typeDiagBtn.textContent = "Loading...";
        typeDiagBtn.disabled = true;
        fetch(`/api/diagram/type?type=${encodeURIComponent(typeName)}&format=mermaid`)
          .then(r => r.json())
          .then(data => {
            typeDiagBtn.textContent = "Type Diagram";
            typeDiagBtn.disabled = false;
            if (data.error) {
              showDiagramPanel("Error", "Error: " + data.error);
            } else {
              showDiagramPanel("Class Diagram — " + typeName, data.output);
            }
          })
          .catch(err => {
            typeDiagBtn.textContent = "Type Diagram";
            typeDiagBtn.disabled = false;
            showDiagramPanel("Error", "Fetch failed: " + err.message);
          });
      });
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
