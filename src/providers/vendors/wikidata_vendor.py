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
from src.services.confidence import for_provider as _confidence_for

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
    # Product/technology-centric properties: without these, non-company
    # nodes have nothing to traverse and the graph dead-ends at the first
    # product you click.
    "P178": ("owns", "company"),           # developer
    "P176": ("owns", "company"),           # manufacturer
    "P127": ("owns", "company"),           # owned by
    "P361": ("belongs_to", "technology"),  # part of
    "P279": ("belongs_to", "technology"),  # subclass of
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
            SELECT ?prop ?value ?valueLabel WHERE {{
              VALUES ?prop {{ {' '.join('wdt:' + p for p in PROPERTY_EDGES)} }}
              wd:{entity['qid']} ?prop ?value .
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
                # The neighbour's own QID travels with the node so the graph
                # explorer can expand it directly, without a label lookup.
                qid = row["value"]["value"].rsplit("/", 1)[-1]
                bundle.nodes.append(GraphNode(
                    id=node_id, type=node_type, label=label,
                    route=f"/terminal/graph?node={node_id}",
                    metadata={"source": "wikidata", "qid": qid if qid.startswith("Q") else ""},
                ))
            # ceo_of/founded/subsidiary_of read person→company; the rest read
            # company→thing. Direction is part of the edge's meaning.
            if edge_type in {"ceo_of", "founded", "subsidiary_of"}:
                bundle.edges.append(GraphEdge(
                    source_id=node_id, target_id=company_id, type=edge_type,
                    provider="wikidata", confidence=_confidence_for("wikidata"),
                ))
            else:
                bundle.edges.append(GraphEdge(
                    source_id=company_id, target_id=node_id, type=edge_type,
                    provider="wikidata", confidence=_confidence_for("wikidata"),
                ))
        return bundle


    def expand_entity(self, qid: str, label: str, node_type: str, node_id: str) -> KnowledgeBundle:
        """Neighbours of an arbitrary graph node (person, product, industry…).

        Traverses outward (the entity's own statements) and inward (who
        points at it), which is what makes exploration continuous: opening
        a product reveals its owner, opening a person reveals every company
        they lead or founded.
        """
        if not qid.startswith("Q"):
            return KnowledgeBundle()
        bundle = KnowledgeBundle(nodes=[GraphNode(
            id=node_id, type=node_type, label=label,
            route=f"/terminal/graph?node={node_id}",
            metadata={"source": "wikidata", "qid": qid},
        )])
        seen = {node_id}

        outward = self._query(f"""
            SELECT ?prop ?value ?valueLabel WHERE {{
              VALUES ?prop {{ {' '.join('wdt:' + p for p in PROPERTY_EDGES)} }}
              wd:{qid} ?prop ?value .
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" }}
            }} LIMIT 60
        """)
        for row in outward:
            prop = row["prop"]["value"].rsplit("/", 1)[-1]
            mapping = PROPERTY_EDGES.get(prop)
            label_value = row.get("valueLabel", {}).get("value", "")
            if not mapping or not label_value or label_value.startswith("Q"):
                continue
            edge_type, other_type = mapping
            other_qid = row["value"]["value"].rsplit("/", 1)[-1]
            other_id = f"{other_type}:{_slug(label_value)}"
            if other_id not in seen:
                seen.add(other_id)
                bundle.nodes.append(GraphNode(
                    id=other_id, type=other_type, label=label_value,
                    route=f"/terminal/graph?node={other_id}",
                    metadata={"source": "wikidata", "qid": other_qid if other_qid.startswith("Q") else ""},
                ))
            bundle.edges.append(GraphEdge(
                source_id=node_id, target_id=other_id, type=edge_type,
                provider="wikidata", confidence=_confidence_for("wikidata"),
            ))

        # Inward: companies whose CEO/founder/product/subsidiary this is.
        inward = self._query(f"""
            SELECT ?prop ?item ?itemLabel ?ticker WHERE {{
              VALUES ?prop {{ wdt:P169 wdt:P112 wdt:P1056 wdt:P355 wdt:P178 wdt:P176 }}
              ?item ?prop wd:{qid} .
              OPTIONAL {{ ?item p:P414 ?listing . ?listing pq:P249 ?ticker }}
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" }}
            }} LIMIT 40
        """)
        # QID → chosen node id, so multi-listing companies collapse to one node.
        by_qid: dict[str, str] = {}
        for row in inward:
            prop = row["prop"]["value"].rsplit("/", 1)[-1]
            mapping = PROPERTY_EDGES.get(prop)
            item_label = row.get("itemLabel", {}).get("value", "")
            if not mapping or not item_label or item_label.startswith("Q"):
                continue
            edge_type, _ = mapping
            ticker = row.get("ticker", {}).get("value", "")
            item_qid = row["item"]["value"].rsplit("/", 1)[-1]
            if item_qid in by_qid:
                # Already have this company; only upgrade a slug id to a
                # ticker id if this row is the one carrying the ticker.
                existing_id = by_qid[item_qid]
                if ticker and existing_id.startswith("company:") and not existing_id.endswith(ticker.upper()):
                    pass
                continue
            # A listed company resolves to its own report; anything else stays
            # in the explorer.
            company_id = f"company:{ticker.upper()}" if ticker else f"company:{_slug(item_label)}"
            by_qid[item_qid] = company_id
            if company_id not in seen:
                seen.add(company_id)
                bundle.nodes.append(GraphNode(
                    id=company_id, type="company", label=item_label,
                    route=(f"/company/{ticker.upper()}" if ticker else f"/terminal/graph?node={company_id}"),
                    metadata={"source": "wikidata", "qid": item_qid, "ticker": ticker.upper()},
                ))
            bundle.edges.append(GraphEdge(
                source_id=company_id, target_id=node_id, type=edge_type,
                provider="wikidata", confidence=_confidence_for("wikidata"),
            ))
        return bundle
