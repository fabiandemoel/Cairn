-- EU ETS excess emissions penalty (Article 16, Directive 2003/87/EC):
-- installation-years where EUTL recorded a nonzero penalty because
-- surrendered allowances fell short of verified emissions. Penalties are
-- rare -- most installations comply, so an empty result is expected, not a
-- bug. Read straight from the pinned snapshot; never computed or estimated
-- by Cairn. Source mart: benchmark_installation_emissions
-- (sources/euets/manifest.yml).
select
    installation_year_key,
    installation_id,
    installation_name,
    nace_section,
    nace_section_label,
    year,
    installation_emissions_t_co2eq,
    surrendered_allowances_t_co2eq,
    excess_emissions_penalty_eur
from benchmark_installation_emissions
where excess_emissions_penalty_eur is not null
    and excess_emissions_penalty_eur != 0
order by excess_emissions_penalty_eur desc
