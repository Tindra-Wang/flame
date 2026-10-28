"""Classical and real diffusion adapters; no silent model substitution."""
from pathlib import Path
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from .io import sha256


def photometric(image: Image.Image, seed: int):
    rng=np.random.default_rng(seed)
    brightness=float(rng.uniform(.8,1.2)); contrast=float(rng.uniform(.85,1.15)); blur=float(rng.uniform(0,.5))
    output=ImageEnhance.Brightness(image).enhance(brightness)
    output=ImageEnhance.Contrast(output).enhance(contrast).filter(ImageFilter.GaussianBlur(blur))
    array=np.asarray(output,dtype=float)+rng.normal(0,1.2,(image.height,image.width,3))
    return Image.fromarray(np.uint8(np.clip(array,0,255))),{"method":"classical_photometric_not_diffusion","brightness":brightness,"contrast":contrast,"blur_radius":blur,"seed":seed}


def weight_fingerprint(model_dir: Path) -> dict:
    files=sorted(p for p in model_dir.rglob("*") if p.is_file() and p.suffix in {".json",".safetensors",".bin",".ckpt"})
    if not files: raise ValueError("Model directory has no model files")
    return {str(p.relative_to(model_dir)):sha256(p) for p in files}


class SafetyRejected(RuntimeError):
    """The model rejected one candidate; it must not enter the dataset."""


class DiffusionEnhancer:
    def __init__(self, model_dir: str, device="cpu", strength=.25, steps=20):
        path=Path(model_dir).resolve()
        if not (path/"model_index.json").is_file():
            raise ValueError("Provide a local Diffusers model directory containing model_index.json")
        if not 0<strength<=1 or steps<1 or int(strength*steps)<1:
            raise ValueError("Diffusion strength/steps must yield at least one denoising step")
        try:
            import torch
            from diffusers import StableDiffusionImg2ImgPipeline
        except ImportError as exc:
            raise RuntimeError("Install the diffusion extra in this environment before requesting diffusion") from exc
        if device=="cuda" and not torch.cuda.is_available(): raise RuntimeError("CUDA requested but unavailable")
        self.torch=torch; self.device=device; self.strength=strength; self.steps=steps
        self.fingerprint=weight_fingerprint(path)
        options={"variant":"fp16"} if (path/"unet/diffusion_pytorch_model.fp16.safetensors").is_file() else {}
        self.pipeline=StableDiffusionImg2ImgPipeline.from_pretrained(str(path),local_files_only=True,torch_dtype=torch.float16 if device=="cuda" else torch.float32,**options).to(device)
        self.pipeline.enable_attention_slicing()

    def run(self,image,seed,prompt="a realistic environment, natural lighting, detailed surfaces",mask=None):
        generator=self.torch.Generator(device=self.device).manual_seed(seed)
        result=self.pipeline(prompt=prompt,negative_prompt="text, watermark, duplicate flames",image=image,strength=self.strength,num_inference_steps=self.steps,generator=generator)
        if result.nsfw_content_detected and any(result.nsfw_content_detected):
            raise SafetyRejected("Generation was flagged by the model safety checker; sample not accepted")
        output=result.images[0].resize(image.size)
        protected=False
        if mask is not None:
            output=protect_flame(image,output,mask); protected=True
        return output,{"method":"stable_diffusion_img2img_guarded_background" if protected else "stable_diffusion_img2img","seed":seed,"strength":self.strength,"steps":self.steps,"prompt":prompt,"model_files_sha256":self.fingerprint,"flame_pixels_preserved":protected,"candidate_labels_require_review":True}


def protect_flame(original,background,mask):
    """Adapt FirePhantom's dilated guard/composite without its server dependencies.

    SD still computes img2img; exact protected pixels are restored after decoding.
    New background fire/occlusion still requires review.
    """
    original=original.convert('RGB'); background=background.convert('RGB').resize(original.size)
    if mask.size!=original.size: raise ValueError('增强掩膜与原图尺寸不一致')
    binary=Image.fromarray(np.uint8(np.asarray(mask.convert('L'))>32)*255)
    guard=binary.filter(ImageFilter.MaxFilter(19))
    # Feather outward: blurring the guard itself then clamping its interior
    # creates a 1 -> ~0.5 jump at the boundary and a visible pasted outline.
    radius=max(1,round(min(original.size)/64))
    outer=guard.filter(ImageFilter.MaxFilter(6*radius+1))
    feather=np.asarray(outer.filter(ImageFilter.GaussianBlur(radius)),dtype=np.float32)/255
    exact=np.asarray(guard)>0; feather=np.maximum(feather,exact)[...,None]
    src=np.asarray(original); dst=np.asarray(background)
    mixed=np.uint8(np.clip(src*feather+dst*(1-feather),0,255)); mixed[exact]=src[exact]
    if not np.array_equal(mixed[exact],src[exact]): raise RuntimeError('火焰保护像素不一致')
    return Image.fromarray(mixed)
