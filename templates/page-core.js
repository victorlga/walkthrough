"use strict";

const MARKER = /\[\[([^\]\n]+)\]\]/g;
const LINE_MARKER = /^L(\d+)(?:-L?(\d+))?$/;

const STRINGS = {
  pt: {
    overview: "Visão geral", back: "Voltar", roteiro: "roteiro", of: "de", story: "A história",
    route: "Roteiro", entryPoints: "Pontos de entrada afetados", otherChanges: "Outras mudanças",
    hunks: "Trechos sem código", mechanical: "Mudanças mecânicas", divergences: "Glossário e código divergem",
    changesSeen: "mudanças vistas", cameFrom: "veio de", line: "linha", callers: "Quem chama", tests: "Testes",
    implementations: "Implementações", context: "Contexto", before: "Como era", whyChanged: "Por que mudou",
    whyExists: "Por que existe", steps: "Passo a passo", impact: "Quem é afetado", usedBy: "Quem usa",
    relation: "Como se liga à mudança", syntax: "Sintaxe usada aqui", explain: "Explicar", stop: "Parar",
    thinking: "Pensando...", ask: "Pergunte sobre esta função", send: "Enviar", copy: "Copiar",
    copied: "Copiado", askInChat: "Sem explicação ainda. Cole no chat do Claude Code:", rateLimited: "Limite de uso atingido. Tente de novo daqui a pouco.",
    failed: "A resposta falhou. Tente de novo.", lostLinks: "Sem links em", pruned: "Explicações removidas por erro",
    trimmed: "Funções cortadas por tamanho", outside: "fora do índice", library: "biblioteca", noCallers: "Ninguém chama esta função no repo.",
    notComputed: "Quem chama não foi calculado nesta profundidade.", hunk: "Trecho", noChanges: "Nenhuma função mudou.",
    chatPrompt: "explica {id} no walkthrough",
  },
  en: {
    overview: "Overview", back: "Back", roteiro: "route", of: "of", story: "The story",
    route: "Reading route", entryPoints: "Affected entry points", otherChanges: "Other changes",
    hunks: "Changes outside code", mechanical: "Mechanical changes", divergences: "Glossary and code disagree",
    changesSeen: "changes seen", cameFrom: "came from", line: "line", callers: "Called by", tests: "Tests",
    implementations: "Implementations", context: "Context", before: "Before", whyChanged: "Why it changed",
    whyExists: "Why it exists", steps: "Step by step", impact: "Who is affected", usedBy: "Used by",
    relation: "How it connects to the change", syntax: "Syntax used here", explain: "Explain", stop: "Stop",
    thinking: "Thinking...", ask: "Ask about this function", send: "Send", copy: "Copy",
    copied: "Copied", askInChat: "No explanation yet. Paste this into Claude Code:", rateLimited: "Usage limit reached. Try again in a moment.",
    failed: "The answer failed. Try again.", lostLinks: "No links in", pruned: "Explanations removed after errors",
    trimmed: "Functions cut for size", outside: "outside the index", library: "library", noCallers: "Nothing in the repo calls this function.",
    notComputed: "Callers were not computed at this depth.", hunk: "Hunk", noChanges: "No function changed.",
    chatPrompt: "explain {id} in the walkthrough",
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

function resolveRef(target, nameIndex) {
  const ids = nameIndex.get(target);
  return ids && ids.size === 1 ? [...ids][0] : null;
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
    const id = resolveRef(segment.target, ctx.nameIndex);
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
  return `walkthrough:v1:${meta.repo || "repo"}:${meta.slug || "head"}`;
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    STRINGS, t, parseMarkers, buildNameIndex, resolveRef, escapeHtml, renderInline, renderMarkdown,
    codeRows, lineSpans, lineSegments, pushEntry, popTo, popOne, progress, numberedSource, storageKey,
  };
}
