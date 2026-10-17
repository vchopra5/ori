// OriSim3D's recorded transitions keep advancing after pause(). Freeze their clock
// without changing their sampled geometry or the engine's motion interpolation.
export function pausablePlayback(command,now=()=>performance.now()){
 const pause=command.pause.bind(command),play=command.play.bind(command),anim=command.anim.bind(command),goTo=command.goTo.bind(command);
 let frozen=null;
 command.pause=()=>{if(command.transition&&frozen===null)frozen=now();pause();};
 command.play=()=>{if(frozen!==null){if(command.transition)command.transition.start+=now()-frozen;frozen=null;}play();};
 command.anim=()=>frozen===null?anim():false;
 command.goTo=(...args)=>{frozen=null;return goTo(...args);};
 return command;
}
