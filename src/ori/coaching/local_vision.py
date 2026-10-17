"""Local stage matching. Downloads occur only via --prepare, never inference."""
from collections import OrderedDict
from hashlib import sha256
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MODEL_ID = 'facebook/dinov2-small'
MODEL_DIR = ROOT / '.local/models/dinov2-small'
# Conservative demo gates, not calibrated probabilities.
MIN_SIMILARITY, MIN_MARGIN, MIN_SHAPE = .88, .015, .72


def prepare():
    from huggingface_hub import HfApi, snapshot_download
    revision = HfApi(token=False).model_info(MODEL_ID).sha
    snapshot_download(MODEL_ID, revision=revision, token=False, local_dir=MODEL_DIR,
                      cache_dir=ROOT / '.local/hf-cache',
                      allow_patterns=['config.json', 'model.safetensors', 'preprocessor_config.json', 'README.md'])
    (MODEL_DIR / 'ori-model.json').write_text(json.dumps(dict(model=MODEL_ID, revision=revision)))
    from .paper_vision import prepare_models
    return dict(encoder=dict(model=MODEL_ID, revision=revision, path=str(MODEL_DIR)), **prepare_models())


def canonical(image, mask):
    """Normalize size, lighting, and background; retain silhouette and fold edges."""
    import numpy as np
    from PIL import Image, ImageOps
    ys, xs = np.nonzero(mask)
    if not len(xs):
        raise ValueError('No foreground')
    box = (int(xs.min()), int(ys.min()), int(xs.max())+1, int(ys.max())+1)
    image = image.crop(box).convert('L')
    mask_image = Image.fromarray((mask*255).astype('uint8')).crop(box)
    pixels = np.asarray(image, dtype=float)
    selected = np.asarray(mask_image)>0
    low, high = np.percentile(pixels[selected], [1,95])
    pixels = 155 + 60 * np.clip((pixels-low)/max(30,high-low),0,1)
    image = Image.fromarray(pixels.astype('uint8'))
    normalized = Image.new('L', image.size, 244)
    normalized.paste(image, mask=mask_image)
    normalized = ImageOps.pad(normalized,(184,184),color=244,method=Image.Resampling.BICUBIC)
    output = Image.new('RGB',(224,224),(244,244,244))
    output.paste(normalized,(20,20))
    small_mask = ImageOps.pad(mask_image,(32,32),color=0,method=Image.Resampling.NEAREST)
    return output, np.asarray(small_mask)>0


def reference_views(state):
    import numpy as np
    from PIL import Image, ImageDraw
    from ori.reconstruction.fold_commands import Panel
    from ori.reconstruction.fold_layers import ordered
    panels = [Panel(uv=np.array(p['material']),xyz=np.array(p['vertices']),id=p['id'],contacts=p.get('contacts',{})) for p in state]
    for tilt in (0, .35, -.35):
        c,s=np.cos(tilt),np.sin(tilt)
        matrix=np.array([[1,0,0],[0,c,-s],[0,s,c]])
        for angle in (0,90,180,270):
            image=Image.new('RGB',(280,280),(244,244,244));mask=Image.new('L',image.size,0)
            draw=ImageDraw.Draw(image);mask_draw=ImageDraw.Draw(mask)
            for panel in ordered(panels,matrix[2]):
                points=panel.xyz @ matrix.T
                xy=[(140+100*p[0],140-100*p[1]) for p in points]
                draw.polygon(xy,fill=(205,205,205));draw.line(xy+[xy[0]],fill=(150,150,150),width=1)
                mask_draw.polygon(xy,fill=255)
            image=image.rotate(angle);mask=mask.rotate(angle)
            yield canonical(image,np.asarray(mask)>0)


def decide(target, competitor, shape, *, has_competitor=True):
    """Recognizable target outlines pass even when adjacent steps look similar."""
    import math
    if not all(math.isfinite(v) for v in (target,competitor,shape)):
        return 'unclear', False
    if target>=MIN_SIMILARITY and shape>=MIN_SHAPE and (not has_competitor or target-competitor>=-.010001):
        return 'match', True
    if competitor>=MIN_SIMILARITY and competitor-target>=MIN_MARGIN:
        return 'other_stage', False
    return 'unclear', False


class LocalStageMatcher:
    def __init__(self):
        if not (MODEL_DIR/'model.safetensors').exists():
            raise RuntimeError('Run npm run coaching:vision-setup first.')
        os.environ['HF_HUB_OFFLINE']='1'
        os.environ['TRANSFORMERS_OFFLINE']='1'
        os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
        import torch
        from transformers import Dinov2Model
        self.torch=torch
        torch.set_num_threads(min(4,os.cpu_count() or 1))
        self.model=Dinov2Model.from_pretrained(str(MODEL_DIR),local_files_only=True,use_safetensors=True).eval()
        self.cache=OrderedDict()
        from .paper_vision import PaperPerception
        self.perception=PaperPerception()

    def encode(self,images):
        import numpy as np
        torch=self.torch
        pixels=np.stack([np.asarray(image,dtype='float32')/255 for image in images])
        pixels=(pixels-np.array([.485,.456,.406],dtype='float32'))/np.array([.229,.224,.225],dtype='float32')
        tensor=torch.from_numpy(pixels.transpose(0,3,1,2).copy())
        embeddings=[]
        with torch.inference_mode():
            for batch in tensor.split(4):
                features=self.model(pixel_values=batch).last_hidden_state
                embedding=torch.cat([features[:,0],features[:,1:].mean(1)],dim=1)
                embeddings.append(torch.nn.functional.normalize(embedding,dim=1).cpu().numpy())
        return np.concatenate(embeddings)

    def references(self,state):
        key=sha256(json.dumps(state,sort_keys=True).encode()).hexdigest()
        if key not in self.cache:
            views=list(reference_views(state))
            self.cache[key]=(self.encode([v[0] for v in views]),[v[1] for v in views])
            if len(self.cache)>12:
                self.cache.popitem(last=False)
        self.cache.move_to_end(key)
        return self.cache[key]

    def compare(self,playback,commands,step,image,point=None):
        import numpy as np
        from time import perf_counter
        start=perf_counter()
        from .paper_vision import previews
        image=image.convert('RGB')
        if np.asarray(image).std(axis=(0,1)).max()<3:
            masks=[];depth=None
        else:
            masks,depth=self.perception.predict(image,point)
        candidates=[canonical(image,mask) for mask,_ in masks]
        base=dict(provider='local-dinov2',advance_allowed=False,score_kind='cosine_similarity',
                  calibration='experimental; not a probability',confidence=None)
        if not candidates:
            return dict(base,verdict='unclear',observation='I have not isolated the paper yet.',
                        instruction='Tap the paper in the camera view, then check again.',
                        segmentation_model='sam2.1-hiera-tiny',depth_model='depth-anything-v2-small')
        embeddings=self.encode([query for query,_ in candidates])
        indices=sorted({max(0,step-1),step,min(len(playback['states'])-1,step+1)})
        references={index:self.references(playback['states'][index]) for index in indices}
        attempts=[]
        for candidate_index,(candidate,embedding) in enumerate(zip(candidates,embeddings)):
            mask=candidate[1]
            scores={}
            for index,(features,reference_masks) in references.items():
                similarities=features @ embedding
                # Choose the view by both visual features and the visible outline.
                shapes=np.array([np.logical_and(mask,m).sum()/max(1,np.logical_or(mask,m).sum()) for m in reference_masks]) if mask is not None else np.zeros(len(reference_masks))
                best=int(np.argmax(similarities+.15*shapes))
                scores[index]=(float(similarities[best]),float(shapes[best]))
            others=[(index,score) for index,score in scores.items() if index!=step]
            competitor,other=max(others,key=lambda pair:pair[1][0]) if others else (None,(-1,0))
            similarity,shape=scores[step]
            verdict,allowed=decide(similarity,other[0],shape,has_competitor=bool(others))
            if mask is None:
                allowed=similarity>=.94 and similarity-other[0]>=.025
                verdict='match' if allowed else 'unclear'
            if verdict=='other_stage':
                verdict='before_fold' if competitor==step-1 else 'unclear'
            attempts.append(dict(verdict=verdict,advance_allowed=allowed,similarity=similarity,
                                 margin=similarity-other[0],shape_agreement=shape,
                                 candidate_index=candidate_index,matching_method='sam2-outline-and-nn'))
        # A valid match wins even when another crop includes clutter or hands.
        result=max(attempts,key=lambda r:(r['advance_allowed'],r['similarity']+.15*r['shape_agreement']))
        instruction=commands[step-1].get('name','Follow the demonstrated fold.') if step else 'Start with a flat square sheet.'
        if result['verdict']=='match':
            observation='Your shape matches this step.'
            instruction='Keep it in view for a moment.'
        elif result['verdict']=='before_fold':
            observation='This looks closer to the shape before this fold.'
        else:
            observation='I have not matched the shape to this step yet.'
            instruction='Show the shape to the camera or turn it slightly. '+instruction
        for key in ('similarity','margin','shape_agreement'):
            result[key]=round(result[key],4)
        selected=result.pop('candidate_index')
        evidence=previews(image,masks[selected][0],depth)
        return dict(base,**result,observation=observation,instruction=instruction,
                    perception=dict(**evidence,segmentation_model='sam2.1-hiera-tiny',depth_model='depth-anything-v2-small'),
                    comparison_steps=indices,elapsed_ms=round((perf_counter()-start)*1000))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare',action='store_true',required=True)
    parser.parse_args()
    print(json.dumps(prepare()))
