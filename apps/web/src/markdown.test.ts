import { describe, expect, it } from "vitest";

import { renderMarkdown } from "./markdown";

describe("renderMarkdown", () => {
  it("renders headings at the right level", () => {
    expect(renderMarkdown("# Title")).toBe("<h1>Title</h1>");
    expect(renderMarkdown("## Sub")).toBe("<h2>Sub</h2>");
    expect(renderMarkdown("### Deep")).toBe("<h3>Deep</h3>");
  });

  it("renders unordered lists, wrapping items in a single <ul>", () => {
    const html = renderMarkdown("- one\n- two");
    expect(html).toBe("<ul>\n<li>one</li>\n<li>two</li>\n</ul>");
  });

  it("renders paragraphs for plain text", () => {
    expect(renderMarkdown("hello world")).toBe("<p>hello world</p>");
  });

  it("renders bold via **...**", () => {
    expect(renderMarkdown("a **bold** word")).toBe("<p>a <strong>bold</strong> word</p>");
  });

  it("converts [n] citation markers to anchor links", () => {
    expect(renderMarkdown("see [1] and [12]")).toBe(
      '<p>see <a class="cite" href="#src-1">[1]</a> and <a class="cite" href="#src-12">[12]</a></p>',
    );
  });

  it("escapes HTML so model output cannot inject markup", () => {
    const html = renderMarkdown("5 < 3 & 4 > 1");
    expect(html).toBe("<p>5 &lt; 3 &amp; 4 &gt; 1</p>");
    expect(html).not.toContain("<3");
  });

  // XSS: a raw <img onerror> payload must be neutralised (escaped), never emitted
  // as a live tag.
  it("escapes an XSS <img onerror> payload (no raw tag in output)", () => {
    const html = renderMarkdown('<img src=x onerror=alert(1)>');
    expect(html).not.toContain("<img");
    expect(html).not.toMatch(/<img[^>]*onerror/i);
    expect(html).toContain("&lt;img");
    expect(html).toContain("&gt;");
  });

  it("does not emit raw <script> tags", () => {
    const html = renderMarkdown("<script>alert('xss')</script>");
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
  });

  it("closes an open list when followed by a heading or paragraph", () => {
    const html = renderMarkdown("- item\n\n# After");
    expect(html).toBe("<ul>\n<li>item</li>\n</ul>\n<h1>After</h1>");
  });
});
