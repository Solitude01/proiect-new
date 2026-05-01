import os
import tempfile
import unittest

from image_distributor import DistributionError, ImageDistributor


class TestImageDistributor(unittest.TestCase):
    def setUp(self):
        self.dist = ImageDistributor(seed=42)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.src_dir = os.path.join(self.temp_dir.name, "src")
        os.makedirs(self.src_dir)

    def _create_files(self, names):
        for name in names:
            path = os.path.join(self.src_dir, name)
            with open(path, "w") as f:
                f.write("test")

    def test_scan_images_finds_supported_formats(self):
        self._create_files(["a.jpg", "b.png", "c.gif", "d.txt", "e.bmp"])
        result = self.dist.scan_images(self.src_dir)
        self.assertEqual(len(result), 4)
        self.assertTrue(any("a.jpg" in p for p in result))
        self.assertFalse(any("d.txt" in p for p in result))

    def test_scan_images_empty_dir(self):
        result = self.dist.scan_images(self.src_dir)
        self.assertEqual(result, [])

    def test_scan_images_case_insensitive(self):
        self._create_files(["A.JPG", "B.PNG", "c.JpEg"])
        result = self.dist.scan_images(self.src_dir)
        self.assertEqual(len(result), 3)

    def test_scan_images_sorted(self):
        self._create_files(["z.jpg", "a.png", "m.gif"])
        result = self.dist.scan_images(self.src_dir)
        names = [os.path.basename(p) for p in result]
        self.assertEqual(names, ["a.png", "m.gif", "z.jpg"])

    def test_scan_images_nonexistent_dir(self):
        with self.assertRaises(DistributionError):
            self.dist.scan_images("/nonexistent/dir/path")

    def test_validate_ratios_valid(self):
        self.assertTrue(ImageDistributor.validate_ratios([0.6, 0.4]))
        self.assertTrue(ImageDistributor.validate_ratios([1.0]))
        self.assertTrue(ImageDistributor.validate_ratios([0.33, 0.33, 0.34]))

    def test_validate_ratios_invalid_sum(self):
        self.assertFalse(ImageDistributor.validate_ratios([0.5, 0.3]))

    def test_validate_ratios_negative(self):
        self.assertFalse(ImageDistributor.validate_ratios([-0.1, 1.1]))

    def test_validate_ratios_empty(self):
        self.assertFalse(ImageDistributor.validate_ratios([]))

    def test_generate_plan_reproducible(self):
        self._create_files([f"img_{i:03d}.jpg" for i in range(20)])
        paths = self.dist.scan_images(self.src_dir)
        plan1 = self.dist.generate_plan(paths, [0.5, 0.5], ["dir_a", "dir_b"])
        plan2 = self.dist.generate_plan(paths, [0.5, 0.5], ["dir_a", "dir_b"])
        self.assertEqual(plan1, plan2)

    def test_generate_plan_different_seeds_different(self):
        self._create_files([f"img_{i:03d}.jpg" for i in range(20)])
        paths = self.dist.scan_images(self.src_dir)
        plan_a = ImageDistributor(seed=1).generate_plan(paths, [0.5, 0.5], ["a", "b"])
        plan_b = ImageDistributor(seed=999).generate_plan(paths, [0.5, 0.5], ["a", "b"])
        not_equal = any(
            set(plan_a[i]) != set(plan_b[i]) for i in range(len(plan_a))
        )
        self.assertTrue(not_equal)

    def test_generate_plan_all_images_assigned(self):
        self._create_files([f"img_{i:03d}.jpg" for i in range(15)])
        paths = self.dist.scan_images(self.src_dir)
        plan = self.dist.generate_plan(paths, [0.6, 0.4], ["a", "b"])
        total = sum(len(f) for f in plan)
        self.assertEqual(total, 15)

    def test_generate_plan_correct_ratios(self):
        self._create_files([f"img_{i:03d}.jpg" for i in range(100)])
        paths = self.dist.scan_images(self.src_dir)
        plan = self.dist.generate_plan(paths, [0.6, 0.4], ["a", "b"])
        self.assertEqual(len(plan[0]), 60)
        self.assertEqual(len(plan[1]), 40)

    def test_generate_plan_three_folders(self):
        self._create_files([f"img_{i:03d}.jpg" for i in range(100)])
        paths = self.dist.scan_images(self.src_dir)
        plan = self.dist.generate_plan(paths, [0.5, 0.3, 0.2], ["a", "b", "c"])
        self.assertEqual(len(plan[0]), 50)
        self.assertEqual(len(plan[1]), 30)
        self.assertEqual(len(plan[2]), 20)

    def test_generate_plan_zero_ratio(self):
        self._create_files([f"img_{i:03d}.jpg" for i in range(10)])
        paths = self.dist.scan_images(self.src_dir)
        plan = self.dist.generate_plan(paths, [0.0, 1.0], ["empty", "full"])
        self.assertEqual(len(plan[0]), 0)
        self.assertEqual(len(plan[1]), 10)

    def test_generate_plan_single_folder(self):
        self._create_files([f"img_{i:03d}.jpg" for i in range(10)])
        paths = self.dist.scan_images(self.src_dir)
        plan = self.dist.generate_plan(paths, [1.0], ["only"])
        self.assertEqual(len(plan[0]), 10)

    def test_generate_plan_bad_ratio(self):
        with self.assertRaises(DistributionError):
            self.dist.generate_plan(["a.jpg"], [0.3, 0.3], ["a", "b"])

    def test_generate_plan_mismatched_counts(self):
        with self.assertRaises(DistributionError):
            self.dist.generate_plan(["a.jpg"], [0.5, 0.5], ["a"])

    def test_execute_plan_copy(self):
        self._create_files(["a.jpg", "b.png", "c.gif", "d.jpg"])
        paths = self.dist.scan_images(self.src_dir)
        plan = self.dist.generate_plan(paths, [0.5, 0.5], ["a", "b"])
        out_a = os.path.join(self.temp_dir.name, "out_a")
        out_b = os.path.join(self.temp_dir.name, "out_b")
        stats = self.dist.execute_plan(plan, [out_a, out_b], mode="copy")
        self.assertEqual(stats["total"], 4)
        self.assertEqual(stats["copied"], 4)
        self.assertEqual(stats["errors"], [])
        self.assertEqual(len(os.listdir(out_a)) + len(os.listdir(out_b)), 4)
        # 原文件仍在
        self.assertEqual(len(os.listdir(self.src_dir)), 4)

    def test_execute_plan_move(self):
        self._create_files(["a.jpg", "b.png"])
        paths = self.dist.scan_images(self.src_dir)
        plan = self.dist.generate_plan(paths, [0.5, 0.5], ["a", "b"])
        out_a = os.path.join(self.temp_dir.name, "out_a")
        out_b = os.path.join(self.temp_dir.name, "out_b")
        stats = self.dist.execute_plan(plan, [out_a, out_b], mode="move")
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["moved"], 2)
        self.assertEqual(len(os.listdir(self.src_dir)), 0)

    def test_execute_plan_progress_callback(self):
        self._create_files(["a.jpg", "b.jpg", "c.jpg"])
        paths = self.dist.scan_images(self.src_dir)
        plan = self.dist.generate_plan(paths, [1.0], ["all"])
        out = os.path.join(self.temp_dir.name, "out")
        progress = []

        def cb(current, total):
            progress.append((current, total))

        self.dist.execute_plan(plan, [out], mode="copy", progress_callback=cb)
        self.assertEqual(len(progress), 3)
        self.assertEqual(progress[-1], (3, 3))

    def test_execute_plan_name_collision(self):
        # 先创建一个冲突文件
        out = os.path.join(self.temp_dir.name, "out")
        os.makedirs(out)
        with open(os.path.join(out, "a.jpg"), "w") as f:
            f.write("existing")
        self._create_files(["a.jpg"])
        paths = self.dist.scan_images(self.src_dir)
        plan = self.dist.generate_plan(paths, [1.0], ["out"])
        stats = self.dist.execute_plan(plan, [out], mode="copy")
        self.assertEqual(stats["total"], 1)
        files = os.listdir(out)
        self.assertIn("a_dup1.jpg", files)

    def test_execute_plan_bad_mode(self):
        with self.assertRaises(DistributionError):
            self.dist.execute_plan([[]], ["dir"], mode="invalid")


if __name__ == "__main__":
    unittest.main()
