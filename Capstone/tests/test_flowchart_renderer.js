const assert = require("node:assert/strict");
const test = require("node:test");

const { buildLayout, normalizeDiagram, wrapText } = require(
  "../frontend/web/assets/flowchart.js",
);

const fixture = {
  id: "access-flow",
  title: "Alur Kontrol Akses",
  nodes: [
    { id: "n1", type: "start", text: "Mulai" },
    { id: "n2", type: "process", text: "Ajukan akses" },
    { id: "n3", type: "decision", text: "Disetujui?" },
    { id: "n4", type: "process", text: "Berikan akses" },
    { id: "n5", type: "end", text: "Selesai" },
  ],
  edges: [
    { source: "n1", target: "n2", label: "" },
    { source: "n2", target: "n3", label: "" },
    { source: "n3", target: "n4", label: "Ya" },
    { source: "n3", target: "n2", label: "Tidak" },
    { source: "n4", target: "n5", label: "" },
  ],
};

test("normalization removes edges that reference missing nodes", () => {
  const normalized = normalizeDiagram({
    ...fixture,
    edges: [...fixture.edges, { source: "n5", target: "missing" }],
  });

  assert.equal(normalized.edges.length, fixture.edges.length);
});

test("layout creates a vertical main path and a side-routed loop", () => {
  const layout = buildLayout(fixture);
  const mainEdge = layout.edges.find(
    (edge) => edge.source === "n1" && edge.target === "n2",
  );
  const loopEdge = layout.edges.find(
    (edge) => edge.source === "n3" && edge.target === "n2",
  );

  assert.match(mainEdge.path, /^M \d+ \d+ L \d+ \d+$/);
  assert.match(loopEdge.path, /^M .+ L .+ L .+ L .+$/);
  assert.equal(loopEdge.label, "Tidak");
  assert.ok(layout.height > 500);
});

test("long node labels are wrapped into multiple lines", () => {
  const lines = wrapText(
    "Karyawan mengajukan permohonan perjalanan dinas kepada atasan",
    24,
  );

  assert.ok(lines.length > 1);
  assert.ok(lines.every((line) => line.length <= 24));
});
