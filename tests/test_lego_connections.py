"""Connector semantics, articulated transforms, and conservative solid checks."""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import numpy as np
from ori.reconstruction.lego import compile_plan, save_run
from ori.reconstruction.lego_connections import CATALOG, frame


def plan(parts,steps):
    return dict(version=2,title='Connector test',uncertainties=[],unsupported=[],
                pieces=[dict(id=i,part=p,color='red') for i,p in parts],steps=steps)


def root(i='base'):return dict(piece=i,position=[0,0,0],instruction='Place base')
def snap(i,to,pc='stud:0:0',sc='socket:0:0',**kw):return dict(piece=i,attach=dict(to=to,connector=pc,self=sc,**kw),instruction='Connect piece')


def hinged():
    return plan([('base','plate_6x8'),('hinge','3937'),('top','6134'),('roof','plate_4x6'),('tile','6636')],
                [root(),snap('hinge','base','stud:2:2'),snap('top','hinge','hinge','hinge',angle=45),
                 snap('roof','top'),snap('tile','roof','stud:0:0')])


class ConnectorTests(unittest.TestCase):
    def test_large_baseplate_supports_far_corner_and_has_no_sockets(self):
        base=CATALOG['baseplate_48x48']
        self.assertEqual(base['size'],[48,48,.5])
        self.assertEqual(len(base['connectors']),48*48)
        self.assertTrue(all(c['kind']=='stud' for c in base['connectors'].values()))
        result=compile_plan(plan([('base','4186'),('corner','brick_2x2')],
                                 [root(),snap('corner','base','stud:46:46')]))
        self.assertEqual(result['connections'][0]['studs'],4)
        np.testing.assert_allclose(result['pieces'][1]['origin'],[46,46,.2])

    def test_catalog_contains_standard_tent_parts(self):
        ids={p['part_id'] for p in CATALOG.values()}
        self.assertTrue({'3036','3032','6636','3937','6134','47457'}<=ids)
        self.assertGreater(len(CATALOG),40)

    def test_tilted_roof_and_tile_inherit_hinge_frame(self):
        result=compile_plan(hinged());pieces={p['id']:p for p in result['pieces']}
        np.testing.assert_allclose(pieces['roof']['matrix'],pieces['top']['matrix'],atol=1e-10)
        np.testing.assert_allclose(pieces['tile']['matrix'],pieces['top']['matrix'],atol=1e-10)
        a,pa,ra=frame(pieces['top'],'stud:0:0');b,pb,rb=frame(pieces['roof'],'socket:0:0')
        np.testing.assert_allclose(pa,pb,atol=1e-10)
        self.assertAlmostEqual(np.dot(ra[:,2],rb[:,2]),-1)

    def test_tile_has_no_top_studs(self):
        p=plan([('base','plate_2x4'),('tile','tile_1x2'),('brick','brick_1x1')],
               [root(),snap('tile','base'),snap('brick','tile')])
        with self.assertRaisesRegex(ValueError,'no connector'):compile_plan(p)

    def test_slope_studs_only_on_high_row(self):
        p=plan([('base','plate_2x4'),('slope','47457'),('brick','brick_1x1')],
               [root(),snap('slope','base'),snap('brick','slope','stud:0:1')])
        with self.assertRaisesRegex(ValueError,'no connector'):compile_plan(p)
        p['steps'][-1]['attach']['connector']='stud:0:0'
        self.assertEqual(len(compile_plan(p)['pieces']),3)

    def test_reused_hinge_and_incompatible_mates(self):
        p=hinged();p['pieces'].append(dict(id='extra',part='6134',color='blue'))
        p['steps'].append(snap('extra','hinge','hinge','hinge',angle=45))
        with self.assertRaisesRegex(ValueError,'already occupied'):compile_plan(p)
        p=hinged();p['steps'][2]['attach']['connector']='socket:0:0'
        with self.assertRaisesRegex(ValueError,'Incompatible'):compile_plan(p)

    def test_overlapping_and_floating_placements(self):
        p=plan([('base','plate_2x4'),('a','brick_2x2'),('b','brick_2x2')],
               [root(),snap('a','base'),snap('b','base','stud:1:0')])
        with self.assertRaisesRegex(ValueError,'overlaps|occupied'):compile_plan(p)
        p['steps'][-1]['attach']['to']='missing'
        with self.assertRaisesRegex(ValueError,'previously placed'):compile_plan(p)

    def test_hinge_motion_moves_all_descendants_and_preserves_previous_states(self):
        p=hinged();p['steps'].append(dict(action='rotate_hinge',piece='top',angle=70,instruction='Tilt roof'))
        result=compile_plan(p)
        self.assertEqual(len(result['states']),6)
        self.assertEqual(result['hinge_angles']['top'],70)
        before=result['states'][-2]['poses'];after=result['states'][-1]['poses']
        self.assertNotEqual(before['tile']['origin'],after['tile']['origin'])
        self.assertEqual(before['base'],after['base'])
        np.testing.assert_allclose(after['tile']['matrix'],after['top']['matrix'],atol=1e-10)

    def test_motion_into_ground_is_rejected(self):
        p=hinged();p['steps'].append(dict(action='rotate_hinge',piece='top',angle=-90,instruction='Tilt roof through ground'))
        with self.assertRaisesRegex(ValueError,'ground'):compile_plan(p)

    def test_rotation_limits_and_finite_values(self):
        for angle in [True,float('nan'),float('inf'),91,-91]:
            with self.subTest(angle=angle):
                p=hinged();p['steps'][2]['attach']['angle']=angle
                with self.assertRaises(ValueError):compile_plan(p)

    def test_side_stud_connection(self):
        p=plan([('base','brick_side_stud_1x1'),('tile','tile_1x1')],
               [root(),snap('tile','base','side_stud')])
        result=compile_plan(p)
        tile=result['pieces'][1]
        self.assertAlmostEqual(tile['matrix'][1][2],-1)

    def test_quarter_turn_and_underside_attachment(self):
        p=plan([('base','brick_1x1'),('plate','plate_1x2'),('foot','brick_1x1')],
               [root(),snap('plate','base',turn=90),snap('foot','plate','socket:0:1','stud:0:0')])
        self.assertEqual(len(compile_plan(p)['connections']),2)

    def test_tent_fixture_has_ten_pieces_and_two_hinges(self):
        p=json.loads((Path(__file__).resolve().parents[1]/'examples/lego/tent.json').read_text())
        result=compile_plan(p)
        self.assertEqual(len(result['pieces']),10)
        self.assertEqual(sum(c['kind']=='hinge' for c in result['connections']),2)
        self.assertEqual(sum(p['count'] for p in result['inventory']),10)
        with TemporaryDirectory() as directory:
            import mujoco
            save_run(p,Path(directory))
            model=mujoco.MjModel.from_xml_path(str(Path(directory)/'assembly.xml'))
            self.assertEqual(model.nbody,12)

    def test_hinge_top_cannot_swing_through_ground(self):
        p=plan([('base','hinge_base_1x2'),('top','hinge_top_2x2')],
               [root(),snap('top','base','hinge','hinge',angle=-45)])
        with self.assertRaisesRegex(ValueError,'ground'):compile_plan(p)

    def test_xml_compiles_with_tilted_meshes(self):
        import mujoco
        with TemporaryDirectory() as directory:
            base=Path(directory);save_run(hinged(),base)
            model=mujoco.MjModel.from_xml_path(str(base/'assembly.xml'))
            self.assertEqual(model.nbody,7)
            self.assertEqual(model.njnt,0)
            playback=json.loads((base/'lego-playback.json').read_text())
            self.assertEqual(playback['version'],2)


if __name__=='__main__':unittest.main()
