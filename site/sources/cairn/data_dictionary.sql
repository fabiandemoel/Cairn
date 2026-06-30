-- Data dictionary: one row per documented (model, column) across the dbt schema
-- files (staging models, marts, seeds), with the column's description and the
-- data tests that guard it. Read-only consolidation of the schema docs.
-- Source mart: mart_data_dictionary (reads transform/models/**/_*.yml + seeds).
select
    dictionary_key,
    layer,
    model_name,
    model_description,
    column_name,
    column_description,
    data_tests,
    is_tested,
    accepted_values
from mart_data_dictionary
order by
    case layer when 'staging' then 0 when 'mart' then 1 when 'seed' then 2 else 9 end,
    model_name,
    column_name
