import json
import unittest

from routebr import OpenAICompatibleBackend


class OpenAICompatibleBackendTest(unittest.TestCase):
    def test_builds_common_json_request_without_logging_key(self):
        observed = {}

        def fake_transport(url, headers, body, timeout):
            observed.update(url=url, headers=headers, body=body, timeout=timeout)
            return {
                "id": "resp-1",
                "model": "reported-snapshot",
                "usage": {"prompt_tokens": 10, "completion_tokens": 4},
                "choices": [
                    {
                        "message": {
                            "content": '{"action_id":"A1","object_id":"NONE","topk":["A1"]}'
                        }
                    }
                ],
            }

        backend = OpenAICompatibleBackend(
            provider="test-provider",
            base_url="https://example.test/v1/",
            api_key="secret-test-key",
            model="fixed-model",
            stage_instructions={"ROUTEBR": "Return the RouteBR JSON object."},
            request_options={"temperature": 0},
            timeout_seconds=12,
            transport=fake_transport,
        )

        content = backend.complete("ROUTEBR", {"request": "测试"})

        self.assertEqual(json.loads(content)["action_id"], "A1")
        self.assertEqual(observed["url"], "https://example.test/v1/chat/completions")
        self.assertEqual(observed["body"]["response_format"], {"type": "json_object"})
        self.assertEqual(observed["body"]["temperature"], 0)
        self.assertNotIn("secret-test-key", repr(backend.calls))
        self.assertEqual(backend.responses[0]["reported_model"], "reported-snapshot")

    def test_repair_uses_original_frozen_instruction(self):
        def fake_transport(url, headers, body, timeout):
            return {"choices": [{"message": {"content": "{}"}}]}

        backend = OpenAICompatibleBackend(
            provider="test-provider",
            base_url="https://example.test/v1",
            api_key="secret-test-key",
            model="fixed-model",
            stage_instructions={"ROUTEBR": "Return RouteBR."},
            transport=fake_transport,
        )
        backend.complete("REPAIR_ROUTEBR", {"invalid_output": "bad"})
        system = backend.calls[0]["request_body"]["messages"][0]["content"]
        self.assertIn("Return RouteBR.", system)
        self.assertIn("Repair formatting only", system)

    def test_repair_prefers_dedicated_frozen_instruction(self):
        def fake_transport(url, headers, body, timeout):
            return {"choices": [{"message": {"content": "{}"}}]}

        backend = OpenAICompatibleBackend(
            provider="test-provider",
            base_url="https://example.test/v1",
            api_key="secret-test-key",
            model="fixed-model",
            stage_instructions={"ROUTEBR": "Return RouteBR.", "REPAIR": "Dedicated repair contract."},
            transport=fake_transport,
        )
        backend.complete("REPAIR_ROUTEBR", {"invalid_output": "bad"})
        system = backend.calls[0]["request_body"]["messages"][0]["content"]
        self.assertEqual(system, "Dedicated repair contract.")


if __name__ == "__main__":
    unittest.main()
