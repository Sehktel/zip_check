import os
import zipfile
import py7zr
import rarfile
import logging
from pathlib import Path
from typing import List, Dict, Tuple

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ArchiveChecker:
    """
    Класс для проверки целостности архивов различных форматов.
    Поддерживает форматы: ZIP, 7Z, RAR
    """
    
    def __init__(self, directory: str):
        """
        Инициализация checker'а
        
        Args:
            directory (str): Путь к директории с архивами
        """
        self.directory = Path(directory)
        self.corrupted_archives: Dict[str, str] = {}
        
        # Настройка путей к внешним программам для Windows
        rarfile.UNRAR_TOOL = "C:\\Program Files\\WinRAR\\UnRAR.exe"
        
    def check_zip(self, file_path: Path) -> Tuple[bool, str]:
        """
        Проверка ZIP архива
        
        Args:
            file_path (Path): Путь к архиву
            
        Returns:
            Tuple[bool, str]: (результат проверки, сообщение об ошибке)
        """
        try:
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                # Проверяем CRC и целостность структуры архива
                result = zip_ref.testzip()
                if result is not None:
                    return False, f"Поврежденный файл в архиве: {result}"
                return True, ""
        except Exception as e:
            return False, str(e)

    def check_7z(self, file_path: Path) -> Tuple[bool, str]:
        """
        Проверка 7Z архива
        
        Args:
            file_path (Path): Путь к архиву
            
        Returns:
            Tuple[bool, str]: (результат проверки, сообщение об ошибке)
        """
        try:
            with py7zr.SevenZipFile(file_path, 'r') as sz_ref:
                # Проверяем CRC архива
                sz_ref.test()
                return True, ""
        except Exception as e:
            return False, str(e)

    def check_rar(self, file_path: Path) -> Tuple[bool, str]:
        """
        Проверка RAR архива
        
        Args:
            file_path (Path): Путь к архиву
            
        Returns:
            Tuple[bool, str]: (результат проверки, сообщение об ошибке)
        """
        try:
            with rarfile.RarFile(file_path, 'r') as rar_ref:
                # Проверяем CRC архива
                rar_ref.testrar()
                return True, ""
        except Exception as e:
            return False, str(e)

    def check_archives(self) -> Dict[str, str]:
        """
        Проверка всех архивов в указанной директории
        
        Returns:
            Dict[str, str]: Словарь с информацией о поврежденных архивах
        """
        if not self.directory.exists():
            raise FileNotFoundError(f"Директория {self.directory} не существует")

        # Поддерживаемые расширения архивов
        extensions = {'.zip': self.check_zip, '.7z': self.check_7z, '.rar': self.check_rar}
        
        for file_path in self.directory.rglob("*"):
            if file_path.suffix.lower() in extensions:
                logger.info(f"Проверка архива: {file_path.name}")
                is_valid, error_msg = extensions[file_path.suffix.lower()](file_path)
                
                if not is_valid:
                    self.corrupted_archives[str(file_path)] = error_msg
                    logger.error(f"Архив поврежден: {file_path.name}. Причина: {error_msg}")
                else:
                    logger.info(f"Архив корректен: {file_path.name}")

        return self.corrupted_archives

    def save_report(self, output_file: str = "corrupted_archives.txt") -> None:
        """
        Сохранение отчета о поврежденных архивах в файл
        
        Args:
            output_file (str): Имя файла для сохранения отчета
        """
        if not self.corrupted_archives:
            logger.info("Все архивы корректны!")
            return

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("Список поврежденных архивов:\n\n")
            for archive_path, error in self.corrupted_archives.items():
                f.write(f"Файл: {archive_path}\n")
                f.write(f"Ошибка: {error}\n")
                f.write("-" * 80 + "\n")
        
        logger.info(f"Отчет сохранен в файл: {output_file}")

def main():
    """
    Основная функция для запуска проверки архивов
    """
    # Путь к директории с архивами (можно изменить на нужный)
    directory = r"C:\Users\YourUsername\Telegram Desktop\Downloads"
    
    try:
        checker = ArchiveChecker(directory)
        checker.check_archives()
        checker.save_report()
    except Exception as e:
        logger.error(f"Произошла ошибка: {e}")

if __name__ == "__main__":
    main() 