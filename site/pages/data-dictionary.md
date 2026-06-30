---
title: Data dictionary & business glossary
description: Every model and column Cairn publishes, with the tests that guard it, plus a glossary of the cross-cutting concepts — generated from the dbt schema files and a reviewed glossary.
---

Two reference views, both **read-only over Cairn's own metadata** — they describe
the warehouse, they do not add to it:

- The **data dictionary** is generated from the dbt schema files
  (`_staging.yml`, `_marts.yml`, `_seeds.yml`): one row per documented model and
  column, with the description and the data tests that guard it.
- The **business glossary** is a reviewed file (`transform/glossary.yml`) of the
  cross-cutting concepts the marts lean on — accounting principles,
  classifications, EU ETS terms, disclosure datapoints, provenance.

```sql dictionary_summary
select
    count(*) as columns,
    count(distinct model_name) as models,
    count(*) filter (where is_tested) as tested_columns
from cairn.data_dictionary
```

```sql glossary_summary
select count(*) as terms from cairn.business_glossary
```

<div class="grid grid-cols-2 md:grid-cols-4 gap-4">

<BigValue data={dictionary_summary} value=models fmt='#,##0' title="Documented models & seeds" />
<BigValue data={dictionary_summary} value=columns fmt='#,##0' title="Documented columns" />
<BigValue data={dictionary_summary} value=tested_columns fmt='#,##0' title="Columns with data tests" />
<BigValue data={glossary_summary} value=terms fmt='#,##0' title="Glossary terms" />

</div>

## Data dictionary

Every published model and column, grouped by model. `layer` is the dbt layer the
resource lives in (`staging` → `mart` → `seed`); `data_tests` are the dbt tests
that fail the build if the column drifts. Use the search box to find a column or
a term inside a description.

```sql data_dictionary
select
    layer,
    model_name,
    column_name,
    column_description,
    data_tests,
    accepted_values
from cairn.data_dictionary
order by
    case layer when 'staging' then 0 when 'mart' then 1 when 'seed' then 2 else 9 end,
    model_name,
    column_name
```

<DataTable data={data_dictionary} search=true rows=20 groupBy=model_name groupsOpen=false rowShading={true}>
    <Column id=column_name title="Column" />
    <Column id=column_description title="Description" wrap={true} />
    <Column id=data_tests title="Tests" />
    <Column id=accepted_values title="Accepted values" wrap={true} />
    <Column id=layer title="Layer" />
</DataTable>

## Business glossary

The concepts behind the numbers. Filter by category, or search across terms and
definitions. Each term lists the models it appears in and an official reference
where one applies.

```sql categories
select category, count(*) as terms
from cairn.business_glossary
group by category
order by category
```

<Dropdown data={categories} name=category value=category title="Filter by category">
    <DropdownOption value="%" valueLabel="All categories" />
</Dropdown>

```sql business_glossary
select
    term,
    category,
    definition,
    aliases,
    related_models,
    reference_url
from cairn.business_glossary
where category like '${inputs.category.value}'
order by category, term
```

<DataTable data={business_glossary} search=true rows=all rowShading={true}>
    <Column id=term title="Term" />
    <Column id=category title="Category" />
    <Column id=definition title="Definition" wrap={true} />
    <Column id=related_models title="Appears in" wrap={true} />
    <Column id=reference_url title="Reference" contentType=link linkLabel="source" openInNewTab=true />
</DataTable>

<Alert status="info">

**This page is generated, not hand-kept.** The dictionary is materialised by
`mart_data_dictionary` straight from the dbt schema files, and the glossary by
`mart_business_glossary` from the reviewed `transform/glossary.yml`. A new column
or term shows up here once it is documented in those files — see
**[Methodology & sources →](/methodology)** for per-figure provenance and
**[Data quality →](/data-quality)** for source pin status.

</Alert>
