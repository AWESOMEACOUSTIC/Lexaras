# Lexaras — Bug Analysis

This document expands on the five issues you flagged, explaining *why* each one is happening at a conceptual level before any code changes are made. The goal is to separate symptom from root cause, because a couple of these look like isolated bugs but actually share the same underlying weakness in the pipeline.

---

## Bug 1 — Semantic Scholar papers aren't getting extracted

**Symptom:** Papers discovered via the academic source come back empty, insufficient, or missing from the final report.

**Root cause: the extraction node was never designed to read Semantic Scholar's landing pages.**

Here's the mechanical chain of events:

1. `academic_search` queries Semantic Scholar and gets back a rich object per paper — title, abstract, year, venue, citation count, and (when it exists) a direct `openAccessPdf` link to the actual full-text PDF.
2. The discovery agent takes that result and writes a `PaperMeta` entry with a single `url` field. In practice, the URL that ends up there is the `semanticscholar.org/paper/...` **landing page**, not the open-access PDF link — because the discovery agent's job is just to pick a URL from what it sees, and it has no strong instruction to prefer the PDF field over the landing page.
3. The extraction node hands that URL to `scrape_url`, which does a plain HTTP GET and runs BeautifulSoup over the response.

The problem is that `semanticscholar.org` paper pages are a **JavaScript-rendered single-page application**. The HTML that `requests` actually receives on a GET request is mostly an empty shell — a `<div id="root">` that gets populated client-side by React after the page loads. There is no headless browser or JS execution step anywhere in `scrape_url` or `extract_pdf`, both of which assume the content is present in the raw HTML response. So the "extracted" content for these pages is either near-empty or just boilerplate (nav labels, cookie banners, footer text) — which is exactly what `_clean_html`'s `<article>`/`<main>`/`<body>` fallback logic scoops up when there's no real article content to find.

That empty-or-boilerplate text then fails (or barely passes) the quality gate in `extraction.py`:

```python
if "[INSUFFICIENT_CONTENT]" in summary or len(summary) < 100:
    ...
    continue
```

So the paper is silently dropped, or worse, kept with a summary built almost entirely by the LLM inferring from the earlier discovery-stage abstract/snippet rather than the actual page — which is a subtle form of the "no fabrication" rule being violated by omission.

**Why this matters conceptually:** the extraction layer has exactly one strategy — "fetch HTML, strip tags, read what's left." That strategy works for traditional server-rendered pages (blogs, arXiv abstract pages, most journal sites) but fails categorically for JS-rendered SPAs. Semantic Scholar's own site is one of those, which means the *one* source we added specifically to fix academic sourcing is structurally the hardest one for the existing extraction tool to read. The fix has to happen at the data-flow level (making the PDF link the primary target, since PDFs are already handled correctly by `extract_pdf`) rather than by tuning prompts.

---

## Bug 2 — Web-sourced papers are often irrelevant, because content isn't being extracted properly

**Symptom:** Some of the "papers" that make it into the report don't actually feel relevant to the topic — because what got extracted from them wasn't the paper's content at all.

**Root cause: the extraction pipeline has no way to tell the difference between "got the article" and "got something else that happens to be 100+ characters long."**

The quality gate that decides whether a scraped page is usable is purely a length check:

```python
if "[INSUFFICIENT_CONTENT]" in summary or len(summary) < 100:
```

This check only catches the *explicit* failure case the extraction agent is told to self-report. It does nothing to catch the much more common *silent* failure case, where `scrape_url` technically succeeds (HTTP 200, some text extracted) but what it extracted isn't the paper at all:

- **Paywalls that don't 404.** Many journal sites (Elsevier, Springer, IEEE) return a 200 status with a page that's mostly "Sign in to read this article" plus an abstract teaser. That's well over 100 characters, so it sails through the gate — but the LLM is now writing key findings based on a paywall notice, not the paper.
- **Cookie-consent and GDPR walls.** Some publishers serve a consent interstitial as the actual page body until a cookie is accepted. `_clean_html`'s fallback to `soup.body` will happily grab that.
- **JS-rendered pages, same issue as Bug 1, but for ordinary web results too.** Not every irrelevant result is Semantic Scholar — some Tavily/web_search hits are themselves JS-heavy blog platforms or news sites with paginated/lazy-loaded content that `requests` never sees.
- **Redirect drift.** `_fetch_with_retry` follows redirects (`allow_redirects=True`) without checking whether the *final* URL still matches the paper — a dead link can 302 to a publisher's generic homepage, which then gets scraped and summarized as if it were the paper.

Once one of these happens, the extraction agent still has to produce *something* in the required JSON shape — a `content_summary`, `key_points`, a `relevance_to_topic` — even if the underlying material was actually a paywall notice or a homepage. The agent isn't fabricating maliciously; it's doing its best with garbage input, which is the textbook "garbage in, garbage out" pattern. Downstream, the writer synthesizes across these contexts with no way of knowing that context #4 wasn't real, and it lands in the final report as if it were a genuine finding — which is exactly the "irrelevant paper" experience you're seeing.

**Why this matters conceptually:** relevance filtering is currently happening once, at discovery time, based on a title + snippet. There's no relevance *re-check* after extraction, when the system actually has the full scraped text and could verify the content plausibly matches the topic and genuinely resembles paper content rather than an access wall. Right now the pipeline trusts that "the fetch succeeded" is equivalent to "the content is usable," and those are not the same thing.

---

## Bug 3 — Raw CSS is visible in the UI instead of being applied as styling

**Symptom:** In some sections, you can see literal CSS text rendered on the page rather than the styled result.

**Root cause: this is almost always one of two Streamlit-specific failure modes — either the CSS never reached a proper `<style>` context, or a markdown/HTML string got escaped or malformed before Streamlit could render it as HTML.**

A few concrete ways this happens in this codebase specifically:

1. **`unsafe_allow_html=True` missing on a call.** Streamlit's `st.markdown()` treats its input as plain Markdown text by default — HTML tags (including `<style>` blocks or inline `style="..."` attributes) are only rendered as real markup when `unsafe_allow_html=True` is explicitly passed. Every custom-styled block in this app (`components.py`, `tabs.py`, `app.py`) relies on this flag being present on *every single* `st.markdown()` call that contains HTML. It only takes one call — during a refactor, a copy-paste, or a new tab being added — to drop that flag, and the entire HTML string (styles included) gets printed to the page as literal text instead of being interpreted.

2. **Malformed HTML breaking the parser's expectations.** Several of the custom components build HTML via f-strings with values interpolated directly from pipeline output — paper titles, relevance notes, report text. If any of that interpolated text contains an unescaped `<`, `>`, `"`, or a stray closing tag, it can prematurely close a `<div>` or `<style>` block. The browser then treats whatever comes after as plain text rather than markup — which is exactly the "I can see the CSS itself" symptom, since a broken tag boundary means the CSS meant to be *inside* a tag attribute or `<style>` block spills out as visible text.

3. **CSS load order / scope issues.** `load_styles()` injects the entire `styles.css` file as one big `<style>` block at the top of the app via `st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)`. If this call fails silently (e.g., the file path resolution breaks when the app is run from a different working directory, which the `styles.py` loader is somewhat fragile to) or executes *after* other components have already rendered, then those earlier components render entirely unstyled — which can look like "raw CSS" if a developer or component elsewhere additionally writes CSS class names or style strings into visible text rather than into a `style="..."` attribute.

**Why this matters conceptually:** this class of bug is invisible in code review because the Python is syntactically fine — `st.markdown(f"<div class='foo'>{text}</div>", unsafe_allow_html=True)` looks correct. The failure only appears when the *interpolated* content (which comes from an LLM, not a developer) contains characters that break the surrounding HTML structure, or when one call among dozens is missing a flag. It's a systemic risk of building UI by hand-assembling HTML strings with unsanitized dynamic content, rather than a single one-line typo.

---

## Bug 4 — Layout feels cluttered; insufficient spacing between the left and right panels

**Symptom:** The two-column layout (`left, right = st.columns([5, 8], gap="large")`) doesn't feel like it has enough breathing room; the overall page reads as visually dense.

**Root cause: spacing in the current UI is applied ad hoc, component by component, rather than from a single consistent spacing system — so there's no shared "gutter" between the panels beyond Streamlit's own default, and every component adds its own arbitrary margin.**

A few compounding factors:

1. **Streamlit's `gap="large"` on `st.columns` only controls the gap *between* columns at the layout level — it does not add any padding *inside* each column.** So the left panel's content (topic input, stage cards, metrics) sits flush against the column boundary, and the right panel's content (tabs, report body) does too. The visual "breathing room" people expect between two panels is usually a combination of an outer gutter *and* inner padding on each side — here there's only the former.

2. **Every component defines its own spacing independently**, using inline styles like `margin-bottom:0.55rem`, `padding: 0.9rem 1.1rem`, `<div style='height:0.4rem'></div>` spacer hacks, and hard-coded `1.5rem` / `1.2rem` values scattered across `styles.css`, `app.py`, and `tabs.py`. None of these numbers derive from a shared scale (e.g., a spacing system of 4/8/16/24/32px multiples) — they were each chosen locally to look "about right" for that one component. The cumulative effect across a full page render is inconsistent rhythm: some sections have generous padding, others are tight, and the eye reads the page as cluttered even though no individual component is technically broken.

3. **The block-container padding is fixed and doesn't respond to content density.** `[data-testid="block-container"] { padding: 2rem 3.5rem 5rem 3.5rem; max-width: 1200px; }` gives one static padding value regardless of how much is being rendered inside — a report with a long list of papers, key findings, and citations has no additional vertical rhythm (e.g., increased spacing before/after major section breaks) to help the eye segment it, so dense report content reads as one long, tightly-packed block.

4. **Column ratio vs. actual content weight.** The `[5, 8]` ratio was presumably chosen to give the report more horizontal room, but the left column's content (radio buttons, an expander, four stage cards, five metric pills) is not light content — it's often *just as dense* as the report side, just narrower. Narrow + dense reads as cramped even with generous vertical spacing, because there's no room for the text inside those cards to breathe horizontally.

**Why this matters conceptually:** this isn't a single misplaced CSS rule; it's the absence of a **spacing system** — one place that defines the small set of spacing values the whole app is allowed to use, so gaps between sections, inside cards, and between columns all feel intentional and consistent rather than independently guessed. A real fix touches the whole visual language, not just the two-column gap value.

---

## Bug 5 — The writer's academic tone is weak, which drags down the evaluation score

**Symptom:** The writer agent does synthesize the full report — it's not missing content — but it doesn't read like a rigorous academic piece, and the evaluator scores it lower as a result (particularly on synthesis quality, and now recency).

**Root cause: the writer is running on the "creative" LLM configuration, and its prompt describes *structure* thoroughly but says very little about *register* — the actual sentence-level voice expected of academic writing.**

Two separate issues stack here:

1. **Model configuration mismatch.** `writer.py` builds its chain from `creative_llm`, which is instantiated with `temperature=0.5` — noticeably higher than the `temperature=0.2` used for `llm` (used by discovery and the evaluator). Temperature controls how much the model is encouraged to pick lower-probability, more "creative" word choices rather than the most standard, expected phrasing. For an academic research report, higher temperature works *against* the goal: it increases the odds of looser transitions, more narrative flourishes, and less consistent terminology across sections — traits that read as engaging in creative writing, but as imprecise or informal in an academic context.

2. **The prompt defines structure, not voice.** The `_WRITER_SYSTEM` prompt is detailed about *what sections to produce* (Introduction, Key Findings, Synthesis, Limitations, Sources) and about *citation mechanics* (inline `[Title, URL]` format), and it does say "tone: authoritative, objective, analytical" — but that's one line among many, and it's a description rather than a set of concrete constraints. There's nothing in the prompt that:
   - Specifies register markers explicitly (e.g., no first person, no contractions, no rhetorical questions, minimal adverbial hedging beyond genuinely uncertain claims).
   - Gives a calibration example of the sentence-level voice expected — "this sentence is the target register, this one isn't."
   - Distinguishes between *narrative flow* (which is good — the doc correctly asks for synthesis over listing) and *narrative tone* (which is not what's wanted here — academic synthesis should still read as measured and precise, not as a magazine feature).

Without either of those constraints, a moderately-high-temperature model defaults to whatever voice is statistically comfortable for "explain research findings to a mixed audience" — which tends to land closer to popular-science writing (engaging framing, exclamation-adjacent enthusiasm about findings, softer transitions) than to the terser, more hedge-precise, more formally structured register of an actual academic or consulting report.

3. **Knock-on effect on scoring.** The evaluator's `synthesis_score` dimension explicitly rewards "insightful connections" over "merely summarizing," but a report with a more casual voice often *reads* as less rigorous even when the underlying synthesis logic is sound — tone and substance aren't perfectly separable to a language-model judge any more than they are to a human reader. And with the new `recency_score` dimension added, a report that doesn't explicitly and precisely flag "the most recent evidence on X dates to only 2021" in a formal, unambiguous way will also lose points there — a softer, more narrative style tends to bury exactly that kind of precise caveat inside looser sentences, rather than stating it as a clear, checkable claim.

**Why this matters conceptually:** this bug is not "the writer is bad at its job" — it's that the writer was configured and prompted for *engaging synthesis*, and is now being graded against a *rigorous academic* rubric it was never precisely instructed to target. The fix is about aligning the model's temperature and the prompt's explicit stylistic constraints with the register the evaluator is actually scoring against, rather than assuming "authoritative, objective, analytical" as three adjectives is enough to reliably shift voice.

---

## Summary

| # | Bug | Core issue |
|---|-----|-------------|
| 1 | Semantic Scholar papers not extracted | Extraction only handles static HTML/PDF; SPA landing pages return empty content, and the PDF link Semantic Scholar provides isn't being prioritized |
| 2 | Web papers extracted are irrelevant | No content-quality check beyond character count; paywalls, consent walls, and redirect drift all pass the gate as "successful" extractions |
| 3 | Raw CSS visible in UI | Missing `unsafe_allow_html=True` on some calls, or dynamic LLM-sourced text breaking HTML tag boundaries mid-render |
| 4 | Cluttered layout / insufficient spacing | No shared spacing system — margins and padding are set ad hoc per component rather than from consistent scale |
| 5 | Weak academic tone hurting scores | Writer runs on higher-temperature "creative" model with a prompt that specifies structure but not concrete register/voice constraints |

Two threads run through all five: **(1)** the extraction layer assumes "fetch succeeded" means "content is usable," which is the shared root of bugs 1 and 2, and **(2)** the UI and writer both suffer from *implicit* rules (styling conventions, tone expectations) that were never made explicit or systematic enough to survive contact with real, messy inputs — which is the shared root of bugs 3, 4, and 5.