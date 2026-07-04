Right now the papers are searched dynamically, but most of the dedicated journals/conference papers are being indexed under google scholars. So if the research engine searches 10 paper then 5 out of 10 papers must be from google scholar and the rest can be from anywhere (This will be the default mode). We can add one more mode where search from google scholar only mode where all papers will be from google scholar only. And the search should be in latest descending order  of papers meaning it will search the papers from present year and then keeps on decrementing up to last 5 years.
---

## The Core Problem With This Idea As Stated

Google Scholar does not have a public API.

This is the single most important thing to understand before architecting this feature. Unlike Tavily, PubMed, Semantic Scholar, or arXiv — which all have documented, stable, free-to-use APIs — Google Scholar is a web interface that Google has deliberately kept closed. They have explicitly prohibited scraping in their Terms of Service, and they actively block it with CAPTCHAs, IP bans, and rate limiting. Any library you find online that claims to "scrape Google Scholar" — SerpApi's Scholar endpoint, scholarly, scrapy-based tools — is either a paid third-party service that screen-scrapes and handles the CAPTCHA solving on their servers, or an open-source library that works intermittently and breaks whenever Google changes its HTML structure, which happens frequently.

So the feature is absolutely the right direction. The implementation path needs to be chosen carefully.

---

## The Three Realistic Implementation Options

**Option A — SerpApi Google Scholar Endpoint (Recommended)**

SerpApi is a paid service that acts as a stable, structured API layer over Google Scholar. You send a search query with parameters, they return clean JSON with title, authors, year, citation count, PDF link when available, and abstract snippet. It handles CAPTCHAs, respects rate limits, and has been stable for years. The free tier gives you 100 searches per month, which is enough to develop and test the feature extensively. The paid tier starts at around $50/month.

This is the right choice for a production system going to a real client. You get structured data, a stable contract, no scraping maintenance burden, and the ability to filter by year natively in the API parameters.

**Option B — Semantic Scholar API (Free, Academic-Grade)**

Semantic Scholar is a free academic search engine built by the Allen Institute for AI. It indexes over 200 million papers, including most of what is on Google Scholar, with full structured metadata — authors, year, citation count, fields of study, open-access PDF links, and even AI-generated paper summaries. The API is completely free, requires only an API key registration, and explicitly allows programmatic access. The year filtering and descending sort by year are native API parameters. The coverage of CS, medicine, biology, and most STEM fields is comparable to Google Scholar.

For most research topics, Semantic Scholar will find the same papers Google Scholar would, often with better structured metadata. The gap is in humanities, law, and social sciences, where Google Scholar's broader web indexing gives it an edge.

**Option C — `scholarly` Python Library (Free, Fragile)**

The `scholarly` library scrapes Google Scholar directly. It works in development but is genuinely unreliable in production — Google blocks it intermittently, it requires proxy rotation to stay alive at any real usage volume, and it has no guaranteed structure for the returned data. I would not recommend this for a client-facing product.

---

## My Honest Recommendation

Use **Semantic Scholar as the primary academic source** and keep **Tavily as the supplementary web source**. Do not try to scrape Google Scholar directly.

The revised architecture for the "5 out of 10 from academic sources" rule becomes: 5 results from Semantic Scholar (peer-reviewed, structured, year-filtered), 5 results from Tavily (web-wide, fills gaps with blogs, preprints, news, grey literature). This is actually a *better* split than "5 from Google Scholar, 5 from anywhere" because Semantic Scholar gives you richer metadata (citation count, open-access PDF direct links, paper abstracts) than Google Scholar's scraped output would.

For the "Google Scholar only" mode, if the client specifically requires Google Scholar, use SerpApi. If they are flexible, Semantic Scholar gives the same academic quality at zero API cost.

---

## The Year-Descending Search Logic

This part of your idea is well-designed and straightforward to implement. Here is how it should work architecturally.

The discovery agent currently generates queries and fires a single search. With temporal ordering, it would instead generate a year-windowed search strategy. Starting from the current year and stepping back one year at a time to a floor of 5 years ago, it fires searches with year constraints until it has collected enough high-quality papers. The stopping condition is either reaching the paper quota or reaching the 5-year floor — whichever comes first.

```
Current year: 2026
Window 1: 2026       → search, collect results
Window 2: 2025       → search, collect results  
Window 3: 2024       → search, collect results
...continue until quota met or floor reached (2021)
```

This is better than a single search with a 5-year range because it guarantees the *most recent* papers are found first and given priority in the report, rather than a mix where a highly-cited 2021 paper might crowd out a more recent 2025 one.

The Semantic Scholar API supports this natively with `year` filter parameters. SerpApi's Scholar endpoint supports it with `as_ylo` (year low) and `as_yhi` (year high) parameters — the same parameters Google Scholar uses in its URL.

---

## What the New Tool Architecture Looks Like

You would add a new tool — `academic_search` — alongside the existing `web_search`. The discovery agent's tool registry would have both. The mode selection (default vs. Scholar-only) would be a parameter passed through `AgentState` that the discovery node reads to decide which tools to call and in what ratio.

```python
# In AgentState — new fields
"search_mode": Literal["default", "scholar_only"]
"year_from": int      # current_year - 5
"year_to": int        # current_year
"academic_quota": int # how many results must come from academic sources (default: 5)
```

The discovery node reads `state["search_mode"]` and branches: in `"default"` mode it calls `academic_search` for 5 results and `web_search` for 5 results; in `"scholar_only"` mode it calls only `academic_search` with a quota of 10, cycling through year windows.

This fits cleanly into the existing LangGraph architecture — you are adding a conditional branch inside the discovery node, not restructuring the graph. The rest of the pipeline (extraction, writing, evaluation) is completely unaffected because it only sees `discovered_papers` in state, regardless of where those papers came from.

---

## One Thing to Add to the Year Logic

The year-descending approach should also carry the publication year into `PaperMeta` as a field — it is currently not stored. The writer agent should then be prompted to prioritise recent findings and flag when it is citing older work. The evaluator should score "recency" as a new dimension alongside relevance, coverage, synthesis, and citation integrity. A report built primarily on 2021 papers when 2025 papers exist on the same topic should score lower on recency than one that found the 2025 work.

