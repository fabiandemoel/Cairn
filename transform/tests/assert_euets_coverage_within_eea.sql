-- Singular test: the installation-level EU ETS total (sum of the mart's NL
-- stationary verified emissions per year) must not EXCEED the EEA official
-- stationary aggregate for the same year by more than 0.5%. Both sources derive
-- from the EUTL, so on real data they reconcile almost exactly (~0.02%); the
-- test is deliberately one-sided so it also passes on the small CI fixture
-- (which holds only a subset of installations, far below the EEA total) while
-- still catching a double-counting bug that would push the mart above the
-- physical official total.
--
-- The EEA stationary total is main_activity_code '20-99' (all stationary
-- activities, excluding aviation) of the verified-emissions category. The test
-- passes when it returns zero rows.

with ets_total as (
    select
        year,
        sum(installation_emissions_t_co2eq) as ets_total_t_co2eq
    from {{ ref('benchmark_installation_emissions') }}
    group by year
),

eea_total as (
    select
        year,
        value as eea_total_t_co2eq
    from {{ ref('stg_eea__ets') }}
    where
        country_code = 'NL'
        and main_activity_code = '20-99'
        and citl_information = '2. Verified emissions'
        and size = 'All sizes'
        and value is not null
)

select
    ets_total.year,
    ets_total.ets_total_t_co2eq,
    eea_total.eea_total_t_co2eq,
    (ets_total.ets_total_t_co2eq - eea_total.eea_total_t_co2eq)
    / eea_total.eea_total_t_co2eq as relative_excess
from ets_total
inner join eea_total using (year)
where
    (ets_total.ets_total_t_co2eq - eea_total.eea_total_t_co2eq)
    / eea_total.eea_total_t_co2eq >= 0.005
