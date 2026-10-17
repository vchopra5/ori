"""Export connector assemblies as anchored rigid MuJoCo bodies at chosen angles."""
import xml.etree.ElementTree as ET
import numpy as np
from .lego_connections import CATALOG


def export_assembly(playback,path):
    root=ET.Element('mujoco',model='lego_connector_assembly')
    asset=ET.SubElement(root,'asset');world=ET.SubElement(root,'worldbody')
    assembly=ET.SubElement(world,'body',name='assembly')
    fmt=lambda a:' '.join(str(float(x)) for x in np.array(a).flat)
    for p in playback['pieces']:
        r=np.array(p['matrix']);t=np.array(p['origin'])*.008
        body=ET.SubElement(assembly,'body',name=p['id'],pos=fmt(t),xyaxes=fmt(np.r_[r[:,0],r[:,1]]))
        rgba=fmt([int(p['hex'][i:i+2],16)/255 for i in (1,3,5)]+[1])
        for i,shape in enumerate(p['solids']):
            name=f"{p['id']}_shape_{i}"
            faces=[[face[0],face[j],face[j+1]] for face in shape['faces'] for j in range(1,len(face)-1)]
            ET.SubElement(asset,'mesh',name=name,vertex=fmt(np.array(shape['vertices'])*.008),face=' '.join(str(x) for f in faces for x in f))
            ET.SubElement(body,'geom',type='mesh',mesh=name,rgba=rgba)
        for c in CATALOG[p['part']]['connectors'].values():
            if c['kind']!='stud':continue
            r=np.array(c['frame']);point=np.array(c['point'])+r[:,2]*.1
            ET.SubElement(body,'geom',type='cylinder',size='.0024 .0008',pos=fmt(point*.008),
                          xyaxes=fmt(np.r_[r[:,0],r[:,1]]),rgba=rgba,contype='0',conaffinity='0')
    ET.ElementTree(root).write(path,encoding='unicode')
