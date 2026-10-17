// Renderer choice follows the file, never a user-selected simulator mode.
export function rendererFor(data){
 if(typeof data==='string')return 'orisim3d';
 if(data?.engine==='orisim3d'&&Array.isArray(data.steps))return 'orisim3d';
 if(data?.engine&&data.engine!=='orisim3d')throw Error(`Unsupported animation engine: ${data.engine}`);
 if(Array.isArray(data)||Array.isArray(data?.vertices_coords)||Array.isArray(data?.file_frames))return 'fold';
 throw Error('Unrecognized instructions. Open a generated animation JSON, native script, or FOLD file.');
}
