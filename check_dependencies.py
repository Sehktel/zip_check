import sys
import importlib
import subprocess
import os

def check_module(module_name):
    try:
        importlib.import_module(module_name)
        print(f"✓ Модуль {module_name} успешно импортирован")
        return True
    except ImportError as e:
        print(f"✗ Ошибка импорта модуля {module_name}: {e}")
        return False

def check_winrar():
    unrar_path = "C:\\Program Files\\WinRAR\\UnRAR.exe"
    if os.path.exists(unrar_path):
        print(f"✓ WinRAR найден: {unrar_path}")
        return True
    else:
        print(f"✗ WinRAR не найден по пути: {unrar_path}")
        return False

def main():
    print("Проверка зависимостей:")
    print("-" * 50)
    
    # Проверяем Python версию
    python_version = sys.version_info
    print(f"Версия Python: {python_version.major}.{python_version.minor}.{python_version.micro}")
    if python_version.major < 3 or (python_version.major == 3 and python_version.minor < 7):
        print("✗ Требуется Python 3.7 или выше")
        return False
    
    # Проверяем необходимые модули
    required_modules = ['PyQt6', 'py7zr', 'rarfile']
    all_modules_ok = all(check_module(module) for module in required_modules)
    
    # Проверяем наличие WinRAR
    winrar_ok = check_winrar()
    
    print("\nРезультаты проверки:")
    print("-" * 50)
    if all_modules_ok and winrar_ok:
        print("✓ Все зависимости установлены корректно")
        print("\nМожно запускать приложение командой:")
        print("python archive_checker_gui.py")
    else:
        print("✗ Обнаружены проблемы с зависимостями")
        print("\nУстановите недостающие зависимости командой:")
        print("pip install -r requirements.txt")

if __name__ == "__main__":
    main() 