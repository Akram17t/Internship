(function attachFlowchartRenderer(globalScope) {
  "use strict";

  const SVG_NS = "http://www.w3.org/2000/svg";
  const WIDTH = 760;
  const CENTER_X = WIDTH / 2;
  const NODE_WIDTH = 260;
  const MIN_NODE_HEIGHT = 72;
  const VERTICAL_GAP = 74;

  function normalizeDiagram(input) {
    const rawNodes = Array.isArray(input?.nodes) ? input.nodes : [];
    const nodes = rawNodes
      .map((node, index) => ({
        id: String(node?.id || `node-${index + 1}`),
        type: String(node?.type || "unknown").toLowerCase(),
        text: String(node?.text || "").trim(),
      }))
      .filter((node) => node.text);
    const nodeIds = new Set(nodes.map((node) => node.id));
    const edges = (Array.isArray(input?.edges) ? input.edges : [])
      .map((edge) => ({
        source: String(edge?.source || edge?.from || ""),
        target: String(edge?.target || edge?.to || ""),
        label: String(edge?.label || "").trim(),
      }))
      .filter(
        (edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target),
      );

    return {
      id: String(input?.id || "flowchart"),
      title: String(input?.title || "Alur Proses"),
      source: String(input?.source || ""),
      page: Number.isFinite(input?.page) ? Number(input.page) : null,
      nodes,
      edges,
    };
  }

  function wrapText(value, maxCharacters = 30) {
    const words = String(value || "").split(/\s+/).filter(Boolean);
    const lines = [];
    let line = "";
    words.forEach((word) => {
      const candidate = line ? `${line} ${word}` : word;
      if (candidate.length > maxCharacters && line) {
        lines.push(line);
        line = word;
      } else {
        line = candidate;
      }
    });
    if (line) lines.push(line);
    return lines.length ? lines : [""];
  }

  function buildLayout(input) {
    const diagram = normalizeDiagram(input);
    const positions = new Map();
    let cursorY = 46;

    diagram.nodes.forEach((node, index) => {
      const lines = wrapText(node.text, node.type === "decision" ? 25 : 31);
      const height = Math.max(MIN_NODE_HEIGHT, 34 + lines.length * 19);
      const width = node.type === "decision" ? 238 : NODE_WIDTH;
      positions.set(node.id, {
        ...node,
        index,
        lines,
        x: CENTER_X - width / 2,
        y: cursorY,
        width,
        height,
        centerX: CENTER_X,
        centerY: cursorY + height / 2,
      });
      cursorY += height + VERTICAL_GAP;
    });

    const edges = diagram.edges.map((edge, edgeIndex) => {
      const source = positions.get(edge.source);
      const target = positions.get(edge.target);
      const isNext = target.index === source.index + 1;
      let path;
      let labelX = CENTER_X + 12;
      let labelY = (source.y + source.height + target.y) / 2 - 4;

      if (isNext) {
        path = `M ${source.centerX} ${source.y + source.height} L ${target.centerX} ${target.y}`;
      } else {
        const isBackward = target.index <= source.index;
        const laneOffset = (edgeIndex % 3) * 18;
        const laneX = isBackward ? WIDTH - 72 - laneOffset : 72 + laneOffset;
        const sourceX = isBackward ? source.x + source.width : source.x;
        const targetX = isBackward ? target.x + target.width : target.x;
        path = [
          `M ${sourceX} ${source.centerY}`,
          `L ${laneX} ${source.centerY}`,
          `L ${laneX} ${target.centerY}`,
          `L ${targetX} ${target.centerY}`,
        ].join(" ");
        labelX = isBackward ? laneX - 10 : laneX + 10;
        labelY = source.centerY + (target.centerY - source.centerY) / 2;
      }

      return { ...edge, path, labelX, labelY };
    });

    return {
      ...diagram,
      width: WIDTH,
      height: Math.max(cursorY - VERTICAL_GAP + 48, 240),
      nodes: diagram.nodes.map((node) => positions.get(node.id)),
      edges,
    };
  }

  function svgElement(name, attributes = {}) {
    const element = document.createElementNS(SVG_NS, name);
    Object.entries(attributes).forEach(([key, value]) =>
      element.setAttribute(key, String(value)),
    );
    return element;
  }

  function renderNode(node) {
    const group = svgElement("g", {
      class: `flowchart-node flowchart-node--${node.type}`,
      transform: `translate(${node.x} ${node.y})`,
    });

    if (node.type === "decision") {
      group.appendChild(
        svgElement("polygon", {
          points: `${node.width / 2},0 ${node.width},${node.height / 2} ${node.width / 2},${node.height} 0,${node.height / 2}`,
        }),
      );
    } else {
      group.appendChild(
        svgElement("rect", {
          width: node.width,
          height: node.height,
          rx: ["start", "end"].includes(node.type) ? node.height / 2 : 8,
        }),
      );
    }

    const text = svgElement("text", {
      x: node.width / 2,
      y: node.height / 2 - ((node.lines.length - 1) * 9),
      "text-anchor": "middle",
    });
    node.lines.forEach((line, index) => {
      const span = svgElement("tspan", {
        x: node.width / 2,
        dy: index === 0 ? 0 : 19,
      });
      span.textContent = line;
      text.appendChild(span);
    });
    group.appendChild(text);
    return group;
  }

  function renderSvg(layout) {
    const markerId = `flow-arrow-${layout.id.replace(/[^a-z0-9]/gi, "")}`;
    const svg = svgElement("svg", {
      class: "flowchart-svg",
      viewBox: `0 0 ${layout.width} ${layout.height}`,
      role: "img",
      "aria-label": layout.title,
    });
    const definitions = svgElement("defs");
    const marker = svgElement("marker", {
      id: markerId,
      viewBox: "0 0 10 10",
      refX: 9,
      refY: 5,
      markerWidth: 7,
      markerHeight: 7,
      orient: "auto-start-reverse",
    });
    marker.appendChild(
      svgElement("path", { d: "M 0 0 L 10 5 L 0 10 z" }),
    );
    definitions.appendChild(marker);
    svg.appendChild(definitions);

    const edgeLayer = svgElement("g", { class: "flowchart-edges" });
    layout.edges.forEach((edge) => {
      edgeLayer.appendChild(
        svgElement("path", {
          d: edge.path,
          "marker-end": `url(#${markerId})`,
        }),
      );
      if (!edge.label) return;
      const label = svgElement("text", {
        class: "flowchart-edge-label",
        x: edge.labelX,
        y: edge.labelY,
        "text-anchor": edge.target < edge.source ? "end" : "start",
      });
      label.textContent = edge.label;
      edgeLayer.appendChild(label);
    });
    svg.appendChild(edgeLayer);

    const nodeLayer = svgElement("g", { class: "flowchart-nodes" });
    layout.nodes.forEach((node) => nodeLayer.appendChild(renderNode(node)));
    svg.appendChild(nodeLayer);
    return svg;
  }

  function render(input) {
    const layout = buildLayout(input);
    if (!layout.nodes.length || typeof document === "undefined") return null;

    const card = document.createElement("section");
    card.className = "flowchart-card";

    const header = document.createElement("header");
    header.className = "flowchart-header";
    const heading = document.createElement("div");
    const kicker = document.createElement("span");
    kicker.textContent = "Interactive Process Map";
    const title = document.createElement("strong");
    title.textContent = layout.title;
    const meta = document.createElement("small");
    meta.textContent = [layout.source, layout.page ? `Halaman ${layout.page}` : ""]
      .filter(Boolean)
      .join(" / ");
    heading.append(kicker, title, meta);

    const controls = document.createElement("div");
    controls.className = "flowchart-controls";
    const viewport = document.createElement("div");
    viewport.className = "flowchart-viewport";
    const svg = renderSvg(layout);
    let zoom = 1;

    const updateZoom = () => {
      svg.style.width = `${layout.width * zoom}px`;
      svg.style.height = `${layout.height * zoom}px`;
    };
    [
      { label: "Perkecil diagram", text: "−", action: () => (zoom = Math.max(0.65, zoom - 0.15)) },
      { label: "Reset ukuran diagram", text: "1:1", action: () => (zoom = 1) },
      { label: "Perbesar diagram", text: "+", action: () => (zoom = Math.min(1.6, zoom + 0.15)) },
    ].forEach((control) => {
      const button = document.createElement("button");
      button.type = "button";
      button.setAttribute("aria-label", control.label);
      button.textContent = control.text;
      button.addEventListener("click", () => {
        control.action();
        updateZoom();
      });
      controls.appendChild(button);
    });

    header.append(heading, controls);
    viewport.appendChild(svg);
    card.append(header, viewport);
    updateZoom();
    return card;
  }

  const api = { buildLayout, normalizeDiagram, render, wrapText };
  globalScope.FlowchartRenderer = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
