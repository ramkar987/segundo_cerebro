cat > sql/schema_duckdb.sql << 'EOF'
CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL,
    caminho TEXT NOT NULL,
    transricao TEXT,
    resumo TEXT,
    tags TEXT,
    traducao TEXT,
    idioma_original TEXT,
    idioma_traducao TEXT,
    data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_transricao TIMESTAMP,
    data_processamento_ia TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_videos_transricao ON videos(transricao);
CREATE INDEX IF NOT EXISTS idx_videos_tags ON videos(tags);
EOF
