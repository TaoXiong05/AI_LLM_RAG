"""RAG demo：Streamlit + PostgreSQL(pgvector) + LangChain"""
import hmac

import streamlit as st

from backend import chunker, db, rag_chain
from backend.parser import UnsupportedFileTypeError, parse_file
from config import settings
from i18n import DEFAULT_LANG, get_strings

st.set_page_config(page_title="RAG Demo", layout="wide")

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

    st.session_state.setdefault("uploader_key", 0)
    uploaded_files = st.file_uploader(
        t["upload_label"],
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
        key=f"uploader_{st.session_state['uploader_key']}",
    )

    if st.button(t["process_button"], disabled=not uploaded_files):
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

    st.divider()
    st.subheader(t["kb_documents_header"])
    sources = db.list_sources()
    if sources:
        st.dataframe(sources, hide_index=True, use_container_width=True)

        source_names = [s["source"] for s in sources]
        selected_source = st.selectbox(t["select_doc_label"], source_names, key="selected_source")

        if not st.session_state.get("confirm_delete_doc"):
            if st.button(t["delete_doc_button"], key="delete_doc_btn"):
                st.session_state["confirm_delete_doc"] = True
                st.session_state["pending_delete_source"] = selected_source
                st.rerun()
        else:
            pending = st.session_state.get("pending_delete_source")
            st.warning(t["confirm_delete_doc_warning"].format(name=pending))
            dcol1, dcol2 = st.columns(2)
            if dcol1.button(t["confirm_delete_button"], type="primary", key="confirm_delete_doc_btn"):
                n = db.delete_source(pending)
                st.session_state["confirm_delete_doc"] = False
                st.session_state["delete_doc_result"] = t["delete_doc_success"].format(name=pending, n=n)
                st.rerun()
            if dcol2.button(t["cancel_button"], key="cancel_delete_doc_btn"):
                st.session_state["confirm_delete_doc"] = False
                st.rerun()
    else:
        st.caption(t["kb_empty"])

    if st.session_state.get("delete_doc_result"):
        st.success(st.session_state.pop("delete_doc_result"))

    st.divider()
    if not st.session_state.get("confirm_clear"):
        if st.button(t["clear_kb_button"], key="clear_kb_btn"):
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
            if col1.button(t["confirm_clear_button"], type="primary", key="confirm_clear_kb_btn"):
                if hmac.compare_digest(entered_password, settings.clear_kb_password):
                    n = db.clear_knowledge_base()
                    st.session_state["confirm_clear"] = False
                    st.session_state["messages"] = []
                    st.session_state["clear_kb_result"] = t["clear_success"].format(n=n)
                else:
                    st.session_state["clear_kb_pw_wrong"] = True
                st.session_state["clear_kb_pw_key"] += 1
                st.rerun()
            if col2.button(t["cancel_button"], key="cancel_clear_kb_btn"):
                st.session_state["confirm_clear"] = False
                st.session_state["clear_kb_pw_key"] += 1
                st.rerun()

    if st.session_state.get("clear_kb_result"):
        st.success(st.session_state.pop("clear_kb_result"))


# ---------- 主区：聊天界面 ----------
st.title(t["app_title"])
st.caption(t["app_description"])
st.warning(t["privacy_notice"], icon="⚠️")

st.session_state.setdefault("messages", [])


def render_sources(sources: list[tuple]) -> None:
    with st.expander(t["sources_expander"]):
        for doc, score in sources:
            source = doc.metadata.get("source", t["unknown_source"])
            st.markdown(f"**{source}**（{t['score_label']}：{score:.4f}）")
            st.text(doc.page_content)


for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sources"):
            render_sources(msg["sources"])

question = st.chat_input(t["chat_input_placeholder"])
if question:
    st.session_state["messages"].append({"role": "user", "content": question, "sources": None})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        try:
            stream, sources = rag_chain.answer_stream(
                question, k=settings.top_k, lang=st.session_state["lang"]
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
