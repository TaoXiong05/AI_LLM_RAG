"""RAG demo：Streamlit + PostgreSQL(pgvector) + LangChain"""
import hmac
from html import escape

import streamlit as st

from backend import chunker, db, rag_chain
from backend.parser import UnsupportedFileTypeError, parse_file
from config import settings
from i18n import DEFAULT_LANG, get_strings

st.set_page_config(page_title="RAG Demo", page_icon="📚", layout="wide")

# ---------------------------------------------------------------------------
# 视觉主题："卡片目录 / 阅览室" —— 深色橡木抽屉侧栏用于归档文档，
# 主区分为对话桌面 + 常驻的引用索引卡侧栏，让检索到的原文片段
# 始终占据实际版面，而不是折叠在每条消息底部的 expander 里。
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Libre+Caslon+Text:wght@400;700&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

    :root {
        --paper: #F1E8D6;
        --card: #FBF7EC;
        --ink: #2A2116;
        --ink-muted: rgba(42, 33, 22, 0.64);
        --ink-faint: rgba(42, 33, 22, 0.42);
        --drawer: #E4D3A9;
        --drawer-panel: #D8C08D;
        --drawer-border: #A9824F;
        --brass: #93701F;
        --brass-bright: #B08A2E;
        --rule: #7FA0AC;
        --rule-faint: rgba(127, 160, 172, 0.32);
        --danger: #A23E2E;
        --success: #4B7052;
    }

    html, body, [class*="css"] { font-family: 'IBM Plex Sans', -apple-system, BlinkMacSystemFont, sans-serif; }
    h1, h2, h3, h4 { font-family: 'Libre Caslon Text', Georgia, serif; color: var(--ink); font-weight: 700; letter-spacing: -0.01em; }
    p, li, span, label, div { color: var(--ink); }
    code, .mono { font-family: 'IBM Plex Mono', monospace; }

    [data-testid="stAppViewContainer"] { background-color: var(--paper); }
    [data-testid="stHeader"] { background-color: transparent; }
    [data-testid="stMainBlockContainer"], .block-container { max-width: 1500px; padding-top: 2rem; padding-bottom: 6rem; }

    /* ---- 侧栏：与主区同色系的橡木抽屉（暖调浅棕，而非深色断层）---- */
    [data-testid="stSidebar"] { background-color: var(--drawer); border-right: 1px solid var(--drawer-border); }
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
        font-family: 'Libre Caslon Text', Georgia, serif; color: var(--ink) !important; font-size: 1.15rem;
    }
    .drawer-eyebrow {
        font-family: 'IBM Plex Mono', monospace; font-size: 0.68rem; letter-spacing: 0.14em;
        text-transform: uppercase; color: var(--brass); margin: 0 0 0.15rem 0;
    }
    .drawer-tab, .drawer-tab * {
        font-family: 'IBM Plex Mono', monospace; font-size: 0.7rem; letter-spacing: 0.1em;
        text-transform: uppercase; color: var(--brass) !important; border-bottom: none;
    }
    .drawer-tab {
        border-bottom: 1px solid var(--drawer-border);
        padding-bottom: 0.35rem; margin-bottom: 0.7rem; display: flex; justify-content: space-between; align-items: center;
    }
    [data-testid="stSidebar"] [data-testid="stVerticalBlockBorderWrapper"] {
        background-color: var(--card); border: 1px solid var(--drawer-border) !important; border-radius: 10px;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] { background-color: var(--card); border: 1px solid var(--drawer-border); border-radius: 10px; }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
        background-color: var(--drawer-panel); border: 1.5px dashed var(--drawer-border); border-radius: 8px;
    }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button {
        background-color: var(--card); border: 1px solid var(--brass); color: var(--brass);
    }
    [data-testid="stSidebar"] .stButton>button {
        background-color: var(--card); border: 1px solid var(--drawer-border); color: var(--ink);
        border-radius: 6px; font-family: 'IBM Plex Sans', sans-serif; white-space: nowrap;
    }
    [data-testid="stSidebar"] .stButton>button:hover { border-color: var(--brass); color: var(--brass); }
    [data-testid="stSidebar"] .stButton>button[kind="primary"] { background-color: var(--brass); border-color: var(--brass); color: var(--card); font-weight: 600; }
    [data-testid="stSidebar"] .stButton>button[kind="primary"]:hover { background-color: var(--brass-bright); border-color: var(--brass-bright); }
    [data-testid="stSidebar"] [data-baseweb="select"] > div,
    [data-testid="stSidebar"] input[type="text"], [data-testid="stSidebar"] input[type="password"] {
        background-color: var(--card) !important; color: var(--ink) !important; border-color: var(--drawer-border) !important;
    }
    [data-testid="stSidebar"] [data-testid="stAlert"] { border-radius: 8px; }
    [data-testid="stSidebar"] [data-testid="stDataFrame"] { border: 1px solid var(--drawer-border); border-radius: 8px; overflow: hidden; }

    /* ---- 主区通用 ---- */
    .stButton>button { border-radius: 8px; border: 1px solid rgba(42,33,22,0.16); color: var(--ink); background-color: var(--card); transition: all 0.15s ease; }
    .stButton>button:hover { border-color: var(--brass); color: var(--brass); background-color: var(--card); }
    .stButton>button[kind="primary"] { background-color: var(--brass); border-color: var(--brass); color: var(--card); font-weight: 600; }
    .stButton>button[kind="primary"]:hover { background-color: var(--brass-bright); border-color: var(--brass-bright); }

    [data-testid="stAlert"] { border-radius: 8px; border: 1px solid rgba(42,33,22,0.1); }
    [data-testid="stExpander"] { border: 1px solid rgba(42,33,22,0.14); border-radius: 10px; background-color: var(--card); }

    /* ---- 顶部标牌 ---- */
    .desk-plate {
        display: flex; justify-content: space-between; align-items: flex-end; gap: 1.5rem;
        border-bottom: 2px solid var(--ink); padding-bottom: 1rem; margin-bottom: 1.6rem; flex-wrap: wrap;
    }
    .desk-eyebrow { font-family: 'IBM Plex Mono', monospace; font-size: 0.72rem; letter-spacing: 0.16em; text-transform: uppercase; color: var(--brass); margin-bottom: 0.3rem; }
    .desk-title { font-size: 2rem; margin: 0; }
    .desk-subtitle { color: var(--ink-muted); font-size: 0.94rem; line-height: 1.6; margin: 0.35rem 0 0 0; max-width: 46rem; }
    .desk-stats { display: flex; gap: 0.6rem; flex-wrap: wrap; }
    .desk-stat-chip {
        font-family: 'IBM Plex Mono', monospace; font-size: 0.76rem; color: var(--ink);
        background-color: var(--card); border: 1px solid rgba(42,33,22,0.14); border-radius: 999px; padding: 0.35rem 0.85rem;
        white-space: nowrap;
    }

    /* ---- 聊天消息 ---- */
    [data-testid="stChatMessage"] {
        background-color: var(--card); border: 1px solid rgba(42,33,22,0.1); border-radius: 12px;
        padding: 0.9rem 1.1rem; margin-bottom: 0.75rem;
    }
    [data-testid="stChatInput"], [data-testid="stBottomBlockContainer"] { background-color: transparent; }
    [data-testid="stBottomBlockContainer"] { max-width: 1500px; margin: 0 auto; }
    [data-testid="stChatInput"] textarea { background-color: var(--card) !important; }
    .history-cite { font-family: 'IBM Plex Mono', monospace; font-size: 0.72rem; color: var(--ink-faint); margin: 0.35rem 0 0.2rem 0; }
    [data-testid="stChatMessageContent"] { padding-bottom: 0.4rem; }

    /* ---- 目录索引卡（右侧引用栏的招牌元素）---- */
    .catalog-card {
        position: relative; background-color: var(--card);
        border: 1px solid rgba(42,33,22,0.14); border-left: 3px solid var(--brass);
        border-radius: 10px; padding: 0.85rem 1rem 0.85rem 2rem; margin-bottom: 0.9rem;
    }
    .catalog-card::before {
        content: ""; position: absolute; left: 0.8rem; top: 1rem; width: 9px; height: 9px;
        border-radius: 50%; background-color: var(--paper); border: 1.5px solid var(--rule);
    }
    .catalog-card-tab {
        position: absolute; top: -9px; right: 12px; background-color: var(--brass); color: var(--card);
        font-family: 'IBM Plex Mono', monospace; font-size: 0.7rem; font-weight: 600; letter-spacing: 0.03em;
        padding: 2px 8px; border-radius: 4px;
    }
    .catalog-card-name { font-weight: 600; font-size: 0.9rem; padding-right: 2.2rem; margin-bottom: 0.15rem; word-break: break-word; }
    .catalog-card-meta { font-family: 'IBM Plex Mono', monospace; font-size: 0.7rem; color: var(--ink-faint); margin-bottom: 0.55rem; }
    .catalog-card-excerpt {
        font-size: 0.82rem; line-height: 1.55; color: var(--ink-muted); white-space: pre-wrap;
    }

    /* ---- 目录索引统计（右侧栏闲置状态）---- */
    .index-idle {
        background-color: var(--card); border: 1px solid rgba(42,33,22,0.14); border-radius: 12px;
        padding: 1.1rem 1.2rem; margin-bottom: 1rem;
    }
    .index-idle-title { font-family: 'Libre Caslon Text', Georgia, serif; font-size: 1.05rem; margin-bottom: 0.2rem; }
    .index-idle-hint { font-size: 0.82rem; color: var(--ink-muted); line-height: 1.55; }
    .index-stat-row { display: flex; gap: 0.7rem; margin: 0.9rem 0; }
    .index-stat { flex: 1; background-color: var(--paper); border-radius: 8px; padding: 0.6rem 0.7rem; }
    .index-stat-value { font-family: 'IBM Plex Mono', monospace; font-size: 1.3rem; font-weight: 600; color: var(--brass); line-height: 1; }
    .index-stat-label { font-size: 0.7rem; color: var(--ink-muted); margin-top: 0.25rem; }
    .index-doc-chip {
        display: flex; justify-content: space-between; gap: 0.6rem; font-size: 0.78rem;
        border-top: 1px solid rgba(42,33,22,0.1); padding: 0.4rem 0; color: var(--ink-muted);
    }
    .index-doc-chip b { color: var(--ink); font-weight: 500; }
    .index-doc-chip span:last-child { font-family: 'IBM Plex Mono', monospace; font-size: 0.72rem; white-space: nowrap; }

    /* Streamlit 的列内部包装 div 默认按内容自适应高度，flex 拉伸只作用到最外层的
       stColumn，不会往下传递，导致粘性元素自己的直接父级和它一样高、完全没有
       "浮动空间"。这里把这一路包装 div 都撑到 100% 高度，粘性定位才有效果。 */
    [data-testid="stColumn"]:has(.st-key-citation_rail) [data-testid="stVerticalBlock"]:not(.st-key-citation_rail) {
        height: 100%;
        /* 问答区与右侧"CITED FROM THE CATALOG"引用栏之间加一条细分隔线，贯穿整列高度 */
        border-left: 1px solid rgba(42, 33, 22, 0.16);
    }
    [data-testid="stColumn"]:has(.st-key-citation_rail) [data-testid="stLayoutWrapper"] {
        height: 100%;
    }
    .st-key-citation_rail { position: sticky; top: 1rem; flex-grow: 0; }
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

kb_sources = db.list_sources()
kb_doc_count = len(kb_sources)
kb_chunk_count = sum(s["chunk_count"] for s in kb_sources)


# ---------- 侧边栏：文档上传与知识库管理（"抽屉"）----------
with st.sidebar:
    header_col, lang_col = st.columns([2.1, 1.1])
    with header_col:
        st.markdown(f'<div class="drawer-eyebrow">{t["sidebar_eyebrow"]}</div>', unsafe_allow_html=True)
        st.header(t["sidebar_header"])
    if lang_col.button(t["lang_switch_button"]):
        st.session_state["lang"] = "zh" if st.session_state["lang"] == "en" else "en"
        st.rerun()

    with st.container(border=True):
        st.markdown(f'<div class="drawer-tab"><span>{t["upload_section_header"]}</span></div>', unsafe_allow_html=True)
        st.session_state.setdefault("uploader_key", 0)
        uploaded_files = st.file_uploader(
            t["upload_label"],
            type=["pdf", "docx", "txt", "png", "jpg", "jpeg", "webp", "bmp"],
            accept_multiple_files=True,
            key=f"uploader_{st.session_state['uploader_key']}",
            label_visibility="collapsed",
        )

        if st.button(t["process_button"], disabled=not uploaded_files, use_container_width=True, type="primary"):
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
        st.markdown(
            f'<div class="drawer-tab"><span>{t["kb_section_header"]}</span>'
            f'<span>{kb_doc_count}</span></div>',
            unsafe_allow_html=True,
        )
        if kb_sources:
            st.dataframe(kb_sources, hide_index=True, use_container_width=True)

            source_names = [s["source"] for s in kb_sources]
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


# ---------- 主区：书桌标牌 ----------
st.markdown(
    f"""
    <div class="desk-plate">
        <div>
            <div class="desk-eyebrow">{t['app_eyebrow']}</div>
            <h1 class="desk-title">{t['app_title']}</h1>
            <p class="desk-subtitle">{t['app_description']}</p>
        </div>
        <div class="desk-stats">
            <span class="desk-stat-chip">{t['kb_doc_count'].format(n=kb_doc_count)}</span>
            <span class="desk-stat-chip">{t['kb_chunk_count'].format(n=kb_chunk_count)}</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.info(f"⚠️ {t['privacy_notice']}", icon=None)

st.session_state.setdefault("messages", [])

# 提问来源：聊天输入框 或 下面点击的示例问题。
# st.chat_input 在根层级调用时会自动固定在视口底部，与代码书写位置无关，
# 因此这里提前拿到取值，方便在渲染两栏布局之前就把新问题检索完毕。
typed_question = st.chat_input(t["chat_input_placeholder"])
pending_question = st.session_state.pop("pending_question", None)
question = pending_question or typed_question

new_sources: list[tuple] | None = None
cited_sources: list[tuple] | None = None
if question:
    with st.spinner(t["searching_status"]):
        new_sources = rag_chain.retrieve(question, k=settings.top_k)


def render_catalog_cards(sources: list[tuple]) -> None:
    """右侧引用栏的招牌样式：把检索到的片段渲染成带孔洞与铜牌编号的索引卡。"""
    for i, (doc, score) in enumerate(sources, 1):
        source = escape(doc.metadata.get("source", t["unknown_source"]))
        excerpt = escape(doc.page_content)
        st.markdown(
            f"""<div class="catalog-card">
                <div class="catalog-card-tab">{i:02d}</div>
                <div class="catalog-card-name">📄 {source}</div>
                <div class="catalog-card-meta">{t['score_label']} · {score:.4f}</div>
                <div class="catalog-card-excerpt">{excerpt}</div>
            </div>""",
            unsafe_allow_html=True,
        )


def render_rail_idle() -> None:
    """右侧引用栏的空闲状态：知识库统计与已归档文档清单。"""
    ready = kb_doc_count > 0
    title = t["rail_idle_ready_title"] if ready else t["rail_idle_empty_title"]
    hint = t["rail_idle_ready_hint"] if ready else t["rail_idle_empty_hint"]
    doc_rows = "".join(
        f'<div class="index-doc-chip"><b>📄 {escape(s["source"])}</b>'
        f'<span>{t["kb_doc_chip_meta"].format(n=s["chunk_count"])}</span></div>'
        for s in kb_sources
    )
    st.markdown(
        f"""<div class="index-idle">
            <div class="drawer-eyebrow" style="color: var(--brass);">{t['rail_idle_eyebrow']}</div>
            <div class="index-idle-title">{title}</div>
            <div class="index-idle-hint">{hint}</div>
            <div class="index-stat-row">
                <div class="index-stat">
                    <div class="index-stat-value">{kb_doc_count}</div>
                    <div class="index-stat-label">{t['kb_section_header']}</div>
                </div>
                <div class="index-stat">
                    <div class="index-stat-value">{kb_chunk_count}</div>
                    <div class="index-stat-label">{t['chunk_stat_label']}</div>
                </div>
            </div>
            {doc_rows}
        </div>""",
        unsafe_allow_html=True,
    )
chat_col, rail_col = st.columns([0.62, 0.38], gap="large")

with chat_col:
    if not st.session_state["messages"] and not question:
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
                with st.expander(t["history_sources_label"].format(n=len(msg["sources"]))):
                    render_catalog_cards(msg["sources"])

    if question:
        with st.chat_message("user", avatar="🧑"):
            st.markdown(question)

        with st.chat_message("assistant", avatar="🤖"):
            try:
                stream = rag_chain.generate(question, new_sources, lang=st.session_state["lang"])
                full_answer = st.write_stream(stream)
            except Exception as exc:  # noqa: BLE001
                full_answer = t["llm_error"].format(error=exc)
                new_sources = []
                st.error(full_answer)

            # 只展示回答中真正引用（标注了 [i] 编号）的片段：
            # 检索结果只是候选，模型判定"未找到相关资料"且未引用任何编号时，
            # cited_sources 为空，不再出现"没找到却显示引用"的矛盾。
            if new_sources:
                cited_sources = rag_chain.select_cited_chunks(full_answer, new_sources)

            if cited_sources:
                st.markdown(
                    f'<div class="history-cite">{t["history_sources_label"].format(n=len(cited_sources))}</div>',
                    unsafe_allow_html=True,
                )

        st.session_state["messages"].append({"role": "user", "content": question, "sources": None})
        st.session_state["messages"].append(
            {"role": "assistant", "content": full_answer, "sources": cited_sources}
        )

with rail_col, st.container(key="citation_rail"):
    if question:
        # 本轮有问答：只展示回答真正引用（标注了 [i] 编号）的片段，
        # 未引用任何片段时回到空闲状态，避免"没找到却显示引用"。
        if cited_sources:
            st.markdown(f"##### {t['rail_sources_header']}")
            render_catalog_cards(cited_sources)
        else:
            render_rail_idle()
    elif st.session_state["messages"]:
        last_assistant = next(
            (m for m in reversed(st.session_state["messages"]) if m["role"] == "assistant" and m.get("sources")),
            None,
        )
        if last_assistant:
            st.markdown(f"##### {t['rail_sources_header']}")
            render_catalog_cards(last_assistant["sources"])
        else:
            render_rail_idle()
    else:
        render_rail_idle()
