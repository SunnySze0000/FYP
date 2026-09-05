# Proposal section guide

[Back to the repository guide](../README.md)

Compile [proposal.tex](proposal.tex), which contains the shared typography and assembles the section files with `\input`. The individual section files are not standalone documents. **Filename prefixes indicate source order, not the printed section number.**

## Where to edit

| Printed section | Source file | Content |
| --- | --- | --- |
| Cover and abstract | [00-summary.tex](sections/00-summary.tex) | Title, team details, supervisor, academic year and abstract |
| 1.1 Overview; 1.2 Objectives | [01-introduction.tex](sections/01-introduction.tex) | Motivation, research question, objectives and users; opens Section 1 |
| 1.2 Objectives, continued | [02-scope.tex](sections/02-scope.tex) | Initial asset universe, minimum viable product, extensions and exclusions |
| 1.3 Literature Survey | [03-related-work.tex](sections/03-related-work.tex) | Related work and research gap |
| 2.1 Design | [04-product.tex](sections/04-product.tex) | Product journey, UI features and concept images; opens Section 2 |
| 2.1 Design, continued | [05-agents.tex](sections/05-agents.tex) | AI agent roles, workflow integration and tool access |
| 2.1 Design, continued | [06-data.tex](sections/06-data.tex) | Data sources, acquisition, processing and provenance |
| 2.1 Design, continued | [07-methods.tex](sections/07-methods.tex) | Proposed probability, wallet, scenario and risk calculations |
| 2.2 Implementation | [08-architecture.tex](sections/08-architecture.tex) | Architecture and backend/frontend choices |
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

The UI concepts are embedded raster images in `04-product.tex`; keep them black and white, with readable labels at their printed size. Their fictional values are illustrative, not research results. Commit replacement images with the source and update their provenance when applicable. Workflow and architecture diagrams remain editable TikZ in their section files.

Use relative figure paths so a fresh clone or Overleaf upload can compile. Keep the report monochrome, without callout boxes or a keywords block. Do not reduce fonts or margins simply to fit extra content; shorten the text first.

## Build and check

From this `proposal/` directory:

```sh
latexmk -pdf -interaction=nonstopmode -halt-on-error proposal.tex
```

Open the generated `proposal.pdf` and inspect page count, contents, citations, figures, tables and page breaks. Resolve missing-reference and overflow warnings in `proposal.log`. PDF output and compilation intermediates are ignored; the source files and figure assets are committed. See the [repository guide](../README.md) for setup, Overleaf and the team branch workflow.
