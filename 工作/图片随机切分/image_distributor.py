import os
import random
import shutil
from pathlib import Path
from typing import Callable

SUPPORTED_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp", ".svg")


class DistributionError(Exception):
    pass


class ImageDistributor:
    def __init__(self, seed: int = 42):
        self.seed = seed

    def scan_images(self, source_dir: str) -> list[str]:
        """扫描目录中所有支持的图片文件，返回按名称排序的绝对路径列表"""
        source = Path(source_dir)
        if not source.is_dir():
            raise DistributionError(f"输入目录不存在: {source_dir}")

        images = []
        for entry in sorted(source.iterdir()):
            if entry.is_file() and entry.suffix.lower() in SUPPORTED_EXTENSIONS:
                images.append(str(entry.resolve()))
        return images

    @staticmethod
    def validate_ratios(ratios: list[float]) -> bool:
        """验证比例列表总和是否等于 1.0"""
        if not ratios:
            return False
        if any(r < 0 for r in ratios):
            return False
        return abs(sum(ratios) - 1.0) < 1e-9

    def generate_plan(
        self,
        image_paths: list[str],
        ratios: list[float],
        output_dirs: list[str],
    ) -> list[list[str]]:
        """根据比例随机分配图片到各个输出文件夹"""
        if not self.validate_ratios(ratios):
            raise DistributionError(f"比例总和必须为 100%，当前值: {sum(ratios):.1%}")
        if len(ratios) != len(output_dirs):
            raise DistributionError("比例列表与输出文件夹数量不匹配")

        n = len(image_paths)
        shuffled = list(image_paths)
        rng = random.Random(self.seed)
        rng.shuffle(shuffled)

        counts = []
        cumulative = 0
        for r in ratios[:-1]:
            c = max(0, round(r * n))
            counts.append(c)
            cumulative += c
        counts.append(n - cumulative)

        # 修正舍入误差导致的边界情况
        while sum(counts) < n:
            counts[-1] += 1
        while sum(counts) > n:
            diff = sum(counts) - n
            for i in range(len(counts) - 1, -1, -1):
                if counts[i] >= diff:
                    counts[i] -= diff
                    break

        plan = []
        start = 0
        for c in counts:
            plan.append(shuffled[start : start + c])
            start += c
        return plan

    def execute_plan(
        self,
        plan: list[list[str]],
        output_dirs: list[str],
        mode: str = "copy",
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> dict:
        """执行文件复制或移动，返回统计信息"""
        if mode not in ("copy", "move"):
            raise DistributionError(f"不支持的操作模式: {mode}")

        stats: dict = {"total": 0, "copied": 0, "moved": 0, "errors": []}
        total_files = sum(len(files) for files in plan)

        for files, dest_dir in zip(plan, output_dirs):
            os.makedirs(dest_dir, exist_ok=True)
            for src_path in files:
                dest_path = os.path.join(dest_dir, os.path.basename(src_path))
                dest_path = self._resolve_collision(dest_path)
                try:
                    if mode == "copy":
                        shutil.copy2(src_path, dest_path)
                        stats["copied"] += 1
                    else:
                        shutil.move(src_path, dest_path)
                        stats["moved"] += 1
                    stats["total"] += 1
                except (OSError, PermissionError) as e:
                    stats["errors"].append({"file": src_path, "error": str(e)})
                if progress_callback:
                    progress_callback(stats["total"], total_files)
        return stats

    @staticmethod
    def _resolve_collision(dest_path: str) -> str:
        """处理文件名冲突，追加 _dup1, _dup2 等后缀"""
        if not os.path.exists(dest_path):
            return dest_path
        base, ext = os.path.splitext(dest_path)
        counter = 1
        while True:
            new_path = f"{base}_dup{counter}{ext}"
            if not os.path.exists(new_path):
                return new_path
            counter += 1
