"""Neural paper masks and relative depth, with strictly offline inference."""
import io
import base64
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
MODELS={
    'segmentation':('facebook/sam2.1-hiera-tiny',ROOT/'.local/models/sam2.1-hiera-tiny'),
    'depth':('depth-anything/Depth-Anything-V2-Small-hf',ROOT/'.local/models/depth-anything-v2-small'),
}


def prepare_models():
    import json
    from huggingface_hub import HfApi, snapshot_download
    result={}
    for role,(model,directory) in MODELS.items():
        revision=HfApi(token=False).model_info(model).sha
        snapshot_download(model,revision=revision,token=False,local_dir=directory,
                          cache_dir=ROOT/'.local/hf-cache',
                          allow_patterns=['*.json','*.safetensors','README.md','LICENSE*'])
        metadata=dict(model=model,revision=revision,path=str(directory))
        (directory/'ori-model.json').write_text(json.dumps(metadata))
        result[role]=metadata
    return result


def png_url(image):
    buffer=io.BytesIO()
    image.save(buffer,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode()


def previews(image,mask,depth):
    """In-memory evidence only; never persist camera pixels."""
    import numpy as np
    from PIL import Image
    mask=mask.astype(bool)
    rgb=np.asarray(image.convert('RGB')).copy()
    rgb[~mask]=[237,240,248]
    mask_image=Image.fromarray(rgb).resize((224,224))
    valid=mask & np.isfinite(depth)
    values=depth[valid]
    normalized=np.zeros(depth.shape,dtype=float)
    if values.size:
        low,high=np.percentile(values,[5,95])
        normalized[valid]=np.clip((depth[valid]-low)/max(float(high-low),1e-6),0,1)
    far=np.array([126,145,218]);near=np.array([247,204,151])
    colors=(far[None,None,:]*(1-normalized[:,:,None])+near[None,None,:]*normalized[:,:,None]).astype('uint8')
    colors[~valid]=[237,240,248]
    return dict(mask_preview=png_url(mask_image),depth_preview=png_url(Image.fromarray(colors).resize((224,224))),
                depth_kind='relative inverse depth; not measured distance',depth_used_for_advancement=False)


class PaperPerception:
    def __init__(self):
        import torch
        from transformers import Sam2Config, Sam2Model, Sam2Processor, AutoImageProcessor, AutoModelForDepthEstimation
        for _,directory in MODELS.values():
            if not (directory/'model.safetensors').exists():
                raise RuntimeError('Run npm run coaching:vision-setup to prepare segmentation and depth models.')
        self.torch=torch
        self.device='mps' if torch.backends.mps.is_available() else 'cpu'
        sam_dir=MODELS['segmentation'][1]
        depth_dir=MODELS['depth'][1]
        # The checkpoint includes video-memory configuration; we use its shared image path.
        import json
        image_config=Sam2Config.from_dict({**json.loads((sam_dir/'config.json').read_text()),'model_type':'sam2'})
        self.segmenter=Sam2Model.from_pretrained(str(sam_dir),config=image_config,local_files_only=True,use_safetensors=True).to(self.device).eval()
        self.segment_processor=Sam2Processor.from_pretrained(str(sam_dir),local_files_only=True)
        self.depth_model=AutoModelForDepthEstimation.from_pretrained(str(depth_dir),local_files_only=True,use_safetensors=True).to(self.device).eval()
        self.depth_processor=AutoImageProcessor.from_pretrained(str(depth_dir),local_files_only=True,use_fast=False)

    def predict(self,image,point=None):
        import numpy as np
        torch=self.torch
        width,height=image.size
        # Points are separate candidate objects, not several positives forced into one mask.
        points=[point] if point is not None else [[.5,.5],[.35,.5],[.65,.5]]
        prompts=[[[x*width,y*height]] for x,y in points]
        inputs=self.segment_processor(images=image,input_points=[prompts],
                                      input_labels=[[[1] for _ in points]],return_tensors='pt')
        inputs=inputs.to(self.device)
        with torch.inference_mode():
            outputs=self.segmenter(**inputs,multimask_output=True)
            masks=self.segment_processor.post_process_masks(outputs.pred_masks.cpu(),inputs['original_sizes'].cpu())[0]
            depth_inputs=self.depth_processor(images=image,return_tensors='pt').to(self.device)
            prediction=self.depth_model(**depth_inputs).predicted_depth
            depth=torch.nn.functional.interpolate(prediction.unsqueeze(1),size=(height,width),mode='bicubic',align_corners=False)[0,0].float().cpu().numpy()
        masks=masks.reshape(-1,height,width).numpy().astype(bool)
        qualities=outputs.iou_scores.float().cpu().numpy().reshape(-1)
        candidates=[]
        for mask,quality in sorted(zip(masks,qualities),key=lambda pair:float(pair[1]),reverse=True):
            if not .015<mask.mean()<.995:
                continue
            if any(np.logical_and(mask,existing[0]).sum()/max(1,np.logical_or(mask,existing[0]).sum())>.97 for existing in candidates):
                continue
            candidates.append((mask,float(quality)))
            if len(candidates)>=4:
                break
        return candidates,depth
