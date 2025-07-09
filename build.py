import PyInstaller.__main__
import os
import sys
from pathlib import Path

def build_exe():
    """Сборка exe файла"""
    # Путь к иконке
    icon_path = os.path.join('resources', 'icon.ico')
    
    # Создаем директорию resources если её нет
    os.makedirs('resources', exist_ok=True)
    
    # Параметры сборки
    params = [
        'archive_checker_gui.py',  # Главный скрипт
        '--name=ArchiveChecker',   # Имя exe файла
        '--onefile',              # Собрать в один файл
        '--windowed',             # Оконное приложение (без консоли)
        f'--icon={icon_path}',    # Путь к иконке
        '--clean',                # Очистить временные файлы
        # Добавляем файлы ресурсов
        '--add-data=resources;resources',
        '--add-data=settings.json;.',
        # Добавляем зависимости
        '--hidden-import=PyQt6',
    ]
    
    # Если Windows, добавляем специфичные параметры
    if sys.platform == 'win32':
        params.extend([
            '--runtime-tmpdir=.',  # Временные файлы в текущей директории
        ])
    
    # Запускаем сборку
    PyInstaller.__main__.run(params)

if __name__ == '__main__':
    build_exe() 