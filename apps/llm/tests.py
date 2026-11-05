from asgiref.sync import async_to_sync
from django.test import SimpleTestCase, override_settings

from .base import ChatMessage
from .factory import get_llm, reset_llm_cache
from .mock import EMBEDDING_DIMENSION, MockLLM
from .tokens import estimate_tokens


class MockProviderTests(SimpleTestCase):
    def setUp(self):
        self.llm = MockLLM(delay=0)

    def test_stream_yields_content_and_usage(self):
        async def collect():
            chunks = []
            async for chunk in self.llm.stream_chat([ChatMessage("user", "hello")], model="mock-1"):
                chunks.append(chunk)
            return chunks

        chunks = async_to_sync(collect)()
        text = "".join(chunk.delta for chunk in chunks)
        self.assertIn("hello", text)
        self.assertTrue(chunks[-1].prompt_tokens)
        self.assertTrue(chunks[-1].completion_tokens)

    def test_complete_returns_answer(self):
        result = async_to_sync(self.llm.complete)([ChatMessage("user", "hi")])
        self.assertIn("hi", result.content)
        self.assertGreater(result.completion_tokens, 0)

    def test_embeddings_are_deterministic_and_normalized(self):
        vectors = async_to_sync(self.llm.embed)(["hello world", "hello world", "other"])
        self.assertEqual(len(vectors[0]), EMBEDDING_DIMENSION)
        self.assertEqual(vectors[0], vectors[1])
        self.assertNotEqual(vectors[0], vectors[2])
        norm = sum(value * value for value in vectors[0]) ** 0.5
        self.assertAlmostEqual(norm, 1.0, places=5)


class FactoryTests(SimpleTestCase):
    @override_settings(LLM_PROVIDER="mock")
    def test_mock_factory(self):
        reset_llm_cache()
        self.assertIsInstance(get_llm(), MockLLM)
        reset_llm_cache()

    def test_token_estimate(self):
        self.assertEqual(estimate_tokens(""), 0)
        self.assertEqual(estimate_tokens("abcd"), 1)
        self.assertGreater(estimate_tokens("a" * 400), 50)
