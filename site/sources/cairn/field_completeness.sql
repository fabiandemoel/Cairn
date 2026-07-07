-- Field-completeness (NULL-rate) observability: per mart, tracked column, and
-- year, populated-vs-NULL row counts and the resulting share.
-- Source mart: mart_field_completeness.
select
    mart_column_year_key,
    mart_name,
    column_name,
    year,
    total_count,
    populated_count,
    null_count,
    populated_share
from mart_field_completeness
order by mart_name, column_name, year
