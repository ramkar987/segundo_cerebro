import streamlit as st

from db import (
    adicionar_nota,
    atualizar_nota,
    buscar_por_palavra_chave,
    excluir_nota,
    init_db,
    listar_notas,
)
from groq_client import MODELOS_DISPONIVEIS, perguntar_as_notas
from search import buscar_por_relevancia

st.set_page_config(page_title="Segundo Cérebro", page_icon="🧠", layout="wide")

init_db()

# ---------------------------------------------------------------------------
# Barra lateral: navegação + configuração opcional da IA
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("🧠 Segundo Cérebro")
    pagina = st.radio(
        "Navegação",
        ["📝 Minhas notas", "🔍 Buscar", "💬 Perguntar à IA"],
        label_visibility="collapsed",
    )

    st.divider()
    st.subheader("IA (opcional)")
    groq_key = st.text_input(
        "Chave da API Groq",
        type="password",
        help="Crie uma chave gratuita em console.groq.com",
    )
    modelo_label = st.selectbox("Modelo", list(MODELOS_DISPONIVEIS.keys()))
    st.caption("Sem chave, o app funciona normalmente com busca por palavra-chave e por relevância.")

# ---------------------------------------------------------------------------
# Página: Minhas notas (CRUD)
# ---------------------------------------------------------------------------
if pagina == "📝 Minhas notas":
    st.header("Minhas notas")

    with st.expander("➕ Nova nota"):
        with st.form("form_nova_nota", clear_on_submit=True):
            titulo = st.text_input("Título")
            conteudo = st.text_area("Conteúdo", height=150)
            tags = st.text_input("Tags (separadas por vírgula)")
            enviar = st.form_submit_button("Salvar nota")
            if enviar:
                if titulo.strip() and conteudo.strip():
                    adicionar_nota(titulo.strip(), conteudo.strip(), tags.strip())
                    st.success("Nota salva!")
                    st.rerun()
                else:
                    st.warning("Preencha pelo menos o título e o conteúdo.")

    notas = listar_notas()
    st.caption(f"{len(notas)} nota(s) salva(s)")

    for nota in notas:
        rotulo = f"**{nota['titulo']}**  ·  {nota['tags'] or 'sem tags'}"
        with st.expander(rotulo):
            st.write(nota["conteudo"])
            st.caption(f"Atualizado em {nota['atualizado_em'][:16].replace('T', ' ')}")

            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("🗑️ Excluir", key=f"del_{nota['id']}"):
                    excluir_nota(nota["id"])
                    st.rerun()
            with col2:
                editar = st.toggle("✏️ Editar", key=f"edit_toggle_{nota['id']}")

            if editar:
                novo_titulo = st.text_input("Título", value=nota["titulo"], key=f"titulo_{nota['id']}")
                novo_conteudo = st.text_area(
                    "Conteúdo", value=nota["conteudo"], key=f"conteudo_{nota['id']}", height=150
                )
                novas_tags = st.text_input("Tags", value=nota["tags"], key=f"tags_{nota['id']}")
                if st.button("Salvar alterações", key=f"save_{nota['id']}"):
                    atualizar_nota(nota["id"], novo_titulo.strip(), novo_conteudo.strip(), novas_tags.strip())
                    st.success("Atualizado!")
                    st.rerun()

# ---------------------------------------------------------------------------
# Página: Buscar (sem IA — funciona sempre)
# ---------------------------------------------------------------------------
elif pagina == "🔍 Buscar":
    st.header("Buscar nas suas notas")
    consulta = st.text_input("O que você está procurando?")

    if consulta:
        notas = listar_notas()
        resultados = buscar_por_relevancia(notas, consulta, top_k=10)

        if not resultados:
            st.info("Nenhum resultado por relevância — tentando busca por palavra-chave.")
            resultados = [dict(r, relevancia=None) for r in buscar_por_palavra_chave(consulta)]

        if not resultados:
            st.warning("Nenhuma nota encontrada.")
        else:
            for r in resultados:
                selo = f" · relevância {r['relevancia']:.2f}" if r.get("relevancia") else ""
                with st.expander(f"**{r['titulo']}**{selo}"):
                    st.write(r["conteudo"])

# ---------------------------------------------------------------------------
# Página: Perguntar à IA (requer chave da Groq)
# ---------------------------------------------------------------------------
elif pagina == "💬 Perguntar à IA":
    st.header("Pergunte às suas notas")

    if not groq_key:
        st.info(
            "Adicione sua chave da Groq na barra lateral para usar essa funcionalidade. "
            "É grátis: crie a sua em https://console.groq.com"
        )
    else:
        pergunta = st.text_input(
            "O que você quer saber?",
            placeholder="Ex: o que eu decidi sobre o projeto X em março?",
        )
        if pergunta:
            notas = listar_notas()
            relevantes = buscar_por_relevancia(notas, pergunta, top_k=5)

            if not relevantes:
                st.warning("Não encontrei notas relacionadas a essa pergunta.")
            else:
                with st.spinner("Pensando..."):
                    try:
                        modelo = MODELOS_DISPONIVEIS[modelo_label]
                        resposta = perguntar_as_notas(groq_key, pergunta, relevantes, modelo)
                        st.markdown(resposta)
                        with st.expander("📎 Notas usadas como contexto"):
                            for n in relevantes:
                                st.markdown(f"- **{n['titulo']}**")
                    except Exception as e:
                        st.error(f"Erro ao consultar a IA: {e}")
