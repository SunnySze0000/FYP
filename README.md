# EventLens — Final Year Project

This repository contains the team's LaTeX proposal for EventLens, an event-risk research platform for key indices and popular equities. It covers the proposed interface, AI-assisted workflow, data pipeline, research methods, implementation and project plan.

The initial asset universe is SPY, QQQ and DIA, plus AAPL, MSFT, NVDA, AMZN and TSLA. The report targets a maximum of **20 PDF pages**, including the cover, contents, references and meeting minutes.

## Start here

- [Report source](proposal/proposal.tex): main document, formatting and section order.
- [Section guide](proposal/README.md): find the file for each printed section and follow the editing conventions.
- [References](proposal/references.tex): bibliography entries used by the report.
- [UI image prompts](proposal/figures/image-prompts.md): provenance of the embedded interface concepts.

## Repository structure

```text
FYP/
├── README.md                 # Team entry point and collaboration workflow
├── .gitignore                # Generated output and local-file exclusions
├── .gitattributes            # Consistent text line endings and binary assets
└── proposal/
    ├── README.md             # Detailed section-to-file map
    ├── proposal.tex          # Compile this file
    ├── references.tex        # Manually maintained bibliography
    ├── sections/             # Cover and report content, split for collaboration
    └── figures/              # UI images and generation prompts
```

`proposal/proposal.pdf` is generated locally and ignored by Git. The `tmp/` folder, if present, contains local review material and is also ignored.

## Build the proposal

Use a TeX Live or MacTeX installation with `latexmk` and pdfLaTeX. From the repository root:

```sh
latexmk -pdf -interaction=nonstopmode -halt-on-error -cd proposal/proposal.tex
```

The result is `proposal/proposal.pdf`. `latexmk` runs the compilation passes needed to resolve the contents, citations and cross-references. If a package is missing, install it through your TeX distribution and rerun the command. The build needs no API keys, image-generation service or bibliography processor.

To remove auxiliary build files while retaining the PDF:

```sh
latexmk -c -cd proposal/proposal.tex
```

For Overleaf, upload the contents of `proposal/`, including `sections/` and `figures/`, and set `proposal.tex` as the main document with pdfLaTeX. Keep this repository as the shared source of record; bring any Overleaf edits back through a branch and pull request before others continue editing the same files.

## Work together

Agree on the section and reviewer before starting. Edit the relevant file in `proposal/sections/`; coordinate changes to the shared preamble, document order and bibliography. Named section owners remain for the team to agree.

Start a branch from an up-to-date `main` with a clean working tree:

```sh
git switch main
git pull --ff-only
git switch -c report/update-methodology
```

After editing, build the proposal and inspect the affected pages. Then stage only the intended source changes; for example:

```sh
git add proposal/sections/08-architecture.tex
git diff --cached --check
git diff --cached
git commit -m "Clarify the implementation approach"
git push -u origin report/update-methodology
```

These commands assume the team repository is configured as `origin`. Open a pull request into `main`, summarise the content changes, and state whether the PDF compiled and its layout was checked. Have another teammate review it before merging. Keep each pull request focused on a section or a related set of edits to reduce conflicts.

Commit `.tex` files, documentation and required figure assets. Generated PDFs, LaTeX auxiliary files, local review material and credentials should stay out of commits. Share a compiled PDF as a review attachment or release artifact when needed. Ignore rules do not remove files that Git already tracks.

## Before requesting review

- Confirm the required outline remains intact; see the [section guide](proposal/README.md).
- Build successfully and resolve undefined citations or references and text-overflow warnings.
- Inspect the PDF for readable figures, table wrapping, page breaks and a total of at most 20 pages.
- Keep the report formal and concise, with monochrome UI concepts and no callout or keywords blocks.
- Review `git diff --check` and `git status --short` for whitespace issues and unintended files.

Compilation and review are manual; this repository does not currently configure automated build checks.
