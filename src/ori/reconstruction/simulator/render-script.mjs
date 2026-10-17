// Capture the existing engine's renderer for model feedback; no geometry conversion.
import {chromium} from 'playwright';
import {createServer} from 'node:http';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {dirname,resolve,extname,sep} from 'node:path';
const root=dirname(fileURLToPath(import.meta.url)),doc=JSON.parse(readFileSync(0,'utf8')),out=resolve(process.argv[2]);
await mkdir(dirname(out),{recursive:true});
const server=createServer(async(req,res)=>{
 try{const path=resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));if(!path.startsWith(root+sep)&&path!==root)throw Error('path');
 const target=path===root||path===root+sep?resolve(root,'index.html'):path;
 res.setHeader('Content-Type',({'.js':'text/javascript','.mjs':'text/javascript','.html':'text/html','.css':'text/css','.json':'application/json'})[extname(target)]||'text/plain');res.end(await readFile(target));
 }catch{res.writeHead(404);res.end();}
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
let browser;
try{
 browser=await chromium.launch({channel:'chrome',headless:true});
 const page=await browser.newPage({viewport:{width:1100,height:850}});
 await page.route('**/latest-animation.json',route=>route.fulfill({contentType:'application/json',body:JSON.stringify(doc)}));
 await page.goto(`http://127.0.0.1:${server.address().port}/`);
 await page.waitForFunction(()=>window.oriPlayback,{timeout:20000});
 if(await page.evaluate(()=>oriPlayback.stepEnds.length)!==doc.steps.length)throw Error('Candidate failed to load in the renderer.');
 const scale=await page.evaluate(()=>oriPlayback.view.scale);
 const images=[];
 const displayNote=async()=>await page.evaluate(()=>oriPlayback.view.layerAmbiguities)?' [Display layer order is approximate here; do not treat the visible stacking as proof of physical layer order.]':'';
 if(doc.review_target){
  // Show a separately constructed endpoint, never interpolate toward it.
  // Restore the actual motion below; target positions never enter the solver.
  await page.evaluate(target=>{
   oriPlayback.command.goTo(oriPlayback.stepEnds.at(-1));
   const points=oriPlayback.model.points;
   if(points.length!==target.points.length)throw Error('Target topology mismatch');
   target.points.forEach((p,i)=>{
    if(p.id!==`p${i}`||Math.hypot(points[i].xf-p.material[0],points[i].yf-p.material[1])>.001)throw Error('Target material correspondence mismatch');
   });
   oriPlayback.model.restorePositions(target.points.flatMap(p=>p.position));
   oriPlayback.view.angleX=0;oriPlayback.view.angleY=0;oriPlayback.view.layerOrders=undefined;
   oriPlayback.view.initBuffers();oriPlayback.view.initModelView();oriPlayback.view.render();
  },doc.review_target);
  const path=out+'.target.png';await page.locator('.viewport').screenshot({path});
  images.push({path,step:0,description:'Independently constructed target endpoint. Layer order unspecified; colors do not establish correct stacking.',view:'front',phase:'target'});
 }
 const indices=doc.steps.map((_,i)=>i).slice(doc.review_start||0);
 if(indices.length){
  const i=indices[0];
  await page.evaluate(({i,scale})=>{oriPlayback.command.goTo(i?oriPlayback.stepEnds[i-1]:oriPlayback.command.first);oriPlayback.view.angleX=-30;oriPlayback.view.angleY=35;oriPlayback.view.scale=scale;},{i,scale});
  await page.waitForTimeout(100);
  const path=out+'.before.png';await page.locator('.viewport').screenshot({path});
  images.push({path,step:i+1,description:doc.steps[i].description+await displayNote(),view:'oblique starting state',phase:'before'});
 }
 for(const i of indices){
  for(const [name,x,y] of [['front',0,0],['back',0,180],['oblique',-30,35]]){
   await page.evaluate(({i,x,y,scale})=>{oriPlayback.command.goTo(oriPlayback.stepEnds[i]);oriPlayback.view.angleX=x;oriPlayback.view.angleY=y;oriPlayback.view.scale=scale;},{i,x,y,scale});
   await page.waitForTimeout(100);
   const path=out+`.step-${i+1}.${name}.png`;await page.locator('.viewport').screenshot({path});images.push({path,step:i+1,description:doc.steps[i].description+await displayNote(),view:name});
  }
  const moved=await page.evaluate((i)=>{
   const end=oriPlayback.stepEnds[i],begin=i?oriPlayback.stepEnds[i-1]:1;
   const paths=[];for(let k=begin+1;k<=end;k++)if(oriPlayback.command.paths[k])paths.push([k,oriPlayback.command.paths[k]]);
   if(!paths.length)return false;
   let remaining=paths.reduce((sum,[,path])=>sum+path.duration,0)/2;
   let selected=paths.at(-1);
   for(const entry of paths){selected=entry;if(remaining<=entry[1].duration)break;remaining-=entry[1].duration;}
   const [k,path]=selected,u=Math.min(1,remaining/path.duration);
   oriPlayback.command.goTo(k);
   let j=0;while(j<path.frames.length-2&&path.frames[j+1].tn<u)j++;
   const a=path.frames[j],b=path.frames[j+1],t=(u-a.tn)/(b.tn-a.tn||1);
   oriPlayback.model.restorePositions(a.coords.map((v,k)=>v+(b.coords[k]-v)*t));
   oriPlayback.command.changed=true;return true;
  },i);
  if(moved){await page.waitForTimeout(100);const path=out+`.step-${i+1}.motion.png`;await page.locator('.viewport').screenshot({path});images.push({path,step:i+1,description:doc.steps[i].description+await displayNote(),view:'MID-MOTION oblique (not final pose)',phase:'during'});}
  if(doc.review_target){
   // Sample each timed instruction separately: a single midpoint can miss a
   // collapse's second stage or a transient spike.
   const samples=await page.evaluate(i=>{
    const begin=i?oriPlayback.stepEnds[i-1]:1,end=oriPlayback.stepEnds[i],out=[];
    const paths=[];for(let k=begin+1;k<=end;k++)if(oriPlayback.command.paths[k])paths.push([k,oriPlayback.command.paths[k]]);
    if(paths.length>3){
     const total=paths.reduce((sum,[,p])=>sum+p.duration,0);
     for(const fraction of [.1,.2,.3,.4,.5,.6,.7,.8,.9]){
      let time=total*fraction;
      for(const [k,p] of paths){if(time<=p.duration){out.push({instruction:k,u:time/p.duration,fraction});break;}time-=p.duration;}
     }
    }else{
     const total=paths.reduce((sum,[,p])=>sum+p.duration,0);let elapsed=0;
     for(const [k,p] of paths){for(const u of [.25,.5,.75])out.push({instruction:k,u,fraction:(elapsed+u*p.duration)/total});elapsed+=p.duration;}
    }
    return out;
   },i);
   for(const sample of samples){
    await page.evaluate(({instruction,u})=>{
     oriPlayback.command.goTo(instruction);
     const frames=oriPlayback.command.paths[instruction].frames,frame=frames.reduce((best,f)=>Math.abs(f.tn-u)<Math.abs(best.tn-u)?f:best);
     oriPlayback.model.restorePositions(frame.coords);oriPlayback.command.changed=true;
    },sample);
    await page.waitForTimeout(100);
    const percent=Math.round(sample.fraction*1000)/10;
    const path=out+`.step-${i+1}.motion-${percent}.png`;
    await page.locator('.viewport').screenshot({path});images.push({path,step:i+1,description:doc.steps[i].description+await displayNote(),view:`oblique, ${percent}% of this continuous action`,phase:'during'});
   }
  }
 }
 process.stdout.write(JSON.stringify({images}));
}finally{await browser?.close();await new Promise(r=>server.close(r));}
