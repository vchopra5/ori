import {readFileSync} from 'node:fs';
import {SymbolicCompiler} from './compiler.mjs';
const input=JSON.parse(readFileSync(0,'utf8'));
const compiler=new SymbolicCompiler(input.initial);
let applied=0;
try{for(const step of input.steps||[]){compiler.apply(step);applied++;}console.log(JSON.stringify({ok:true,applied,state:compiler.catalog(),fold:compiler.export()}));}
catch(e){console.log(JSON.stringify({ok:false,error:e.message,failed_step:applied+1,applied,state:compiler.catalog(),fold:compiler.export()}));}
