CREATE TABLE IF NOT EXISTS videos (
    id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
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
)
