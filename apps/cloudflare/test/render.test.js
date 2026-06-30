import { describe, expect, it } from "vitest";

import { escapeHtml, renderMarkdown } from "../public/render.js";

describe("escapeHtml", () => {
  it("escapes the HTML-significant characters", () => {
    expect(escapeHtml('& < > "')).toBe("&amp; &lt; &gt; &quot;");
  });
});

describe("renderMarkdown", () => {
  it("renders headings at the right level", () => {
    expect(renderMarkdown("# Title")).toBe("<h1>Title</h1>");
    expect(renderMarkdown("### Deep")).toBe("<h3>Deep</h3>");
  });

  it("renders unordered lists inside a single <ul>", () => {
    expect(renderMarkdown("- one\n- two")).toBe("<ul>\n<li>one</li>\n<li>two</li>\n</ul>");
  });

  it("renders '- [ ] text' as an unchecked task item with a ☐ glyph", () => {
    expect(renderMarkdown("- [ ] Freeze your credit")).toBe(
      '<ul>\n<li class="task todo"><span class="box">☐</span>Freeze your credit</li>\n</ul>',
    );
  });

  it("renders '- [x] text' as a checked task item with a ☑ glyph", () => {
    expect(renderMarkdown("- [x] Done already")).toBe(
      '<ul>\n<li class="task done"><span class="box">☑</span>Done already</li>\n</ul>',
    );
  });

  it("keeps citations inside a task item", () => {
    expect(renderMarkdown("- [ ] Place a fraud alert [2]")).toBe(
      '<ul>\n<li class="task todo"><span class="box">☐</span>Place a fraud alert ' +
        '<a class="cite" href="#source-2">[2]</a></li>\n</ul>',
    );
  });

  it("renders bold and converts [n] citations to source anchors", () => {
    expect(renderMarkdown("a **b** [3]")).toBe(
      '<p>a <strong>b</strong> <a class="cite" href="#source-3">[3]</a></p>',
    );
  });

  it("escapes an XSS <img onerror> payload (no live tag in output)", () => {
    const html = renderMarkdown("<img src=x onerror=alert(1)>");
    expect(html).not.toContain("<img");
    expect(html).not.toMatch(/<img[^>]*onerror/i);
    expect(html).toContain("&lt;img");
  });

  it("does not emit raw <script> tags", () => {
    const html = renderMarkdown("<script>alert('xss')</script>");
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
  });
});
