# Survey Paper Template

This directory contains the IEEE-style template used by the literature-review skill for survey and literature review manuscripts.

## Compiling LaTeX to PDF via Command Line

```bash
# Basic compilation
pdflatex main.tex

# With bibliography from the `.bib` file (full workflow)
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex

# Using latexmk (handles dependencies automatically)
latexmk -pdf main.tex

# Continuous compilation (watches for changes)
latexmk -pdf -pvc main.tex
```

## Troubleshooting Compilation

**"File not found" errors:**

```bash
# Ensure you're in the template directory
cd templates/IEEE_Conference_Template
pdflatex main.tex
```

**Bibliography not appearing:**

```bash
# Run bibtex after first pdflatex
pdflatex main.tex
bibtex main        # Uses main.aux to find citations
pdflatex main.tex  # Incorporates bibliography
pdflatex main.tex  # Resolves references
```

The template is configured to use `IEEE.bib` through BibTeX. Do not convert the template back to an inline `thebibliography` section.

**Missing packages:**

```bash
# TeX Live package manager
tlmgr install <package-name>

# Or install full distribution to avoid this
```

## Usage

```latex
\documentclass[conference]{IEEEtran}

\begin{document}
% Your survey paper content
\end{document}
```

Key files:

- `main.tex` - Example manuscript
- `IEEEtran.cls` - Style file
- `IEEE.bib` - Bibliography file

## Page Limits Summary

Use the page limit requested by the user or the target publisher. If no limit is specified, follow the default survey target in the skill instructions.

## Common Issues

### Compilation Errors

1. **Missing packages**: Install full TeX distribution (TeX Live Full or MikTeX)
2. **Bibliography errors**: Use the provided `.bib` file with `\bibliographystyle{}` and `\bibliography{}`
3. **Font warnings**: Install `cm-super` or use `\usepackage{lmodern}`

### Anonymization

For submission, ensure:
- No author names in `\author{}` for draft review copies
- No acknowledgments section in draft review copies
- No grant numbers in draft review copies
- Use anonymous repositories if you need a code link during review
- Cite own work in third person

### Common LaTeX Packages

```latex
% Recommended packages (check compatibility with the template)
\usepackage{amsmath,amsthm,amssymb}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{hyperref}
\usepackage{algorithm,algorithmic}
\usepackage{natbib}
```
