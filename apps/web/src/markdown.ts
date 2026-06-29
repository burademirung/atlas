/** Minimal, safe Markdown → HTML. Escapes first, then applies a small subset,
 *  so untrusted model output can't inject HTML (the LLM05 output-handling control). */
function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function inline(s: string): string {
  return s
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\[(\d+)\]/g, '<a class="cite" href="#src-$1">[$1]</a>');
}

export function renderMarkdown(md: string): string {
  const lines = escapeHtml(md).split("\n");
  const out: string[] = [];
  let inList = false;
  const closeList = () => {
    if (inList) {
      out.push("</ul>");
      inList = false;
    }
  };
  for (const raw of lines) {
    const line = raw.trimEnd();
    const h = line.match(/^(#{1,3})\s+(.*)$/);
    const li = line.match(/^\s*[-*]\s+(.*)$/);
    if (h) {
      closeList();
      out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`);
    } else if (li) {
      if (!inList) {
        out.push("<ul>");
        inList = true;
      }
      out.push(`<li>${inline(li[1])}</li>`);
    } else if (line.trim() === "") {
      closeList();
    } else {
      closeList();
      out.push(`<p>${inline(line)}</p>`);
    }
  }
  closeList();
  return out.join("\n");
}
