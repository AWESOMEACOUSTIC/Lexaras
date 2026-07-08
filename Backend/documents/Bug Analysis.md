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

### Strategic production-level solution

The guiding principle: **never let a scrape be the only path to content when a structured API already handed you better data.** Semantic Scholar gives you an abstract and (often) a PDF link at discovery time — the extraction step should be built around using that, not around hoping a generic scraper can out-perform an API.

1. **Carry a richer payload out of discovery, not just a bare URL.** Extend `PaperMeta` to carry `pdf_url` (from `openAccessPdf`) and `abstract` (from the S2 API response) as first-class fields, separate from `url` (kept only for citation/display). This costs nothing extra — the data is already returned by `academic_search`; it's just being thrown away today when only `url` gets written into `PaperMeta`.

2. **Give the extraction node a tiered strategy per paper, ordered by reliability, not by convenience:**
   - **Tier 1 — Direct PDF.** If `pdf_url` is present, call `extract_pdf` on it directly. This is already the most robust path in the codebase (`pdfplumber` reads real text, no JS-rendering problem exists for a PDF).
   - **Tier 2 — Landing page scrape.** Only if no PDF link exists, fall back to `scrape_url` on the landing page — but only for domains known to be server-rendered (see the domain-reputation idea in Bug 2's solution below).
   - **Tier 3 — Structured abstract as guaranteed floor.** If both of the above fail or return insufficient content, the extraction node should not drop the paper — it should build a valid, clearly-labeled `content_summary` from the abstract and metadata already captured at discovery time, with an explicit `extraction_depth: "abstract_only"` flag carried into the context. This turns a hard failure into a graceful degradation: the paper still appears in the report, correctly cited, but the writer and evaluator both know to treat it as less deeply analyzed rather than either silently dropping it or quietly treating a thin summary as if it were full-text depth.

3. **Add DOI-based open-access resolution as a second-line fallback.** When a paper has a DOI but no `openAccessPdf` from Semantic Scholar directly, query the free Unpaywall API (`api.unpaywall.org`) with the DOI to check for an alternate open-access copy elsewhere (an institutional repository, a preprint server). This is a single additional free API call and meaningfully increases the odds of Tier 1 succeeding instead of falling through to Tier 3.

4. **Treat "known SPA domain" as a routing decision, not a runtime surprise.** Maintain a small, explicit registry (e.g., `JS_RENDERED_DOMAINS = {"semanticscholar.org", ...}`) that the extraction node checks before choosing a strategy — so a landing-page scrape is never even attempted against a domain known in advance to return an empty shell. This is cheap to maintain and immediately removes an entire class of wasted network calls and false "insufficient content" failures.

5. **Observability:** log which tier each paper's content actually came from (`extraction_depth`), and expose this per-paper in the Sources tab (e.g., a small "Full text" / "Abstract only" badge) — so degraded-but-honest extractions are visible to the end user rather than looking identical to a full-text read.

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

### Strategic production-level solution

The guiding principle: **a successful HTTP fetch is not the same claim as usable content, and the pipeline needs a real content-quality gate, not a character count.**

1. **Replace the length-only gate with a layered validity check**, cheapest checks first so obviously-bad pages are rejected before spending any extra LLM budget on them:
   - **Heuristic pattern gate (near-free, runs first):** scan the fetched text for high-signal paywall/consent phrases ("sign in to read", "subscribe to continue", "accept cookies", "verify you are human", "access denied") and reject immediately on match, before the extraction agent even summarizes it.
   - **Structural sanity gate:** check basic prose statistics — sentence count, average sentence length, ratio of unique words — against a plausible range for real article text. A cookie banner or nav-menu dump tends to fail this even when it clears 100 characters (short repeated phrases, low lexical diversity).
   - **Final LLM confidence gate:** require the extraction agent's own structured output to include an `extraction_confidence` field (0–1) reflecting *its own* judgment of whether the fetched text was genuinely the paper. Only accept the context into the pipeline above a set threshold (e.g., 0.6). This is cheap to add to the existing JSON schema and puts the agent's uncertainty to use instead of discarding it.

2. **Validate the final URL, not just the requested one.** After `_fetch_with_retry` follows redirects, compare `response.url` against the originally requested URL's domain/path pattern. A redirect to a bare homepage or a generic "article not found" path is a strong signal the real content was never reached — flag or reject rather than silently scraping whatever the homepage happens to contain.

3. **Introduce a domain-reputation cache** — a simple persisted mapping of domain → historical extraction success rate, updated after every run. Over time this lets discovery *deprioritize* domains that reliably fail extraction (paywalled publishers, JS-heavy blog platforms) in favor of domains that reliably succeed (arXiv, PubMed Central, open-access repositories) — turning a static, one-shot filtering decision into a system that gets better at sourcing extractable content the more it runs. This is a standard production pattern: feed operational outcomes back into upstream decisions rather than treating each pipeline stage as blind to what happens downstream.

4. **Prefer open-access-first sourcing at discovery time**, not just at extraction time — instruct discovery (and `academic_search`'s ranking) to favor results that already carry an open-access PDF link or come from domains on an allowlist (arXiv, PMC, DOAJ-indexed venues), since these are extraction-friendly by construction. This reduces the *rate* at which bug 2's failure mode is even encountered, rather than only getting better at detecting it after the fact.

5. **Make partial failure visible and actionable, not silent.** When a paper is rejected post-fetch, log the *specific* rejection reason (paywall pattern matched / structural gate failed / low confidence / redirect mismatch) rather than a single generic "insufficient content" bucket — this is what makes the domain-reputation feedback loop in point 3 possible, and it also gives the Debug tab something genuinely diagnostic to show instead of an opaque count.

---

## Bug 3 — Raw CSS is visible in the UI instead of being applied as styling

**Symptom:** In some sections, you can see literal CSS text rendered on the page rather than the styled result.

**Root cause: this is almost always one of two Streamlit-specific failure modes — either the CSS never reached a proper `<style>` context, or a markdown/HTML string got escaped or malformed before Streamlit could render it as HTML.**

A few concrete ways this happens in this codebase specifically:

1. **`unsafe_allow_html=True` missing on a call.** Streamlit's `st.markdown()` treats its input as plain Markdown text by default — HTML tags (including `<style>` blocks or inline `style="..."` attributes) are only rendered as real markup when `unsafe_allow_html=True` is explicitly passed. Every custom-styled block in this app (`components.py`, `tabs.py`, `app.py`) relies on this flag being present on *every single* `st.markdown()` call that contains HTML. It only takes one call — during a refactor, a copy-paste, or a new tab being added — to drop that flag, and the entire HTML string (styles included) gets printed to the page as literal text instead of being interpreted.

2. **Malformed HTML breaking the parser's expectations.** Several of the custom components build HTML via f-strings with values interpolated directly from pipeline output — paper titles, relevance notes, report text. If any of that interpolated text contains an unescaped `<`, `>`, `"`, or a stray closing tag, it can prematurely close a `<div>` or `<style>` block. The browser then treats whatever comes after as plain text rather than markup — which is exactly the "I can see the CSS itself" symptom, since a broken tag boundary means the CSS meant to be *inside* a tag attribute or `<style>` block spills out as visible text.

3. **CSS load order / scope issues.** `load_styles()` injects the entire `styles.css` file as one big `<style>` block at the top of the app via `st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)`. If this call fails silently (e.g., the file path resolution breaks when the app is run from a different working directory, which the `styles.py` loader is somewhat fragile to) or executes *after* other components have already rendered, then those earlier components render entirely unstyled — which can look like "raw CSS" if a developer or component elsewhere additionally writes CSS class names or style strings into visible text rather than into a `style="..."` attribute.

**Why this matters conceptually:** this class of bug is invisible in code review because the Python is syntactically fine — `st.markdown(f"<div class='foo'>{text}</div>", unsafe_allow_html=True)` looks correct. The failure only appears when the *interpolated* content (which comes from an LLM, not a developer) contains characters that break the surrounding HTML structure, or when one call among dozens is missing a flag. It's a systemic risk of building UI by hand-assembling HTML strings with unsanitized dynamic content, rather than a single one-line typo.

### Strategic production-level solution

The guiding principle: **it should be structurally impossible to forget the escape flag or to let dynamic content break markup — both need to be handled in one place, not re-remembered at every call site.**

1. **Funnel every custom HTML render through a single helper function**, e.g. `render_html(content: str) -> None`, that internally always sets `unsafe_allow_html=True`. No component (`app.py`, `components.py`, `tabs.py`) should call `st.markdown(..., unsafe_allow_html=True)` directly anymore — they call the helper instead. This makes the missing-flag failure mode structurally unreachable rather than something a future edit can accidentally reintroduce.

2. **Escape every piece of dynamic content before interpolation, as a hard rule.** Anything that originates from pipeline output — paper titles, relevance notes, LLM-generated report text, error messages — must pass through `html.escape()` (already used correctly in `controller.py`'s `md_to_html`, but not consistently applied elsewhere, e.g. `tabs.py`'s paper cards interpolate `p.get("title")` raw) before being placed inside an HTML string. Only the *structural* HTML written by the developer (the literal `<div class="...">` wrapper) should remain unescaped.

3. **Add a lightweight CI lint step** that statically scans for `st.markdown(` calls containing `<` in the string and fails the build if `unsafe_allow_html=True` isn't present in the same call — or, once step 1 is done, a lint rule that fails the build if *any* raw `st.markdown(..., unsafe_allow_html=True)` call exists outside the shared helper. This converts a runtime visual bug into a build-time failure.

4. **Sanitize rather than trust.** For any dynamic text that might legitimately contain HTML-like characters (a paper title with a `<` in it, e.g. "A < B: a comparative study"), use a proper sanitizer (e.g. the `bleach` library) rather than manual escaping, so the behavior is well-tested and handles edge cases (malformed entities, partial tags) that hand-rolled escaping tends to miss.

5. **Make `load_styles()` fail loudly, not silently.** Wrap the CSS file read in an explicit check that raises a clear error (rather than a bare `open()` that can fail unpredictably depending on working directory) and call it as the very first Streamlit operation in `app.py`, before any other rendering, so there's no ordering ambiguity about whether styles are active yet.

6. **Add visual regression testing to CI** (e.g., Playwright screenshot diffing against the running Streamlit app) so that a broken-markup regression is caught by an automated pixel/DOM diff before it reaches a user, rather than being discovered by eye.

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

### Strategic production-level solution

The guiding principle: **spacing should come from a small, named scale that every component references — never a locally-guessed rem value.**

1. **Define a spacing token scale as CSS custom properties**, e.g. `--space-xs: 4px; --space-sm: 8px; --space-md: 16px; --space-lg: 24px; --space-xl: 32px; --space-2xl: 48px;` at the root of `styles.css`. Every margin, padding, and gap value in every component (`.stage-card`, `.metric-pill`, `.paper-card`, `.report-body`, the inline spacer divs in `app.py`) is rewritten to reference one of these tokens instead of a bespoke number. This is the single highest-leverage change: it doesn't just fix column spacing, it makes every future component automatically consistent by construction.

2. **Give each column its own inner "panel" padding**, independent of the `st.columns(gap=...)` value — wrap the left and right column content in a container with consistent `padding: var(--space-lg)` on all sides, so there's breathing room both *between* the panels and *inside* each one, rather than relying on the outer gap alone to do all the work.

3. **Replace ad hoc `<div style='height:0.4rem'></div>` spacer hacks with token-based utility classes** (e.g. `.mt-md`, `.mb-lg`) applied consistently, so vertical rhythm is controlled the same way everywhere rather than through one-off empty divs scattered through `app.py`.

4. **Re-evaluate the column ratio against actual content weight, not just intended emphasis.** Since the left panel's controls (mode selector, expander, stage cards, five metric pills) are visually dense, consider either widening the left column's ratio slightly (e.g. `[5, 7]` instead of `[5, 8]`) or moving some of its content (the "Run Stats" metrics) into a header strip above both columns, so neither side is forced to compress dense content into a narrow space.

5. **Introduce a documented style guide as the source of truth** — a short internal reference (spacing scale, type scale, the three or four card/panel patterns used app-wide, color roles) that any future component change is checked against, the same way a design system would be maintained for a production consumer product. This prevents the slow drift back into ad hoc values after the first fix.

6. **Add visual regression testing** (same tooling as Bug 3's solution) so that spacing/layout regressions — not just broken markup — are caught automatically across common viewport widths before shipping, rather than being noticed after the fact as "this feels cluttered."

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

### Strategic production-level solution

The guiding principle: **tone is a controllable output like structure or citations — it needs its own explicit constraints, its own calibration examples, and ideally its own dedicated pass, not just a description folded into a longer prompt.**

1. **Give the writer its own dedicated model configuration, separate from `creative_llm`.** Introduce something like `academic_llm = _make_llm(temperature=0.2)` (matching the more deterministic setting already used for discovery/evaluation) specifically for the writer chain. Reserve `creative_llm`'s higher temperature for any future task that genuinely wants expressive variation — a research report is not that task.

2. **Add concrete positive and negative style examples to the prompt, not just adjectives.** A prompt engineering principle that generalizes well here: showing the model 2–3 sentences of the *target* register alongside 2–3 sentences of what to avoid teaches voice far more reliably than describing it abstractly. For example, contrasting a precise, hedge-appropriate academic sentence against a looser, narrative-toned rewrite of the same finding gives the model a concrete target to pattern-match against, rather than inferring "authoritative, objective, analytical" from three words.

3. **Add explicit, checkable register rules to the system prompt**, phrased as constraints rather than tone adjectives: no first-person pronouns, no contractions, no rhetorical questions, hedge only where evidence is genuinely uncertain (and say so precisely, e.g. "the most recent evidence on X dates to 2021" rather than "it seems X might still be true"). Concrete, checkable rules are easier for a language model to satisfy consistently than a mood description.

4. **Introduce a generate → critique → revise loop as a second pipeline stage**, rather than trusting single-shot generation. After the writer produces a draft, run a lightweight second pass (can reuse the evaluator's own rubric) that specifically scores register/tone adherence and returns targeted revision notes; the writer then produces a final version incorporating that feedback before the draft is handed to the full evaluator. This mirrors a standard production pattern for LLM-generated content that needs to hit a quality bar — draft, critique, revise — rather than hoping the first pass is good enough.

5. **Make the writer rubric-aware.** Feed the evaluator's actual scoring dimensions (relevance, coverage, synthesis, citation integrity, recency) directly into the writer's prompt as explicit goals, so the writer is optimizing toward the same criteria it will be graded against, rather than the writer and evaluator operating from two independently-authored descriptions of "good."

6. **Add automated tone-regression checks**, tracked over time like any other quality metric: simple heuristics such as hedge-word density, first-person pronoun count, contraction count, or an off-the-shelf formality/readability classifier, run against every generated report and logged. This turns "the tone feels off" from a subjective, occasional complaint into a measurable signal that can be monitored in production and caught before it silently drags down evaluation scores across many runs.

---

## Summary

| # | Bug | Core issue | Strategic fix, in one line |
|---|-----|-------------|------------------------------|
| 1 | Semantic Scholar papers not extracted | Extraction only handles static HTML/PDF; SPA landing pages return empty content, and the PDF link Semantic Scholar provides isn't being prioritized | Tiered extraction (PDF → landing page → guaranteed abstract fallback), routed by a known-domain registry |
| 2 | Web papers extracted are irrelevant | No content-quality check beyond character count; paywalls, consent walls, and redirect drift all pass the gate as "successful" extractions | Layered content-validity gate (pattern match → structural check → LLM confidence score) plus a domain-reputation feedback loop |
| 3 | Raw CSS visible in UI | Missing `unsafe_allow_html=True` on some calls, or dynamic LLM-sourced text breaking HTML tag boundaries mid-render | One shared render helper + mandatory escaping of dynamic content + CI lint/visual regression tests |
| 4 | Cluttered layout / insufficient spacing | No shared spacing system — margins and padding are set ad hoc per component rather than from consistent scale | A token-based spacing scale used everywhere, plus inner panel padding and a documented style guide |
| 5 | Weak academic tone hurting scores | Writer runs on higher-temperature "creative" model with a prompt that specifies structure but not concrete register/voice constraints | Dedicated low-temperature academic model + example-driven prompt + a draft → critique → revise pass |

Two threads run through all five: **(1)** the extraction layer assumes "fetch succeeded" means "content is usable," which is the shared root of bugs 1 and 2, and **(2)** the UI and writer both suffer from *implicit* rules (styling conventions, tone expectations) that were never made explicit or systematic enough to survive contact with real, messy inputs — which is the shared root of bugs 3, 4, and 5.

### What "production-level" means across all five fixes

The five solutions above share a small number of recurring production engineering habits, worth naming explicitly since they generalize beyond this specific bug list:

- **Graceful degradation over silent failure.** Bugs 1 and 2 both move from "drop it or fake it" to "clearly label the degraded case and keep it visible" (abstract-only extraction, rejection reasons, tone regression scores).
- **Push decisions upstream once you can measure downstream outcomes.** The domain-reputation cache (Bug 2) and open-access-first sourcing (Bug 1) both turn one-shot filtering into a feedback loop that improves with usage.
- **Make correctness structural, not a matter of remembering.** The shared `render_html` helper (Bug 3) and the design-token scale (Bug 4) both convert "don't forget to do X" into "it's no longer possible to do X wrong."
- **Separate concerns that were previously bundled into one step.** The generate → critique → revise split (Bug 5) and the tiered extraction strategy (Bug 1) both break a single all-or-nothing step into staged steps that can each be tuned and monitored independently.
- **Add automated regression coverage for things that used to only be caught by eye** — CI lint for markup safety, visual regression for layout, and tone-metric tracking for writing quality all turn "someone will notice eventually" into "the pipeline itself will catch it."