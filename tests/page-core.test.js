const test = require("node:test");
const assert = require("node:assert");
const core = require("../templates/page-core.js");

const nodes = {
  "a.py#calc": { name: "calc", qualname: "calc", lines: [10, 14], source: "def calc(x):\n    y = 1\n    return x + y\n\n# end",
    change: { status: "modified", added: [12], removed: [{ after: 11, text: ["    old = 2"] }] },
    links: [{ line: 12, col: 15, len: 1, to: "a.py#y" }], external: [] },
  "a.py#handler": { name: "handler", qualname: "handler", lines: [20, 22] },
  "b.py#handler": { name: "handler", qualname: "handler", lines: [1, 3] },
  "c.clj#source-amount->spread": { name: "source-amount->spread", qualname: "source-amount->spread", lines: [1, 9] },
};
const ctx = { nameIndex: core.buildNameIndex(nodes), nodes, lineRange: [10, 14] };

test("markers split into text, line ranges and references", () => {
  const parts = core.parseMarkers("Veja [[L13-11]] e [[calc]].");
  assert.deepStrictEqual(parts.map((p) => p.type), ["text", "lines", "text", "ref", "text"]);
  assert.deepStrictEqual([parts[1].from, parts[1].to], [11, 13]);
});

test("markdown escapes html and only links what resolves", () => {
  const html = core.renderMarkdown("<script>x</script> [[L12]] [[L99]] [[handler]] [[source-amount->spread]]", ctx);
  assert.ok(html.includes("&lt;script&gt;"));
  assert.ok(html.includes('<button class="chip" data-lines="12-12">L12</button>'));
  assert.ok(!html.includes('data-lines="99-99"'));
  assert.ok(html.includes("<code>handler</code>"));
  assert.ok(html.includes('data-ref="c.clj#source-amount-&gt;spread">source-amount-&gt;spread</a>'));
});

test("numbered steps carry the lines they explain", () => {
  const html = core.renderMarkdown("1. Lê [[L11]].\n2. Soma [[L12-13]] e [[L99]].", ctx);
  assert.ok(html.startsWith("<ol>"));
  assert.ok(html.includes('<li data-lines="11-11">'));
  assert.ok(html.includes('<li data-lines="12-13">'));
});

test("code rows place removed lines after the line they followed", () => {
  const rows = core.codeRows(nodes["a.py#calc"]);
  assert.deepStrictEqual(rows.slice(0, 4).map((r) => [r.n, r.kind]), [[10, "ctx"], [11, "ctx"], [null, "del"], [12, "add"]]);
});

test("a five thousand line function still renders every row", () => {
  const source = Array.from({ length: 5000 }, (_, i) => `line ${i}`).join("\n");
  const rows = core.codeRows({ lines: [1, 5000], source, change: { status: "unchanged", added: [], removed: [] } });
  assert.strictEqual(rows.length, 5000);
});

test("link segments use the same UTF-16 columns as the index", () => {
  const text = 'x = "ação 😀"; total(y)';
  const col = 'x = "ação 😀"; '.length;
  const segments = core.lineSegments(text, [{ col, len: 5, to: "t" }, { col: 200, len: 3, to: "far" }]);
  assert.deepStrictEqual(segments.map((s) => s.text), ['x = "ação 😀"; ', "total", "(y)"]);
  assert.strictEqual(segments[1].span.to, "t");
});

test("the stack pushes, pops and jumps back without losing the root", () => {
  let stack = [{ id: null }];
  stack = core.pushEntry(stack, { id: "a", fromId: null, fromLine: null });
  stack = core.pushEntry(stack, { id: "b", fromId: "a", fromLine: 12 });
  stack = core.pushEntry(stack, { id: "c", fromId: "b", fromLine: 3 });
  assert.deepStrictEqual(core.popTo(stack, 1).map((e) => e.id), [null, "a"]);
  assert.deepStrictEqual(core.popOne(stack).map((e) => e.id), [null, "a", "b"]);
  assert.deepStrictEqual(core.popOne([{ id: null }]), [{ id: null }]);
});

test("progress counts the roteiro and every change", () => {
  const data = { plan: { skeleton: ["a", "b"] }, index: { changed: ["a", "b", "c"] } };
  assert.deepStrictEqual(core.progress(data, new Set(["a", "c"])), { roteiroSeen: 1, roteiroTotal: 2, changedSeen: 2, changedTotal: 3 });
});

const askData = {
  lang: "pt",
  rules: "REGRAS DO FORMATO",
  index: { nodes: {
    "a.py#calc": { ...nodes["a.py#calc"], path: "a.py", kind: "function", callers: [{ from: "a.py#handler", path: "a.py", line: 20, lines: [21], test: false }] },
    "a.py#handler": { ...nodes["a.py#handler"], path: "a.py", kind: "function", source: "def handler():\n    return calc(1)\n", change: { status: "unchanged", added: [], removed: [] }, links: [], external: [], callers: [] },
    "b.py#handler": { ...nodes["b.py#handler"], path: "b.py", kind: "function", source: "def handler():\n    pass\n", change: { status: "unchanged", added: [], removed: [] }, links: [], external: [], callers: [] },
  } },
  explanations: { overview: { story: "A história da branch." }, nodes: { "a.py#handler": { level: "summary", summary: "Recebe a chamada." } } },
};
const askStack = [{ id: null }, { id: "a.py#handler", fromId: null, fromLine: null }, { id: "a.py#calc", fromId: "a.py#handler", fromLine: 21 }];

test("the explain prompt carries the rules, the path, the diff and the required sections", () => {
  const prompt = core.explainPrompt({ data: askData, id: "a.py#calc", stack: askStack });
  assert.ok(prompt.includes("REGRAS DO FORMATO"));
  assert.ok(prompt.includes("Portuguese"));
  assert.ok(prompt.includes("handler > calc (called at line 21 of handler)"));
  assert.ok(prompt.includes("  12 +     return x + y"));
  assert.ok(prompt.includes('"context", "before", "why", "steps", "impact"'));
  assert.ok(prompt.includes("handler: Recebe a chamada."));
});

test("ask turns start with the context and end with the question", () => {
  const turns = core.askTurns({ data: askData, id: "a.py#calc", stack: askStack },
    [{ role: "user", content: "antes?" }, { role: "assistant", content: "sim" }], "por que y?");
  assert.strictEqual(turns[0].role, "user");
  assert.ok(turns[0].content.includes("A história da branch."));
  assert.deepStrictEqual(turns.slice(1).map((turn) => turn.role), ["user", "assistant", "user"]);
  assert.strictEqual(turns[turns.length - 1].content, "por que y?");
});

test("ask tools read and find functions from the index only", () => {
  const tools = Object.fromEntries(core.askTools(askData).map((tool) => [tool.name, tool]));
  assert.deepStrictEqual(tools.find_function.execute({ name: "handler" }), ["a.py#handler", "b.py#handler"]);
  assert.ok(tools.read_function.execute({ id: "a.py#calc" }).source.includes("  12 +     return x + y"));
  assert.deepStrictEqual(tools.callers_of.execute({ id: "a.py#calc" }), [{ id: "a.py#handler", lines: [21], test: false }]);
  assert.throws(() => tools.read_function.execute({ id: "nope" }), /not in the index/);
});

test("an ambiguous reference resolves to the preferred neighbor", () => {
  const prefer = [new Set(["b.py#handler"])];
  const html = core.renderMarkdown("Usa [[handler]].", { ...ctx, prefer });
  assert.ok(html.includes('data-ref="b.py#handler"'));
  assert.ok(core.renderMarkdown("Usa [[handler]].", ctx).includes("<code>handler</code>"));
});
