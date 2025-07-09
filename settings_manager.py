import json
import os
from pathlib import Path
from typing import Dict, List, Optional

class SettingsManager:
    """
    Менеджер настроек приложения
    """
    def __init__(self):
        self.settings_file = Path("settings.json")
        self.settings = self.load_settings()
        
    def load_settings(self) -> dict:
        """Загрузка настроек из файла"""
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return self.get_default_settings()
        except Exception as e:
            print(f"Ошибка при загрузке настроек: {e}")
            return self.get_default_settings()
            
    def save_settings(self) -> bool:
        """Сохранение настроек в файл"""
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Ошибка при сохранении настроек: {e}")
            return False
            
    def get_default_settings(self) -> dict:
        """Получение настроек по умолчанию"""
        return {
            "default_directory": "D:/Telegram Desktop",
            "archive_types": {
                ".zip": {
                    "enabled": True,
                    "check_method": "internal",
                    "description": "ZIP архивы",
                    "extensions": [".zip"]
                },
                ".rar": {
                    "enabled": True,
                    "check_method": "unrar",
                    "description": "RAR архивы",
                    "extensions": [".rar", ".r00", ".part1.rar", ".001"]
                },
                ".7z": {
                    "enabled": True,
                    "check_method": "7z",
                    "description": "7-Zip архивы",
                    "extensions": [".7z", ".001"]
                }
            },
            "max_threads": 4,
            "recursive_scan": True
        }
        
    def get_enabled_extensions(self) -> List[str]:
        """Получение списка включенных расширений"""
        extensions = []
        for archive_type in self.settings["archive_types"].values():
            if archive_type["enabled"]:
                extensions.extend(archive_type["extensions"])
        return extensions
        
    def get_default_directory(self) -> str:
        """Получение директории по умолчанию"""
        return self.settings.get("default_directory", "")
        
    def set_default_directory(self, directory: str) -> None:
        """Установка директории по умолчанию"""
        self.settings["default_directory"] = directory
        self.save_settings()
        
    def get_max_threads(self) -> int:
        """Получение максимального количества потоков"""
        return self.settings.get("max_threads", 4)
        
    def get_recursive_scan(self) -> bool:
        """Получение настройки рекурсивного сканирования"""
        return self.settings.get("recursive_scan", True)
        
    def get_archive_types(self) -> Dict:
        """Получение настроек типов архивов"""
        return self.settings.get("archive_types", {}) 