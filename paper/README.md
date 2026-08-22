
# Paper source

This directory contains the current 11-page A4 IEEE LaTeX source: 10 pages of paper content and one references page. Compile with a standard TeX Live installation:

```bash
cd paper
latexmk -pdf main.tex
```

The compiled PDF is not committed because PDF creation and modification timestamps vary by build. The public companion artifact is available at <https://github.com/YgcCoder/RouteBR>.
