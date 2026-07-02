-- Staging: typed 1:1 view of the pinned EEX EU ETS primary-market auction
-- results snapshot (EEX = European Energy Exchange, the appointed Phase 4
-- auctioneer). Reads the parquet at the snapshot dir passed via the
-- `eua_raw_dir` var. A straight read/relabel of the clearing-price and
-- auction-outcome columns: every value is a typed copy of a raw column, with no
-- computation (no tonnes x price, no currency conversion) and no row filtering.
--
-- Scope note (CLAUDE.md invariant 5): the auction clearing price is a moving
-- market number, not a pinned emissions figure. This model exists so a future
-- site page can show it as clearly-labelled context; it must NEVER be ref'd by a
-- benchmark mart or the ESRS E1 export. Source columns that carry spaces or the
-- EUR/tCO2 unit glyph must be double-quoted (unavoidable) and aliased to
-- snake_case; single-word columns (time, contract, status, country) are
-- referenced unquoted and lowercase -- DuckDB resolves them case-insensitively,
-- and quoting them trips sqlfluff RF06.

with raw_auctions as (
    select * from read_parquet('{{ var("eua_raw_dir") }}/data.parquet')
)

select
    -- one row per auction event: date + auction platform/name
    time || '|' || "Auction Name" as auction_key,
    date '1899-12-30' + cast(try_cast(time as double) as integer) as auction_date,
    "Auction Name" as auction_name,
    contract,
    status,
    country,
    try_cast("Auction Price €/tCO2" as double) as auction_price_eur_per_tco2,
    try_cast("Minimum Bid €/tCO2" as double) as minimum_bid_eur_per_tco2,
    try_cast("Maximum Bid €/tCO2" as double) as maximum_bid_eur_per_tco2,
    try_cast("Mean €/tCO2" as double) as mean_price_eur_per_tco2,
    try_cast("Median €/tCO2" as double) as median_price_eur_per_tco2,
    try_cast("Auction Volume tCO2" as double) as auction_volume_tco2,
    try_cast("Cover Ratio" as double) as cover_ratio,
    try_cast("Total Number of Bidders" as integer) as total_bidders,
    try_cast("Number of Successful Bidders" as integer) as successful_bidders,
    try_cast("Total Revenue €" as double) as total_revenue_eur
from raw_auctions
