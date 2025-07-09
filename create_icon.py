from PIL import Image, ImageDraw
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
    
    # Основная часть архива (с закругленными углами)
    for i in range(margin, margin + rect_width):
        for j in range(margin, margin + rect_height):
            # Проверяем, находится ли точка в закругленном прямоугольнике
            corner_radius = size // 16
            x_dist = min(i - margin, margin + rect_width - i)
            y_dist = min(j - margin, margin + rect_height - j)
            
            if x_dist < corner_radius and y_dist < corner_radius:
                # Точка в углу, проверяем расстояние до центра угла
                corner_x = margin + corner_radius if i < size//2 else margin + rect_width - corner_radius
                corner_y = margin + corner_radius if j < size//2 else margin + rect_height - corner_radius
                if ((i - corner_x) ** 2 + (j - corner_y) ** 2) ** 0.5 <= corner_radius:
                    draw.point((i, j), fill='#FFD700')
            else:
                draw.point((i, j), fill='#FFD700')
    
    # Рисуем верхнюю часть архива
    top_height = rect_height // 6
    for i in range(margin, margin + rect_width):
        for j in range(margin, margin + top_height):
            corner_radius = size // 32
            x_dist = min(i - margin, margin + rect_width - i)
            y_dist = min(j - margin, margin + top_height - j)
            
            if x_dist < corner_radius and y_dist < corner_radius:
                corner_x = margin + corner_radius if i < size//2 else margin + rect_width - corner_radius
                corner_y = margin + corner_radius if j < size//2 else margin + top_height - corner_radius
                if ((i - corner_x) ** 2 + (j - corner_y) ** 2) ** 0.5 <= corner_radius:
                    draw.point((i, j), fill='#FFED4A')
            else:
                draw.point((i, j), fill='#FFED4A')
    
    # Рисуем молнию
    lightning_width = size // 4
    lightning_height = size // 2
    center_x = size // 2
    top_y = margin + top_height + size // 8
    bottom_y = margin + rect_height - size // 8
    
    lightning_points = [
        (center_x, top_y),  # верхняя точка
        (center_x + lightning_width//2, (top_y + bottom_y)//2 - lightning_height//4),  # правый выступ
        (center_x, (top_y + bottom_y)//2),  # центр
        (center_x + lightning_width//4, bottom_y),  # нижняя точка
        (center_x - lightning_width//2, (top_y + bottom_y)//2 + lightning_height//4),  # левый выступ
        (center_x, (top_y + bottom_y)//2),  # центр
    ]
    
    # Рисуем контур молнии
    draw.polygon(lightning_points, fill='#FF4444', outline='#CC0000', width=max(1, size // 64))
    
    # Добавляем блики на молнии
    highlight_points = [
        (center_x - lightning_width//8, top_y + lightning_height//8),
        (center_x + lightning_width//4, (top_y + bottom_y)//2 - lightning_height//8),
        (center_x - lightning_width//8, (top_y + bottom_y)//2 + lightning_height//8)
    ]
    for x, y in highlight_points:
        radius = size // 32
        for i in range(-radius, radius + 1):
            for j in range(-radius, radius + 1):
                if i*i + j*j <= radius*radius:
                    draw.point((x + i, y + j), fill='#FFAAAA')
    
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