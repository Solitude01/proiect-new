#!/usr/bin/env python3
"""
生成浏览器扩展所需的 PNG 图标
"""

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("请先安装 Pillow: pip install Pillow")
    exit(1)

def create_icon(size):
    """创建指定尺寸的图标"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 背景
    padding = size // 8
    draw.rounded_rectangle(
        [padding, padding * 2, size - padding, size - padding * 2],
        radius=size // 10,
        fill=(66, 133, 244, 255),  # Google Blue
        outline=(26, 115, 232, 255),
        width=max(1, size // 20)
    )

    # 内部矩形 - 红色
    inner_padding = size // 5
    draw.rounded_rectangle(
        [inner_padding, size // 3, inner_padding + size // 4, size - inner_padding],
        radius=size // 20,
        fill=(234, 67, 53, 200)  # Google Red with opacity
    )

    # 内部矩形 - 绿色
    draw.rounded_rectangle(
        [inner_padding + size // 4 + 2, size // 2, inner_padding + size // 2, size - inner_padding],
        radius=size // 20,
        fill=(52, 168, 83, 200)  # Google Green with opacity
    )

    # 内部矩形 - 黄色
    draw.rounded_rectangle(
        [inner_padding + size // 2 + 4, size // 2.5, size - inner_padding, size - inner_padding],
        radius=size // 20,
        fill=(251, 188, 4, 200)  # Google Yellow with opacity
    )

    return img

def main():
    sizes = [16, 48, 128]

    for size in sizes:
        img = create_icon(size)
        filename = f"icons/icon{size}.png"
        img.save(filename)
        print(f"✓ 已生成 {filename}")

    print("\n所有图标生成完成！")

if __name__ == "__main__":
    main()
