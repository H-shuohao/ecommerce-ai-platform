import unittest
from types import SimpleNamespace
from unittest.mock import patch

from services.llm_service import LLMService


class FakeCompletions:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make_service(outcomes) -> tuple[LLMService, FakeCompletions]:
    completions = FakeCompletions(outcomes)
    service = object.__new__(LLMService)
    service.client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions),
    )
    return service, completions


class LLMResilienceTests(unittest.TestCase):
    @patch("services.llm_service.settings.LLM_RETRY_BACKOFF_SECONDS", 0)
    @patch("services.llm_service.settings.LLM_MAX_ATTEMPTS", 2)
    def test_complete_recovers_after_transient_failure(self) -> None:
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="恢复成功"))],
        )
        service, completions = make_service(
            [TimeoutError("temporary timeout"), response],
        )

        result = service.complete([{"role": "user", "content": "你好"}])

        self.assertEqual(result, "恢复成功")
        self.assertEqual(completions.calls, 2)

    @patch("services.llm_service.settings.LLM_RETRY_BACKOFF_SECONDS", 0)
    @patch("services.llm_service.settings.LLM_MAX_ATTEMPTS", 2)
    def test_complete_stops_after_configured_attempts(self) -> None:
        service, completions = make_service(
            [TimeoutError("first"), TimeoutError("second")],
        )

        with self.assertRaisesRegex(RuntimeError, "大模型调用失败"):
            service.complete([{"role": "user", "content": "你好"}])

        self.assertEqual(completions.calls, 2)

    @patch("services.llm_service.settings.LLM_RETRY_BACKOFF_SECONDS", 0)
    @patch("services.llm_service.settings.LLM_MAX_ATTEMPTS", 2)
    def test_stream_creation_recovers_before_any_text_is_sent(self) -> None:
        chunk = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content="流式恢复成功"),
                )
            ],
        )
        service, completions = make_service(
            [ConnectionError("temporary disconnect"), iter([chunk])],
        )

        result = list(
            service.complete_stream(
                [{"role": "user", "content": "你好"}],
            )
        )

        self.assertEqual(result, ["流式恢复成功"])
        self.assertEqual(completions.calls, 2)


if __name__ == "__main__":
    unittest.main()
