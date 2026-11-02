import { CITATION_TITLE, parseCitationHref } from "../stream/citations";

/**
 * Marks the text each citation covers: the inline content since the previous citation, or since the
 * start of its paragraph or list item, whichever is later. That text is wrapped in a span the chip can
 * highlight on hover; a segment never crosses a block boundary. Each citation (and its segment) gets
 * an id from its position in the Markdown, which stays stable while the answer streams in.
 *
 * Property names are hast's (camelCase); they reach React as `data-citation-segment` and
 * `data-citation-numbers`.
 */
export const SEGMENT_PROP = "data-citation-segment";
export const NUMBERS_PROP = "data-citation-numbers";

interface HastNode {
  type: string;
  tagName?: string;
  value?: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
}

const BLOCK_TAGS = new Set([
  "p", "ul", "ol", "li", "blockquote", "pre", "table", "div", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
]);

function isCitation(node: HastNode): boolean {
  return node.type === "element" && node.tagName === "a" && node.properties?.title === CITATION_TITLE;
}

function hasContent(nodes: readonly HastNode[]): boolean {
  return nodes.some((node) => node.type !== "text" || Boolean(node.value?.trim()));
}

export function rehypeCitationSegments({ idPrefix }: { idPrefix: string }) {
  return (tree: HastNode) => {
    let count = 0;

    const visit = (parent: HastNode) => {
      const children: HastNode[] = [];
      let pending: HastNode[] = [];
      const release = () => {
        children.push(...pending);
        pending = [];
      };

      for (const child of parent.children ?? []) {
        if (isCitation(child)) {
          const numbers = parseCitationHref(String(child.properties?.href ?? ""));
          const id = `${idPrefix}-${count++}`;
          if (numbers.length && hasContent(pending)) {
            children.push({
              type: "element",
              tagName: "span",
              properties: { dataCitationSegment: id, dataCitationNumbers: numbers.join(",") },
              children: pending,
            });
            pending = [];
          } else {
            release();
          }
          children.push({ ...child, properties: { ...child.properties, dataCitationSegment: id } });
        } else if (child.type === "element") {
          visit(child);
          if (BLOCK_TAGS.has(child.tagName ?? "")) {
            release();
            children.push(child);
          } else {
            pending.push(child);
          }
        } else {
          pending.push(child);
        }
      }
      release();
      parent.children = children;
    };

    visit(tree);
  };
}
