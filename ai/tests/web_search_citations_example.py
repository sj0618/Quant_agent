#!/usr/bin/env python3
"""
Azure AI Foundry Agent Service - Web Search Example

이전에는 모델 배포 엔드포인트(https://<resource>.openai.azure.com/openai/v1)에
tools=[{"type": "web_search_preview"}]를 직접 넘겨 웹 검색을 사용했지만,
조직 관리자가 구독 레벨에서 web_search 툴을 모델에 직접 붙이는 것을 차단하면
"Tool 'web_search_preview' disabled for this organization" 에러가 발생한다.

Foundry GUI에서도 안내하듯, 웹 검색 툴은 이제 모델이 아니라 "Agent"에만 붙일 수 있다.
따라서 Foundry 포털에서 웹 검색 툴을 붙여 만들어 둔 Agent(예: sol-omx-0711)를
azure-ai-projects SDK로 그대로 호출한다. AIProjectClient.get_openai_client(agent_name=...)가
"{endpoint}/agents/{agent_name}/endpoint/protocols/openai" 형태의 base_url과 Entra ID 인증을
자동으로 구성해주므로, 클라이언트 쪽에서 tools를 다시 지정할 필요가 없다
(툴은 이미 Agent 정의에 붙어 있음).

Requirements
------------
pip install -U azure-ai-projects azure-identity openai

Auth
----
DefaultAzureCredential을 사용하므로 로컬에서는 `az login`이 되어 있어야 하고,
CI/서버 환경에서는 AZURE_CLIENT_ID / AZURE_CLIENT_SECRET / AZURE_TENANT_ID 같은
서비스 주체 환경변수를 DefaultAzureCredential이 알아서 사용한다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from typing import Any

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient


PROJECT_ENDPOINT = os.environ.get("AZURE_AI_PROJECT_ENDPOINT", "")
AGENT_NAME = os.environ.get("AZURE_AI_AGENT_NAME", "sol-omx-0711")
SEARCH_PROMPT = "오늘 한국 증시 어땠는지 한 줄로 알려줘."

# instructions는 Agent 쪽(Foundry 포털)에 이미 설정되어 있어서 요청에
# instructions를 같이 보내면 "Not allowed when agent is specified" 400 에러가 난다.
# 시스템 지시문을 바꾸려면 포털에서 Agent 정의 자체를 수정해야 한다.

# ============================================================


@dataclass(frozen=True)
class WebCitation:
    title: str
    url: str
    start_index: int | None
    end_index: int | None


@dataclass(frozen=True)
class WebSearchResult:
    response_id: str | None
    answer: str
    citations: list[WebCitation]

    def to_dict(self):
        return {
            "response_id": self.response_id,
            "answer": self.answer,
            "citations": [asdict(x) for x in self.citations],
        }


def _extract_url_citations(response: Any):

    citations = []

    for item in getattr(response, "output", []) or []:

        if getattr(item, "type", None) != "message":
            continue

        for content in getattr(item, "content", []) or []:

            if getattr(content, "type", None) != "output_text":
                continue

            for ann in getattr(content, "annotations", []) or []:

                if getattr(ann, "type", None) != "url_citation":
                    continue

                citations.append(
                    WebCitation(
                        title=getattr(ann, "title", "") or "",
                        url=getattr(ann, "url", ""),
                        start_index=getattr(ann, "start_index", None),
                        end_index=getattr(ann, "end_index", None),
                    )
                )

    unique = {}

    for c in citations:
        unique[(c.url, c.start_index, c.end_index)] = c

    return list(unique.values())


def run_agent(prompt: str):

    project = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
        # Agent 전용 엔드포인트(agent_name)를 쓰려면 preview 기능 활성화가 필요.
        allow_preview=True,
    )

    client = project.get_openai_client(agent_name=AGENT_NAME)

    # tools를 여기서 다시 지정하지 않는다: 웹 검색 툴은 Foundry 포털에서
    # 이미 이 Agent(sol-omx-0711)의 정의에 붙어 있으므로 서버 사이드에서 처리된다.
    response = client.responses.create(
        input=prompt,
    )

    return WebSearchResult(
        response_id=response.id,
        answer=response.output_text,
        citations=_extract_url_citations(response),
    )


def main():

    result = run_agent(SEARCH_PROMPT)

    print("=" * 60)
    print(result.answer)
    print("=" * 60)

    print()

    if not result.citations:
        print("No citations.")
        return

    print("CITATIONS\n")

    for i, c in enumerate(result.citations, 1):
        print(f"[{i}] {c.title}")
        print(c.url)
        print()


if __name__ == "__main__":
    main()
