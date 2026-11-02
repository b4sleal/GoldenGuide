import { describe, expect, it } from "vitest";

import { rehypeCitationSegments } from "./rehypeCitationSegments";

interface Node {
  type: string;
  tagName?: string;
  value?: string;
  properties?: Record<string, unknown>;
  children?: Node[];
}

const text = (value: string): Node => ({ type: "text", value });
const element = (tagName: string, children: Node[], properties: Record<string, unknown> = {}): Node => ({
  type: "element",
  tagName,
  properties,
  children,
});
const cite = (...numbers: number[]): Node =>
  element("a", [text(numbers.join(","))], { href: `#gg-cite-${numbers.join("-")}`, title: "gg-citation" });

function run(...children: Node[]): Node {
  const tree: Node = { type: "root", children };
  rehypeCitationSegments({ idPrefix: "t" })(tree);
  return tree;
}

/** A node's shape in one line: text as JSON, citation chips and their segments by id. */
function shape(node: Node): string {
  if (node.type === "text") return JSON.stringify(node.value);
  const properties = node.properties ?? {};
  const id = properties.dataCitationSegment;
  if (node.tagName === "a" && id) return `chip ${id}`;
  const inner = (node.children ?? []).map(shape).join(", ");
  if (node.tagName === "span" && id) return `segment ${id} [${properties.dataCitationNumbers}](${inner})`;
  return `${node.tagName}(${inner})`;
}

const paragraph = (tree: Node) => tree.children![0]!.children!.map(shape);

describe("rehypeCitationSegments", () => {
  it("wraps the text since the previous citation, numbering citations in order", () => {
    const tree = run(element("p", [text("A. "), cite(1), text("B. "), cite(2, 3)]));
    expect(paragraph(tree)).toEqual(['segment t-0 [1]("A. ")', "chip t-0", 'segment t-1 [2,3]("B. ")', "chip t-1"]);
  });

  it("includes inline formatting in the segment", () => {
    const tree = run(element("p", [element("strong", [text("Brantford:")]), text(" Opened in 1999. "), cite(1)]));
    expect(paragraph(tree)).toEqual(['segment t-0 [1](strong("Brantford:"), " Opened in 1999. ")', "chip t-0"]);
  });

  it("starts a segment at each list item and never crosses into a nested list", () => {
    const nested = element("ul", [element("li", [text("Inner "), cite(1)])]);
    const tree = run(element("li", [text("Outer "), nested, cite(2)]));
    const item = tree.children![0]!.children!.map(shape);
    // The citation after the nested list has no text of its own to cover.
    expect(item).toEqual(['"Outer "', 'ul(li(segment t-0 [1]("Inner "), chip t-0))', "chip t-1"]);
  });

  it("gives a citation straight after another none of its own text", () => {
    const tree = run(element("p", [text("A"), cite(1), cite(2)]));
    expect(paragraph(tree)).toEqual(['segment t-0 [1]("A")', "chip t-0", "chip t-1"]);
  });

  it("does not wrap whitespace on its own", () => {
    const tree = run(element("p", [text("\n"), cite(1)]));
    expect(paragraph(tree)).toEqual(['"\\n"', "chip t-0"]);
  });

  it("leaves content without citations, and ordinary links, untouched", () => {
    const link = element("a", [text("CP264")], { href: "https://www.wlu.ca" });
    const tree = run(element("p", [text("See "), link]));
    expect(tree).toEqual({ type: "root", children: [element("p", [text("See "), link])] });
  });
});
