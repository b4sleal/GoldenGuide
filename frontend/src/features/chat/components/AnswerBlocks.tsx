import type { AnswerBlock } from "../stream/answer";
import { EvidenceTable } from "./EvidenceTable";
import { Markdown } from "./Markdown";

/** Live and restored answers share the same safe renderers, including table scrolling. */
export function AnswerBlocks({ blocks }: { blocks: readonly AnswerBlock[] }) {
  return blocks.map((block, index) =>
    block.kind === "markdown" ? (
      <Markdown key={index} markdown={block.markdown} idPrefix={String(index)} />
    ) : (
      <EvidenceTable key={index} table={block.table} />
    ),
  );
}
