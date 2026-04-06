"""
Generate query hints for top subgraphs by introspecting their schemas.

Queries the Graph gateway for each subgraph's __schema, extracts the top
queryable entities with their sortable fields, and generates sample queries.
Stores results in the registry DB's query_hint column.

Usage:
    GRAPH_API_KEY=your_key python scripts/generate_query_hints.py
    GRAPH_API_KEY=your_key python scripts/generate_query_hints.py --min-queries 100000
    GRAPH_API_KEY=your_key python scripts/generate_query_hints.py --db /path/to/registry.db

Designed to run as part of the 3-day registry cron update.
"""

import json
import os
import sqlite3
import sys
import time
import urllib.request
import urllib.error

API_KEY = os.environ.get("GRAPH_API_KEY", "")
DB_PATH = sys.argv[sys.argv.index("--db") + 1] if "--db" in sys.argv else "/tmp/subgraph_registry_full.db"
MIN_QUERIES = int(sys.argv[sys.argv.index("--min-queries") + 1]) if "--min-queries" in sys.argv else 10000

# Fields to ignore (internal/meta)
SKIP_FIELDS = {"id", "blockNumber", "blockTimestamp", "transactionHash", "logIndex", "timestamp"}
SKIP_TYPES = {"_Meta_", "_Block_", "_SubgraphErrorPolicy_", "Query", "Subscription"}

# Common sortable field patterns (prioritize these)
SORT_PRIORITY = [
    "totalValueLockedUSD", "reserveUSD", "volumeUSD", "totalDepositBalanceUSD",
    "totalBorrowBalanceUSD", "totalSupply", "totalLiquidity", "balance",
    "amount", "amountUSD", "price", "priceUSD", "timestamp", "blockNumber",
    "createdAtTimestamp", "registrationDate", "totalSettlements", "totalPayments",
]

INTROSPECTION_QUERY = """{
  __schema {
    types {
      name
      kind
      fields {
        name
        type {
          name
          kind
          ofType { name kind }
        }
      }
    }
  }
}"""


def introspect_subgraph(subgraph_id: str) -> dict | None:
    """Query a subgraph's schema via the Graph gateway or MCP endpoint."""
    # Method 1: Try the subgraph MCP schema endpoint (works when gateway blocks introspection)
    mcp_url = "https://api.playgrounds.network/v1/proxy/subgraphs/id/" + subgraph_id
    try:
        data = json.dumps({"query": INTROSPECTION_QUERY}).encode()
        req = urllib.request.Request(mcp_url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            if "data" in result and "__schema" in result["data"]:
                return result["data"]["__schema"]
    except Exception:
        pass

    # Method 2: Try gateway with API key
    if API_KEY:
        url = f"https://gateway.thegraph.com/api/{API_KEY}/subgraphs/id/{subgraph_id}"
        try:
            data = json.dumps({"query": INTROSPECTION_QUERY}).encode()
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read())
                if "data" in result and "__schema" in result["data"]:
                    return result["data"]["__schema"]
        except Exception:
            pass

    # Method 3: Parse schema from the all_entities column in the DB (fallback)
    return None


def introspect_from_registry(subgraph_id: str, conn: sqlite3.Connection) -> list[dict] | None:
    """Build entity info from the registry DB's all_entities column as fallback."""
    row = conn.execute(
        "SELECT all_entities, canonical_entities FROM subgraphs WHERE id = ?",
        (subgraph_id,),
    ).fetchone()
    if not row or not row[0]:
        return None
    try:
        entities = json.loads(row[0])
        result = []
        for e in entities:
            name = e.get("name", "")
            etype = e.get("type", "")
            field_count = e.get("fields", 0)
            if not name or field_count < 2:
                continue
            # We don't have field names, so generate from type hints
            sort_field = None
            if etype == "liquidity_pool":
                sort_field = "totalValueLockedUSD"
            elif etype == "token":
                sort_field = "volumeUSD"
            elif etype == "trade" or etype == "swap":
                sort_field = "amountUSD"
            elif etype == "account":
                sort_field = None
            result.append({
                "name": name,
                "entity_type": etype or "",
                "fields": [],  # Unknown from DB
                "nested": [],
                "sort_field": sort_field,
                "total_fields": field_count,
                "from_db": True,
            })
        return result[:5] if result else None
    except (json.JSONDecodeError, KeyError):
        return None


def generate_hint_from_db_entities(entities: list[dict]) -> str:
    """Generate a best-effort query hint from DB entity metadata using type-based field templates."""
    # Known field patterns by entity type
    TYPE_TEMPLATES = {
        "liquidity_pool": {
            "sort": "totalValueLockedUSD",
            "fields": "id totalValueLockedUSD volumeUSD feeTier token0 { symbol } token1 { symbol }",
        },
        "token": {
            "sort": "totalValueLockedUSD",
            "fields": "id symbol name decimals totalValueLockedUSD volumeUSD",
        },
        "trade": {
            "sort": "timestamp",
            "fields": "id amountUSD timestamp sender recipient",
        },
        "position": {
            "sort": "liquidity",
            "fields": "id owner liquidity",
        },
        "transaction": {
            "sort": "timestamp",
            "fields": "id timestamp blockNumber",
        },
        "account": {
            "sort": None,
            "fields": "id",
        },
        "vault": {
            "sort": "totalValueLockedUSD",
            "fields": "id totalValueLockedUSD",
        },
        "collateral": {
            "sort": "totalValueLockedUSD",
            "fields": "id totalValueLockedUSD",
        },
        "daily_snapshot": {
            "sort": "date",
            "fields": "id date totalValueLockedUSD volumeUSD",
        },
        "liquidation": {
            "sort": "timestamp",
            "fields": "id timestamp amountUSD",
        },
        "loan": {
            "sort": "timestamp",
            "fields": "id timestamp amount",
        },
        "proposal": {
            "sort": None,
            "fields": "id description status",
        },
        "domain_name": {
            "sort": None,
            "fields": "id name owner { id }",
        },
        "nft_collection": {
            "sort": None,
            "fields": "id name totalSupply",
        },
        "delegate": {
            "sort": None,
            "fields": "id delegatedVotes",
        },
    }

    parts = []
    for e in entities[:3]:
        name = e["name"]
        etype = e.get("entity_type", "")

        # Pluralize
        plural = name[0].lower() + name[1:]
        if not plural.endswith("s"):
            if plural.endswith("y") and not plural.endswith("ay") and not plural.endswith("ey"):
                plural = plural[:-1] + "ies"
            else:
                plural = plural + "s"

        template = TYPE_TEMPLATES.get(etype, {})
        sort = template.get("sort", e.get("sort_field", ""))
        fields = template.get("fields", "id")

        if sort:
            parts.append(f"{plural}(first: 5, orderBy: {sort}, orderDirection: desc) {{ {fields} }}")
        else:
            parts.append(f"{plural}(first: 5) {{ {fields} }}")

    return "{ " + " ".join(parts) + " }" if parts else ""


def extract_entities(schema: dict) -> list[dict]:
    """Extract queryable entities with their key fields from a schema."""
    entities = []
    for t in schema.get("types", []):
        name = t.get("name", "")
        kind = t.get("kind", "")

        # Only OBJECT types, skip internal types
        if kind != "OBJECT" or name.startswith("_") or name in SKIP_TYPES:
            continue
        if name.endswith("_filter") or name.endswith("_orderBy"):
            continue

        fields = t.get("fields") or []
        field_names = []
        scalar_fields = []
        sortable_field = None
        nested_fields = []

        for f in fields:
            fname = f.get("name", "")
            if fname in SKIP_FIELDS or fname.startswith("_"):
                continue

            ftype = f.get("type", {})
            ftype_kind = ftype.get("kind", "")
            ftype_name = ftype.get("name", "")
            inner = ftype.get("ofType", {})
            inner_kind = inner.get("kind", "") if inner else ""

            # Scalar fields (String, Int, BigInt, BigDecimal, Boolean, Bytes)
            if ftype_kind == "SCALAR" or (ftype_kind == "NON_NULL" and inner_kind == "SCALAR"):
                scalar_fields.append(fname)
                if fname in SORT_PRIORITY and not sortable_field:
                    sortable_field = fname
            # Nested object fields (like token0 { symbol })
            elif ftype_kind == "OBJECT" or (ftype_kind == "NON_NULL" and inner_kind == "OBJECT"):
                nested_fields.append(fname)

            field_names.append(fname)

        if len(scalar_fields) < 2:
            continue

        # Pick best sort field
        if not sortable_field:
            for pf in SORT_PRIORITY:
                if pf in scalar_fields:
                    sortable_field = pf
                    break
            if not sortable_field and scalar_fields:
                sortable_field = scalar_fields[0]

        entities.append({
            "name": name,
            "fields": scalar_fields[:10],  # Top 10 scalar fields
            "nested": nested_fields[:5],
            "sort_field": sortable_field,
            "total_fields": len(field_names),
        })

    # Sort by field count (richer entities first)
    entities.sort(key=lambda e: e["total_fields"], reverse=True)
    return entities[:5]  # Top 5 entities


def generate_query_hint(entities: list[dict]) -> str:
    """Generate a sample GraphQL query from extracted entities."""
    if not entities:
        return ""

    parts = []
    for e in entities[:3]:  # Top 3 entities
        name = e["name"]
        # Pluralize: Pool -> pools, Token -> tokens, Pair -> pairs
        plural = name[0].lower() + name[1:] + "s"
        if name.endswith("s"):
            plural = name[0].lower() + name[1:]
        elif name.endswith("y"):
            plural = name[0].lower() + name[1:-1] + "ies"

        sort = e.get("sort_field", "")
        fields = e["fields"][:6]

        # Add nested fields with { symbol } or { id }
        for nf in e.get("nested", [])[:2]:
            if nf in ("token0", "token1", "inputToken", "outputToken"):
                fields.append(f"{nf} {{ symbol name }}")
            elif nf in ("account", "user", "owner", "sender", "recipient"):
                fields.append(f"{nf} {{ id }}")
            else:
                fields.append(f"{nf} {{ id }}")

        field_str = " ".join(fields)
        if sort:
            parts.append(f"{plural}(first: 5, orderBy: {sort}, orderDirection: desc) {{ {field_str} }}")
        else:
            parts.append(f"{plural}(first: 5) {{ {field_str} }}")

    return "{ " + " ".join(parts) + " }"


def main():
    if not API_KEY:
        print("ERROR: Set GRAPH_API_KEY env var")
        sys.exit(1)

    print(f"DB: {DB_PATH}")
    print(f"Min queries: {MIN_QUERIES:,}")

    conn = sqlite3.connect(DB_PATH)

    # Add query_hint column if not exists
    try:
        conn.execute("ALTER TABLE subgraphs ADD COLUMN query_hint TEXT")
        conn.commit()
        print("Added query_hint column")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Get top subgraphs by query volume
    rows = conn.execute(
        "SELECT id, display_name, query_volume_30d FROM subgraphs "
        "WHERE query_volume_30d >= ? ORDER BY query_volume_30d DESC",
        (MIN_QUERIES,),
    ).fetchall()

    print(f"Subgraphs to introspect: {len(rows)}")
    print()

    success = 0
    failed = 0
    skipped = 0

    for i, (subgraph_id, name, queries) in enumerate(rows):
        # Check if already has a hint
        existing = conn.execute(
            "SELECT query_hint FROM subgraphs WHERE id = ?", (subgraph_id,)
        ).fetchone()
        if existing and existing[0]:
            skipped += 1
            continue

        print(f"[{i+1}/{len(rows)}] {name or subgraph_id[:20]} (queries: {queries:,})")

        # Try full introspection first
        schema = introspect_subgraph(subgraph_id)
        if schema:
            entities = extract_entities(schema)
            if entities:
                hint = generate_query_hint(entities)
                entity_summary = ", ".join(f"{e['name']}({e['total_fields']})" for e in entities)
            else:
                hint = None
        else:
            # Fallback: build from DB metadata
            db_entities = introspect_from_registry(subgraph_id, conn)
            if db_entities:
                hint = generate_hint_from_db_entities(db_entities)
                entities = db_entities
                entity_summary = ", ".join(f"{e['name']}({e['total_fields']},db)" for e in entities)
                print(f"  (using DB fallback)")
            else:
                hint = None
                entities = []

        if not hint:
            print(f"  No queryable entities found")
            failed += 1
            continue

        entity_summary = entity_summary if 'entity_summary' in dir() else ""

        print(f"  Entities: {entity_summary}")
        print(f"  Hint: {hint[:120]}...")

        conn.execute(
            "UPDATE subgraphs SET query_hint = ? WHERE id = ?",
            (hint, subgraph_id),
        )
        conn.commit()
        success += 1

        # Rate limit: ~2 req/sec
        time.sleep(0.5)

    print()
    print(f"Done: {success} hints generated, {failed} failed, {skipped} skipped (already had hints)")
    conn.close()


if __name__ == "__main__":
    main()
