from __future__ import annotations

from typing import Any


DEFAULT_UNET = "flux-2-klein-base-4b-fp8.safetensors"
DEFAULT_CLIP = "qwen_3_4b.safetensors"
DEFAULT_VAE = "full_encoder_small_decoder.safetensors"


def build_flux2_klein_edit_workflow(
    *,
    prompt: str,
    seed: int,
    input_name: str,
    filename_prefix: str,
    steps: int = 28,
    cfg: float = 5.0,
) -> dict[str, dict[str, Any]]:
    """Build a native ComfyUI API workflow for one-reference FLUX.2 Klein editing."""
    return {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": DEFAULT_UNET, "weight_dtype": "default"},
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": DEFAULT_CLIP, "type": "flux2", "device": "default"},
        },
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": DEFAULT_VAE}},
        "4": {"class_type": "LoadImage", "inputs": {"image": input_name}},
        "5": {
            "class_type": "ImageScaleToTotalPixels",
            "inputs": {
                "image": ["4", 0],
                "upscale_method": "nearest-exact",
                "megapixels": 1.0,
                "resolution_steps": 1,
            },
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["2", 0], "text": prompt},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["2", 0], "text": ""},
        },
        "8": {
            "class_type": "VAEEncode",
            "inputs": {"pixels": ["5", 0], "vae": ["3", 0]},
        },
        "9": {
            "class_type": "ReferenceLatent",
            "inputs": {"conditioning": ["6", 0], "latent": ["8", 0]},
        },
        "10": {
            "class_type": "ReferenceLatent",
            "inputs": {"conditioning": ["7", 0], "latent": ["8", 0]},
        },
        "11": {"class_type": "RandomNoise", "inputs": {"noise_seed": int(seed)}},
        "12": {
            "class_type": "EmptyFlux2LatentImage",
            "inputs": {"width": 1536, "height": 1024, "batch_size": 1},
        },
        "13": {
            "class_type": "CFGGuider",
            "inputs": {
                "model": ["1", 0],
                "positive": ["9", 0],
                "negative": ["10", 0],
                "cfg": float(cfg),
            },
        },
        "14": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "15": {
            "class_type": "Flux2Scheduler",
            "inputs": {"steps": int(steps), "width": 1536, "height": 1024},
        },
        "16": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["11", 0],
                "guider": ["13", 0],
                "sampler": ["14", 0],
                "sigmas": ["15", 0],
                "latent_image": ["12", 0],
            },
        },
        "17": {
            "class_type": "SaveImage",
            "inputs": {
                "images": ["18", 0],
                "filename_prefix": filename_prefix,
            },
        },
        "18": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["16", 0], "vae": ["3", 0]},
        },
    }


QWEN_EDIT_UNET = "qwen_image_edit_fp8_e4m3fn.safetensors"
QWEN_EDIT_CLIP = "qwen_2.5_vl_7b_fp8_scaled.safetensors"
QWEN_EDIT_VAE = "qwen_image_vae.safetensors"
QWEN_EDIT_LIGHTNING_LORA = "Qwen-Image-Lightning-4steps-V1.0.safetensors"


def build_qwen_image_edit_workflow(
    *, prompt: str, seed: int, input_name: str, filename_prefix: str
) -> dict[str, dict[str, Any]]:
    """Build a pinned four-step Qwen Image Edit API workflow."""
    for field, value in {
        "prompt": prompt,
        "input_name": input_name,
        "filename_prefix": filename_prefix,
    }.items():
        if not value.strip():
            raise ValueError(f"{field} must not be empty")
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": QWEN_EDIT_UNET, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": QWEN_EDIT_CLIP, "type": "qwen_image", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": QWEN_EDIT_VAE}},
        "4": {"class_type": "LoadImage", "inputs": {"image": input_name}},
        "5": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["1", 0], "lora_name": QWEN_EDIT_LIGHTNING_LORA, "strength_model": 1.0}},
        "6": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["5", 0], "shift": 3.0}},
        "7": {"class_type": "CFGNorm", "inputs": {"model": ["6", 0], "strength": 1.0}},
        "8": {"class_type": "TextEncodeQwenImageEdit", "inputs": {"clip": ["2", 0], "prompt": prompt, "vae": ["3", 0], "image": ["4", 0]}},
        "9": {"class_type": "TextEncodeQwenImageEdit", "inputs": {"clip": ["2", 0], "prompt": "", "vae": ["3", 0], "image": ["4", 0]}},
        "10": {"class_type": "VAEEncode", "inputs": {"pixels": ["4", 0], "vae": ["3", 0]}},
        "12": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["7", 0], "seed": int(seed), "steps": 4, "cfg": 1.0,
                "sampler_name": "euler", "scheduler": "simple",
                "positive": ["8", 0], "negative": ["9", 0],
                "latent_image": ["10", 0], "denoise": 1.0,
            },
        },
        "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["3", 0]}},
        "15": {"class_type": "SaveImage", "inputs": {"images": ["13", 0], "filename_prefix": filename_prefix}},
    }
