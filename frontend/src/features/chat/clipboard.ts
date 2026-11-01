import { COPIED_SOURCES_LABEL } from "./labels";
import { type AnswerBlock, CITATION_TITLE } from "./stream/answer";
import type { Source } from "./stream/events";

function tableCell(value: string): string {
  // Quote multi-line cells so spreadsheet pastes keep meetings in their original row and column.
  return /[\t\r\n"]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value;
}

/** Keep block order and source URLs when pasting into a document or another chat.
 * Markdown stays editable; structured tables use tabs rather than compressed column widths.
 */
export function answerClipboardText(blocks: readonly AnswerBlock[], sources: readonly Source[]): string {
  const parts = blocks.map((block) => {
    if (block.kind === "markdown") {
      // This private renderer hint is not part of the answer students should paste.
      return block.markdown.replaceAll(` "${CITATION_TITLE}")`, ")");
    }
    const { title, columns, rows } = block.table;
    return [title, columns.map(tableCell).join("\t"), ...rows.map((row) => row.map(tableCell).join("\t"))].filter(Boolean).join("\n");
  });
  if (sources.length) {
    parts.push([
      COPIED_SOURCES_LABEL,
      ...sources.map((source, index) => `[${index + 1}] ${source.title}${source.url ? `: ${source.url}` : ""}`),
    ].join("\n"));
  }
  return parts.filter((part) => part.trim()).join("\n\n").trim();
}
