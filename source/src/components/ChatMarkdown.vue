<script lang="ts">
import { defineComponent, h, type VNodeChild } from "vue";
import { Marked, type MarkedToken, type Token, type Tokens } from "marked";
import markedCjkFriendly from "marked-cjk-friendly";
import { decodeHTMLStrict } from "entities/decode";

const markdown = new Marked({ gfm: true, breaks: true }, markedCjkFriendly());

function tableRow(cells: Tokens.TableCell[]) {
  return h(
    "tr",
    cells.map((cell) =>
      h(
        cell.header ? "th" : "td",
        {
          scope: cell.header ? "col" : undefined,
          style: cell.align ? { textAlign: cell.align } : undefined,
        },
        cell.tokens.map(renderToken),
      ),
    ),
  );
}

function renderLink(token: Tokens.Link) {
  const label = token.autolink ? token.text : token.tokens.map(renderToken);
  const href = token.autolink ? token.href : decodeHTMLStrict(token.href);
  // Resolve relative references only to inspect their browser-parsed protocol.
  try {
    const url = new URL(href, "https://example.invalid/");
    if (!["https:", "http:", "mailto:"].includes(url.protocol)) return label;
  } catch {
    return label;
  }
  return h(
    "a",
    {
      href,
      title: token.title ? decodeHTMLStrict(token.title) : undefined,
      target: "_blank",
      rel: "noopener noreferrer",
    },
    label,
  );
}

// The CJK extension emits standard Marked tokens. Render only known Vue elements.
function renderToken(input: Token): VNodeChild {
  const token = input as MarkedToken;
  switch (token.type) {
    case "text":
      return token.tokens?.map(renderToken) ?? decodeHTMLStrict(token.text);
    case "escape":
    case "html":
      return token.text;
    case "space":
    case "def":
      return null;
    case "paragraph":
      return h("p", token.tokens.map(renderToken));
    case "heading":
      return h(`h${token.depth}`, token.tokens.map(renderToken));
    case "blockquote":
    case "em":
    case "strong":
    case "del":
      return h(token.type, token.tokens.map(renderToken));
    case "br":
    case "hr":
      return h(token.type);
    case "code":
      return h("pre", [h("code", token.text)]);
    case "codespan":
      return h("code", token.text);
    case "list":
      return h(
        token.ordered ? "ol" : "ul",
        {
          start: token.ordered && token.start !== 1 ? token.start : undefined,
        },
        token.items.map(renderToken),
      );
    case "list_item":
      return h(
        "li",
        { class: { "task-item": token.task } },
        token.tokens.map(renderToken),
      );
    case "checkbox":
      return h("input", {
        type: "checkbox",
        disabled: true,
        checked: token.checked,
        "aria-label": token.checked ? "已完成" : "未完成",
      });
    case "table":
      return h("div", { class: "table-scroll" }, [
        h("table", [
          h("thead", [tableRow(token.header)]),
          h("tbody", token.rows.map(tableRow)),
        ]),
      ]);
    case "link":
      return renderLink(token);
    case "image":
      return token.tokens.map(renderToken);
    default:
      return input.raw;
  }
}

export default defineComponent({
  props: { content: { type: String, required: true } },
  setup(props) {
    return () =>
      h(
        "div",
        { class: "chat-markdown" },
        markdown.lexer(props.content).map(renderToken),
      );
  },
});
</script>

<style scoped>
.chat-markdown {
  min-width: 0;
  margin-top: 0.45em;
  color: #35445b;
  line-height: 1.7;
  overflow-wrap: anywhere;
}
.chat-markdown p,
.chat-markdown ul,
.chat-markdown ol,
.chat-markdown blockquote,
.chat-markdown pre,
.chat-markdown .table-scroll {
  margin: 0.65em 0;
}
.chat-markdown p {
  font: inherit;
  white-space: normal;
}
.chat-markdown :is(h1, h2, h3, h4, h5, h6) {
  margin: 1em 0 0.35em;
  color: #253750;
  font-size: 1.06em;
  line-height: 1.4;
}
.chat-markdown h1 {
  font-size: 1.3em;
}
.chat-markdown h2 {
  font-size: 1.16em;
}
.chat-markdown strong {
  color: #253750;
  font-weight: 700;
}
.chat-markdown :is(ul, ol) {
  padding-inline-start: 1.65em;
}
.chat-markdown li + li {
  margin-top: 0.18em;
}
.chat-markdown li :is(ul, ol) {
  margin-block: 0.18em;
}
.task-item {
  list-style: none;
}
.task-item input {
  margin: 0 0.45em 0 -1.45em;
  vertical-align: middle;
}
.chat-markdown blockquote {
  border-inline-start: 3px solid #c0cfea;
  padding-inline-start: 0.85em;
  color: #53647c;
}
.chat-markdown code {
  border-radius: 4px;
  padding: 0.12em 0.35em;
  background: #edf1f7;
  color: #374e78;
  font:
    0.92em/1.55 ui-monospace,
    SFMono-Regular,
    Consolas,
    monospace;
}
.chat-markdown pre {
  max-width: 100%;
  overflow-x: auto;
  padding: 0.8em 0.95em;
  border: 1px solid #dfe6ef;
  border-radius: 7px;
  background: #f6f8fc;
  white-space: pre;
  tab-size: 4;
}
.chat-markdown pre code {
  padding: 0;
  background: transparent;
  color: inherit;
}
.chat-markdown a {
  color: var(--blue);
  text-decoration: underline;
  text-underline-offset: 2px;
}
.table-scroll {
  max-width: 100%;
  overflow-x: auto;
}
.chat-markdown table {
  width: 100%;
  border-collapse: collapse;
}
.chat-markdown :is(th, td) {
  min-width: 4.5em;
  padding: 0.35em 0.55em;
  border: 1px solid #dce4ef;
  text-align: start;
}
.chat-markdown th {
  background: #f1f5fb;
}
.chat-markdown hr {
  margin-block: 0.9em;
  border: 0;
  border-top: 1px solid #dce4ef;
}
.chat-markdown > :first-child {
  margin-top: 0;
}
.chat-markdown > :last-child {
  margin-bottom: 0;
}
</style>
