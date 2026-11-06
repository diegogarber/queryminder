import unittest

from queryminder.monitors import MARGIN, Monitor, Rect, default_position, fit, is_reachable

PRIMARY = Monitor(Rect(0, 0, 1920, 1040), primary=True)  # 1080p minus taskbar
RIGHT = Monitor(Rect(1920, 0, 4480, 1400))  # second monitor to the right
LEFT = Monitor(Rect(-2560, 0, 0, 1400))  # second monitor to the left (negative coords)
W, H = 320, 250


class FitTests(unittest.TestCase):
    def test_no_saved_position_goes_to_primary_top_right(self):
        self.assertEqual(fit(None, None, W, H, [RIGHT, PRIMARY]), (1920 - W - MARGIN, MARGIN))

    def test_saved_on_existing_second_monitor_is_kept(self):
        self.assertEqual(fit(3000, 500, W, H, [PRIMARY, RIGHT]), (3000, 500))
        self.assertEqual(fit(-1000, 200, W, H, [PRIMARY, LEFT]), (-1000, 200))

    def test_saved_on_missing_monitor_moves_to_primary(self):
        self.assertEqual(fit(3000, 500, W, H, [PRIMARY]), default_position(W, [PRIMARY]))
        self.assertEqual(fit(-1000, 200, W, H, [PRIMARY]), default_position(W, [PRIMARY]))

    def test_partially_off_screen_is_nudged_inside(self):
        self.assertEqual(fit(1800, 900, W, H, [PRIMARY]), (1920 - W, 1040 - H))
        self.assertEqual(fit(-20, -10, W, H, [PRIMARY]), (0, 0))

    def test_resolution_shrank(self):
        small = Monitor(Rect(0, 0, 1280, 680), primary=True)
        self.assertEqual(fit(1500, 300, W, H, [small]), default_position(W, [small]))
        self.assertEqual(fit(1100, 600, W, H, [small]), (1280 - W, 680 - H))

    def test_straddling_two_monitors_stays_on_the_bigger_overlap(self):
        x, y = fit(1800, 100, W, H, [PRIMARY, RIGHT])  # 120 px on primary, 200 px on right
        self.assertEqual((x, y), (1920, 100))

    def test_no_monitors_returns_input(self):
        self.assertEqual(fit(5, 6, W, H, []), (5, 6))


class ReachableTests(unittest.TestCase):
    def test_reachable(self):
        self.assertTrue(is_reachable(100, 100, W, [PRIMARY]))
        self.assertTrue(is_reachable(1920 - 50, 100, W, [PRIMARY]))  # 50 px of header visible
        self.assertFalse(is_reachable(1920 - 20, 100, W, [PRIMARY]))
        self.assertFalse(is_reachable(100, -30, W, [PRIMARY]))  # header above the screen
        self.assertFalse(is_reachable(3000, 100, W, [PRIMARY]))


if __name__ == "__main__":
    unittest.main()
