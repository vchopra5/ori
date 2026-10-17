"""Validate model plans before native simulation or GPU initialization."""
import unittest

from ori.reconstruction.genesis_trial import check


def plan():
    return dict(E=5000,nu=.3,rho=1400,duration=2.5,keys=[
        dict(time=0,position=[-.15,0,.105]),
        dict(time=.4,position=[-.15,0,.105]),
        dict(time=1.8,position=[.08,0,.089]),
        dict(time=2.5,position=[.15,0,.13])])


class PlanTests(unittest.TestCase):
    def test_rejects_unstable_or_unsafe_model_parameters(self):
        for name,value in [('E',float('nan')),('rho',-1),('yield_stress',-1)]:
            with self.subTest(name=name):
                candidate=plan()
                candidate[name]=value
                with self.assertRaises(ValueError):
                    check(candidate)
        candidate=plan()
        candidate['keys'][2]['position'][2]=.05
        with self.assertRaisesRegex(ValueError,'penetrate'):
            check(candidate)

    def test_rejects_reversed_motion_time(self):
        candidate=plan()
        candidate['keys'][2]['time']=.1
        with self.assertRaisesRegex(ValueError,'increase'):
            check(candidate)


if __name__ == '__main__':
    unittest.main()
