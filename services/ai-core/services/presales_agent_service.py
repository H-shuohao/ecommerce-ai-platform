import asyncio
import json
import re
from typing import Any

from app.schemas.agents import AgentChatResponse, ToolCallTrace
from app.tools.registry import tool_registry
from services.llm_service import llm_service
from services.rag_service import rag_service


PLANNER_PROMPT = """
你是电商售前 Agent 的工具规划器。根据用户问题和已经执行的工具结果，决定下一步。
只输出一个 JSON 对象，不要输出 Markdown、解释或其他文字。
格式：{"tool": "工具名或null", "arguments": {}}
每轮最多选择一个工具；如果已有信息足够回答，将 tool 设为 null。
如果用户要求“有库存”或查询库存，获得商品 ID 后必须继续调用 check_inventory。
同一轮中 check_inventory 已返回目标商品库存后，必须将 tool 设为 null，不要再搜索或重复查询。
工具参数只能使用工具定义中列出的精确参数名，不能创造 price_range 等未定义参数。
不能编造工具名称、参数或商品 ID，只能使用工具结果中真实出现的数据。
""".strip()


FINAL_PROMPT = """
你是电商售前咨询助手。请根据用户问题、工具结果和知识库资料回答。
工具返回的价格、库存、订单状态属于可靠业务数据，不得擅自修改。
没有查询到的事实要明确说明，不得编造。回答简洁，并说明推荐或判断依据。
""".strip()


class PresalesAgentService:
    max_tool_calls = 3
    stop_tool_names = {"", "null", "none", "nil", "no_tool"}
    terminal_tool_names = {"get_product", "check_inventory", "query_order"}

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise ValueError("模型没有返回有效 JSON")
        value = json.loads(text[start : end + 1])
        if not isinstance(value, dict):
            raise ValueError("工具计划必须是 JSON 对象")
        return value

    @classmethod
    def _should_stop_tool_loop(cls, tool_name: Any) -> bool:
        """Accept both JSON null and common string forms returned by an LLM."""
        if tool_name is None:
            return True
        return (
            isinstance(tool_name, str)
            and tool_name.strip().lower() in cls.stop_tool_names
        )

    @staticmethod
    def _requires_fresh_inventory(question: str) -> bool:
        return any(keyword in question for keyword in ("库存", "有货", "现货"))

    @staticmethod
    def _find_recent_product_id(
        question: str,
        history: list[dict[str, str]],
    ) -> str | None:
        contents = [message.get("content", "") for message in history]
        for content in reversed([*contents, question]):
            matches = re.findall(r"\bP\d+\b", content, flags=re.IGNORECASE)
            if matches:
                return matches[-1].upper()
        return None

    @staticmethod
    def _find_product_id(text: str) -> str | None:
        matches = re.findall(r"\bP\d+\b", text, flags=re.IGNORECASE)
        return matches[-1].upper() if matches else None

    async def run(
        self,
        question: str,
        history: list[dict[str, str]] | None = None,
        current_product_id: str | None = None,
    ) -> AgentChatResponse:
        conversation_history = history or []
        tool_definitions = [
            definition.model_dump()
            for definition in tool_registry.list_tools()
        ]
        traces: list[ToolCallTrace] = []
        executed_calls: set[str] = set()

        # A pronoun-based inventory follow-up already has a product selected in
        # conversation history. Route this deterministic case directly to the
        # live inventory tool instead of asking the LLM to rediscover it.
        direct_inventory_product_id = None
        if (
            self._requires_fresh_inventory(question)
            and self._find_product_id(question) is None
        ):
            direct_inventory_product_id = (
                current_product_id
                or self._find_recent_product_id(question, conversation_history)
            )
        if direct_inventory_product_id:
            arguments = {"product_id": direct_inventory_product_id}
            traces.append(
                ToolCallTrace(
                    tool="check_inventory",
                    arguments=arguments,
                    result=tool_registry.invoke("check_inventory", arguments),
                )
            )
        else:
            for _ in range(self.max_tool_calls):
                planner_context = {
                    "available_tools": tool_definitions,
                    "question": question,
                    "conversation_history": conversation_history,
                    "previous_tool_calls": [trace.model_dump() for trace in traces],
                }
                planner_messages = [
                    {"role": "system", "content": PLANNER_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(planner_context, ensure_ascii=False),
                    },
                ]
                plan_text = await asyncio.to_thread(
                    llm_service.complete,
                    planner_messages,
                    max_tokens=200,
                    temperature=0.0,
                )
                plan = self._extract_json(plan_text)
                print(f"[PresalesAgent] 第{len(traces) + 1}轮计划: {plan}")
                tool_name = plan.get("tool")
                arguments = plan.get("arguments") or {}
                if self._should_stop_tool_loop(tool_name):
                    inventory_already_checked = any(
                        trace.tool == "check_inventory" for trace in traces
                    )
                    if (
                        self._requires_fresh_inventory(question)
                        and not inventory_already_checked
                    ):
                        product_id = self._find_recent_product_id(
                            question,
                            conversation_history,
                        )
                        if product_id:
                            result = tool_registry.invoke(
                                "check_inventory",
                                {"product_id": product_id},
                            )
                            traces.append(
                                ToolCallTrace(
                                    tool="check_inventory",
                                    arguments={"product_id": product_id},
                                    result=result,
                                )
                            )
                            continue
                    break
                if not isinstance(tool_name, str) or not isinstance(arguments, dict):
                    raise ValueError("工具计划格式不正确")

                call_key = json.dumps(
                    {"tool": tool_name, "arguments": arguments},
                    ensure_ascii=False,
                    sort_keys=True,
                )
                if call_key in executed_calls:
                    raise ValueError("模型重复调用了相同工具和参数")
                executed_calls.add(call_key)

                result = tool_registry.invoke(tool_name, arguments)
                traces.append(
                    ToolCallTrace(tool=tool_name, arguments=arguments, result=result)
                )
                if tool_name in self.terminal_tool_names:
                    break

        # Structured business tools are authoritative for product, inventory,
        # and order facts. RAG is reserved for questions that were not handled
        # by those tools, avoiding an unrelated external retrieval round trip.
        rag_context = ""
        if not traces:
            rag_result = await rag_service.retrieve_result(question)
            rag_context = rag_result.context if rag_result.relevant else ""
        final_context = {
            "question": question,
            "conversation_history": conversation_history,
            "tool_calls": [trace.model_dump() for trace in traces],
            "rag_context": rag_context,
        }
        final_messages = [
            {"role": "system", "content": FINAL_PROMPT},
            {
                "role": "user",
                "content": json.dumps(final_context, ensure_ascii=False),
            },
        ]
        answer = await asyncio.to_thread(
            llm_service.complete,
            final_messages,
            max_tokens=400,
            temperature=0.1,
        )
        return AgentChatResponse(
            answer=answer,
            tool_calls=traces,
            rag_used=bool(rag_context),
        )


presales_agent_service = PresalesAgentService()
