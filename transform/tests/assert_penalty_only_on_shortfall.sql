-- Excess emissions penalty (Article 16, EU ETS Directive 2003/87/EC) may only
-- be present when the installation-year had a definitive shortfall: verified
-- emissions exceeding surrendered allowances. Where surrendered is NULL
-- (surrender can lag), shortfall is unknown, not disproven -- those rows are
-- deliberately not flagged. This is a magnitude/consistency sanity bound only,
-- never a re-derivation of EUTL's own penalty decision. Fails (returns rows)
-- wherever a nonzero penalty coexists with a known non-shortfall.

select
    installation_id,
    year,
    installation_emissions_t_co2eq,
    surrendered_allowances_t_co2eq,
    excess_emissions_penalty_eur
from {{ ref('benchmark_installation_emissions') }}
where
    excess_emissions_penalty_eur is not null
    and excess_emissions_penalty_eur != 0
    and surrendered_allowances_t_co2eq is not null
    and installation_emissions_t_co2eq <= surrendered_allowances_t_co2eq
