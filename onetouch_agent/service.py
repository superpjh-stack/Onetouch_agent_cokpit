from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .citations import extract_evidence, extract_sources
from .factory_tools import OnetouchToolRegistry
from .prompts import AGENT_INSTRUCTIONS


@dataclass(frozen=True)
class AgentAnswer:
    text: str
    sources: list[str]
    evidence: list[dict[str, Any]]
    response_id: str | None
    data_tools: list[str]
    searched_documents: bool
    tool_rounds: int
    knowledge_base_connected: bool


class ManufacturingAgent:
    def __init__(self, client: Any, model: str = "gpt-5.6", factory_tools: OnetouchToolRegistry | None = None) -> None:
        self.client = client
        self.model = model
        self.factory_tools = factory_tools

    def create_knowledge_base(self, name: str = "원터치 CAD 견적 지식베이스") -> str:
        return self.client.vector_stores.create(name=name).id

    def add_file(self, vector_store_id: str, file_path: str | Path) -> Any:
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        with path.open("rb") as handle:
            return self.client.vector_stores.files.upload_and_poll(vector_store_id=vector_store_id, file=handle)

    def ask(self, question: str, vector_store_id: str | None = None,
            previous_response_id: str | None = None, max_results: int = 6) -> AgentAnswer:
        if not question.strip():
            raise ValueError("질문을 입력해 주세요.")
        tools: list[dict[str, Any]] = []
        include: list[str] = []
        if self.factory_tools:
            tools.extend(self.factory_tools.definitions)
        if vector_store_id:
            tools.append({"type": "file_search", "vector_store_ids": [vector_store_id], "max_num_results": max_results})
            include.append("file_search_call.results")
        if not tools:
            raise ValueError("견적 Data Hub 또는 지식문서를 연결해 주세요.")
        request: dict[str, Any] = {"model": self.model, "instructions": AGENT_INSTRUCTIONS,
                                   "input": question.strip(), "tools": tools, "parallel_tool_calls": False}
        if previous_response_id:
            request["previous_response_id"] = previous_response_id
        if include:
            request["include"] = include
        response = self.client.responses.create(**request)
        used_tools: list[str] = []
        sources: list[str] = []
        evidence: list[dict[str, Any]] = []
        searched_documents = False
        rounds = 0

        def collect(current: Any) -> None:
            for source in extract_sources(current):
                if source not in sources:
                    sources.append(source)
            for item in extract_evidence(current, limit=max_results):
                marker = (item.get("filename"), item.get("text"))
                if marker not in {(row.get("filename"), row.get("text")) for row in evidence}:
                    evidence.append(item)

        collect(response)
        for _ in range(4):
            calls = [item for item in getattr(response, "output", []) if getattr(item, "type", None) == "function_call"]
            if not calls:
                break
            rounds += 1
            outputs = []
            for call in calls:
                used_tools.append(call.name)
                result = self.factory_tools.execute(call.name, call.arguments) if self.factory_tools else '{"error":"Data Hub not connected"}'
                if call.name == "search_local_knowledge":
                    searched_documents = True
                    try:
                        payload = json.loads(result)
                        for row in payload.get("result", []):
                            item = {"filename": row.get("filename", "로컬 지식문서"), "score": row.get("score"), "text": row.get("text", ""), "document_id": row.get("document_id")}
                            if item not in evidence:
                                evidence.append(item)
                            if item["filename"] not in sources:
                                sources.append(item["filename"])
                    except (TypeError, json.JSONDecodeError):
                        pass
                outputs.append({"type": "function_call_output", "call_id": call.call_id, "output": result})
            follow_up: dict[str, Any] = {"model": self.model, "instructions": AGENT_INSTRUCTIONS,
                                         "previous_response_id": response.id, "input": outputs,
                                         "tools": tools, "parallel_tool_calls": False}
            if include:
                follow_up["include"] = include
            response = self.client.responses.create(**follow_up)
            collect(response)
            searched_documents = searched_documents or any(
                getattr(item, "type", None) == "file_search_call" for item in getattr(response, "output", [])
            )
        remaining_calls = [item for item in getattr(response, "output", []) if getattr(item, "type", None) == "function_call"]
        if remaining_calls:
            response = self.client.responses.create(
                model=self.model, instructions=AGENT_INSTRUCTIONS,
                previous_response_id=response.id,
                input="지금까지 조회한 근거만 사용해 최종 답변을 작성하세요.",
                tools=tools, tool_choice="none", parallel_tool_calls=False,
            )
            collect(response)
        text = (getattr(response, "output_text", "") or "현재 조회된 근거만으로 답변을 만들지 못했습니다. 담당자가 Data Hub 연결 상태를 확인해 주세요.").strip()
        return AgentAnswer(text, sources, evidence[:max_results], getattr(response, "id", None),
                           list(dict.fromkeys(used_tools)), searched_documents, rounds, bool(vector_store_id))
