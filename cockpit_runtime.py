from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Callable

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI


STYLE = """<style>
:root{--steel:#182026;--steel-2:#242f36;--line:#39464e;--orange:#ff6b24;--paper:#f3f5f6;--muted:#78858d}
.stApp{background:linear-gradient(180deg,#eef1f2 0,#f7f8f8 18rem)}
.block-container{padding-top:1.05rem;max-width:1680px}
[data-testid=stMetric]{background:#fff;border:1px solid #d9dee1;border-top:3px solid var(--orange);border-radius:5px;padding:10px 13px;box-shadow:0 4px 14px #1820260d}
.kicker{font:800 .72rem/1.2 sans-serif;letter-spacing:.14em;color:#bd4a15}.title{font-size:1.78rem;font-weight:850;color:#172027}.subtitle,.tiny{color:#68757d}.tiny{font-size:.76rem}.card{border:1px solid #dce1e3;border-radius:5px;padding:11px;background:#fff;margin-bottom:8px}.label{font-size:.72rem;color:#748087;text-transform:uppercase;letter-spacing:.04em}.value{font-size:1.03rem;font-weight:780;color:#172027}
div.stButton>button{border-radius:4px;text-align:left;justify-content:flex-start;white-space:normal;height:auto;min-height:2.75rem;border-color:#cfd6da}
div.stButton>button[kind=primary]{background:var(--orange);border-color:var(--orange);color:white}
.st-key-chat_console{background:var(--steel);border:1px solid #11181c;border-top:4px solid var(--orange);border-radius:6px;padding:.45rem .7rem;box-shadow:0 10px 28px #17202720}
.st-key-chat_console h4,.st-key-chat_console p{color:#edf2f3}.st-key-chat_console [data-testid=stCaptionContainer] p{color:#aebbc1}
.st-key-chat_console [data-testid=stChatMessage]{border-radius:5px;padding:.45rem .7rem;margin-bottom:.55rem;background:#f8fafb;color:#172027}
.st-key-chat_console [data-testid=stChatMessage] p{color:#172027}.st-key-chat_console [data-testid=stChatMessage]:has([data-testid=chatAvatarIcon-user]){background:#313e46;border-left:3px solid var(--orange)}
.st-key-chat_console [data-testid=stChatMessage]:has([data-testid=chatAvatarIcon-user]) p{color:#fff}
@media(max-width:740px){.block-container{padding:.65rem .65rem 5rem}.title{font-size:1.35rem}[data-testid=stMetric],.st-key-secondary_left,.st-key-secondary_context{display:none!important}.st-key-chat_console{min-height:calc(100dvh - 11rem);padding:.25rem}.subtitle{font-size:.82rem}.st-key-chat_console [data-testid=stVerticalBlockBorderWrapper]{height:auto!important;min-height:62dvh}body{overflow-x:hidden}}
</style>"""


def render_cockpit(*, base_dir: Path, page_title: str, icon: str, title: str, subtitle: str,
                   repository: Any, registry: Any, agent_factory: Callable[[Any, str, Any], Any],
                   question_groups: dict[str, list[str]], welcome_message: dict[str, Any],
                   timestamp: Callable[[], str], history_fn: Callable[..., list[dict[str, str]]],
                   metrics: list[tuple[str, str]], entity_label: str, entity_ids: list[str],
                   snapshot_builder: Callable[[str], dict[str, Any]], knowledge_label: str,
                   knowledge_base_name: str, source_label: str, chat_placeholder: str,
                   safety_note: str) -> None:
    load_dotenv()
    st.set_page_config(page_title=page_title, page_icon=icon, layout="wide", initial_sidebar_state="collapsed")
    st.markdown(STYLE, unsafe_allow_html=True)
    first_group = next(iter(question_groups))
    server_key = os.getenv("OPENAI_API_KEY", "").strip()
    default_model = os.getenv("OPENAI_MODEL", "gpt-5.6").strip() or "gpt-5.6"
    defaults = {"messages":[welcome_message.copy()],"vector_store_id":None,"uploaded_names":[],"previous_response_id":None,
                "pending_question":None,"question_group":first_group,
                "agent_settings":{"api_key": server_key, "key_source": "server" if server_key else "none", "model": default_model, "max_results": 6}}
    for key, default in defaults.items():
        if key not in st.session_state: st.session_state[key] = default

    with st.sidebar:
        st.header("⚙️ Agent 설정")
        settings = st.session_state.agent_settings
        current_key = settings["api_key"]
        masked = f"••••{current_key[-4:]}" if current_key else "연결 안 됨"
        source = "서버 기본 키" if settings["key_source"] == "server" else ("세션 전용 키" if settings["key_source"] == "session" else "키 없음")
        st.caption(f"{source} · {masked}")
        with st.expander("연결 설정 변경", expanded=False):
            with st.form("agent_settings_form", clear_on_submit=True):
                override = st.text_input("세션 API Key", type="password", placeholder="비우면 현재 키 유지")
                model_input = st.text_input("모델", value=settings["model"])
                result_input = st.slider("문서 검색 결과", 1, 20, int(settings["max_results"]))
                if st.form_submit_button("설정 적용", width="stretch"):
                    changed_key = bool(override.strip()) and override.strip() != settings["api_key"]
                    if override.strip():
                        settings["api_key"] = override.strip(); settings["key_source"] = "session"
                    settings["model"] = model_input.strip() or default_model
                    settings["max_results"] = result_input
                    if changed_key: st.session_state.previous_response_id = None
                    st.rerun()
            if settings["key_source"] == "session" and st.button("서버 기본 키로 복원", width="stretch"):
                settings["api_key"] = server_key; settings["key_source"] = "server" if server_key else "none"
                st.session_state.previous_response_id = None; st.rerun()
        api_key, model, max_results = settings["api_key"], settings["model"], int(settings["max_results"])
        st.divider(); st.subheader("📚 지식문서")
        uploads = st.file_uploader(knowledge_label, accept_multiple_files=True, type=["pdf","docx","txt","md","csv"])
        upload_agent = agent_factory(OpenAI(api_key=api_key, timeout=45.0, max_retries=2), model, registry) if api_key else None
        if st.button("문서 인덱싱", width="stretch", disabled=not uploads or not upload_agent):
            try:
                if not st.session_state.vector_store_id: st.session_state.vector_store_id = upload_agent.create_knowledge_base(knowledge_base_name)
                for uploaded in uploads:
                    temp_path = None
                    try:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded.name).suffix) as temp:
                            temp.write(uploaded.getbuffer()); temp_path = temp.name
                        upload_agent.add_file(st.session_state.vector_store_id, temp_path)
                        if uploaded.name not in st.session_state.uploaded_names: st.session_state.uploaded_names.append(uploaded.name)
                    finally:
                        if temp_path: Path(temp_path).unlink(missing_ok=True)
                st.success(f"{len(uploads)}개 문서 연결 완료")
            except Exception as exc: st.error(f"문서 인덱싱 실패: {exc}")
        st.caption("연결 문서: " + (", ".join(st.session_state.uploaded_names) if st.session_state.uploaded_names else "없음"))
        st.divider(); st.caption(safety_note)

    agent = agent_factory(OpenAI(api_key=api_key, timeout=45.0, max_retries=2), model, registry) if api_key else None
    st.markdown('<div class="kicker">MANUFACTURING AGENT COCKPIT</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="title">{title}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="subtitle">{subtitle}</div>', unsafe_allow_html=True)
    metric_cols = st.columns(len(metrics))
    for column, (label, value) in zip(metric_cols, metrics): column.metric(label, value)
    left, chat, context = st.columns([1.05,2.35,1.2], gap="medium")

    with left:
      with st.container(key="secondary_left"):
        with st.container(border=True):
            a,b=st.columns([1.6,1]); a.markdown("#### 대화 이력")
            if b.button("새 대화",width="stretch"):
                st.session_state.messages=[welcome_message.copy()]; st.session_state.previous_response_id=None; st.rerun()
            history=history_fn(st.session_state.messages)
            if not history: st.caption("아직 질문이 없습니다.")
            for i,item in enumerate(history):
                label=item["content"] if len(item["content"])<=38 else item["content"][:38]+"…"
                if st.button(f"💬 {label}",key=f"history_{i}",width="stretch",help=item["created_at"]): st.session_state.pending_question=item["content"]; st.rerun()
        with st.container(border=True):
            st.markdown("#### 추천 질문")
            group=st.segmented_control("업무 영역",list(question_groups),default=st.session_state.question_group,label_visibility="collapsed")
            if group: st.session_state.question_group=group
            for i,q in enumerate(question_groups[st.session_state.question_group]):
                if st.button(q,key=f"suggestion_{st.session_state.question_group}_{i}",width="stretch"): st.session_state.pending_question=q; st.rerun()
            st.markdown('<div class="tiny">추천질문은 채팅으로 전달되며, 위험 조치는 승인 담당자와 함께 안내됩니다.</div>',unsafe_allow_html=True)

    with context:
      with st.container(key="secondary_context"):
        with st.container(border=True):
            st.markdown(f"#### {entity_label} 상황")
            entity_id=st.selectbox(entity_label,entity_ids,label_visibility="collapsed")
            snap=snapshot_builder(entity_id)
            st.markdown(f'<div class="card"><div class="label">종합 위험</div><div class="value">{snap["icon"]} {snap["risk"]}</div></div>',unsafe_allow_html=True)
            st.markdown(f'<div class="card"><div class="label">{snap["primary_label"]}</div><div class="value">{snap["primary"]}</div></div>',unsafe_allow_html=True)
            if snap.get("progress") is not None: st.progress(float(snap["progress"])/100,text=f"진척 {float(snap['progress']):.0f}%")
            st.caption(snap["caption"])
            count_cols=st.columns(len(snap["counts"]))
            for column,(label,value) in zip(count_cols,snap["counts"]): column.metric(label,value)
            if st.button(f"이 {entity_label} 브리핑",width="stretch",type="primary"): st.session_state.pending_question=snap["brief"]; st.rerun()
        with st.container(border=True):
            st.markdown("#### 승인 대기")
            if snap["approvals"]:
                for item in snap["approvals"]: st.write("• "+item)
            else: st.success("현재 주요 승인 대기 없음")
            st.markdown('<div class="tiny">Agent는 조회·분석·권고만 수행합니다.</div>',unsafe_allow_html=True)
        with st.expander("지식 · Data Hub", expanded=False):
            knowledge_tab, data_tab, rule_tab = st.tabs(["지식", "DB", "규칙"])
            with knowledge_tab:
                keyword = st.text_input("지식문서 검색", placeholder="예: 도면 개정, 소재 대체", key="knowledge_keyword")
                docs = repository.search_knowledge(keyword, 5) if keyword else repository.knowledge_documents()
                if docs:
                    labels = [f"{row['document_id']} · {row.get('title', row.get('filename'))}" for row in docs]
                    chosen = st.selectbox("문서", labels, label_visibility="collapsed")
                    row = docs[labels.index(chosen)]
                    st.caption(f"{row.get('status','-')} · {row.get('owner','-')} · {row.get('revision','-')}")
                    if row.get("text"): st.write(row["text"])
                else: st.info("검색 결과가 없습니다.")
            with data_tab:
                catalog = repository.table_catalog()
                options = {f"{row['label']} ({row['rows']})": row["table"] for row in catalog}
                selected = st.selectbox("테이블", list(options), label_visibility="collapsed")
                rows = repository.browse_table(options[selected], 20, 0)
                if rows: st.dataframe(rows, width="stretch", hide_index=True)
                else: st.info("표시할 레코드가 없습니다.")
            with rule_tab:
                rules = repository.rules(None)
                for rule in rules:
                    st.markdown(f"**{rule['rule_id']} · {rule['name']}**")
                    st.caption(f"{rule['status']} · 담당 {rule['owner']} · 근거 {rule['source_document']}")
                    st.write(rule["action"])

    with chat:
      with st.container(key="chat_console"):
        with st.container(border=False,height=690):
            status_text = "ONLINE · Data Hub + 지식검색" if agent else "DEMO · API 키 연결 대기"
            st.markdown(f"#### Agent 대화  ·  `{status_text}`")
            if not agent: st.info("API 키를 설정하면 자연어 대화를 시작할 수 있습니다. 추천질문과 현장 상황은 미리 볼 수 있습니다.")
            for msg in st.session_state.messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"]); grounds=list(msg.get("sources",[]))
                    if msg.get("data_tools"): grounds.append(source_label+": "+", ".join(msg["data_tools"]))
                    if grounds: st.caption("근거 · "+" · ".join(grounds))
                    if msg.get("role") == "assistant" and msg.get("searched_documents") is False and msg.get("data_tools"):
                        st.warning("이 답변은 지식문서를 검색하지 않았습니다. 절차·기준 질문은 문서 근거를 추가로 확인하세요.")
                    if msg.get("evidence"):
                        with st.expander("검색 문서 근거"):
                            for evidence in msg["evidence"]: st.markdown(f"**{evidence['filename']}**"); st.write(evidence.get("text") or "검색 텍스트 미제공")
      typed=st.chat_input(chat_placeholder,disabled=agent is None)

    question=st.session_state.pop("pending_question",None) or typed
    if question:
        if not agent: st.toast("질문을 실행하려면 API 키를 먼저 설정하세요.",icon="🔑")
        else:
            st.session_state.messages.append({"role":"user","content":question,"created_at":timestamp()})
            try:
                answer=agent.ask(question,vector_store_id=st.session_state.vector_store_id,previous_response_id=st.session_state.previous_response_id,max_results=max_results)
                st.session_state.messages.append({"role":"assistant","content":answer.text,"sources":answer.sources,"evidence":answer.evidence,"data_tools":answer.data_tools,"searched_documents":answer.searched_documents,"created_at":timestamp()}); st.session_state.previous_response_id=answer.response_id
            except Exception as exc: st.session_state.messages.append({"role":"assistant","content":f"답변 생성에 실패했습니다: {exc}","created_at":timestamp()})
            st.rerun()
