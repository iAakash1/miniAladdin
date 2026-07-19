"""
Wikidata vendor — encyclopedic company structure, keyless.

Wikidata is the highest-value free source for the *entity graph* around a
company: executives, founders, headquarters, industry, products, brands,
subsidiaries, parent, and stock exchange. One SPARQL query returns all of
it with stable identifiers, which is what lets several providers converge
on one canonical node instead of duplicating people and products.

Everything normalizes into KnowledgeBundle — nodes and typed, sourced
edges. No prose is returned.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from src.providers.base import VendorClient
from src.providers.research_schemas import GraphEdge, GraphNode, KnowledgeBundle

logger = logging.getLogger(__name__)

# Wikidata properties → our closed edge vocabulary. Keeping this mapping
# explicit (rather than passing through P-numbers) is what keeps the graph
# queryable by meaning.
PROPERTY_EDGES: dict[str, tuple[str, str]] = {
    "P169": ("ceo_of", "person"),          # chief executive officer
    "P112": ("founded", "person"),         # founded by
    "P452": ("belongs_to", "industry"),    # industry
    "P159": ("headquartered_in", "country"),  # headquarters location
    "P1056": ("produces", "product"),      # product or material produced
    "P355": ("parent_of", "subsidiary"),   # has subsidiary
    "P749": ("subsidiary_of", "company"),  # parent organization
    "P414": ("listed_on", "exchange"),     # stock exchange
    "P17": ("headquartered_in", "country"),  # country
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:60]


class WikidataVendor(VendorClient):
    NAME = "wikidata"
    KEY_ENV = None  # public SPARQL endpoint
    DEFAULT_RPM = 20  # courteous: the public endpoint is shared infrastructure

    SPARQL = "https://query.wikidata.org/sparql"

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": "OmniSignal Research (research@omnisignal.app)",
            "Accept": "application/sparql-results+json",
        }

    def _query(self, sparql: str) -> list[dict[str, Any]]:
        data = self._get_json(
            self.SPARQL, params={"query": sparql, "format": "json"}, headers=self._headers()
        )
        return ((data or {}).get("results") or {}).get("bindings") or []

    def find_company(self, symbol: str, company_name: str = "") -> Optional[dict[str, str]]:
        """Resolve a ticker to a Wikidata entity.

        Ticker (P249) is matched first because it is unambiguous; the name
        fallback is deliberately exact-match to avoid attaching the wrong
        company, which would poison the graph.
        """
        escaped = symbol.upper().replace('"', "")
        # Tickers are stored as a QUALIFIER (pq:P249) on the "listed in stock
        # exchange" statement (p:P414), not as a direct wdt:P249 property —
        # verified against Q182477/NVDA. Querying wdt:P249 returns nothing.
        rows = self._query(f"""
            SELECT ?item ?itemLabel ?itemDescription WHERE {{
              ?item p:P414 ?listing .
              ?listing pq:P249 "{escaped}" .
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" }}
            }} LIMIT 1
        """)
        if not rows and company_name:
            safe = company_name.replace('"', "").replace("\\", "")
            rows = self._query(f"""
                SELECT ?item ?itemLabel ?itemDescription WHERE {{
                  ?item rdfs:label "{safe}"@en .
                  ?item wdt:P31/wdt:P279* wd:Q4830453 .
                  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" }}
                }} LIMIT 1
            """)
        if not rows:
            return None
        row = rows[0]
        return {
            "qid": row["item"]["value"].rsplit("/", 1)[-1],
            "label": row.get("itemLabel", {}).get("value", company_name or symbol),
            "description": row.get("itemDescription", {}).get("value", ""),
        }

    def get_knowledge(self, symbol: str, company_name: str = "") -> KnowledgeBundle:
        entity = self.find_company(symbol, company_name)
        if not entity:
            return KnowledgeBundle()
        symbol = symbol.upper()
        company_id = f"company:{symbol}"
        bundle = KnowledgeBundle(nodes=[GraphNode(
            id=company_id, type="company", label=entity["label"],
            description=entity["description"] or None,
            route=f"/company/{symbol}",
            metadata={"wikidata": entity["qid"], "source": "wikidata"},
        )])

        properties = " ".join(f"wdt:{p}" for p in PROPERTY_EDGES)
        rows = self._query(f"""
            SELECT ?prop ?value ?valueLabel ?website WHERE {{
              VALUES ?prop {{ {' '.join('wdt:' + p for p in PROPERTY_EDGES)} }}
              wd:{entity['qid']} ?prop ?value .
              OPTIONAL {{ wd:{entity['qid']} wdt:P856 ?website }}
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" }}
            }} LIMIT 120
        """) if properties else []

        seen: set[str] = set()
        for row in rows:
            prop = row["prop"]["value"].rsplit("/", 1)[-1]
            mapping = PROPERTY_EDGES.get(prop)
            label = row.get("valueLabel", {}).get("value", "")
            if not mapping or not label or label.startswith("Q"):
                continue
            edge_type, node_type = mapping
            node_id = f"{node_type}:{_slug(label)}"
            if node_id not in seen:
                seen.add(node_id)
                bundle.nodes.append(GraphNode(
                    id=node_id, type=node_type, label=label,
                    metadata={"source": "wikidata"},
                ))
            # ceo_of/founded/subsidiary_of read person→company; the rest read
            # company→thing. Direction is part of the edge's meaning.
            if edge_type in {"ceo_of", "founded", "subsidiary_of"}:
                bundle.edges.append(GraphEdge(
                    source_id=node_id, target_id=company_id, type=edge_type,
                    provider="wikidata", confidence=0.9,
                ))
            else:
                bundle.edges.append(GraphEdge(
                    source_id=company_id, target_id=node_id, type=edge_type,
                    provider="wikidata", confidence=0.9,
                ))
        return bundle
