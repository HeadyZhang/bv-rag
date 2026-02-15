-- ==========================================
-- 1. Regulations table (with full-text search)
-- ==========================================
CREATE TABLE IF NOT EXISTS regulations (
    doc_id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    title TEXT,
    breadcrumb TEXT,
    collection TEXT,
    document TEXT,
    chapter TEXT,
    part TEXT,
    regulation TEXT,
    paragraph TEXT,
    body_text TEXT,
    page_type TEXT,
    version TEXT,
    parent_doc_id TEXT,

    -- PostgreSQL full-text search vector (replaces Elasticsearch)
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(regulation, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(breadcrumb, '')), 'B') ||
        setweight(to_tsvector('english', coalesce(body_text, '')), 'C')
    ) STORED,

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_regulations_search ON regulations USING GIN (search_vector);
CREATE INDEX IF NOT EXISTS idx_regulations_document ON regulations (document);
CREATE INDEX IF NOT EXISTS idx_regulations_collection ON regulations (collection);
CREATE INDEX IF NOT EXISTS idx_regulations_parent ON regulations (parent_doc_id);

-- ==========================================
-- 2. Chunks table
-- ==========================================
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    doc_id TEXT REFERENCES regulations(doc_id),
    url TEXT,
    text TEXT NOT NULL,
    text_for_embedding TEXT NOT NULL,
    metadata JSONB NOT NULL,
    token_count INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks (doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_metadata ON chunks USING GIN (metadata);

-- ==========================================
-- 3. Cross-references table (replaces Neo4j REFERENCES edges)
-- ==========================================
CREATE TABLE IF NOT EXISTS cross_references (
    id SERIAL PRIMARY KEY,
    source_doc_id TEXT REFERENCES regulations(doc_id),
    target_doc_id TEXT,
    target_url TEXT,
    anchor_text TEXT,
    context TEXT,
    relation_type TEXT DEFAULT 'REFERENCES',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_xref_source ON cross_references (source_doc_id);
CREATE INDEX IF NOT EXISTS idx_xref_target ON cross_references (target_doc_id);
CREATE INDEX IF NOT EXISTS idx_xref_type ON cross_references (relation_type);

-- ==========================================
-- 4. Concept entities (replaces Neo4j Concept nodes)
-- ==========================================
CREATE TABLE IF NOT EXISTS concepts (
    concept_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT
);

CREATE TABLE IF NOT EXISTS regulation_concepts (
    doc_id TEXT REFERENCES regulations(doc_id),
    concept_id TEXT REFERENCES concepts(concept_id),
    PRIMARY KEY (doc_id, concept_id)
);

-- Seed concept entities
INSERT INTO concepts (concept_id, name, category) VALUES
    ('oil_tanker', 'oil tanker', 'ship_type'),
    ('bulk_carrier', 'bulk carrier', 'ship_type'),
    ('passenger_ship', 'passenger ship', 'ship_type'),
    ('cargo_ship', 'cargo ship', 'ship_type'),
    ('chemical_tanker', 'chemical tanker', 'ship_type'),
    ('gas_carrier', 'gas carrier', 'ship_type'),
    ('container_ship', 'container ship', 'ship_type'),
    ('roro_ship', 'ro-ro ship', 'ship_type'),
    ('fishing_vessel', 'fishing vessel', 'ship_type'),
    ('high_speed_craft', 'high-speed craft', 'ship_type'),
    ('modu', 'MODU', 'ship_type'),
    ('fpso', 'FPSO', 'ship_type'),
    ('offshore_supply', 'offshore supply vessel', 'ship_type'),
    ('fire_safety', 'fire safety', 'concept'),
    ('pollution_prevention', 'pollution prevention', 'concept'),
    ('navigation_safety', 'navigation safety', 'concept'),
    ('life_saving', 'life saving', 'concept'),
    ('stability', 'stability', 'concept'),
    ('machinery', 'machinery', 'concept'),
    ('electrical', 'electrical installations', 'concept'),
    ('security', 'maritime security', 'concept'),
    ('ism_audit', 'ISM audit', 'concept'),
    ('port_state_control', 'port state control', 'concept')
ON CONFLICT DO NOTHING;
