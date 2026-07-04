
## The Core Insight First

Right now Lexaras is **topic-centric** — give it a subject, get a report. The shift you are describing is making it **problem-centric** — give it a *human situation*, get an *actionable answer backed by research*. That is a fundamentally different product. Here is how you expand into that space.

---

## Tier 1 — High Impact, Directly Buildable Now

**Guided Research Modes**

Instead of a blank topic box, give users a mode selector. "Explain this to me simply" triggers a different writer prompt that avoids jargon. "I need to make a decision about X" triggers a pros/cons extraction frame. "I am writing a paper on X" keeps the current academic mode. "I am a practitioner dealing with X" extracts clinical or applied findings, not theoretical ones. Same four agents underneath — the only thing that changes is the system prompt given to the writer. This single feature makes Lexaras useful to a doctor researching a treatment, a student writing a literature review, and a product manager researching market trends — all from the same engine.

**Claim Verification Mode**

A user pastes a claim — "Studies show intermittent fasting reduces cancer risk" — and Lexaras searches for papers that support it, papers that contradict it, and papers that are neutral, then writes a verdict with a confidence score. This is the fact-checking use case. The discovery agent gets a modified prompt that searches for both confirming and disconfirming evidence. The writer agent is prompted to write in the structure: Claim → Supporting Evidence → Counter Evidence → Verdict. The evaluator scores how well-balanced the search was.

**Follow-up Question Engine**

After a report is generated, the user can ask follow-up questions — "What did the 2022 paper say about dosage?" or "Which of these findings apply only to children?" — and the system answers using only the already-extracted contexts, without re-running the full pipeline. This is a retrieval-augmented Q&A layer on top of the existing extraction. The extracted contexts are stored in session state; the follow-up goes to a lightweight chain that retrieves the relevant context and answers. This feels like talking to a research assistant who has already read everything.

**Comparative Research**

"Compare CRISPR-Cas9 vs base editing for sickle cell disease." The discovery agent runs two parallel searches — one for each concept — and the writer agent is explicitly prompted to produce a structured comparison: methodology differences, efficacy comparisons, risk profiles, cost considerations, current research maturity. This addresses the very common human problem of "I need to choose between two approaches and do not know enough about either."

**Research Gap Finder**

After reading N papers on a topic, the evaluator agent gets an additional prompt: "Based on the papers you read, what questions are being actively debated? What sub-topics appear underexplored? What methodological limitations appear repeatedly?" This outputs a "gaps and open questions" section at the end of every report. For researchers and PhD students, this is one of the most valuable outputs possible — it tells them where original contribution is possible.

---

## Tier 2 — Deeper Product Features

**Longitudinal Research Tracking**

Store past research runs (topic, discovered papers, report, evaluation score) in a lightweight SQLite database or even a JSON file per session. Let users return to a topic a week later and run "Update my research on X" — the system searches for papers published after the last run's date, extracts only new content, and writes a "What changed since your last report" delta update. This addresses the real problem of researchers who need to stay current on a fast-moving field without re-reading everything.

**Source Credibility Scoring**

Not all sources are equal. A Wikipedia article, an arXiv preprint, a peer-reviewed Nature paper, and a blog post are fundamentally different levels of evidence. The discovery agent can be extended to tag each source with a credibility tier based on its domain and publication type. The writer agent is then prompted to weight findings by tier — claims from peer-reviewed journals carry more weight than preprints, which carry more weight than editorial pieces. The evaluator scores this dimension explicitly. This addresses the problem of users not knowing how much to trust the report.

**Multi-language Research**

Tavily can surface papers and sources in non-English languages. An additional translation step — using the same Mistral model — can translate non-English abstracts and key findings before passing them to the writer. This matters enormously for topics where the primary research is published in Mandarin, German, Japanese, or French. The user writes their query in English and gets a report that synthesises global research, not just anglophone research.

**Structured Output Formats**

Beyond Markdown, the writer agent can produce: a structured literature review in IEEE or APA citation format (for academics), an executive briefing in three bullet points per finding (for executives), a patient-facing summary in plain language (for healthcare), or a SWOT analysis frame (for business research). These are all prompt-engineering changes to the writer node with different output schemas.

**Interactive Report Editor**

After the report is generated, the user can click on any finding and say "expand this", "find more evidence for this", or "I disagree — search for counter-evidence on this point." Each action triggers a targeted mini-search using the extraction tools, and the specific section of the report is updated in place. This turns the report from a static output into a living document.

---

## Tier 3 — Architectural Expansions

**Domain Specialisation Agents**

Different research domains need fundamentally different extraction logic. A medical research topic needs the extraction agent to identify: study design (RCT, cohort, meta-analysis), sample size, effect size, p-values, and clinical significance. A legal research topic needs: jurisdiction, case citations, statute references, and majority vs. dissenting opinion. A financial research topic needs: time period, data sources, market conditions, and forward-looking statements. You would add a "domain classifier" node early in the graph that detects the topic's domain and selects the appropriate extraction prompt. The LangGraph conditional edge pattern makes this trivial to add without touching existing nodes.

**Citation Graph Builder**

When the extraction agent pulls cited works from each paper, those citations are currently stored in `AgentState` but not acted upon. A citation graph node could take those cited works, search for them, and add the most-cited ones to the extraction queue — going one level deeper into the literature. This is how a human researcher actually works: they read one good paper, find its references, read those, find their references. Two levels of citation traversal would dramatically improve the depth of coverage on any topic.

**Confidence-gated Evaluation**

If the evaluator gives the report an overall score below 5, instead of delivering it to the user, the pipeline automatically triggers a second discovery pass with broader queries, re-extracts, re-writes, and re-evaluates. Only when the score crosses a threshold does the report get delivered. This means the quality floor of what a user receives is guaranteed — the pipeline self-improves until it meets the bar. The LangGraph retry loop pattern you already have makes this straightforward to implement.