-- ════════════════════════════════════════════════════════════════════════
-- agentic.market × ERC-8004 × x402 — Dune Dashboard SQL
--
-- Setup:
--   1. Upload these CSVs as Dune datasets (Dune → Datasets → Upload CSV):
--        bazaar_merchants.csv         → dune.<your_handle>.dataset_bazaar
--        agentic_market_services.csv  → dune.<your_handle>.dataset_amarket
--        agent0_base_agents.csv       → dune.<your_handle>.dataset_agents
--   2. Find the CDP facilitator wallet (see README.md), save as Dune Parameter.
--   3. Create the dashboard with one panel per query below.
--
-- All on-chain queries hit `erc20_base.evt_transfer` (Dune-indexed, free).
-- The agent JOIN uses `owner OR agent_wallet` because most ERC-8004 agents
-- leave agent_wallet=null and the owner address IS the receiving wallet.
-- ════════════════════════════════════════════════════════════════════════

-- Parameters (set in Dune Parameter UI):
--   {{cdp_facilitator}} → CDP facilitator address (e.g. 0x...) — see README
--   {{timeframe_days}}  → number, default 30


-- ────────────────────────────────────────────────────────────────────────
-- 1. HERO STATS — top-of-dashboard tiles
-- ────────────────────────────────────────────────────────────────────────
SELECT
    COUNT(*)                                AS tx_count,
    SUM(CAST(value AS DOUBLE) / 1e6)        AS volume_usdc,
    COUNT(DISTINCT "to")                    AS unique_merchants,
    COUNT(DISTINCT "from")                  AS unique_buyers,
    AVG(CAST(value AS DOUBLE) / 1e6)        AS avg_price_usdc,
    APPROX_PERCENTILE(CAST(value AS DOUBLE) / 1e6, 0.50) AS median_price_usdc,
    APPROX_PERCENTILE(CAST(value AS DOUBLE) / 1e6, 0.90) AS p90_price_usdc
FROM erc20_base.evt_transfer
WHERE contract_address = 0x833589fcd6edb6e08f4c7c32d4f71b54bda02913
  AND "from"            = LOWER('{{cdp_facilitator}}')
  AND evt_block_time   >= NOW() - INTERVAL '{{timeframe_days}}' DAY;


-- ────────────────────────────────────────────────────────────────────────
-- 2. DAILY VOLUME — line chart
-- ────────────────────────────────────────────────────────────────────────
SELECT
    DATE_TRUNC('day', evt_block_time)       AS day,
    SUM(CAST(value AS DOUBLE) / 1e6)        AS volume_usdc,
    COUNT(*)                                AS tx_count,
    COUNT(DISTINCT "to")                    AS unique_merchants,
    COUNT(DISTINCT "from")                  AS unique_buyers
FROM erc20_base.evt_transfer
WHERE contract_address = 0x833589fcd6edb6e08f4c7c32d4f71b54bda02913
  AND "from"            = LOWER('{{cdp_facilitator}}')
  AND evt_block_time   >= NOW() - INTERVAL '{{timeframe_days}}' DAY
GROUP BY 1
ORDER BY 1;


-- ────────────────────────────────────────────────────────────────────────
-- 3. TOP MERCHANTS — fully enriched leaderboard
--    Joins on-chain revenue with agentic.market names + categories +
--    ERC-8004 agent identity (via Agent0 subgraph on Base).
-- ────────────────────────────────────────────────────────────────────────
WITH merchants AS (
    SELECT
        "to"                                AS pay_to,
        COUNT(*)                            AS tx_count,
        SUM(CAST(value AS DOUBLE) / 1e6)    AS volume_usdc,
        COUNT(DISTINCT "from")              AS unique_buyers,
        MIN(evt_block_time)                 AS first_paid_at,
        MAX(evt_block_time)                 AS last_paid_at,
        AVG(CAST(value AS DOUBLE) / 1e6)    AS avg_price_usdc
    FROM erc20_base.evt_transfer
    WHERE contract_address = 0x833589fcd6edb6e08f4c7c32d4f71b54bda02913
      AND "from"            = LOWER('{{cdp_facilitator}}')
      AND evt_block_time   >= NOW() - INTERVAL '{{timeframe_days}}' DAY
    GROUP BY 1
)
SELECT
    m.pay_to,
    -- agentic.market enrichment (curated catalog)
    am.name                                 AS service_name,
    am.category                             AS category,
    am.integration_type                     AS first_or_third_party,
    am.domain                               AS domain,
    -- ERC-8004 enrichment (Agent0 Base subgraph)
    ag.agent_id                             AS agent_id,
    CASE
        WHEN ag.agent_wallet IS NOT NULL
          OR ag.owner       IS NOT NULL THEN '🤖 Registered ERC-8004 agent'
        ELSE '❓ Anonymous wallet'
    END                                     AS identity_status,
    -- Volume metrics
    m.volume_usdc,
    m.tx_count,
    m.unique_buyers,
    m.avg_price_usdc,
    m.first_paid_at,
    m.last_paid_at,
    CAST(EXTRACT(EPOCH FROM (NOW() - m.last_paid_at)) / 3600 AS INTEGER) AS hours_since_last_paid
FROM merchants m
LEFT JOIN dune.<your_handle>.dataset_amarket am
       ON LOWER(am.pay_to) = m.pay_to
LEFT JOIN dune.<your_handle>.dataset_agents ag
       ON LOWER(ag.owner)        = m.pay_to
       OR LOWER(ag.agent_wallet) = m.pay_to
ORDER BY m.volume_usdc DESC
LIMIT 100;


-- ────────────────────────────────────────────────────────────────────────
-- 4. AGENT SHARE OF ECONOMY — registered vs anon split
-- ────────────────────────────────────────────────────────────────────────
WITH merchants AS (
    SELECT
        "to" AS pay_to,
        SUM(CAST(value AS DOUBLE) / 1e6) AS volume_usdc,
        COUNT(*) AS tx_count
    FROM erc20_base.evt_transfer
    WHERE contract_address = 0x833589fcd6edb6e08f4c7c32d4f71b54bda02913
      AND "from"            = LOWER('{{cdp_facilitator}}')
      AND evt_block_time   >= NOW() - INTERVAL '{{timeframe_days}}' DAY
    GROUP BY 1
),
tagged AS (
    SELECT
        m.pay_to,
        m.volume_usdc,
        m.tx_count,
        CASE
            WHEN ag.agent_id IS NOT NULL THEN '🤖 Registered agent'
            ELSE '❓ Anonymous wallet'
        END AS merchant_type
    FROM merchants m
    LEFT JOIN dune.<your_handle>.dataset_agents ag
           ON LOWER(ag.owner)        = m.pay_to
           OR LOWER(ag.agent_wallet) = m.pay_to
)
SELECT
    merchant_type,
    COUNT(DISTINCT pay_to)                                  AS merchant_count,
    SUM(volume_usdc)                                         AS volume_usdc,
    SUM(tx_count)                                            AS tx_count,
    100.0 * SUM(volume_usdc) / SUM(SUM(volume_usdc)) OVER () AS pct_of_volume,
    100.0 * SUM(tx_count)    / SUM(SUM(tx_count))    OVER () AS pct_of_calls
FROM tagged
GROUP BY 1
ORDER BY volume_usdc DESC;


-- ────────────────────────────────────────────────────────────────────────
-- 5. CATEGORY BREAKDOWN — by agentic.market category
-- ────────────────────────────────────────────────────────────────────────
WITH merchants AS (
    SELECT
        "to" AS pay_to,
        SUM(CAST(value AS DOUBLE) / 1e6) AS volume_usdc,
        COUNT(*) AS tx_count
    FROM erc20_base.evt_transfer
    WHERE contract_address = 0x833589fcd6edb6e08f4c7c32d4f71b54bda02913
      AND "from"            = LOWER('{{cdp_facilitator}}')
      AND evt_block_time   >= NOW() - INTERVAL '{{timeframe_days}}' DAY
    GROUP BY 1
)
SELECT
    COALESCE(am.category, 'Uncategorized')          AS category,
    COUNT(DISTINCT m.pay_to)                         AS service_count,
    SUM(m.volume_usdc)                               AS volume_usdc,
    SUM(m.tx_count)                                  AS tx_count,
    AVG(m.volume_usdc)                               AS avg_volume_per_service
FROM merchants m
LEFT JOIN dune.<your_handle>.dataset_amarket am ON LOWER(am.pay_to) = m.pay_to
GROUP BY 1
ORDER BY volume_usdc DESC;


-- ────────────────────────────────────────────────────────────────────────
-- 6. NEW SERVICE LAUNCH RADAR — first-paid-on-chain timeline
-- ────────────────────────────────────────────────────────────────────────
WITH all_time AS (
    SELECT
        "to" AS pay_to,
        MIN(evt_block_time) AS first_paid_at,
        COUNT(*) AS lifetime_tx_count,
        SUM(CAST(value AS DOUBLE) / 1e6) AS lifetime_volume
    FROM erc20_base.evt_transfer
    WHERE contract_address = 0x833589fcd6edb6e08f4c7c32d4f71b54bda02913
      AND "from"            = LOWER('{{cdp_facilitator}}')
    GROUP BY 1
)
SELECT
    a.pay_to,
    am.name                          AS service_name,
    am.category,
    a.first_paid_at,
    a.lifetime_tx_count,
    a.lifetime_volume,
    CASE WHEN ag.agent_id IS NOT NULL THEN '🤖 agent' ELSE '❓ anon' END AS identity
FROM all_time a
LEFT JOIN dune.<your_handle>.dataset_amarket am ON LOWER(am.pay_to) = a.pay_to
LEFT JOIN dune.<your_handle>.dataset_agents ag
       ON LOWER(ag.owner)        = a.pay_to
       OR LOWER(ag.agent_wallet) = a.pay_to
WHERE a.first_paid_at >= NOW() - INTERVAL '{{timeframe_days}}' DAY
ORDER BY a.first_paid_at DESC
LIMIT 50;


-- ────────────────────────────────────────────────────────────────────────
-- 7. PRICING DISTRIBUTION — buckets
-- ────────────────────────────────────────────────────────────────────────
SELECT
    CASE
        WHEN CAST(value AS DOUBLE) / 1e6 < 0.001 THEN '< $0.001'
        WHEN CAST(value AS DOUBLE) / 1e6 < 0.01  THEN '$0.001-$0.01'
        WHEN CAST(value AS DOUBLE) / 1e6 < 0.10  THEN '$0.01-$0.10'
        WHEN CAST(value AS DOUBLE) / 1e6 < 1.00  THEN '$0.10-$1'
        WHEN CAST(value AS DOUBLE) / 1e6 < 10.0  THEN '$1-$10'
        ELSE '$10+'
    END                                     AS price_bucket,
    COUNT(*)                                AS tx_count,
    SUM(CAST(value AS DOUBLE) / 1e6)        AS total_volume_usdc,
    100.0 * COUNT(*) / SUM(COUNT(*)) OVER () AS pct_of_calls
FROM erc20_base.evt_transfer
WHERE contract_address = 0x833589fcd6edb6e08f4c7c32d4f71b54bda02913
  AND "from"            = LOWER('{{cdp_facilitator}}')
  AND evt_block_time   >= NOW() - INTERVAL '{{timeframe_days}}' DAY
GROUP BY 1
ORDER BY MIN(CAST(value AS DOUBLE)) ASC;


-- ────────────────────────────────────────────────────────────────────────
-- 8. AGENT LEADERBOARD — top-earning ERC-8004 registered agents only
-- ────────────────────────────────────────────────────────────────────────
WITH merchant_revenue AS (
    SELECT
        "to" AS pay_to,
        SUM(CAST(value AS DOUBLE) / 1e6) AS volume_usdc,
        COUNT(*) AS tx_count,
        COUNT(DISTINCT "from") AS unique_buyers
    FROM erc20_base.evt_transfer
    WHERE contract_address = 0x833589fcd6edb6e08f4c7c32d4f71b54bda02913
      AND "from"            = LOWER('{{cdp_facilitator}}')
      AND evt_block_time   >= NOW() - INTERVAL '{{timeframe_days}}' DAY
    GROUP BY 1
)
SELECT
    ag.agent_id                                AS erc8004_agent_id,
    ag.chain_id,
    ag.owner                                   AS agent_owner,
    am.name                                    AS service_name,
    am.category,
    m.volume_usdc,
    m.tx_count,
    m.unique_buyers,
    m.pay_to
FROM dune.<your_handle>.dataset_agents ag
INNER JOIN merchant_revenue m
       ON LOWER(ag.owner)        = m.pay_to
       OR LOWER(ag.agent_wallet) = m.pay_to
LEFT JOIN dune.<your_handle>.dataset_amarket am ON LOWER(am.pay_to) = m.pay_to
ORDER BY m.volume_usdc DESC
LIMIT 50;


-- ────────────────────────────────────────────────────────────────────────
-- 9. UNLISTED EARNERS — earning but not in agentic.market curated catalog
--    (outreach list: services that should be onboarded)
-- ────────────────────────────────────────────────────────────────────────
SELECT
    "to" AS pay_to,
    COUNT(*) AS tx_count,
    SUM(CAST(value AS DOUBLE) / 1e6) AS volume_usdc,
    COUNT(DISTINCT "from") AS unique_buyers,
    MAX(evt_block_time) AS last_paid_at
FROM erc20_base.evt_transfer e
LEFT JOIN dune.<your_handle>.dataset_amarket am ON LOWER(am.pay_to) = e."to"
WHERE contract_address = 0x833589fcd6edb6e08f4c7c32d4f71b54bda02913
  AND "from"            = LOWER('{{cdp_facilitator}}')
  AND evt_block_time   >= NOW() - INTERVAL '{{timeframe_days}}' DAY
  AND am.pay_to IS NULL
GROUP BY 1
HAVING SUM(CAST(value AS DOUBLE) / 1e6) > 1
ORDER BY volume_usdc DESC
LIMIT 50;


-- ────────────────────────────────────────────────────────────────────────
-- 11. MULTI-FACILITATOR — the FULL Base x402 economy (not just Coinbase)
--     Joins dataset_facilitators so every facilitator's volume is counted.
--     This is the right query for the headline "total ecosystem volume" number.
-- ────────────────────────────────────────────────────────────────────────
WITH base_facilitators AS (
    SELECT LOWER(address) AS address, facilitator
    FROM dune.<your_handle>.dataset_facilitators
    WHERE chains LIKE '%base%'
)
SELECT
    f.facilitator,
    COUNT(*)                                AS tx_count,
    SUM(CAST(value AS DOUBLE) / 1e6)        AS volume_usdc,
    COUNT(DISTINCT t."to")                   AS unique_sellers,
    COUNT(DISTINCT t."from")                 AS unique_buyers
FROM erc20_base.evt_transfer t
INNER JOIN base_facilitators f ON LOWER(t."from") = f.address
WHERE t.contract_address = 0x833589fcd6edb6e08f4c7c32d4f71b54bda02913
  AND t.evt_block_time   >= NOW() - INTERVAL '{{timeframe_days}}' DAY
GROUP BY 1
ORDER BY volume_usdc DESC;


-- ────────────────────────────────────────────────────────────────────────
-- 12. ECOSYSTEM HERO STATS — across ALL 29 facilitators on Base
-- ────────────────────────────────────────────────────────────────────────
WITH base_facilitators AS (
    SELECT LOWER(address) AS address
    FROM dune.<your_handle>.dataset_facilitators
    WHERE chains LIKE '%base%'
)
SELECT
    COUNT(*)                                AS tx_count,
    SUM(CAST(value AS DOUBLE) / 1e6)        AS volume_usdc,
    COUNT(DISTINCT t."to")                   AS unique_merchants,
    COUNT(DISTINCT t."from")                 AS unique_buyers,
    COUNT(DISTINCT t."from") AS unique_facilitators_used
FROM erc20_base.evt_transfer t
INNER JOIN base_facilitators f ON LOWER(t."from") = f.address
WHERE t.contract_address = 0x833589fcd6edb6e08f4c7c32d4f71b54bda02913
  AND t.evt_block_time   >= NOW() - INTERVAL '{{timeframe_days}}' DAY;


-- ────────────────────────────────────────────────────────────────────────
-- 10. CATALOG vs ACTIVITY MATRIX — % of listed services that earn
-- ────────────────────────────────────────────────────────────────────────
WITH listed AS (
    SELECT DISTINCT LOWER(pay_to) AS pay_to FROM dune.<your_handle>.dataset_amarket WHERE pay_to <> ''
),
earners AS (
    SELECT DISTINCT "to" AS pay_to
    FROM erc20_base.evt_transfer
    WHERE contract_address = 0x833589fcd6edb6e08f4c7c32d4f71b54bda02913
      AND "from"            = LOWER('{{cdp_facilitator}}')
      AND evt_block_time   >= NOW() - INTERVAL '{{timeframe_days}}' DAY
)
SELECT
    'Listed on agentic.market AND earning' AS bucket,
    COUNT(*) AS count_
FROM listed l INNER JOIN earners e ON l.pay_to = e.pay_to
UNION ALL
SELECT 'Listed on agentic.market but NO recent earnings',
    COUNT(*) FROM listed l LEFT JOIN earners e ON l.pay_to = e.pay_to WHERE e.pay_to IS NULL
UNION ALL
SELECT 'Earning on-chain but NOT listed on agentic.market',
    COUNT(*) FROM earners e LEFT JOIN listed l ON l.pay_to = e.pay_to WHERE l.pay_to IS NULL;
