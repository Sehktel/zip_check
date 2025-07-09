from PIL import Image, ImageDraw, ImageFont
import os

def create_icon(size=256):
    """Создание простой иконки с текстом ZIP"""
    # Создаем новое изображение с прозрачным фоном
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Рисуем желтый прямоугольник (архив)
    margin = size // 8
    rect_width = size - 2 * margin
    rect_height = int(rect_width * 1.2)
    draw.rectangle(
        [margin, margin, margin + rect_width, margin + rect_height],
        fill='#FFD700',
        outline='#000000',
        width=max(1, size // 32)
    )
    
    # Рисуем верхнюю часть архива
    top_height = rect_height // 6
    draw.rectangle(
        [margin, margin, margin + rect_width, margin + top_height],
        fill='#FFED4A',
        outline='#000000',
        width=max(1, size // 32)
    )
    
    # Рисуем молнию
    lightning_points = [
        (size//2, margin + top_height + size//8),  # верх
        (size//2 + size//6, size//2),  # правый выступ
        (size//2, size//2),  # центр
        (size//2 + size//8, size - margin - size//8),  # низ
        (size//2 - size//6, size//2),  # левый выступ
        (size//2, size//2),  # центр
    ]
    draw.polygon(lightning_points, fill='#FF4444', outline='#000000', width=max(1, size // 32))
    
    # Добавляем текст ZIP
    font_size = size // 4
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except:
        font = ImageFont.load_default()
    
    text = "ZIP"
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    
    text_x = (size - text_width) // 2
    text_y = size - margin - text_height - size//8
    draw.text((text_x, text_y), text, font=font, fill='#000000')
    
    return img

def create_ico(ico_path, sizes=[16, 32, 48, 64, 128, 256]):
    """Создание ICO файла с разными размерами"""
    images = []
    for size in sizes:
        img = create_icon(size)
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
    ico_path = os.path.join(current_dir, 'resources', 'icon.ico')
    create_ico(ico_path) 