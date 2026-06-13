"""Minimal client for the CBS StatLine OData v4 API.

CBS retired the OData v3 ``TypedDataSet`` feed (``opendata.cbs.nl/ODataApi``)
in favour of the v4 API at ``datasets.cbs.nl``. v4 does not hand back a single
denormalised table; instead it exposes an ``Observations`` entity set of coded
rows plus one ``*Codes`` entity set per dimension that decodes those codes into
labels. This client fetches an entity set (following ``@odata.nextLink``
pagination) and the table ``Properties`` singleton that carries the release
metadata.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from urllib.parse import quote
from urllib.request import Request, urlopen

BASE_URL = "https://datasets.cbs.nl/odata/v1/CBS"

_TIMEOUT = 60


def _get_json(url: str) -> dict:
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310 - fixed https host
        return json.loads(resp.read().decode("utf-8"))


def fetch_properties(table: str) -> dict:
    """Return the ``Properties`` singleton (Title, Modified, ObservationCount...)."""
    return _get_json(f"{BASE_URL}/{quote(table)}/Properties")


def iter_entityset(table: str, entity_set: str) -> Iterator[dict]:
    """Yield every row of an entity set, following ``@odata.nextLink`` pages."""
    url: str | None = f"{BASE_URL}/{quote(table)}/{quote(entity_set)}"
    while url:
        page = _get_json(url)
        yield from page.get("value", [])
        url = page.get("@odata.nextLink")
