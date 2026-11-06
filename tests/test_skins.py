import unittest

from queryminder.skins import ANIMATIONS, MASCOTS, SKINS


class SkinDataTests(unittest.TestCase):
    def test_mascots_exist(self):
        for s in SKINS:
            if s.mascot:
                self.assertIn(s.mascot, MASCOTS, s.key)
            lo, hi = s.anim_idle
            self.assertTrue(0 < lo <= hi, s.key)

    def test_animation_frames_use_known_colours(self):
        for key, anims in ANIMATIONS.items():
            self.assertIn(key, MASCOTS)
            palette = MASCOTS[key][1]
            base_h = len(MASCOTS[key][0])
            names = [a.name for a in anims]
            self.assertEqual(len(names), len(set(names)), key)
            for a in anims:
                self.assertTrue(a.frames, a.name)
                self.assertTrue(1 <= a.repeat[0] <= a.repeat[1], a.name)
                for f in a.frames:
                    self.assertGreater(f.ms, 0, a.name)
                    self.assertEqual(len(f.rows), base_h, a.name)
                    for row in f.rows:
                        self.assertTrue(set(row) <= set(palette) | {"."}, (a.name, row))

    def test_dalek_has_several_animations(self):
        self.assertGreaterEqual(len(ANIMATIONS["dalek"]), 3)


if __name__ == "__main__":
    unittest.main()
