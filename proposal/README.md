# Proposal section guide

[Back to the repository guide](../README.md)

Read the [compiled proposal](proposal.pdf) directly, or edit and build the source below.

Compile [proposal.tex](proposal.tex), which contains the shared typography and assembles the section files with `\input`. The individual section files are not standalone documents. **Filename prefixes indicate source order, not the printed section number.**

## Where to edit

| Printed section | Source file | Content |
| --- | --- | --- |
| Cover and abstract | [00-summary.tex](sections/00-summary.tex) | Title, team details, supervisor, academic year and abstract |
| 1.1 Overview; 1.2 Objectives | [01-introduction.tex](sections/01-introduction.tex) | Motivation, research question, objectives and users; opens Section 1 |
| 1.2 Objectives, continued | [02-scope.tex](sections/02-scope.tex) | Initial asset universe, minimum viable product, extensions and exclusions |
| 1.3 Literature Survey | [03-related-work.tex](sections/03-related-work.tex) | Related work and research gap |
| 2.1 Design | [04-design-overview.tex](sections/04-design-overview.tex) | System overview, logical architecture and component responsibilities; opens Section 2 |
| 2.1 Design, continued | [05-data-design.tex](sections/05-data-design.tex) | Data sources, acquisition, logical data model and provenance |
| 2.1 Design, continued | [06-analytics.tex](sections/06-analytics.tex) | Probability, wallet, relevance, forecasting, scenario and backtest methods |
| 2.1 Design, continued | [07-delivery.tex](sections/07-delivery.tex) | Controlled assistant, user journey, evidence inspection and concept screens |
| 2.2 Implementation | [08-architecture.tex](sections/08-architecture.tex) | Three-page visual plan: endpoint contracts, physical schema, feature spaces, model candidates, scenarios, CrewAI/RAG/tools/memory and deployment |
| 2.3 Testing; 2.4 Evaluation | [09-evaluation.tex](sections/09-evaluation.tex) | Tests, baselines, evaluation measures, risks and acceptance criteria |
| 3.1 Division of Work; 3.2 GANTT Chart | [10-delivery.tex](sections/10-delivery.tex) | Work tracks, schedule and milestones; opens Section 3 |
| 4.1 Hardware Requirements; 4.2 Software Requirements | [11-resources.tex](sections/11-resources.tex) | Equipment, software and access constraints; opens Section 4 |
| 5. References | [references.tex](references.tex) | Bibliography; the Section 5 heading is emitted in `proposal.tex` |
| 6. Appendix A: Meeting Minutes | [12-meeting-minutes.tex](sections/12-meeting-minutes.tex) | Recorded meeting, discussion and outstanding confirmations |

## Required report outline

```text
1. Introduction
   1.1 Overview
   1.2 Objectives
   1.3 Literature Survey
2. Methodology
   2.1 Design
   2.2 Implementation
   2.3 Testing
   2.4 Evaluation
3. Project Planning
   3.1 Division of Work
   3.2 GANTT Chart
4. Hardware and Software Requirements
   4.1 Hardware Requirements
   4.2 Software Requirements
5. References
6. Appendix A: Meeting Minutes
```

The cover is unnumbered, the contents use Roman numbering, and Introduction starts at page 1. Contents page numbers are generated automatically. Keep the full PDF within **20 physical pages**, including front matter, references and the appendix.

## Editing conventions

Use the existing section files for content changes. Keep shared fonts, margins, spacing and heading styles in `proposal.tex`. Adding a source file also requires adding its `\input` there. Use `\subsubsection*{...}` for unnumbered topics inside the existing subsections when appropriate; coordinate changes to numbered headings so the required outline is preserved.

Write concise, formal prose and explain technical choices in terms of their purpose. Retain the initial scope of key indices and popular equities, and distinguish proposed work from completed results. Named ownership, provider access and official milestone dates remain subject to team confirmation. Record meeting outcomes only when they have actually been agreed.

### References

The bibliography uses `\bibitem{key}` entries in `references.tex` and `\cite{key}` in the section files. Reuse an existing key when citing the same source. There is no `.bib` file and no BibTeX or Biber step.

The bibliography is currently split across two pages using two `thebibliography` environments. The second starts with `\setcounter{enumiv}{11}`: if you change the number of entries in the first group, update that counter to match. Rebuild and check numbering and page breaks after adding references.

### Figures

- [overview-ui.png](figures/overview-ui.png): research dashboard concept.
- [scenario-ui.png](figures/scenario-ui.png): scenario-analysis concept.
- [image-prompts.md](figures/image-prompts.md): generation prompts and provenance.
- [logical-architecture.tex](figures/logical-architecture.tex): system layers with consistent box sizes and routed connectors.
- [logical-data-model.tex](figures/logical-data-model.tex): records grouped by domain, with relationship and dependency arrows distinguished.
- [research-journey.tex](figures/research-journey.tex): shared six-step user journey.
- [model-illustrations.tex](figures/model-illustrations.tex): PGFPlots illustrations of regression, clustering and scenario loss.
- [model_illustrations.py](figures/src/model_illustrations.py): reproducible synthetic data generator for [model-coordinates.tex](figures/model-coordinates.tex).

The UI concepts are embedded raster images in `07-delivery.tex`. Keep them black and white, with readable labels at their printed size. Their fictional values are illustrative, not research results. Commit replacement images with the source and update their provenance when applicable. Design diagrams live in the figure sources above. Scenario and assistant diagrams remain editable TikZ in `08-architecture.tex`.

Section 2.2 is limited to three pages including tables and figures. Its model settings, schemas and assistant tools are proposed implementation choices. The plotted data are synthetic and must never be described as backtest results. PGFPlots renders vector charts during the normal LaTeX build, with no shell escape or external plotting service. To regenerate the checked-in synthetic coordinates, run `python3 figures/src/model_illustrations.py` from this directory with NumPy available, then rebuild the PDF. Ordinary builds use the committed coordinates and do not require Python.

Use relative figure paths so a fresh clone or Overleaf upload can compile. Keep the report monochrome, without callout boxes or a keywords block. Do not reduce fonts or margins simply to fit extra content; shorten the text first.

## Build and check

From this `proposal/` directory:

```sh
latexmk -pdf -interaction=nonstopmode -halt-on-error proposal.tex
```

Open the generated `proposal.pdf` and inspect page count, contents, citations, figures, tables and page breaks. Resolve missing-reference and overflow warnings in `proposal.log`. Commit the rebuilt PDF alongside report source and figure changes in the same pull request; ensure it reflects the final source before merging. Compilation intermediates remain ignored. For PDF conflicts, resolve the source first and regenerate the PDF. Documentation-only changes do not require a rebuild. See the [repository guide](../README.md) for setup, Overleaf and the team branch workflow.
