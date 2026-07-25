import unittest

from factory.providers.comfyui import (
    build_flux2_klein_edit_workflow,
    build_qwen_image_edit_workflow,
)


class Flux2KleinWorkflowTests(unittest.TestCase):
    def test_builds_pinned_reference_conditioned_workflow(self):
        workflow = build_flux2_klein_edit_workflow(
            prompt="benchmark prompt",
            seed=4242,
            input_name="reference-contact-sheet.jpg",
            filename_prefix="benchmark/candidate-01",
        )

        self.assertEqual(workflow["1"]["class_type"], "UNETLoader")
        self.assertEqual(
            workflow["1"]["inputs"]["unet_name"],
            "flux-2-klein-base-4b-fp8.safetensors",
        )
        self.assertEqual(workflow["2"]["inputs"]["clip_name"], "qwen_3_4b.safetensors")
        self.assertEqual(workflow["2"]["inputs"]["type"], "flux2")
        self.assertEqual(
            workflow["3"]["inputs"]["vae_name"],
            "full_encoder_small_decoder.safetensors",
        )
        self.assertEqual(workflow["4"]["inputs"]["image"], "reference-contact-sheet.jpg")
        self.assertEqual(workflow["6"]["inputs"]["text"], "benchmark prompt")
        self.assertEqual(workflow["11"]["inputs"]["noise_seed"], 4242)
        self.assertNotIn("model", workflow["15"]["inputs"])
        self.assertEqual(workflow["17"]["inputs"]["filename_prefix"], "benchmark/candidate-01")
        self.assertEqual(workflow["9"]["class_type"], "ReferenceLatent")
        self.assertEqual(workflow["10"]["class_type"], "ReferenceLatent")


class QwenImageEditWorkflowTests(unittest.TestCase):
    def test_builds_pinned_object_rotation_workflow(self):
        workflow = build_qwen_image_edit_workflow(
            prompt="rotate the approved object to a direct front view",
            seed=8181,
            input_name="approved-c09.png",
            filename_prefix="benchmark/qwen-front",
        )
        self.assertEqual(workflow["1"]["inputs"]["unet_name"], "qwen_image_edit_fp8_e4m3fn.safetensors")
        self.assertEqual(workflow["2"]["inputs"]["clip_name"], "qwen_2.5_vl_7b_fp8_scaled.safetensors")
        self.assertEqual(workflow["3"]["inputs"]["vae_name"], "qwen_image_vae.safetensors")
        self.assertEqual(workflow["5"]["inputs"]["lora_name"], "Qwen-Image-Lightning-4steps-V1.0.safetensors")
        self.assertEqual(workflow["8"]["inputs"]["prompt"], "rotate the approved object to a direct front view")
        self.assertEqual(workflow["12"]["inputs"]["seed"], 8181)
        self.assertEqual(workflow["12"]["inputs"]["steps"], 4)
        self.assertEqual(workflow["15"]["inputs"]["filename_prefix"], "benchmark/qwen-front")


if __name__ == "__main__":
    unittest.main()
