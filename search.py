"""
Busca por relevância usando TF-IDF + similaridade de cosseno.

Isso NÃO é IA generativa, é estatística sobre palavras — por isso funciona
100% offline e sem nenhuma chave de API. Agora também olha a transcrição
completa das notas de vídeo, então dá pra encontrar um vídeo por uma frase
específica que foi dita nele, não só pelo resumo.

Limitação: como é baseado em palavras (não em significado), uma busca por
"dinheiro" pode não encontrar uma nota que só fala em "orçamento". Para
busca semântica de verdade, daria para trocar isso por embeddings — pergunte
se quiser evoluir para isso.
"""

from typing import Dict, List

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def buscar_por_relevancia(notas: List[Dict], consulta: str, top_k: int = 5) -> List[Dict]:
    if not notas or not consulta.strip():
        return []

    textos = [
        f"{n['titulo']} {n['conteudo']} {n['tags']} {n.get('transcricao_completa', '')}"
        for n in notas
    ]
    textos.append(consulta)

    vectorizer = TfidfVectorizer()
    try:
        matriz = vectorizer.fit_transform(textos)
    except ValueError:
        # Acontece se todas as notas estiverem vazias ou só com stop words
        return []

    consulta_vec = matriz[-1]
    notas_vec = matriz[:-1]
    similaridades = cosine_similarity(consulta_vec, notas_vec).flatten()

    resultados = []
    for nota, score in zip(notas, similaridades):
        if score > 0:
            nota_com_score = dict(nota)
            nota_com_score["relevancia"] = float(score)
            resultados.append(nota_com_score)

    resultados.sort(key=lambda x: x["relevancia"], reverse=True)
    return resultados[:top_k]
