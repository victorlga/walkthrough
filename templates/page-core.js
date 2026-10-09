"use strict";

const MARKER = /\[\[([^\]\n]+)\]\]/g;
const LINE_MARKER = /^L(\d+)(?:-L?(\d+))?$/;

const STRINGS = {
  pt: {
    overview: "Visão geral", roteiro: "roteiro", of: "de", story: "A história",
    route: "Roteiro", entryPoints: "Pontos de entrada afetados", otherChanges: "Outras mudanças",
    mechanical: "Mudanças mecânicas", divergences: "Glossário e código divergem",
    changesSeen: "mudanças vistas", cameFrom: "veio de", line: "linha", callers: "Quem chama", tests: "Testes",
    implementations: "Implementações", change: "O que mudou", adds: "O que acrescenta", why: "Por quê",
    steps: "Passo a passo", risk: "Risco", relation: "Como se liga à mudança", syntax: "Sintaxe usada aqui", explain: "Explicar", stop: "Parar", noExplanation: "Esta função ainda não tem explicação completa.",
    thinking: "Pensando...", ask: "Pergunte sobre esta função", send: "Enviar", copy: "Copiar",
    copied: "Copiado", askInChat: "Sem explicação ainda. Cole no chat do seu agente:", rateLimited: "Limite de uso atingido. Tente de novo daqui a pouco.",
    failed: "A resposta falhou. Tente de novo.", lostLinks: "Sem links em", pruned: "Explicações removidas por erro",
    trimmed: "Funções cortadas por tamanho", outside: "fora do índice", library: "biblioteca", noCallers: "Ninguém chama esta função no repo.",
    notComputed: "Quem chama não foi calculado nesta profundidade.", hunk: "Trecho", noChanges: "Nenhuma função mudou.",
    chatPrompt: "explica {id} no walkthrough", fold: "Recolher ou abrir o bloco", lines: "linhas", next: "Próximo", more: "mais",
  },
  en: {
    overview: "Overview", roteiro: "route", of: "of", story: "The story",
    route: "Reading route", entryPoints: "Affected entry points", otherChanges: "Other changes",
    mechanical: "Mechanical changes", divergences: "Glossary and code disagree",
    changesSeen: "changes seen", cameFrom: "came from", line: "line", callers: "Called by", tests: "Tests",
    implementations: "Implementations", change: "What changed", adds: "What it adds", why: "Why",
    steps: "Step by step", risk: "Risk", relation: "How it connects to the change", syntax: "Syntax used here", explain: "Explain", stop: "Stop", noExplanation: "This function has no full explanation yet.",
    thinking: "Thinking...", ask: "Ask about this function", send: "Send", copy: "Copy",
    copied: "Copied", askInChat: "No explanation yet. Paste this into your coding agent:", rateLimited: "Usage limit reached. Try again in a moment.",
    failed: "The answer failed. Try again.", lostLinks: "No links in", pruned: "Explanations removed after errors",
    trimmed: "Functions cut for size", outside: "outside the index", library: "library", noCallers: "Nothing in the repo calls this function.",
    notComputed: "Callers were not computed at this depth.", hunk: "Hunk", noChanges: "No function changed.",
    chatPrompt: "explain {id} in the walkthrough", fold: "Fold or unfold the block", lines: "lines", next: "Next", more: "more",
  },
};

function t(lang, key) {
  return (STRINGS[lang] || STRINGS.en)[key] || STRINGS.en[key] || key;
}

function parseMarkers(text) {
  const out = [];
  const source = String(text || "");
  let last = 0;
  for (const match of source.matchAll(MARKER)) {
    if (match.index > last) out.push({ type: "text", value: source.slice(last, match.index) });
    const inner = match[1].trim();
    const line = LINE_MARKER.exec(inner);
    if (line) {
      const first = Number(line[1]);
      const second = line[2] ? Number(line[2]) : first;
      out.push({ type: "lines", from: Math.min(first, second), to: Math.max(first, second), raw: match[0] });
    } else {
      out.push({ type: "ref", target: inner, raw: match[0] });
    }
    last = match.index + match[0].length;
  }
  if (last < source.length) out.push({ type: "text", value: source.slice(last) });
  return out;
}

function buildNameIndex(nodes) {
  const index = new Map();
  for (const [id, node] of Object.entries(nodes || {})) {
    for (const key of new Set([id, node.name, node.qualname])) {
      if (!key) continue;
      if (!index.has(key)) index.set(key, new Set());
      index.get(key).add(id);
    }
  }
  return index;
}

function resolveRef(target, nameIndex, prefer) {
  const ids = nameIndex.get(target);
  if (!ids) return null;
  if (ids.size === 1) return [...ids][0];
  for (const preferred of prefer || []) {
    const narrowed = [...ids].filter((id) => preferred.has(id));
    if (narrowed.length === 1) return narrowed[0];
  }
  return null;
}

function neighborsOf(node) {
  const ids = new Set();
  (node.links || []).forEach((link) => { if (link.to) ids.add(link.to); });
  (node.callers || []).forEach((caller) => ids.add(caller.from));
  (node.implementations || []).forEach((id) => ids.add(id));
  return ids;
}

function escapeHtml(value) {
  return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function formatInline(html) {
  return html.replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}

function lineInRange(segment, ctx) {
  return Boolean(ctx.lineRange) && segment.from >= ctx.lineRange[0] && segment.to <= ctx.lineRange[1];
}

function renderInline(text, ctx) {
  return parseMarkers(text).map((segment) => {
    if (segment.type === "text") return formatInline(escapeHtml(segment.value));
    if (segment.type === "lines") {
      const label = segment.from === segment.to ? `L${segment.from}` : `L${segment.from}-${segment.to}`;
      if (!lineInRange(segment, ctx)) return escapeHtml(label);
      return `<button class="chip" data-lines="${segment.from}-${segment.to}">${label}</button>`;
    }
    const id = resolveRef(segment.target, ctx.nameIndex, ctx.prefer);
    if (!id) return `<code>${escapeHtml(segment.target)}</code>`;
    return `<a class="ref" href="#" data-ref="${escapeHtml(id)}">${escapeHtml(ctx.nodes[id].name)}</a>`;
  }).join("");
}

function listItem(item, ctx) {
  const ranges = parseMarkers(item).filter((s) => s.type === "lines" && lineInRange(s, ctx)).map((s) => `${s.from}-${s.to}`);
  const attribute = ranges.length ? ` data-lines="${ranges.join(",")}"` : "";
  return `<li${attribute}>${renderInline(item, ctx)}</li>`;
}

function renderBlock(block, ctx) {
  const lines = block.split("\n");
  const ordered = /^\d+[.)]\s+/;
  const bullet = /^[-*]\s+/;
  if (ordered.test(lines[0]) || bullet.test(lines[0])) {
    const pattern = ordered.test(lines[0]) ? ordered : bullet;
    const items = [];
    for (const line of lines) {
      if (pattern.test(line)) items.push(line.replace(pattern, ""));
      else if (items.length) items[items.length - 1] += " " + line.trim();
    }
    const tag = pattern === ordered ? "ol" : "ul";
    return `<${tag}>${items.map((item) => listItem(item, ctx)).join("")}</${tag}>`;
  }
  return `<p>${renderInline(lines.map((line) => line.trim()).join(" "), ctx)}</p>`;
}

function renderMarkdown(text, ctx) {
  return String(text || "").replace(/\r\n/g, "\n").split(/\n{2,}/)
    .map((block) => block.trim()).filter(Boolean).map((block) => renderBlock(block, ctx)).join("");
}

function codeRows(node) {
  const start = node.lines[0];
  const change = node.change || {};
  const added = new Set(change.added || []);
  const removedAfter = new Map();
  for (const block of change.removed || []) {
    removedAfter.set(block.after, (removedAfter.get(block.after) || []).concat(block.text));
  }
  const rows = [];
  const pushRemoved = (after) => {
    for (const text of removedAfter.get(after) || []) rows.push({ n: null, kind: "del", text });
  };
  pushRemoved(start - 1);
  String(node.source).split("\n").forEach((text, offset) => {
    const n = start + offset;
    rows.push({ n, kind: added.has(n) ? "add" : "ctx", text });
    pushRemoved(n);
  });
  return rows;
}

function lineSpans(node) {
  const map = new Map();
  const add = (span) => {
    if (!map.has(span.line)) map.set(span.line, []);
    map.get(span.line).push(span);
  };
  (node.links || []).forEach(add);
  (node.external || []).forEach(add);
  for (const list of map.values()) list.sort((a, b) => a.col - b.col);
  return map;
}

function lineSegments(text, spans) {
  const segments = [];
  let position = 0;
  for (const span of spans || []) {
    if (span.col < position || span.col + span.len > text.length) continue;
    if (span.col > position) segments.push({ text: text.slice(position, span.col) });
    segments.push({ text: text.slice(span.col, span.col + span.len), span });
    position = span.col + span.len;
  }
  if (position < text.length || segments.length === 0) segments.push({ text: text.slice(position) });
  return segments;
}

function indentOf(text) {
  return /^[ \t]*/.exec(text)[0].replace(/\t/g, "    ").length;
}

function foldRegions(rows) {
  const blank = (i) => !String(rows[i].text).trim();
  const regions = [];
  for (let i = 0; i < rows.length; i += 1) {
    if (blank(i)) continue;
    const base = indentOf(rows[i].text);
    let next = i + 1;
    while (next < rows.length && blank(next)) next += 1;
    if (next >= rows.length || indentOf(rows[next].text) <= base) continue;
    let end = next;
    for (let k = next; k < rows.length; k += 1) {
      if (blank(k)) continue;
      if (indentOf(rows[k].text) <= base) break;
      end = k;
    }
    regions.push({ start: i, end });
  }
  return regions;
}

function defaultFolds(rows, regions, minHidden = 6) {
  const folded = new Set();
  const changedBefore = [0];
  rows.forEach((row) => changedBefore.push(changedBefore[changedBefore.length - 1] + (row.kind === "ctx" ? 0 : 1)));
  if (changedBefore[rows.length] === 0) return folded;
  let coveredUntil = -1;
  for (const region of regions) {
    if (region.start <= coveredUntil || region.end - region.start < minHidden) continue;
    if (changedBefore[region.end + 1] - changedBefore[region.start] > 0) continue;
    folded.add(region.start);
    coveredUntil = region.end;
  }
  return folded;
}

function hiddenRows(regions, folded) {
  const hidden = new Set();
  for (const region of regions) {
    if (!folded.has(region.start)) continue;
    for (let i = region.start + 1; i <= region.end; i += 1) hidden.add(i);
  }
  return hidden;
}

const CALLABLE_KINDS = new Set(["function", "method", "constructor", "other", "toplevel"]);

function entryLines(index, skeleton = []) {
  const route = new Set(skeleton);
  const rank = (id) => [route.has(id) ? 0 : 1, CALLABLE_KINDS.has(((index.nodes || {})[id] || {}).kind) ? 0 : 1, id];
  const byRank = (a, b) => {
    const [x, y] = [rank(a), rank(b)];
    return x[0] - y[0] || x[1] - y[1] || x[2].localeCompare(y[2]);
  };
  const reachedBy = new Map();
  for (const [changedId, info] of Object.entries(index.impact || {})) {
    for (const path of info.paths || []) {
      const entry = path[path.length - 1];
      const node = (index.nodes || {})[entry];
      if (!node || node.test || !CALLABLE_KINDS.has(node.kind)) continue;
      if (!reachedBy.has(entry)) reachedBy.set(entry, new Set());
      reachedBy.get(entry).add(changedId);
    }
  }
  return [...reachedBy].map(([id, reached]) => ({ id, reached: [...reached].sort(byRank) }))
    .sort((a, b) => b.reached.length - a.reached.length || a.id.localeCompare(b.id));
}

function groupByFile(ids, pathOf) {
  const groups = new Map();
  for (const id of ids) {
    const path = pathOf(id);
    if (!groups.has(path)) groups.set(path, []);
    groups.get(path).push(id);
  }
  return [...groups].sort((a, b) => a[0].localeCompare(b[0])).map(([path, members]) => ({ path, ids: members }));
}

function splitPath(path) {
  const cut = path.lastIndexOf("/") + 1;
  return { dir: path.slice(0, cut), file: path.slice(cut) };
}

function nextInRoute(plan, id) {
  const route = ((plan && plan.parts) || []).flatMap((part) => part.roteiro || []);
  const position = route.indexOf(id);
  return position >= 0 && position + 1 < route.length ? route[position + 1] : null;
}

function pushEntry(stack, entry) {
  return stack.concat([entry]);
}

function popTo(stack, index) {
  return stack.slice(0, Math.max(1, index + 1));
}

function popOne(stack) {
  return stack.length > 1 ? stack.slice(0, -1) : stack;
}

function progress(data, visited) {
  const seen = (ids) => ids.filter((id) => visited.has(id)).length;
  const skeleton = (data.plan && data.plan.skeleton) || [];
  const changed = data.index.changed || [];
  return { roteiroSeen: seen(skeleton), roteiroTotal: skeleton.length, changedSeen: seen(changed), changedTotal: changed.length };
}

function numberedSource(node) {
  const mark = { add: "+", del: "-", ctx: " " };
  return codeRows(node).map((row) => `${row.n === null ? "    " : String(row.n).padStart(4)} ${mark[row.kind]} ${row.text}`).join("\n");
}

function storageKey(meta) {
  return `walkthrough:v1:${meta.repo || "repo"}:${meta.slug || "head"}:${meta.head || ""}`;
}

const CORE_SECTION = { added: "change", modified: "change", unchanged: "relation" };
const LANGUAGE_NAMES = { pt: "Portuguese", en: "English" };

function summaryOf(data, id) {
  const entry = (data.explanations.nodes || {})[id];
  return entry && entry.summary ? entry.summary : "";
}

function pathLine(data, stack) {
  const nodes = data.index.nodes;
  return stack.slice(1).map((entry) => {
    const node = nodes[entry.id];
    const name = node ? node.name : entry.id;
    if (entry.fromId && entry.fromLine && nodes[entry.fromId]) return `${name} (called at line ${entry.fromLine} of ${nodes[entry.fromId].name})`;
    return name;
  }).join(" > ");
}

function contextBlock({ data, id, stack }) {
  const nodes = data.index.nodes;
  const node = nodes[id];
  const status = (node.change && node.change.status) || "unchanged";
  const describe = (otherId) => `- ${nodes[otherId].name}: ${summaryOf(data, otherId) || nodes[otherId].path}`;
  const calls = [...new Set((node.links || []).filter((l) => l.to && nodes[l.to]).map((l) => l.to))].map(describe);
  const callers = (node.callers || []).filter((c) => nodes[c.from]).map((c) => describe(c.from) + (c.test ? " (test)" : ""));
  return [
    `Write in ${LANGUAGE_NAMES[data.lang] || "English"}.`,
    `Story of the branch:\n${(data.explanations.overview || {}).story || "(none)"}`,
    `How the reader got here: ${pathLine(data, stack) || node.name}`,
    `Function ${id} (${node.kind}, ${status}) in ${node.path}, lines ${node.lines[0]}-${node.lines[1]}. Lines marked + were added, lines marked - were removed:`,
    numberedSource(node),
    `It calls:\n${calls.join("\n") || "(nothing in the index)"}`,
    `Called by:\n${callers.join("\n") || "(nobody in the index)"}`,
  ].join("\n\n");
}

function explainPrompt(ctx) {
  const node = ctx.data.index.nodes[ctx.id];
  const status = (node.change && node.change.status) || "unchanged";
  const core = CORE_SECTION[status] || CORE_SECTION.unchanged;
  return [
    "You explain code to a reviewer who is reading a walkthrough of a branch. Follow these rules exactly:",
    ctx.data.rules || "",
    contextBlock(ctx),
    `Return only JSON shaped as {"summary": "one sentence starting with a verb", "sections": {...}}. The sections object must have the key "${core}". Add "steps", "why", "risk" or "syntax" only when they tell the reader something the code beside it does not show. Keep to the word limits in the rules.`,
    `Mark lines of this function with [[L${node.lines[0]}]] or [[L${node.lines[0]}-${node.lines[0] + 1}]], staying between ${node.lines[0]} and ${node.lines[1]}. Mark other functions with [[name]], using only names listed above. Every numbered step in "steps" needs a line marker.`,
  ].join("\n\n");
}

function askTurns(ctx, history, question) {
  const intro = [
    "You answer questions from a reviewer who is reading a walkthrough of a branch. Follow these rules for markers and tone:",
    ctx.data.rules || "",
    contextBlock(ctx),
    "Answer in short paragraphs. Use [[Lnn]] markers for lines of this function and [[name]] for other functions. You may call the tools to read other functions of the index. Say plainly when something is not in the code you can see.",
  ].join("\n\n");
  return [{ role: "user", content: intro }, ...history, { role: "user", content: question }];
}

function askTools(data) {
  const nodes = data.index.nodes;
  const need = (id) => {
    const node = nodes[String(id)];
    if (!node) throw new Error(`${id} is not in the index`);
    return node;
  };
  return [
    {
      name: "read_function",
      description: "Returns one function of the walkthrough index by id: path, line range, numbered source with + and - diff marks, and its summary when there is one.",
      inputSchema: { type: "object", properties: { id: { type: "string" } }, required: ["id"] },
      execute: ({ id }) => {
        const node = need(id);
        return { id: String(id), path: node.path, lines: node.lines, summary: summaryOf(data, String(id)), source: numberedSource(node).slice(0, 8000) };
      },
    },
    {
      name: "find_function",
      description: "Finds function ids in the walkthrough index whose name or id contains the given text. Returns at most 20 ids.",
      inputSchema: { type: "object", properties: { name: { type: "string" } }, required: ["name"] },
      execute: ({ name }) => {
        const query = String(name);
        return Object.keys(nodes).filter((id) => nodes[id].name === query || id.includes(query)).sort().slice(0, 20);
      },
    },
    {
      name: "callers_of",
      description: "Lists the functions that call the given function id, with the call lines and whether the caller is a test.",
      inputSchema: { type: "object", properties: { id: { type: "string" } }, required: ["id"] },
      execute: ({ id }) => (need(id).callers || []).map((c) => ({ id: c.from, lines: c.lines, test: c.test })),
    },
  ];
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    STRINGS, t, parseMarkers, buildNameIndex, resolveRef, escapeHtml, renderInline, renderMarkdown,
    codeRows, lineSpans, lineSegments, foldRegions, defaultFolds, hiddenRows, entryLines, groupByFile, splitPath, nextInRoute, pushEntry, popTo, popOne, progress, numberedSource, storageKey, neighborsOf,
    CORE_SECTION, contextBlock, explainPrompt, askTurns, askTools,
  };
}
