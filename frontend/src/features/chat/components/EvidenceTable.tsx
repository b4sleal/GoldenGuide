import type { TableEvent } from "../stream/events";
import { TableScroll } from "./TableScroll";

/**
 * A table of database records sent as a `table` event. Rendered from the data itself (never as
 * Markdown), so scraped values such as "|" or "<" cannot change its structure.
 */
export function EvidenceTable({ table }: { table: Omit<TableEvent, "type"> }) {
  return (
    <figure className="min-w-0 space-y-1.5">
      <figcaption className="text-sm font-semibold">{table.title}</figcaption>
      <TableScroll label={table.title}>
        <table aria-label={table.title} className="text-sm">
          <thead>
            <tr>
              {table.columns.map((column) => (
                <th key={column} scope="col" className="bg-muted px-3 py-1.5 text-left font-semibold whitespace-nowrap">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, cellIndex) => (
                  // TableScroll preserves explicit meeting line breaks without wrapping whole columns.
                  <td key={cellIndex} className="border-t px-3 py-1.5 align-top">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </TableScroll>
    </figure>
  );
}
