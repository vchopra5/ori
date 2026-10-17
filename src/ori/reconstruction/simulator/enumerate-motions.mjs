// Engine-generated choices, all evaluated on the same immutable starting state.
import {readFileSync} from 'node:fs';
import {compileScript} from './script-runtime.mjs';
import {expandRecipe} from './recipes.mjs';
const {script}=JSON.parse(readFileSync(0,'utf8'));
const candidates=[],unavailable=[],prior=compileScript(script).command.instructions.length;
for(const [id,description,recipe] of [
 ['square-base','Collapse the square base',{name:'square_base'}],
 ['petal-0','Raise the petal containing material corner (+200,+200)',{name:'petal_fold',material_rotation:0,duration_ms:2000}],
 ['petal-90','Raise the petal containing material corner (-200,+200)',{name:'petal_fold',material_rotation:90,duration_ms:2000}],
 ['petal-180','Raise the opposite petal containing material corner (-200,-200)',{name:'petal_fold',material_rotation:180,duration_ms:2000}],
 ['petal-270','Raise the petal containing material corner (+200,-200)',{name:'petal_fold',material_rotation:270,duration_ms:2000}],
]){
 try{
  const commands=expandRecipe(script,recipe),result=compileScript(script+'\n'+commands);
  candidates.push({id,description,step:{description,recipe},resolved_step:{description,recipe,commands},max_strain:Math.max(0,...result.strainByInstruction.slice(prior+1))});
 }catch(error){unavailable.push({id,reason:error.message});}
}
console.log(JSON.stringify({candidates,unavailable,validation:'Geometry and segment strain checked. Global self-collision and video correspondence require further validation.'}));
