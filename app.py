"""RAG demo：Streamlit + PostgreSQL(pgvector) + LangChain"""
import hmac

import streamlit as st

from backend import chunker, db, rag_chain
from backend.parser import UnsupportedFileTypeError, parse_file
from config import settings
from i18n import DEFAULT_LANG, get_strings

st.set_page_config(page_title="RAG Demo", page_icon="📚", layout="wide")

# Notion 风格：大量留白、中性灰白配色、克制的边框，不用装饰性背景/强调色。
st.markdown(
    """
    <style>
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue",
            Helvetica, Arial, sans-serif;
    }
    [data-testid="stAppViewContainer"] { background-color: #FFFFFF; }
    [data-testid="stHeader"] { background-color: transparent; }
    [data-testid="stSidebar"] {
        background-color: #F7F6F3;
        border-right: 1px solid #EDECE9;
    }
    [data-testid="stSidebar"] h2 { font-size: 1rem; font-weight: 600; color: #37352F; }
    .block-container { max-width: 1100px; padding-top: 3rem; margin: 0 auto; }
    [data-testid="stBottomBlockContainer"] { max-width: 1100px; margin: 0 auto; }
    h1, h2, h3 { color: #37352F; font-weight: 700; letter-spacing: -0.01em; }
    p, li, span, label { color: #37352F; }
    .stCaption, [data-testid="stCaptionContainer"] { color: rgba(55, 53, 47, 0.75) !important; }
    .app-subtitle {
        color: #57554E;
        font-size: 1rem;
        line-height: 1.6;
        margin: 0.2rem 0 1rem 0;
    }

    [data-testid="stChatMessage"] {
        padding: 0.7rem 0;
        border-radius: 0;
        border-bottom: 1px solid #EDECE9;
        margin-bottom: 0.4rem;
        background-color: transparent;
    }

    .stButton>button {
        border-radius: 6px;
        border: 1px solid #E9E9E7;
        color: #37352F;
        transition: background-color 0.15s ease;
    }
    .stButton>button:hover {
        background-color: #F1F1EF;
        border-color: #E9E9E7;
        color: #37352F;
    }
    .stButton>button[kind="primary"] {
        background-color: #37352F;
        border-color: #37352F;
        color: #FFFFFF;
    }
    .stButton>button[kind="primary"]:hover { background-color: #2F2E2A; }

    .source-card {
        border: 1px solid #E9E9E7;
        background-color: #FFFFFF;
        border-radius: 8px;
        padding: 0.6rem 0.9rem;
        margin-bottom: 0.5rem;
        transition: box-shadow 0.15s ease;
    }
    .source-card:hover { box-shadow: 0 1px 6px rgba(15, 15, 15, 0.08); }
    .source-card-header {
        display: flex;
        justify-content: space-between;
        font-size: 0.8rem;
        margin-bottom: 0.3rem;
        color: rgba(55, 53, 47, 0.65);
    }

    [data-testid="stExpander"] {
        border: 1px solid #E9E9E7;
        border-radius: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.session_state.setdefault("lang", DEFAULT_LANG)
t = get_strings(st.session_state["lang"])


@st.cache_resource
def init_backend() -> tuple[bool, str]:
    try:
        db.ensure_pgvector_extension()
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    return db.test_connection()


ok, err_msg = init_backend()
if not ok:
    st.error(t["db_error"].format(msg=err_msg))
    st.stop()

if not settings.openai_api_key or not settings.openai_api_key.isascii():
    st.error(t["api_key_error"])
    st.stop()


# ---------- 侧边栏：文档上传与知识库管理 ----------
with st.sidebar:
    header_col, lang_col = st.columns([3, 1])
    header_col.header(t["sidebar_header"])
    if lang_col.button(t["lang_switch_button"]):
        st.session_state["lang"] = "zh" if st.session_state["lang"] == "en" else "en"
        st.rerun()

    with st.container(border=True):
        st.markdown(f"**{t['upload_section_header']}**")
        st.session_state.setdefault("uploader_key", 0)
        uploaded_files = st.file_uploader(
            t["upload_label"],
            type=["pdf", "docx", "txt", "png", "jpg", "jpeg", "webp", "bmp"],
            accept_multiple_files=True,
            key=f"uploader_{st.session_state['uploader_key']}",
            label_visibility="collapsed",
        )

        if st.button(t["process_button"], disabled=not uploaded_files, use_container_width=True):
            total = len(uploaded_files)
            progress = st.progress(0)
            ok_count = 0
            chunk_count = 0
            warnings = []
            for i, f in enumerate(uploaded_files, 1):
                try:
                    parsed = parse_file(f)
                    chunks = chunker.chunk_document(parsed)
                    if not chunks:
                        warnings.append(t["skip_no_text"].format(name=f.name))
                        continue
                    db.add_documents(chunks)
                    ok_count += 1
                    chunk_count += len(chunks)
                except UnsupportedFileTypeError as exc:
                    warnings.append(t["skip_unsupported"].format(name=f.name, reason=exc))
                except Exception as exc:  # noqa: BLE001
                    warnings.append(t["skip_failed"].format(name=f.name, error=exc))
                progress.progress(i / total)

            st.session_state["ingest_warnings"] = warnings
            st.session_state["ingest_result"] = (
                ("success", t["process_success"].format(ok=ok_count, total=total, chunks=chunk_count))
                if ok_count
                else ("error", t["process_all_failed"])
            )
            # 换一个新的 widget key，让文件上传框和进度条在重新渲染时清空，只留下面持久化的结果提示
            st.session_state["uploader_key"] += 1
            st.rerun()

        for w in st.session_state.get("ingest_warnings", []):
            st.warning(w)
        if st.session_state.get("ingest_result"):
            level, msg = st.session_state["ingest_result"]
            getattr(st, level)(msg)

    with st.container(border=True):
        sources = db.list_sources()
        st.markdown(f"**{t['kb_section_header']}**")
        if sources:
            st.caption(t["kb_doc_count"].format(n=len(sources)))
            st.dataframe(sources, hide_index=True, use_container_width=True)

            source_names = [s["source"] for s in sources]
            selected_source = st.selectbox(t["select_doc_label"], source_names, key="selected_source")

            if not st.session_state.get("confirm_delete_doc"):
                if st.button(t["delete_doc_button"], key="delete_doc_btn", use_container_width=True):
                    st.session_state["confirm_delete_doc"] = True
                    st.session_state["pending_delete_source"] = selected_source
                    st.rerun()
            else:
                pending = st.session_state.get("pending_delete_source")
                st.warning(t["confirm_delete_doc_warning"].format(name=pending))
                dcol1, dcol2 = st.columns(2)
                if dcol1.button(t["confirm_delete_button"], type="primary", key="confirm_delete_doc_btn", use_container_width=True):
                    n = db.delete_source(pending)
                    st.session_state["confirm_delete_doc"] = False
                    st.session_state["delete_doc_result"] = t["delete_doc_success"].format(name=pending, n=n)
                    st.rerun()
                if dcol2.button(t["cancel_button"], key="cancel_delete_doc_btn", use_container_width=True):
                    st.session_state["confirm_delete_doc"] = False
                    st.rerun()
        else:
            st.caption(t["kb_empty"])

        if st.session_state.get("delete_doc_result"):
            st.success(st.session_state.pop("delete_doc_result"))

    with st.expander(t["danger_zone_header"]):
        if not st.session_state.get("confirm_clear"):
            if st.button(t["clear_kb_button"], key="clear_kb_btn", use_container_width=True):
                st.session_state["confirm_clear"] = True
                st.rerun()
        else:
            st.warning(t["confirm_clear_warning"])
            if not settings.clear_kb_password:
                st.error(t["clear_kb_password_not_configured"])
            else:
                st.session_state.setdefault("clear_kb_pw_key", 0)
                if st.session_state.pop("clear_kb_pw_wrong", False):
                    st.error(t["clear_kb_password_wrong"])
                entered_password = st.text_input(
                    t["clear_kb_password_label"],
                    type="password",
                    key=f"clear_kb_pw_{st.session_state['clear_kb_pw_key']}",
                )
                col1, col2 = st.columns(2)
                if col1.button(t["confirm_clear_button"], type="primary", key="confirm_clear_kb_btn", use_container_width=True):
                    if hmac.compare_digest(entered_password, settings.clear_kb_password):
                        n = db.clear_knowledge_base()
                        st.session_state["confirm_clear"] = False
                        st.session_state["messages"] = []
                        st.session_state["clear_kb_result"] = t["clear_success"].format(n=n)
                    else:
                        st.session_state["clear_kb_pw_wrong"] = True
                    st.session_state["clear_kb_pw_key"] += 1
                    st.rerun()
                if col2.button(t["cancel_button"], key="cancel_clear_kb_btn", use_container_width=True):
                    st.session_state["confirm_clear"] = False
                    st.session_state["clear_kb_pw_key"] += 1
                    st.rerun()

        if st.session_state.get("clear_kb_result"):
            st.success(st.session_state.pop("clear_kb_result"))


# ---------- 主区：聊天界面 ----------
st.markdown(f"<h1 style='margin-bottom:0.2rem'>{t['app_title']}</h1>", unsafe_allow_html=True)
st.markdown(f'<p class="app-subtitle">{t["app_description"]}</p>', unsafe_allow_html=True)
st.info(f"⚠️ {t['privacy_notice']}", icon=None)

st.session_state.setdefault("messages", [])


def render_sources(sources: list[tuple]) -> None:
    with st.expander(t["sources_expander"]):
        for doc, score in sources:
            source = doc.metadata.get("source", t["unknown_source"])
            st.markdown(
                f"""<div class="source-card">
                <div class="source-card-header">
                    <span>📄 <b>{source}</b></span>
                    <span>{t['score_label']}: {score:.4f}</span>
                </div>
                </div>""",
                unsafe_allow_html=True,
            )
            st.text(doc.page_content)


# 提问来源：聊天输入框 或 下面点击的示例问题
pending_question = st.session_state.pop("pending_question", None)

if not st.session_state["messages"] and not pending_question:
    st.markdown(f"##### {t['empty_state_title']}")
    st.caption(t["empty_state_subtitle"])
    example_cols = st.columns(len(t["example_questions"]))
    for col, example in zip(example_cols, t["example_questions"]):
        if col.button(example, key=f"example_{example}", use_container_width=True):
            st.session_state["pending_question"] = example
            st.rerun()

for msg in st.session_state["messages"]:
    avatar = "🧑" if msg["role"] == "user" else "🤖"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])
        if msg.get("sources"):
            render_sources(msg["sources"])

typed_question = st.chat_input(t["chat_input_placeholder"])
question = pending_question or typed_question
if question:
    st.session_state["messages"].append({"role": "user", "content": question, "sources": None})
    with st.chat_message("user", avatar="🧑"):
        st.markdown(question)

    with st.chat_message("assistant", avatar="🤖"):
        try:
            # 1) 检索阶段：显示"正在检索"动画。
            with st.status(t["searching_status"], expanded=False) as status:
                sources = rag_chain.retrieve(question, k=settings.top_k)
                status.update(label=t["searching_done"], state="complete", expanded=False)

            # 2) 生成阶段：直接在聊天区逐字流式输出（类似 DeepSeek/ChatGPT）。
            stream = rag_chain.generate(
                question, sources, lang=st.session_state["lang"]
            )
            full_answer = st.write_stream(stream)
        except Exception as exc:  # noqa: BLE001
            full_answer = t["llm_error"].format(error=exc)
            sources = []
            st.error(full_answer)

        if sources:
            render_sources(sources)

    st.session_state["messages"].append(
        {"role": "assistant", "content": full_answer, "sources": sources}
    )
