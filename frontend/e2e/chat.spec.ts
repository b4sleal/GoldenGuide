import { expect, type Locator, type Page, test } from "@playwright/test";

const CONVERSATION = "44444444-4444-4444-8444-444444444444";

const events = [
  { type: "status", stage: "understanding" },
  { type: "sources", sources: [{ title: "CP264 Data Structures II", url: "https://academic-calendar.wlu.ca/" }] },
  { type: "text", text: "CP264 requires **CP164**" },
  { type: "citation", source_nums: [1], urls: ["https://academic-calendar.wlu.ca/"] },
  { type: "ok" },
];

async function finishComposerTransition(page: Page) {
  // A mocked answer can finish before the composer reaches the bottom. Await the real CSS
  // transition so geometry checks and table keyboard scrolling use the settled layout.
  await page.locator(".chat-layout").evaluate(async (element) => {
    await Promise.all(element.getAnimations().map((animation) => animation.finished));
  });
}

async function scrollWithKey(viewport: Locator, key: "ArrowRight" | "ArrowLeft" | "ArrowDown" | "ArrowUp") {
  // A positive offset is only an intermediate frame (e.g. 39px on the way to 40px).
  // Register before pressing, then wait for native scrolling to finish before reversing direction.
  const completion = await viewport.evaluateHandle((element) => {
    const state = { ended: false };
    element.addEventListener("scrollend", () => { state.ended = true; }, { once: true });
    return state;
  });
  try {
    await viewport.press(key);
    await expect.poll(() => completion.evaluate((state) => state.ended), {
      message: `The table should finish scrolling after ${key}`,
    }).toBe(true);
    return await viewport.evaluate((element) => ({ left: element.scrollLeft, top: element.scrollTop }));
  } finally {
    await completion.dispose();
  }
}

test("asks a question and shows a sourced answer", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.route("**/api/v1/chat/conversations", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/chat/stream", (route) =>
    route.fulfill({
      contentType: "application/x-ndjson",
      headers: { "X-Conversation-Id": CONVERSATION },
      body: events.map((event) => JSON.stringify(event)).join("\n") + "\n",
    }),
  );

  await page.goto("/");
  const input = page.getByLabel(/ask about laurier/i);
  const originalInput = await input.elementHandle();
  const initialBounds = (await input.boundingBox())!;
  const mainBounds = (await page.getByRole("main").boundingBox())!;
  // Check real layout in both desktop and phone projects, not jsdom's zero-sized rectangles.
  expect(Math.abs(initialBounds.y + initialBounds.height / 2 - (mainBounds.y + mainBounds.height / 2))).toBeLessThan(60);
  await expect(page.locator(".chat-layout")).toHaveCSS("transition-duration", "0.55s");
  await input.fill("What are the prerequisites for CP264?");
  await page.keyboard.press("Enter");

  const answer = page.getByRole("article", { name: /goldenguide answer/i });
  await expect(answer.getByText("CP164")).toBeVisible();
  await expect(answer.getByRole("button", { name: "Source: CP264 Data Structures II" })).toBeVisible();
  await expect(answer.getByRole("region", { name: "Sources" })).toContainText("CP264 Data Structures II");
  await expect(page).toHaveURL(new RegExp(`/c/${CONVERSATION}$`));
  await expect(input).toBeFocused();
  expect(await originalInput!.evaluate((element) => element.isConnected)).toBe(true);
  await finishComposerTransition(page);
  await expect.poll(async () => {
    const bottomBounds = (await input.boundingBox())!;
    const currentMainBounds = (await page.getByRole("main").boundingBox())!;
    return currentMainBounds.y + currentMainBounds.height - bottomBounds.y - bottomBounds.height;
  }).toBeLessThan(100);
  expect((await input.boundingBox())!.y).toBeGreaterThan(initialBounds.y + mainBounds.height / 4);
  await expect(answer.getByRole("button", { name: "Copy answer" })).toBeVisible();
});

test("switches themes immediately in new and populated chats", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "no-preference" });
  await page.route("**/api/v1/chat/conversations", (route) => route.fulfill({ json: [] }));
  await page.route(`**/api/v1/chat/conversations/${CONVERSATION}/messages`, (route) => route.fulfill({ json: [{
    id: 2, position: 2, role: "assistant", content: "Course offerings", status: "complete",
    created_at: "2026-11-01T00:00:01Z",
    answer_content: { version: 1, blocks: [
      { type: "text", text: "Course offerings" },
      { type: "table", title: "Courses", columns: ["Course", "Term"], rows: Array.from({ length: 30 }, (_, index) => [`CP${100 + index}`, "Winter 2027"]) },
    ] },
  }] }));

  for (const path of ["/", `/c/${CONVERSATION}`]) {
    await page.goto(path);
    if (path !== "/") await expect(page.getByRole("cell", { name: "CP100", exact: true })).toBeVisible();
    for (const theme of ["dark", "light"]) {
      await page.getByRole("button", { name: `Switch to ${theme} theme` }).click();
      // Check actual browser animation work on a populated DOM, not just equal CSS durations.
      const state = await page.evaluate(() => {
        const newChat = [...document.querySelectorAll("a")].find((link) => link.textContent?.trim() === "New chat")!;
        return {
          dark: document.documentElement.classList.contains("dark"),
          buttonDuration: getComputedStyle(newChat).transitionDuration,
          bodyDuration: getComputedStyle(document.body).transitionDuration,
          colorTransitions: document.getAnimations().filter((animation) => animation instanceof CSSTransition && (
            animation.transitionProperty.includes("color") || ["fill", "stroke", "box-shadow"].includes(animation.transitionProperty)
          )).length,
        };
      });
      expect(state).toEqual({ dark: theme === "dark", buttonDuration: "0s", bodyDuration: "0s", colorTransitions: 0 });
    }
  }
  await page.reload();
  await expect(page.getByRole("button", { name: "Switch to dark theme" })).toBeVisible();
  await expect(page.locator("html")).not.toHaveClass(/dark/);
  await expect(page.locator("html")).not.toHaveClass(/theme-transition/);
});

test("respects reduced motion for the composer and theme change", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await page.route("**/api/v1/chat/conversations", (route) => route.fulfill({ json: [] }));
  await page.goto("/");
  await expect(page.locator(".chat-layout")).toHaveCSS("transition-duration", "0s");
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await expect(page.locator("html")).not.toHaveClass(/theme-transition/);
});

test("opens a conversation directly and reloads its stored messages", async ({ page }) => {
  await page.route("**/api/v1/chat/conversations", (route) => route.fulfill({ json: [] }));
  await page.route(`**/api/v1/chat/conversations/${CONVERSATION}/messages`, (route) =>
    route.fulfill({
      json: [
        { id: 1, position: 1, role: "user", content: "Prerequisites for CP264?", status: "complete", created_at: "2026-11-01T00:00:00Z" },
        { id: 2, position: 2, role: "assistant", content: "CP264 requires **CP164**.", status: "complete", created_at: "2026-11-01T00:00:01Z" },
      ],
    }),
  );

  // Neither entry may rely on an earlier visit to /; the server must serve the SPA at this URL.
  await page.goto(`/c/${CONVERSATION}`);
  await expect(page.getByText("Prerequisites for CP264?")).toBeVisible();
  await page.reload();
  await expect(page.getByRole("article", { name: /goldenguide answer/i }).getByText("CP164")).toBeVisible();
  await expect(page.getByRole("button", { name: "Good answer" })).toBeVisible();
});

test("restores streamed tables, citations and sources after a full reload", async ({ page }) => {
  const blocks = [
    { type: "text", text: "CP264 sections" },
    { type: "citation", source_nums: [1], urls: ["https://loris.wlu.ca"] },
    { type: "table", title: "CP264 sections", columns: ["Section", "Days"], rows: [["A", "Mon/Wed"], ["B", "Friday"]] },
    { type: "text", text: "Check LORIS for live availability." },
  ];
  const sources = [{ title: "LORIS registration", url: "https://loris.wlu.ca" }];
  await page.route("**/api/v1/chat/conversations", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/chat/stream", (route) => route.fulfill({
    contentType: "application/x-ndjson",
    headers: { "X-Conversation-Id": CONVERSATION },
    body: [{ type: "sources", sources }, ...blocks, { type: "ok" }].map((event) => JSON.stringify(event)).join("\n") + "\n",
  }));
  await page.route(`**/api/v1/chat/conversations/${CONVERSATION}/messages`, (route) => route.fulfill({ json: [{
    id: 2, position: 2, role: "assistant", content: "CP264 sectionsCheck LORIS for live availability.",
    status: "complete", created_at: "2026-11-01T00:00:01Z", answer_content: { version: 1, blocks }, sources,
  }] }));

  await page.goto("/");
  await page.getByLabel(/ask about laurier/i).fill("Show CP264 sections");
  await page.keyboard.press("Enter");
  await expect(page.getByText("Answer ready.")).toBeAttached();
  await expect(page).toHaveURL(new RegExp(`/c/${CONVERSATION}$`));
  await expect(page.getByRole("cell", { name: "Mon/Wed" })).toBeVisible();

  // A full reload discards the provider's live state; everything below must come from stored history.
  await page.reload();
  const answer = page.getByRole("article", { name: /goldenguide answer/i });
  await expect(answer.getByRole("cell", { name: "Mon/Wed" })).toBeVisible();
  await expect(answer.getByRole("cell", { name: "Friday" })).toBeVisible();
  await answer.getByRole("button", { name: "Source: LORIS registration" }).click();
  await expect(page.getByRole("list", { name: "Cited sources" }).getByRole("link")).toHaveAttribute("href", "https://loris.wlu.ca");
  await expect(answer.getByRole("region", { name: "Sources" })).toContainText("LORIS registration");
  await expect(answer.getByRole("button", { name: "Good answer" })).toBeVisible();
});

test("scrolls wide, tall answer tables without compressing cells or widening the page", async ({ page }) => {
  const columns = ["Section", "Meetings", "Instructor", "Registration notes"];
  const rows = Array.from({ length: 35 }, (_, index) => [
    `CP264 section ${index + 1}`,
    "Monday 10:00 - 11:20\nWednesday 10:00 - 11:20",
    "An instructor with a long display name",
    "Check LORIS registration for the latest seat availability and section restrictions.",
  ]);
  const markdownTable = [
    `| ${columns.join(" | ")} |`,
    "| --- | --- | --- | --- |",
    ...rows.map((row) => `| ${row.map((cell) => cell.replaceAll("\n", "; ")).join(" | ")} |`),
  ].join("\n");
  const tableEvents = [
    { type: "table", title: "CP264 sections", columns, rows },
    { type: "text", text: `\n\n${markdownTable}\n` },
    { type: "ok" },
  ];
  await page.route("**/api/v1/chat/conversations", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/chat/stream", (route) =>
    route.fulfill({
      contentType: "application/x-ndjson",
      headers: { "X-Conversation-Id": CONVERSATION },
      body: tableEvents.map((event) => JSON.stringify(event)).join("\n") + "\n",
    }),
  );

  await page.goto("/");
  await page.getByLabel(/ask about laurier/i).fill("Show CP264 sections");
  await page.keyboard.press("Enter");
  await expect(page.getByText("Answer ready.")).toBeAttached();

  // jsdom has no layout engine: exercise actual overflow and sticky positioning in both viewports.
  await finishComposerTransition(page);
  for (const name of ["CP264 sections", "Answer table"]) {
    const viewport = page.getByRole("region", { name, exact: true });
    const header = viewport.getByRole("columnheader", { name: "Section", exact: true });
    await expect.poll(() => viewport.evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(true);
    await expect.poll(() => viewport.evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(true);
    await expect(viewport.getByRole("cell").first()).toHaveCSS("white-space", "pre");
    await expect(viewport.getByRole("cell").first()).toHaveCSS("font-size", "14px");

    await viewport.focus();
    await expect(viewport).toBeFocused();
    const start = await viewport.evaluate((element) => ({ left: element.scrollLeft, top: element.scrollTop }));
    const right = await scrollWithKey(viewport, "ArrowRight");
    expect(right.left).toBeGreaterThan(start.left);
    const left = await scrollWithKey(viewport, "ArrowLeft");
    expect(left.left).toBeLessThan(right.left);

    const down = await scrollWithKey(viewport, "ArrowDown");
    expect(down.top).toBeGreaterThan(left.top);
    const up = await scrollWithKey(viewport, "ArrowUp");
    expect(up.top).toBeLessThan(down.top);

    // Check the far-corner sticky header separately: a programmatic jump must not interrupt
    // the native keyboard scroll animation whose direction we are asserting above.
    await viewport.evaluate((element) => {
      element.scrollLeft = element.scrollWidth;
      element.scrollTop = element.scrollHeight;
    });
    await expect(header).toHaveCSS("position", "sticky");
    await expect.poll(() => header.evaluate((element) => {
      const scrollArea = element.closest('[role="region"]')!;
      return Math.abs(element.getBoundingClientRect().top - scrollArea.getBoundingClientRect().top - scrollArea.clientTop);
    })).toBeLessThan(2);
  }
  expect(await page.locator("html").evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
});

test("keeps sources in one row with mouse dragging, keyboard controls and native touch scrolling", async ({ page, isMobile }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const sources = Array.from({ length: 12 }, (_, index) => ({
    title: `Official source ${index + 1}`, url: `https://academic-calendar.wlu.ca/source-${index + 1}`,
  }));
  await page.route("**/api/v1/chat/conversations", (route) => route.fulfill({ json: [] }));
  await page.route(`**/api/v1/chat/conversations/${CONVERSATION}/messages`, (route) => route.fulfill({ json: [{
    id: 2, position: 2, role: "assistant", content: "An answer with several official references.",
    status: "complete", created_at: "2026-11-01T00:00:01Z", sources,
  }] }));
  await page.goto(`/c/${CONVERSATION}`);
  const list = page.getByRole("list", { name: "Source links" });
  await expect(list.getByRole("listitem")).toHaveCount(sources.length);
  await expect(list).toHaveCSS("scrollbar-width", "none");
  expect(await list.evaluate((element) => getComputedStyle(element, "::-webkit-scrollbar").display)).toBe("none");
  const cardTops = await list.getByRole("listitem").evaluateAll((cards) => cards.map((card) => card.getBoundingClientRect().top));
  expect(Math.max(...cardTops) - Math.min(...cardTops)).toBeLessThan(1);
  expect((await list.boundingBox())!.height).toBeLessThan(90);
  await expect(page.getByRole("button", { name: "Previous sources" })).toBeDisabled();

  const bounds = (await list.boundingBox())!;
  const pageCount = page.context().pages().length;
  // Start on an anchor: dragging must scroll rather than opening its link or starting native link-drag.
  await page.mouse.move(bounds.x + 180, bounds.y + bounds.height / 2);
  await page.mouse.down();
  await page.mouse.move(bounds.x + 40, bounds.y + bounds.height / 2, { steps: 12 });
  await page.mouse.up();
  await expect.poll(() => list.evaluate((element) => element.scrollLeft)).toBeGreaterThan(100);
  expect(page.context().pages()).toHaveLength(pageCount);

  await list.focus();
  const beforeKey = await list.evaluate((element) => element.scrollLeft);
  const afterKey = await scrollWithKey(list, "ArrowRight");
  expect(afterKey.left).toBeGreaterThan(beforeKey);
  await page.getByRole("button", { name: "Next sources" }).click();
  await expect.poll(() => list.evaluate((element) => element.scrollLeft)).toBeGreaterThan(afterKey.left);

  if (isMobile) {
    // CDP sends real touch input to the phone browser; no pointer-event mock or scrollLeft assignment.
    const touch = await page.context().newCDPSession(page);
    const current = (await list.boundingBox())!;
    const y = current.y + current.height / 2;
    const x = current.x + current.width * 0.85;
    const beforeSwipe = await list.evaluate((element) => element.scrollLeft);
    try {
      await touch.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y }] });
      for (let step = 1; step <= 8; step++) {
        await touch.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x: x - step * 20, y }] });
      }
      await touch.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
      await expect.poll(() => list.evaluate((element) => element.scrollLeft)).toBeGreaterThan(beforeSwipe);
    } finally {
      await touch.detach();
    }
  }
  expect(await page.locator("html").evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
});

test("shows cited sources in a card on hover and lights up the text they cover", async ({ page, isMobile }) => {
  const sources = Array.from({ length: 4 }, (_, index) => ({
    title: `Official source ${index + 1}`, url: `https://www.wlu.ca/source-${index + 1}`, snippet: `Preview of source ${index + 1}`,
  }));
  const stream = [
    { type: "sources", sources },
    { type: "text", text: "Opened in 1999." },
    { type: "citation", source_nums: [1, 2, 3, 4], urls: sources.map((source) => source.url) },
    { type: "text", text: " Later." },
    { type: "citation", source_nums: [2], urls: [sources[1]!.url] },
    { type: "ok" },
  ];
  await page.route("**/api/v1/chat/conversations", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/chat/stream", (route) => route.fulfill({
    contentType: "application/x-ndjson",
    headers: { "X-Conversation-Id": CONVERSATION },
    body: stream.map((event) => JSON.stringify(event)).join("\n") + "\n",
  }));
  await page.goto("/");
  await page.getByLabel(/ask about laurier/i).fill("When did it open?");
  await page.keyboard.press("Enter");
  await expect(page.getByText("Answer ready.")).toBeAttached();

  const answer = page.getByRole("article", { name: /goldenguide answer/i });
  const chip = answer.getByRole("button", { name: /Official source 1/ });
  // Phones cannot hover: a tap opens the same card.
  if (isMobile) await chip.tap();
  else await chip.hover();
  const card = page.getByRole("list", { name: "Cited sources" });
  await expect(card).toBeVisible();
  await expect(card.getByRole("link").first()).toHaveAttribute("href", sources[0]!.url);

  // The card shows about two sources and scrolls the rest, so it never covers the answer.
  const { visible, total } = await card.evaluate((element) => ({ visible: element.clientHeight, total: element.scrollHeight }));
  expect(total).toBeGreaterThan(visible);
  expect(visible).toBeLessThan(240);

  // The chip alone highlights nothing; hovering a source in its card highlights only the text it covers.
  await expect(answer.locator("[data-highlighted]")).toHaveCount(0);
  await card.getByRole("link").first().hover();
  await expect(answer.locator("span[data-highlighted]", { hasText: "Opened in 1999." })).toBeVisible();
  await expect(answer.locator("span[data-highlighted]", { hasText: "Later." })).toHaveCount(0);

  if (!isMobile) {
    await card.getByRole("link").first().hover();
    await expect(card).toBeVisible();
    await page.mouse.move(0, 0);
    await expect(card).toBeHidden();
  }
});
