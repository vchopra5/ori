// Minimal local host for the unmodified Origami Simulator GPU solver.
window.gtag = function() {}; // Upstream telemetry call sites are disabled.
window.globals = initGlobals();
globals.color1='dfa1a6';globals.color2='fff0d3';globals.backgroundColor='e9eee6';
globals.creasePercent=0;globals.numSteps=100;
globals.warn=message=>{document.getElementById('error').textContent=String(message);};
globals.controls={setDeltaT(){},updateCreasePercent(){}};
globals.setCreasePercent=value=>{globals.creasePercent=value;globals.shouldChangeCreasePercent=true;};
try {
  globals.threeView=initThreeView(globals);
  globals.model=initModel(globals);
  globals.dynamicSolver=initDynamicSolver(globals);
  globals.pattern=initPattern(globals);
  let source=null;
  window.foldSolver={
    load(fold, state=false){
      document.getElementById('error').textContent='';
      source=JSON.parse(JSON.stringify(fold));
      globals.creasePercent=0;
      globals.simulationRunning=true;
      const mesh=JSON.parse(JSON.stringify(fold));
      if(state&&mesh.vertices_coords[0].length===3)mesh.vertices_coords=mesh.vertices_coords.map(([x,y,z])=>[x,z,-y]);
      globals.pattern.setFoldData(mesh,true);
      globals.model.sync();globals.model.syncSolver();
      globals.simulationRunning=!state;
      globals.setCreasePercent(0);
      globals.threeView.resetCamera();
    },
    setProgress(value){globals.setCreasePercent(Math.max(0,Math.min(1,value)));},
    reset(){globals.setCreasePercent(0);globals.model.reset();},
    snapshot(){
      const positions=Array.from(globals.model.getPositionsArray()||[]);
      return {positions,progress:globals.creasePercent,finite:positions.every(Number.isFinite),error:document.getElementById('error').textContent};
    },
    source(){return source;}
  };
  window.addEventListener('resize',()=>globals.threeView.onWindowResize());
  parent.postMessage({type:'ori-fold-ready'},location.origin);
} catch(error) {document.getElementById('error').textContent=error.message;parent.postMessage({type:'ori-fold-error',message:error.message},location.origin);}
