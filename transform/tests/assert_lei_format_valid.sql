-- Every non-NULL LEI in the reviewed lei_mapping_euets seed must be a valid
-- ISO 17442 Legal Entity Identifier: exactly 20 characters of uppercase
-- letters and digits. This guards against a malformed or hand-mangled code
-- slipping into the methodology seed (an invented or wrong identifier would
-- silently mis-attribute an installation to the wrong legal entity). A NULL lei
-- is the deliberate "unmatched" value and is allowed. The test fails (returns
-- rows) on any non-conforming code.

select
    euets_installation_id,
    lei
from {{ ref('lei_mapping_euets') }}
where
    lei is not null
    and not regexp_full_match(lei, '[A-Z0-9]{20}')
