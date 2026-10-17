import {readFileSync} from 'node:fs';
import {compileScript,registry} from './script-runtime.mjs';
try{
 const {model,command,warnings,maxStrain}=compileScript(readFileSync(0,'utf8'));
 process.stdout.write(JSON.stringify({ok:true,state:registry(model),warnings,maxStrain,instructions:command.instructions.length,animated:command.paths.filter(Boolean).length}));
}catch(error){process.stdout.write(JSON.stringify({ok:false,error:error.message,state:error.state,construction_states:error.constructionStates}));process.exitCode=1;}
