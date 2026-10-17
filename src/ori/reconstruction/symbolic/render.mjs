// Capture the existing engine's renderer for model feedback; no geometry conversion.
import {chromium} from 'playwright';
import {createServer} from 'node:http';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {dirname,resolve,extname,sep} from 'node:path';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../simulator'),doc=JSON.parse(readFileSync(0,'utf8')),out=resolve(process.argv[2]);
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
 await page.waitForFunction(()=>document.getElementById('geometry-player')?.contentWindow?.oriLoadGeometry,{timeout:20000});
 const frame=page.frameLocator('#geometry-player');
 const images=[];
 const states=[doc,...(doc.file_frames||[])];
 for(const i of [states.length-1]){
  await page.evaluate(({state})=>document.getElementById('geometry-player').contentWindow.oriLoadGeometry(state),{state:states[i]});
  await page.waitForTimeout(300);
  const path=out+'.png';await frame.locator('#solver').screenshot({path});
  images.push({path,step:i,description:states[i].frame_title,view:'compiled FOLD state'});
 }
 process.stdout.write(JSON.stringify({images}));
}finally{await browser?.close();await new Promise(r=>server.close(r));}
