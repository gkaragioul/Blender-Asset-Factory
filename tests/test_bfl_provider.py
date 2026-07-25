import tempfile
import unittest
from pathlib import Path

from factory.providers.bfl import BFLClient, BFLProviderError
from factory.io import sha256_file
from tests.temp_paths import temporary_root


class BFLProviderTest(unittest.TestCase):
    def test_pinned_multi_reference_generation_is_reproducible_and_hashed(self):
        calls = []

        def http_json(method, url, headers, payload):
            calls.append((method, url, headers, payload))
            if method == "POST":
                return {"id": "request-1", "polling_url": "https://poll.example/request-1"}
            return {
                "status": "Ready",
                "result": {"sample": "https://cdn.example/concept.png"},
            }

        def download(url, destination):
            self.assertEqual(url, "https://cdn.example/concept.png")
            destination.write_bytes(b"generated-concept")

        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            output = Path(temp) / "concept.png"
            client = BFLClient(
                "secret-test-key",
                http_json=http_json,
                download=download,
                sleep=lambda _seconds: None,
            )
            result = client.generate(
                prompt="A controlled benchmark concept",
                reference_urls=["https://ref/1.jpg", "https://ref/2.jpg", "https://ref/3.jpg"],
                output_path=output,
                seed=1234,
                width=1536,
                height=1024,
                timeout_seconds=30,
            )
            output_sha256 = sha256_file(output)

        post = calls[0]
        self.assertEqual(post[0], "POST")
        self.assertEqual(post[1], "https://api.bfl.ai/v1/flux-2-pro")
        self.assertEqual(post[2]["x-key"], "secret-test-key")
        self.assertEqual(post[3]["input_image"], "https://ref/1.jpg")
        self.assertEqual(post[3]["input_image_2"], "https://ref/2.jpg")
        self.assertEqual(post[3]["input_image_3"], "https://ref/3.jpg")
        self.assertEqual(post[3]["seed"], 1234)
        self.assertEqual(result["model"], "flux-2-pro")
        self.assertEqual(result["output_sha256"], output_sha256)
        self.assertEqual(len(result["prompt_sha256"]), 64)
        self.assertEqual(len(result["workflow_sha256"]), 64)
        self.assertNotIn("secret-test-key", str(result))

    def test_rejects_more_than_eight_reference_images(self):
        client = BFLClient(
            "secret",
            http_json=lambda *_args: {},
            download=lambda *_args: None,
            sleep=lambda _seconds: None,
        )
        with self.assertRaisesRegex(BFLProviderError, "eight"):
            client.generate(
                prompt="test",
                reference_urls=[f"https://ref/{index}.jpg" for index in range(9)],
                output_path=Path("unused.png"),
                seed=1,
            )


if __name__ == "__main__":
    unittest.main()
