from dataclasses import dataclass
from typing import Any

import httpx

from config import settings
from services.utils import Signer


@dataclass(frozen=True)
class RagResult:
    context: str = ""
    score: float | None = None
    relevant: bool = False
    reason: str = "no_result"


class RagService:
    def __init__(self) -> None:
        self.ak = settings.VOLC_AK
        self.sk = settings.VOLC_SK
        self.collection_name = settings.KB_COLLECTION_NAME
        self.project_name = settings.KB_PROJECT_NAME
        self.account_id = settings.VOLC_ACCOUNT_ID

        self.host = "api-knowledgebase.mlp.cn-beijing.volces.com"
        self.region = "cn-north-1"
        self.service = "air"

    @staticmethod
    def _as_float(value: Any) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    async def retrieve_result(self, query: str) -> RagResult:
        """Retrieve one candidate and decide whether it is reliable enough for RAG."""
        if not self.ak or not self.sk or not self.account_id:
            print(
                "[RagService] Configuration missing: check "
                f"VOLC_AK, VOLC_SK, VOLC_ACCOUNT_ID (account: {self.account_id})"
            )
            return RagResult(reason="configuration_missing")

        path = "/api/knowledge/collection/search_knowledge"
        body = {
            "project": self.project_name,
            "name": self.collection_name,
            "query": query,
            "limit": 1,
            "pre_processing": {
                "need_instruction": True,
                "return_token_usage": True,
                "messages": [{"role": "user", "content": query}],
            },
            "post_processing": {
                "get_attachment_link": True,
                "rerank_switch": False,
            },
        }
        headers = {
            "Host": self.host,
            "Content-Type": "application/json",
            "V-Account-Id": self.account_id,
        }
        request_data = {
            "method": "POST",
            "path": path,
            "headers": headers,
            "body": body,
            "params": {},
        }

        try:
            signer = Signer(request_data, service=self.service, region=self.region)
            signer.add_authorization(
                {"accessKeyId": self.ak, "secretKey": self.sk}
            )

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://{self.host}{path}",
                    headers=request_data["headers"],
                    json=body,
                    timeout=10.0,
                )

            if response.status_code != 200:
                print(
                    f"[RagService] Request failed: {response.status_code}, "
                    f"{response.text}"
                )
                return RagResult(reason="request_failed")

            result_list = response.json().get("data", {}).get("result_list", [])
            candidates = [item for item in result_list if item.get("content")]
            if not candidates:
                print("[RagService] No knowledge candidate was returned")
                return RagResult(reason="no_result")

            candidate = candidates[0]
            score = self._as_float(candidate.get("rerank_score"))
            if score is None:
                score = self._as_float(candidate.get("score"))

            context = str(candidate.get("content", "")).strip()
            if len(context) > settings.KB_MAX_CONTEXT_CHARS:
                context = (
                    context[: settings.KB_MAX_CONTEXT_CHARS]
                    + "\n\n[知识库内容过长，已截断]"
                )

            has_score = score is not None
            relevant = has_score and score >= settings.KB_MIN_RELEVANCE_SCORE

            reason = "relevant" if relevant else (
                "score_missing" if not has_score else "score_below_threshold"
            )
            score_display = f"{score:.4f}" if score is not None else "missing"
            print(
                "[RagService] Candidate: "
                f"score={score_display}, "
                f"threshold={settings.KB_MIN_RELEVANCE_SCORE:.4f}, "
                f"relevant={relevant}, reason={reason}"
            )
            print(f"[RagService] Candidate preview: {context[:120]}")

            return RagResult(
                context=context,
                score=score,
                relevant=relevant,
                reason=reason,
            )
        except Exception as exc:
            print(f"[RagService] Exception: {exc}")
            return RagResult(reason="exception")

    async def retrieve(self, query: str) -> str:
        """Compatibility wrapper: only return context that passed relevance gating."""
        result = await self.retrieve_result(query)
        return result.context if result.relevant else ""


rag_service = RagService()
