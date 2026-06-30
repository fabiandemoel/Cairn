-- Business glossary: one row per curated definition of a cross-cutting Cairn
-- concept (accounting principles, classifications, EU ETS terms, disclosure,
-- provenance), with its category, aliases, related models, and reference.
-- Source mart: mart_business_glossary (reads transform/glossary.yml).
select
    glossary_key,
    term,
    category,
    definition,
    aliases,
    related_models,
    reference_url
from mart_business_glossary
order by category, term
