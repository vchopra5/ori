import {compileScript,registry} from './script-runtime.mjs';
import {readFileSync} from 'node:fs';
import {alignEdge} from './edge-alignment.mjs';
import {rotateFlap} from './hinge-rotation.mjs';
import {expandRecipe} from './recipes.mjs';
const {script,steps}=JSON.parse(readFileSync(0,'utf8'));
let history=script;const resolved=[];
try {
 for(const step of steps){
  if([step.recipe,step.operation,step.commands].filter(x=>x!==undefined).length!==1)throw Error('Choose exactly one of operation, recipe, or commands.');
  const operation=step.operation?(step.operation.name==='rotate_flap'||(!step.operation.name&&step.operation.hinge)?rotateFlap(history,step.operation):alignEdge(history,step.operation)):null;
  const commands=operation?operation.commands:step.recipe?expandRecipe(history,step.recipe):step.commands;
  if(typeof commands!=='string'||typeof step.description!=='string')throw Error('Each step needs description and recipe or commands.');
  compileScript(history+'\n'+commands);
  resolved.push({...step,commands,...(operation?{selection:operation.selection}:{})});history+='\n'+commands;
 }
 console.log(JSON.stringify({ok:true,steps:resolved}));
}catch(error){let state;try{state=registry(compileScript(history).model);}catch{}
 console.log(JSON.stringify({ok:false,error:error.message,failed_step:resolved.length+1,resolved_steps:resolved,state,state_scope:'Temporary state AFTER the successful prefix, BEFORE the failed step. Nothing was committed.'}));}
