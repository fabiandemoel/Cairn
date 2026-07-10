---
applyTo: "pages/**,sources/**,components/**"
excludeAgent: "cloud-agent"
---

# Evidence.dev layer review

- SQL in Evidence pages must only select, rename, filter, and join. Flag aggregations or calculations that produce figures not present in the pinned source data, unless clearly labeled as Cairn-derived.
- Every chart or table displaying source figures must reference its provenance (source name and manifest entry). Flag visualizations with no traceable source.
- Column relabels must preserve meaning: flag renames where the new label could misrepresent what the official source measures (e.g. "emissions" for a value that is "allocated allowances").
- Check that number formatting does not silently change precision or units from the source.
- Custom Svelte components should not fetch external data at runtime; all data flows through the pinned sources.
