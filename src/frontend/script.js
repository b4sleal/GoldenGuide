// GoldenGuide chat client.
// Reads the NDJSON stream from POST /api/v1/chat/stream (protocol: src/backend/api/streaming.py).
// An answer counts as complete ONLY when the server sends {"type": "ok"} as the last event.

const INTERRUPTED_NOTICE = "Stream interrupted, try asking again.";

document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("submit-btn").addEventListener("click", ask);
});

// Wrap every Markdown table in a scroll container (marked's standard renderer extension point).
// The answer text stays pure Markdown; the wrapper exists only in the rendered HTML. Styling and
// the "scroll only when needed" behaviour are in styles.css (.table-scroll).
marked.use({
    renderer: {
        table(token) {
            return `<div class="table-scroll">${marked.Renderer.prototype.table.call(this, token)}</div>`;
        },
    },
});

// Render Markdown to safe HTML. marked passes raw HTML through, so model output containing HTML
// could inject script; DOMPurify removes anything executable while keeping formatting, tables,
// links and our wrapper. `target` is kept so citation/source links open in a new tab.
function renderMarkdown(markdown) {
    return DOMPurify.sanitize(marked.parse(markdown), { ADD_ATTR: ["target"] });
}

// Escape one value for a GFM Markdown table cell. Values come from scraped LORIS data, so a "|"
// in a title would split the cell and shift every column, "<" would become HTML (marked renders
// raw HTML), "*", "_", "[" etc. would become formatting or links, and a bare "http://..." or
// "www..." would be auto-linked. Every such character is written as an HTML numeric entity
// (e.g. "|" -> "&#124;"): Markdown never sees the raw character, the browser still displays it.
// (Backslash escapes are not enough: GFM's autolinker ignores them.)
const MARKDOWN_SPECIAL = /[&<>"'|\\`*_{}\[\]()#+!~:.-]/g;

function escapeMarkdownCell(value) {
    return String(value)
        .replace(MARKDOWN_SPECIAL, ch => `&#${ch.charCodeAt(0)};`)
        .replace(/\r?\n/g, "<br>");   // GFM cells are one line; a multi-meeting cell shows one meeting per line
}

// Keep a short data value on one line ("Mon/Wed/Fri", "10:00–11:20", "Iga Mergler"): spaces become
// non-breaking spaces and a word joiner (U+2060) follows "/" and surrounds "–", the characters
// browsers would otherwise break at. Only applied to our database tables; tables the model writes
// (which may contain sentences) keep normal wrapping. Each meeting is still its own line (<br>).
function keepTogether(value) {
    return String(value)
        .replace(/ /g, " ")
        .replace(/\//g, "/⁠")
        .replace(/–/g, "⁠–⁠");
}

// Turn a {"type": "table", title, columns, rows} event into a Markdown table with its title in bold,
// so the whole answer stays Markdown like other chatbots. Blank lines around it make Markdown
// treat it as its own block.
function toMarkdownTable(event) {
    const row = cells => `| ${cells.map(cell => escapeMarkdownCell(keepTogether(cell))).join(" | ")} |`;
    return [
        "",
        `**${escapeMarkdownCell(event.title)}**`,
        "",
        row(event.columns),
        `| ${event.columns.map(() => "---").join(" | ")} |`,
        ...event.rows.map(row),
        "",
        "",
    ].join("\n");
}

// Turn a server error envelope {"error": {code, message, request_id}} into display text.
// The request ID lets staff find the exact request in logs/traces from a user's screenshot.
function describeError(error, fallback) {
    const message = error?.message ?? fallback;
    return error?.request_id ? `${message} (reference: ${error.request_id})` : message;
}

async function ask() {
    const input = document.getElementById("question");
    const btn = document.getElementById("submit-btn");
    const container = document.getElementById("answer-container");
    const content = document.getElementById("answer-content");

    const question = input.value.trim();
    if (!question) return;

    // Step 1: reset the UI for a new answer.
    btn.setAttribute("aria-busy", "true");
    btn.textContent = "Thinking...";
    content.innerHTML = "";

    let fullText = "";           // markdown accumulated from text/citation/sources events
    let finished = false;        // true once a terminal event ("ok" or "error") arrives

    // Re-render the accumulated markdown.
    function render() {
        content.innerHTML = renderMarkdown(fullText);
        container.classList.add("visible");
    }

    // Append a visible notice under whatever partial answer was already shown.
    function showNotice(message) {
        fullText += `\n\n> ⚠️ ${message}`;
        render();
    }

    // Step 2: apply one stream event to the answer.
    function handleEvent(event) {
        switch (event.type) {
            case "text":
                fullText += event.text || "";
                break;
            case "citation":
                fullText += event.source_nums.map((num, i) => {
                    const url = event.urls?.[i];
                    return url
                        ? `<a href="${url}" target="_blank" rel="noopener noreferrer">[${num}]</a>`
                        : `[${num}]`;
                }).join(" ");
                break;
            case "table":
                // A complete table built by the server from database records. It arrives in one
                // event, so it renders fully formed (never half-drawn).
                fullText += toMarkdownTable(event);
                break;
            case "sources":
                fullText += "\n\n---\n### 📚 Sources\n";
                fullText += event.sources.map(source =>
                    source.url ? `* [${source.title}](${source.url})` : `* ${source.title}`
                ).join("\n");
                break;
            case "ok":
                // Terminal success: the answer is complete.
                finished = true;
                return;
            case "error":
                // Terminal failure reported by the server mid-answer.
                finished = true;
                showNotice(describeError(event.error, INTERRUPTED_NOTICE));
                return;
            default:
                // Unknown event types are ignored so the server can add new ones safely.
                return;
        }
        render();
    }

    try {
        // Step 3: send the question.
        const res = await fetch("/api/v1/chat/stream", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: question }),
        });

        // Step 4: errors before streaming starts arrive as a normal HTTP error with a JSON envelope
        // (rate limit, validation, retrieval failure, ...).
        if (!res.ok) {
            const body = await res.json().catch(() => null);
            showNotice(describeError(body?.error, `Request failed (HTTP ${res.status})`));
            return;
        }

        // Step 5: read the stream. Network chunks do not align with lines, so keep the
        // incomplete tail in `pending` until its newline arrives.
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let pending = "";

        while (!finished) {
            const { value, done } = await reader.read();
            if (done) break;

            pending += decoder.decode(value, { stream: true });
            const lines = pending.split("\n");
            pending = lines.pop();

            for (const line of lines) {
                if (line.trim()) handleEvent(JSON.parse(line));
                if (finished) break;
            }
        }

        // Step 6: flush any final line that arrived without a trailing newline.
        pending += decoder.decode();
        if (!finished && pending.trim()) handleEvent(JSON.parse(pending));

        // Step 7: the connection closed without "ok" or "error": the answer is incomplete.
        if (!finished) showNotice(INTERRUPTED_NOTICE);

    } catch (err) {
        // Network drop mid-stream, malformed JSON line, or fetch failure.
        // Log the technical detail for developers; show students a clear next step.
        console.error(err);
        if (!finished) showNotice(INTERRUPTED_NOTICE);
    } finally {
        btn.setAttribute("aria-busy", "false");
        btn.textContent = "Ask GoldenGuide";
    }
}
