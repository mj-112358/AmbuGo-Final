# Research paper

[Read the current research paper](AmbuGo_Research_Paper.pdf)

**Congestion-Aware Joint Ambulance Routing and Selective Traffic Signal Priority:
A Reproducible Simulation Study** — 14 pages.

The PDF is the supplied revised manuscript, preserved byte for byte.

- SHA-256: `95cd780fbc388edbbab426a104bd42f10c8da8a42aa0e96b25ecaa660d27fec9`
- File size: 1,275,341 bytes.

## Supporting files

- [Episode_Reliability.csv](Episode_Reliability.csv): episode-level counts and
  exact binomial intervals, including the JSEL results in Table XI.
- [plot_results.py](plot_results.py): regenerates the nine condition-specific
  JSEL-minus-JFAST duration and spatial-exposure contrasts from
  `work/v9/sumo_analysis.json`.
- [Reproduction guide](../docs/reproduction.md): setup, analysis regeneration
  and simulation commands.

The experiments comprise 1,728 primary microscopic policy runs
(48 paired seeds × 3 loads × 3 mission doses × 4 policies), 264 secondary
microscopic runs and 14,400 corrected mesoscopic runs. Development runs are
listed separately in the paper.

## Archived authoring files

[archive/audited/](archive/audited/) retains the earlier audited draft's editable
DOCX, manuscript, references, audit notes, figures and document builder.
These files preserve the earlier wording and layout. The current revision was
provided as a PDF; its editable authoring source was not supplied.

The archived builder writes its outputs inside that archive directory. See the
[reproduction guide](../docs/reproduction.md#rebuild-the-archived-editable-draft)
for the command.
