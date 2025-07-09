from cairosvg import svg2png
from PIL import Image
import io
import os

def svg_to_ico(svg_path, ico_path, sizes=[16, 32, 48, 64, 128, 256]):
    """Конвертация SVG в ICO с разными размерами"""
    images = []
    for size in sizes:
        # Конвертируем SVG в PNG
        with open(svg_path, 'rb') as f:
            svg_data = f.read()
        png_data = svg2png(bytestring=svg_data, output_width=size, output_height=size)
        
        # Создаем изображение из PNG данных
        img = Image.open(io.BytesIO(png_data))
        images.append(img)
    
    # Создаем директорию если её нет
    os.makedirs(os.path.dirname(ico_path), exist_ok=True)
    
    # Сохраняем как ICO
    images[0].save(
        ico_path,
        format='ICO',
        sizes=[(img.width, img.height) for img in images],
        append_images=images[1:]
    )

if __name__ == '__main__':
    current_dir = os.path.dirname(os.path.abspath(__file__))
    svg_path = os.path.join(current_dir, 'resources', 'icon.svg')
    ico_path = os.path.join(current_dir, 'resources', 'icon.ico')
    svg_to_ico(svg_path, ico_path) 