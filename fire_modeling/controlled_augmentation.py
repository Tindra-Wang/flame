"""Inpainting adapter and image-space constraints, independent of orchestration."""
from pathlib import Path
import numpy as np
from PIL import Image,ImageFilter
from .enhancement import weight_fingerprint,SafetyRejected


def edit_region(mask,mode):
    binary=mask.convert('L').point(lambda p:255 if p>32 else 0)
    guard=binary.filter(ImageFilter.MaxFilter(19))
    if mode=='background':return Image.fromarray(255-np.asarray(guard))
    if mode=='flame':return guard
    raise ValueError('未知增强模式')


def constrain(original,generated,mask,mode):
    """Exact outside-region preservation, and fresh flame candidate labels."""
    original=original.convert('RGB');generated=generated.convert('RGB').resize(original.size)
    region=np.asarray(edit_region(mask,mode))>0
    if not (np.asarray(mask.convert('L'))>32).any():raise ValueError('火焰掩码为空，不能受控增强')
    src=np.asarray(original);dst=np.asarray(generated);out=src.copy();out[region]=dst[region]
    result=Image.fromarray(out)
    if mode=='background':candidate=mask.convert('L').copy()
    else:
        hsv=np.asarray(result.convert('HSV'));rgb=np.asarray(result)
        warm=(hsv[:,:,0]<50)&(hsv[:,:,1]>50)&(hsv[:,:,2]>60)&(rgb[:,:,0]>=rgb[:,:,1])&region
        candidate=Image.fromarray(np.uint8(warm)*255)
        old=np.asarray(mask.convert('L'))>32
        overlap=int((warm&old).sum())/max(1,int(old.sum()))
        if overlap<.1 or warm.sum()<16:raise ValueError('火焰候选轮廓不足或漂移，已拒绝')
    return result,candidate,{'outside_edit_region_unchanged':bool(np.array_equal(out[~region],src[~region])),
        'edit_fraction':float(region.mean()),'label_policy':'inherited_candidate_requires_review' if mode=='background' else 'warm_color_candidate_recomputed_requires_review',
        'physical_ground_truth':False,'temporal_consistency':'not_verified_still_image_only'}


class InpaintingEnhancer:
    def __init__(self,model_dir,*,controlnet=False,controlnet_dir='/app/models/controlnet-depth',device='cuda'):
        import torch
        from diffusers import StableDiffusionInpaintPipeline,StableDiffusionControlNetInpaintPipeline,ControlNetModel
        path=Path(model_dir)
        if not (path/'model_index.json').is_file():raise ValueError('本地SD模型不存在')
        options={'local_files_only':True,'torch_dtype':torch.float16 if device=='cuda' else torch.float32}
        if (path/'unet/diffusion_pytorch_model.fp16.safetensors').is_file():options['variant']='fp16'
        self.model_hashes=weight_fingerprint(path);self.control_hashes=None;self.torch=torch;self.device=device
        if controlnet:
            if not (Path(controlnet_dir)/'config.json').is_file():raise ValueError('ControlNet深度权重未安装，不能把普通inpainting标作ControlNet')
            model=ControlNetModel.from_pretrained(controlnet_dir,local_files_only=True,torch_dtype=options['torch_dtype'])
            self.control_hashes=weight_fingerprint(Path(controlnet_dir))
            self.pipeline=StableDiffusionControlNetInpaintPipeline.from_pretrained(str(path),controlnet=model,**options)
        else:self.pipeline=StableDiffusionInpaintPipeline.from_pretrained(str(path),**options)
        self.pipeline.enable_attention_slicing()
        if device=='cuda':self.pipeline.enable_model_cpu_offload()
        else:self.pipeline.to(device)

    def run(self,image,mask,depth,*,mode,seed,weather,strength,steps):
        prompts={'background':'a detailed photograph of an emergency fire drill scene, realistic surrounding surfaces, natural lighting, preserve scene layout',
                 'flame':'a scientific photograph of a small controlled burner fire, detailed orange and yellow flame tongues, turbulent flame texture, realistic smoke and lighting'}
        weather_text={'clear':'clear weather','fog':'foggy atmosphere','rain':'rainy atmosphere','snow':'snowy atmosphere'}
        kwargs={'prompt':prompts[mode]+', '+weather_text[weather], 'negative_prompt':'text, watermark, distorted objects, duplicate fire sources',
                'image':image.resize((512,512)),'mask_image':edit_region(mask,mode).resize((512,512),Image.Resampling.NEAREST),
                'height':512,'width':512,'strength':strength,'num_inference_steps':steps,
                'generator':self.torch.Generator(device='cpu').manual_seed(seed)}
        if self.control_hashes:kwargs.update(control_image=depth.convert('RGB').resize((512,512)),controlnet_conditioning_scale=.8)
        output=self.pipeline(**kwargs)
        if output.nsfw_content_detected and any(output.nsfw_content_detected):raise SafetyRejected('模型过滤器拒绝该候选')
        result,candidate,checks=constrain(image,output.images[0],mask,mode)
        return result,candidate,{'method':'controlnet_depth_inpainting' if self.control_hashes else 'masked_inpainting','mode':mode,'seed':seed,'strength':strength,'steps':steps,
            'model_hashes':self.model_hashes,'controlnet_hashes':self.control_hashes,'prompt':kwargs['prompt'],'checks':checks}
