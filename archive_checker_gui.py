import sys
import os
import json
import time
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton,
    QTextEdit, QFileDialog, QProgressBar, QLabel, QMessageBox,
    QHBoxLayout, QComboBox, QSpacerItem, QSizePolicy, QLineEdit,
    QCheckBox, QGroupBox, QGridLayout, QStyle, QStyleFactory
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QShortcut, QKeySequence, QIcon
from check_archives import ArchiveChecker
from settings_manager import SettingsManager
from settings_dialog import SettingsDialog
import logging
from pathlib import Path
import zipfile
import zlib
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Версия программы
VERSION = "1.0.0"

class ArchiveCheckerWorker(QThread):
    """
    Отдельный поток для проверки архивов
    """
    progress_signal = pyqtSignal(str)
    progress_percent_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(dict)
    stats_signal = pyqtSignal(dict)
    
    def __init__(self, directory, extensions, recursive=True, max_workers=None):
        super().__init__()
        self.directory = directory
        self.extensions = extensions
        self.recursive = recursive
        self.start_time = None
        self.total_files = 0
        self.processed_files = 0
        self.stop_flag = False
        self.executor = None  # Сохраняем ссылку на executor
        # Если max_workers не указано, используем количество ядер процессора
        self.max_workers = max_workers or max(1, multiprocessing.cpu_count() - 1)
        
        # Создаем handler для отправки логов в GUI
        self.log_handler = GUILogHandler(self.progress_signal)
        self.logger = logging.getLogger(__name__)
        self.logger.addHandler(self.log_handler)

    def stop(self):
        """Остановка проверки"""
        self.stop_flag = True
        self.logger.info("Остановка проверки...")
        if self.executor:
            self.executor.shutdown(wait=False)  # Принудительно завершаем все задачи

    def force_stop(self):
        """Принудительная остановка всех процессов"""
        self.stop_flag = True
        if self.executor:
            # Принудительно завершаем все задачи
            self.executor.shutdown(wait=False)
        # Принудительно завершаем текущий поток
        self.terminate()

    def count_archives(self):
        """
        Подсчет общего количества архивов в директории
        """
        count = 0
        if self.recursive:
            for root, _, files in os.walk(self.directory):
                count += sum(1 for f in files if any(f.lower().endswith(ext.lower()) for ext in self.extensions))
        else:
            files = os.listdir(self.directory)
            count = sum(1 for f in files if any(f.lower().endswith(ext.lower()) for ext in self.extensions))
        return count

    def process_archive(self, file_path, checker):
        """
        Обработка одного архива в отдельном потоке
        """
        if self.stop_flag:
            return None
            
        # Определяем метод проверки
        check_methods = {
            '.zip': checker.check_zip,
            '.7z': checker.check_7z,
            '.rar': checker.check_rar,
            '.r00': checker.check_rar,
            '.part1.rar': checker.check_rar,
            '.001': checker.check_rar
        }
        
        check_method = None
        for ext, method in check_methods.items():
            if file_path.name.lower().endswith(ext):
                check_method = method
                break
        
        if check_method:
            try:
                # Периодически проверяем stop_flag во время проверки
                checker.stop_flag = self.stop_flag
                is_valid, error_msg = check_method(file_path)
                
                # Проверяем stop_flag после длительной операции
                if self.stop_flag:
                    return None
                
                # Обновляем прогресс
                self.processed_files += 1
                progress = int((self.processed_files / self.total_files) * 100)
                self.progress_percent_signal.emit(progress)
                
                # Обновляем статистику
                elapsed_time = time.time() - self.start_time
                stats = {
                    'total_files': self.total_files,
                    'processed_files': self.processed_files,
                    'corrupted_files': 0,  # Будет обновлено позже
                    'elapsed_time': int(elapsed_time),
                    'avg_time_per_file': round(elapsed_time / self.processed_files, 2) if self.processed_files > 0 else 0
                }
                self.stats_signal.emit(stats)
                
                if not is_valid:
                    self.logger.error(f"Проверка архива: {file_path.name}; Ошибка: {error_msg}")
                    return str(file_path), error_msg
                else:
                    self.logger.info(f"Проверка архива: {file_path.name}; OK!")
                    return None
            except Exception as e:
                if not self.stop_flag:  # Логируем ошибку только если это не остановка
                    self.logger.error(f"Ошибка при проверке {file_path.name}: {str(e)}")
                return str(file_path), str(e)
        return None

    def run(self):
        try:
            self.start_time = time.time()
            self.total_files = self.count_archives()
            self.processed_files = 0
            self.stop_flag = False
            
            checker = ArchiveChecker(self.directory)
            corrupted_archives = {}
            
            # Собираем список всех архивов для проверки
            archives_to_check = []
            if self.recursive:
                for file_path in self.directory.rglob("*"):
                    if any(file_path.name.lower().endswith(ext.lower()) for ext in self.extensions):
                        archives_to_check.append(file_path)
            else:
                for file_path in self.directory.iterdir():
                    if file_path.is_file() and any(file_path.name.lower().endswith(ext.lower()) for ext in self.extensions):
                        archives_to_check.append(file_path)
            
            # Создаем пул потоков для параллельной обработки
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                self.executor = executor  # Сохраняем ссылку на executor
                # Запускаем задачи на проверку архивов
                future_to_archive = {
                    executor.submit(self.process_archive, archive, checker): archive
                    for archive in archives_to_check
                }
                
                # Собираем результаты по мере их готовности
                for future in as_completed(future_to_archive):
                    if self.stop_flag:
                        executor.shutdown(wait=False)
                        break
                        
                    result = future.result()
                    if result:
                        file_path, error_msg = result
                        corrupted_archives[file_path] = error_msg
                        
                        # Обновляем статистику поврежденных файлов
                        stats = {
                            'total_files': self.total_files,
                            'processed_files': self.processed_files,
                            'corrupted_files': len(corrupted_archives),
                            'elapsed_time': int(time.time() - self.start_time),
                            'avg_time_per_file': round((time.time() - self.start_time) / self.processed_files, 2) if self.processed_files > 0 else 0
                        }
                        self.stats_signal.emit(stats)
            
            self.finished_signal.emit(corrupted_archives)
            
        except Exception as e:
            self.logger.error(f"Ошибка: {str(e)}")
            self.finished_signal.emit({})
        finally:
            self.executor = None
            self.logger.removeHandler(self.log_handler)

class GUILogHandler(logging.Handler):
    def __init__(self, signal):
        super().__init__()
        self.signal = signal
        
    def emit(self, record):
        msg = self.format(record)
        self.signal.emit(msg)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Проверка целостности архивов v{VERSION}")
        self.setMinimumSize(800, 600)
        
        # Устанавливаем иконку
        icon_path = os.path.join('resources', 'icon.svg')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # Инициализируем менеджер настроек
        self.settings_manager = SettingsManager()
        
        # Устанавливаем стиль
        if sys.platform == 'win32':
            QApplication.setStyle(QStyleFactory.create('Fusion'))
        
        # Определяем оптимальное количество потоков из настроек
        self.max_workers = self.settings_manager.get_max_threads()
        
        # Создаем центральный виджет и его layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Флаг для отслеживания состояния проверки
        self.is_checking = False
        
        self.setup_ui(layout)
        self.current_stats = {}
        
        # Загружаем настройки
        self.load_settings()
        
        # Добавляем горячие клавиши
        self.setup_shortcuts()

    def setup_shortcuts(self):
        """Настройка горячих клавиш"""
        # Ctrl+S для старта проверки
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self.start_check)
        # Ctrl+X для остановки
        QShortcut(QKeySequence("Ctrl+X"), self).activated.connect(self.stop_check)
        # Ctrl+Q для выхода
        QShortcut(QKeySequence("Ctrl+Q"), self).activated.connect(self.confirm_exit)

    def setup_ui(self, layout):
        # Группа настроек директории
        dir_group = QGroupBox("Настройки директории")
        dir_layout = QGridLayout()
        dir_layout.setColumnStretch(1, 1)  # Растягиваем вторую колонку
        
        # Поле выбора директории
        self.dir_edit = QLineEdit()
        self.select_dir_btn = QPushButton("Обзор...")
        self.select_dir_btn.clicked.connect(self.select_directory)
        dir_layout.addWidget(QLabel("Директория:"), 0, 0)
        dir_layout.addWidget(self.dir_edit, 0, 1)
        dir_layout.addWidget(self.select_dir_btn, 0, 2)
        
        # Поле расширений файлов и кнопка настроек
        self.ext_edit = QLineEdit()
        settings_btn = QPushButton("Настройки")
        settings_btn.clicked.connect(self.show_settings)
        dir_layout.addWidget(QLabel("Расширения:"), 1, 0)
        dir_layout.addWidget(self.ext_edit, 1, 1)
        dir_layout.addWidget(settings_btn, 1, 2)
        
        # Объединяем все настройки в одну строку
        options_layout = QHBoxLayout()
        
        # Флажок рекурсивной проверки
        self.recursive_check = QCheckBox("Проверять подпапки")
        options_layout.addWidget(self.recursive_check)
        
        # Выбор формата отчета
        options_layout.addWidget(QLabel("Формат отчета:"))
        self.report_format = QComboBox()
        self.report_format.addItems(["TXT", "CSV", "HTML", "JSON"])
        options_layout.addWidget(self.report_format)
        
        # Добавляем растяжку между элементами
        options_layout.addStretch()
        
        # Выбор количества потоков
        options_layout.addWidget(QLabel("Количество потоков:"))
        self.threads_combo = QComboBox()
        self.threads_combo.addItems([str(i) for i in range(1, self.max_workers + 1)])
        self.threads_combo.setCurrentText(str(self.max_workers))
        options_layout.addWidget(self.threads_combo)
        
        dir_layout.addLayout(options_layout, 2, 0, 1, 3)
        
        dir_group.setLayout(dir_layout)
        layout.addWidget(dir_group)
        
        # Область лога
        log_group = QGroupBox("Лог проверки")
        log_layout = QVBoxLayout()
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        log_layout.addWidget(self.log_area)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        # Прогресс и статистика
        progress_group = QGroupBox("Прогресс и статистика")
        progress_layout = QVBoxLayout()
        
        # Прогресс-бар и метка процента
        progress_bar_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.hide()
        progress_bar_layout.addWidget(self.progress_bar)
        self.progress_label = QLabel("0%")
        self.progress_label.hide()
        progress_bar_layout.addWidget(self.progress_label)
        progress_layout.addLayout(progress_bar_layout)
        
        # Статистика
        self.stats_label = QLabel("Статистика проверки:")
        progress_layout.addWidget(self.stats_label)
        
        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)
        
        # Кнопки управления (разделены на три равные части)
        buttons_layout = QHBoxLayout()
        
        # Левая часть - кнопка "Начать проверку"
        left_layout = QHBoxLayout()
        self.start_btn = QPushButton("Начать проверку (Ctrl+S)")
        self.start_btn.setStyleSheet("background-color: #98FB98;")  # Салатовый цвет
        self.start_btn.clicked.connect(self.start_check)
        left_layout.addWidget(self.start_btn)
        left_layout.addStretch()
        buttons_layout.addLayout(left_layout)
        
        # Центральная часть - кнопка "Остановить"
        center_layout = QHBoxLayout()
        center_layout.addStretch()
        self.stop_btn = QPushButton("Остановить проверку (Ctrl+X)")
        self.stop_btn.clicked.connect(self.stop_check)
        self.stop_btn.hide()  # Изначально скрыта
        center_layout.addWidget(self.stop_btn)
        center_layout.addStretch()
        buttons_layout.addLayout(center_layout)
        
        # Правая часть - кнопка "Выход"
        right_layout = QHBoxLayout()
        right_layout.addStretch()
        exit_btn = QPushButton("Выход (Ctrl+Q)")
        exit_btn.setStyleSheet("background-color: #ff6b6b;")  # Красный цвет
        exit_btn.clicked.connect(self.confirm_exit)
        right_layout.addWidget(exit_btn)
        buttons_layout.addLayout(right_layout)
        
        layout.addLayout(buttons_layout)

    def select_directory(self):
        """
        Выбор директории через диалог
        """
        directory = QFileDialog.getExistingDirectory(
            self,
            "Выберите директорию с архивами",
            self.dir_edit.text() or str(Path.home())
        )
        if directory:
            self.dir_edit.setText(directory)
            self.start_btn.setEnabled(True) # Enable start button after selecting directory
            self.log_area.clear()
            self.stats_label.setText("Статистика проверки:")
    
    def load_settings(self):
        """Загрузка настроек в интерфейс"""
        # Устанавливаем директорию по умолчанию
        default_dir = self.settings_manager.get_default_directory()
        if os.path.exists(default_dir):
            self.dir_edit.setText(default_dir)
            
        # Устанавливаем расширения
        extensions = self.settings_manager.get_enabled_extensions()
        self.ext_edit.setText(", ".join(extensions))
        
        # Устанавливаем рекурсивную проверку
        self.recursive_check.setChecked(self.settings_manager.get_recursive_scan())
        
        # Устанавливаем количество потоков
        max_threads = self.settings_manager.get_max_threads()
        index = self.threads_combo.findText(str(max_threads))
        if index >= 0:
            self.threads_combo.setCurrentIndex(index)

    def show_settings(self):
        """Показ диалога настроек"""
        dialog = SettingsDialog(self.settings_manager, self)
        if dialog.exec():
            self.load_settings()

    def get_extensions(self):
        """Получение списка расширений из поля ввода"""
        return [ext.strip().lower() for ext in self.ext_edit.text().split(",") if ext.strip()]
    
    def stop_check(self):
        """Остановка проверки архивов"""
        # Проверяем, идет ли проверка
        if not self.is_checking:
            return
            
        if hasattr(self, 'worker') and self.worker.isRunning():
            # Сначала пробуем остановить мягко
            self.worker.stop()
            self.stop_btn.setEnabled(False)
            
            # Даем 3 секунды на мягкую остановку
            start_time = time.time()
            while self.worker.isRunning() and (time.time() - start_time) < 3:
                time.sleep(0.1)
                QApplication.processEvents()  # Позволяем GUI обновляться
            
            # Если поток все еще работает, используем force_stop
            if self.worker.isRunning():
                self.worker.force_stop()
                self.log_area.append('<span style="color: #ff6b6b;">Проверка принудительно остановлена!</span>')
            else:
                self.log_area.append('<span style="color: #ff6b6b;">Проверка остановлена.</span>')
            
            self.stop_btn.hide()
            
            # Включаем элементы управления
            self.dir_edit.setEnabled(True)
            self.select_dir_btn.setEnabled(True)
            self.recursive_check.setEnabled(True)
            self.threads_combo.setEnabled(True)
            self.report_format.setEnabled(True)
            self.ext_edit.setEnabled(True)
            self.start_btn.setEnabled(True)
            self.start_btn.setText("Начать проверку (Ctrl+S)")
            
            # Сбрасываем флаг проверки
            self.is_checking = False

    def start_check(self):
        """Запуск проверки архивов"""
        # Проверяем, не идет ли уже проверка
        if self.is_checking:
            return
            
        directory = self.dir_edit.text()
        if not directory or not os.path.exists(directory):
            QMessageBox.warning(self, "Ошибка", "Выберите существующую директорию")
            return
        
        # Проверяем наличие расширений
        if not self.ext_edit.text().strip():
            QMessageBox.warning(self, "Ошибка", "Укажите хотя бы одно расширение файла")
            return
        
        # Устанавливаем флаг проверки
        self.is_checking = True
        
        # Отключаем элементы управления во время сканирования
        self.dir_edit.setEnabled(False)
        self.select_dir_btn.setEnabled(False)
        self.recursive_check.setEnabled(False)
        self.threads_combo.setEnabled(False)
        self.report_format.setEnabled(False)
        self.ext_edit.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.start_btn.setText("Проверка...")
        self.stop_btn.show()
        self.stop_btn.setEnabled(True)
        
        # Очищаем предыдущие результаты
        self.log_area.clear()
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.progress_label.show()
        
        # Запускаем проверку в отдельном потоке
        self.worker = ArchiveCheckerWorker(
            Path(directory),
            self.get_extensions(),
            self.recursive_check.isChecked(),
            int(self.threads_combo.currentText())
        )
        
        # Подключаем сигналы
        self.worker.progress_signal.connect(self.update_log)
        self.worker.progress_percent_signal.connect(self.update_progress)
        self.worker.finished_signal.connect(self.check_finished)
        self.worker.stats_signal.connect(self.update_stats)
        
        # Запускаем поток
        self.worker.start()

    def update_stats(self, stats):
        """Обновление статистики"""
        if not hasattr(self, 'stats_label'):
            return
            
        stats_text = (
            f"Всего файлов: {stats.get('total_files', 0)}\n"
            f"Обработано файлов: {stats.get('processed_files', 0)}\n"
            f"Поврежденных файлов: {stats.get('corrupted_files', 0)}\n"
            f"Затраченное время: {stats.get('elapsed_time', 0)} сек.\n"
            f"Среднее время на файл: {stats.get('avg_time_per_file', 0)} сек."
        )
        self.stats_label.setText(f"Статистика проверки:\n{stats_text}")
    
    def update_progress(self, percent):
        self.progress_bar.setValue(percent)
        self.progress_label.setText(f"{percent}%")
    
    def update_log(self, message):
        """Обновление лога с форматированием"""
        # Определяем тип сообщения по ключевым словам
        if "Ошибка" in message:
            message = f'<span style="color: red;">{message}</span>'
        elif "OK!" in message:
            message = f'<span style="color: green;">{message}</span>'
        elif "Проверка архива" in message:
            # Форматируем сообщение о проверке
            parts = message.split(';')
            if len(parts) == 2:
                file_info = parts[0].strip()
                status = parts[1].strip()
                if "OK!" in status:
                    status_color = "green"
                else:
                    status_color = "red"
                message = f'<div style="margin: 2px 0;"><span style="color: #0066cc;">{file_info}</span>; <span style="color: {status_color};">{status}</span></div>'
        
        # Добавляем сообщение в лог
        self.log_area.append(message)
        # Прокручиваем до последнего сообщения
        self.log_area.verticalScrollBar().setValue(self.log_area.verticalScrollBar().maximum())
    
    def save_report_txt(self, corrupted_archives, report_path):
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("Отчет о проверке архивов\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Дата проверки: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Директория: {self.dir_edit.text()}\n")
            f.write(f"Расширения: {', '.join(self.get_extensions())}\n")
            f.write(f"Рекурсивная проверка: {'Да' if self.recursive_check.isChecked() else 'Нет'}\n\n")
            
            # Статистика
            f.write("Статистика:\n")
            f.write("-" * 20 + "\n")
            for key, value in self.current_stats.items():
                f.write(f"{key}: {value}\n")
            f.write("\n")
            
            # Поврежденные архивы
            f.write("Поврежденные архивы:\n")
            f.write("-" * 20 + "\n")
            for archive_path, error in corrupted_archives.items():
                f.write(f"Файл: {archive_path}\n")
                f.write(f"Ошибка: {error}\n")
                f.write("-" * 50 + "\n")
    
    def save_report_csv(self, corrupted_archives, report_path):
        """Сохранение отчета в формате CSV"""
        try:
            with open(report_path, 'w', encoding='utf-8', newline='') as f:
                # Записываем заголовки
                f.write("Путь к файлу,Тип ошибки,Дата проверки\n")
                
                # Записываем данные
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                for archive_path, error in corrupted_archives.items():
                    f.write(f'"{archive_path}","{error}","{current_time}"\n')
            
            self.log_area.append(f"Отчет сохранен в {report_path}")
            return True
        except Exception as e:
            self.log_area.append(f"Ошибка при сохранении отчета: {str(e)}")
            return False

    def save_report_json(self, corrupted_archives, report_path):
        """Сохранение отчета в текстовом формате, похожем на JSON"""
        try:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            report_data = {
                "scan_date": current_time,
                "total_files": self.current_stats.get('total_files', 0),
                "processed_files": self.current_stats.get('processed_files', 0),
                "corrupted_files": len(corrupted_archives),
                "corrupted_archives": [
                    {
                        "path": str(path),
                        "error": error
                    }
                    for path, error in corrupted_archives.items()
                ]
            }
            
            with open(report_path, 'w', encoding='utf-8') as f:
                # Используем текстовый формат, похожий на JSON
                f.write("{\n")
                f.write(f'    "scan_date": "{report_data["scan_date"]}",\n')
                f.write(f'    "total_files": {report_data["total_files"]},\n')
                f.write(f'    "processed_files": {report_data["processed_files"]},\n')
                f.write(f'    "corrupted_files": {report_data["corrupted_files"]},\n')
                f.write('    "corrupted_archives": [\n')
                
                # Записываем информацию о каждом поврежденном архиве
                for i, archive in enumerate(report_data["corrupted_archives"]):
                    f.write('        {\n')
                    f.write(f'            "path": "{archive["path"]}",\n')
                    f.write(f'            "error": "{archive["error"]}"\n')
                    f.write('        }' + (',' if i < len(report_data["corrupted_archives"]) - 1 else '') + '\n')
                
                f.write('    ]\n')
                f.write("}\n")
            
            self.log_area.append(f"Отчет сохранен в {report_path}")
            return True
        except Exception as e:
            self.log_area.append(f"Ошибка при сохранении отчета: {str(e)}")
            return False

    def save_report_html(self, corrupted_archives, report_path):
        """Сохранение отчета в формате HTML"""
        try:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            html_content = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Отчет о проверке архивов</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 5px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 2px solid #eee;
            padding-bottom: 10px;
        }}
        .stats {{
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #f8f9fa;
            font-weight: bold;
        }}
        tr:hover {{
            background-color: #f5f5f5;
        }}
        .error {{
            color: #dc3545;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Отчет о проверке архивов</h1>
        <div class="stats">
            <p><strong>Дата проверки:</strong> {current_time}</p>
            <p><strong>Всего файлов:</strong> {self.current_stats.get('total_files', 0)}</p>
            <p><strong>Обработано файлов:</strong> {self.current_stats.get('processed_files', 0)}</p>
            <p><strong>Найдено поврежденных архивов:</strong> {len(corrupted_archives)}</p>
        </div>
        
        <h2>Список поврежденных архивов</h2>
        <table>
            <thead>
                <tr>
                    <th>№</th>
                    <th>Путь к файлу</th>
                    <th>Описание ошибки</th>
                </tr>
            </thead>
            <tbody>
"""
            
            # Добавляем информацию о каждом поврежденном архиве
            for i, (archive_path, error) in enumerate(corrupted_archives.items(), 1):
                html_content += f"""
                <tr>
                    <td>{i}</td>
                    <td>{archive_path}</td>
                    <td class="error">{error}</td>
                </tr>"""
            
            html_content += """
            </tbody>
        </table>
    </div>
</body>
</html>
"""
            
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            self.log_area.append(f"Отчет сохранен в {report_path}")
            return True
        except Exception as e:
            self.log_area.append(f"Ошибка при сохранении отчета: {str(e)}")
            return False

    def check_finished(self, corrupted_archives):
        """Обработка завершения проверки"""
        # Включаем элементы управления
        self.dir_edit.setEnabled(True)
        self.select_dir_btn.setEnabled(True)
        self.recursive_check.setEnabled(True)
        self.threads_combo.setEnabled(True)
        self.report_format.setEnabled(True)
        self.ext_edit.setEnabled(True)
        self.start_btn.setEnabled(True)
        self.start_btn.setText("Начать проверку (Ctrl+S)")
        self.stop_btn.hide()
        self.stop_btn.setEnabled(False)
        
        # Сбрасываем флаг проверки
        self.is_checking = False
        
        # Скрываем прогресс-бар
        self.progress_bar.hide()
        self.progress_label.hide()
        
        # Выводим статистику
        total_files = self.current_stats.get('total_files', 0)
        processed_files = self.current_stats.get('processed_files', 0)
        elapsed_time = self.current_stats.get('elapsed_time', 0)
        avg_time = self.current_stats.get('avg_time_per_file', 0)
        
        stats_text = (
            f"\nПроверка завершена!\n"
            f"Всего файлов: {total_files}\n"
            f"Обработано файлов: {processed_files}\n"
            f"Поврежденных архивов: {len(corrupted_archives)}\n"
            f"Затраченное время: {elapsed_time} сек.\n"
            f"Среднее время на файл: {avg_time} сек.\n"
        )
        self.log_area.append(stats_text)
        
        # Если есть поврежденные архивы, предлагаем сохранить отчет
        if corrupted_archives:
            reply = QMessageBox.question(
                self,
                "Сохранить отчет",
                "Найдены поврежденные архивы. Хотите сохранить отчет?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # Создаем диалог сохранения файла
                file_dialog = QFileDialog(self)
                file_dialog.setWindowTitle("Сохранить отчет")
                file_dialog.setNameFilter(
                    "Text Files (*.txt);;CSV Files (*.csv);;HTML Files (*.html);;Plain JSON (*.json)"
                )
                file_dialog.setDefaultSuffix("txt")
                
                if file_dialog.exec() == QFileDialog.DialogCode.Accepted:
                    file_path = file_dialog.selectedFiles()[0]
                    file_format = file_dialog.selectedNameFilter()
                    
                    # Определяем формат по расширению
                    if file_path.lower().endswith('.txt'):
                        success = self.save_report_txt(corrupted_archives, file_path)
                    elif file_path.lower().endswith('.csv'):
                        success = self.save_report_csv(corrupted_archives, file_path)
                    elif file_path.lower().endswith('.html'):
                        success = self.save_report_html(corrupted_archives, file_path)
                    elif file_path.lower().endswith('.json'):
                        success = self.save_report_json(corrupted_archives, file_path)
                    
                    if not success:
                        QMessageBox.warning(
                            self,
                            "Ошибка",
                            "Не удалось сохранить отчет. Проверьте права доступа к файлу."
                        )

    def confirm_exit(self):
        """Подтверждение выхода из программы"""
        reply = QMessageBox.question(
            self,
            'Подтверждение выхода',
            'Вы уверены, что хотите выйти из программы?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Если идет проверка, останавливаем её
            if hasattr(self, 'worker') and self.worker.isRunning():
                self.worker.force_stop()
                self.worker.wait(100)
            QApplication.quit()

    def closeEvent(self, event):
        """Обработка закрытия окна"""
        if hasattr(self, 'worker') and self.worker.isRunning():
            reply = QMessageBox.question(
                self,
                'Подтверждение выхода',
                'Проверка архивов еще выполняется. Вы уверены, что хотите выйти?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # Принудительно останавливаем все процессы
                self.worker.force_stop()
                # Ждем небольшую паузу для завершения процессов
                self.worker.wait(100)
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

class ArchiveChecker:
    """Класс для проверки целостности архивов"""
    
    def __init__(self, directory):
        self.directory = directory
        self.stop_flag = False  # Флаг для остановки проверки
        
    def find_multipart_files(self, base_file):
        """
        Поиск всех частей многотомного архива
        """
        base_path = Path(base_file)
        base_name = base_path.stem
        directory = base_path.parent
        
        # Шаблоны для разных форматов многотомных архивов
        patterns = [
            # ZIP: name.z01, name.z02, ..., name.zip
            (f"{base_name}.z[0-9][0-9]", f"{base_name}.zip"),
            # RAR: name.part1.rar, name.part2.rar, ...
            (f"{base_name}.part[0-9]*.rar", None),
            # RAR (старый формат): name.r00, name.r01, ..., name.rar
            (f"{base_name}.r[0-9][0-9]", f"{base_name}.rar"),
            # 7z: name.001, name.002, ..., name.7z
            (f"{base_name}.[0-9][0-9][0-9]", f"{base_name}.7z")
        ]
        
        found_parts = []
        for pattern, last_part in patterns:
            parts = list(directory.glob(pattern))
            if parts:
                if last_part:
                    last = directory / last_part
                    if last.exists():
                        parts.append(last)
                found_parts.extend(parts)
                break
        
        return sorted(found_parts) if found_parts else []

    def check_multipart_sequence(self, parts):
        """
        Проверка последовательности частей многотомного архива
        """
        if not parts:
            return False, "Не найдены части многотомного архива"
            
        # Определяем формат по первому файлу
        first_part = parts[0].name
        base_name = parts[0].stem
        
        if first_part.endswith('.z01'):  # ZIP
            expected = [f"{base_name}.z{i:02d}" for i in range(1, len(parts))]
            expected.append(f"{base_name}.zip")
        elif '.part' in first_part:  # RAR (новый формат)
            expected = [f"{base_name}.part{i}.rar" for i in range(1, len(parts) + 1)]
        elif first_part.endswith('.r00'):  # RAR (старый формат)
            expected = [f"{base_name}.r{i:02d}" for i in range(0, len(parts) - 1)]
            expected.append(f"{base_name}.rar")
        elif first_part.endswith('.001'):  # 7z
            expected = [f"{base_name}.{i:03d}" for i in range(1, len(parts))]
            expected.append(f"{base_name}.7z")
        else:
            return False, "Неизвестный формат многотомного архива"
            
        actual = [p.name for p in parts]
        missing = set(expected) - set(actual)
        
        if missing:
            return False, f"Отсутствуют части архива: {', '.join(sorted(missing))}"
            
        return True, ""

    def check_zip(self, file_path):
        """Проверка ZIP архива"""
        try:
            with zipfile.ZipFile(file_path, 'r') as zip_file:
                # Проверяем каждый файл в архиве
                for file_info in zip_file.infolist():
                    if self.stop_flag:  # Проверяем флаг остановки
                        return False, "Проверка прервана пользователем"
                    try:
                        # Проверяем CRC32
                        with zip_file.open(file_info.filename) as f:
                            while f.read(8192):  # Читаем по частям
                                if self.stop_flag:  # Проверяем флаг остановки
                                    return False, "Проверка прервана пользователем"
                    except (zipfile.BadZipFile, zlib.error) as e:
                        return False, f"Ошибка CRC в файле {file_info.filename}: {str(e)}"
                return True, None
        except zipfile.BadZipFile as e:
            return False, f"Поврежденный ZIP архив: {str(e)}"
        except Exception as e:
            return False, f"Ошибка при проверке архива: {str(e)}"
            
    def check_rar(self, file_path):
        """Проверка RAR архива"""
        try:
            # Проверяем наличие мультичастей
            parts = self.find_multipart_files(file_path)
            if parts:
                if self.stop_flag:  # Проверяем флаг остановки
                    return False, "Проверка прервана пользователем"
                return self.check_multipart_sequence(parts)
            
            # Проверяем с помощью unrar
            result = subprocess.run(
                ['unrar', 't', '-inul', str(file_path)],
                capture_output=True,
                text=True
            )
            
            if self.stop_flag:  # Проверяем флаг остановки
                return False, "Проверка прервана пользователем"
                
            if result.returncode != 0:
                return False, f"Ошибка в RAR архиве: {result.stderr}"
            return True, None
        except Exception as e:
            return False, f"Ошибка при проверке архива: {str(e)}"
            
    def check_7z(self, file_path):
        """Проверка 7Z архива"""
        try:
            # Проверяем наличие мультичастей
            parts = self.find_multipart_files(file_path)
            if parts:
                if self.stop_flag:  # Проверяем флаг остановки
                    return False, "Проверка прервана пользователем"
                return self.check_multipart_sequence(parts)
            
            # Проверяем с помощью 7z
            result = subprocess.run(
                ['7z', 't', str(file_path)],
                capture_output=True,
                text=True
            )
            
            if self.stop_flag:  # Проверяем флаг остановки
                return False, "Проверка прервана пользователем"
                
            if result.returncode != 0:
                return False, f"Ошибка в 7Z архиве: {result.stderr}"
            return True, None
        except Exception as e:
            return False, f"Ошибка при проверке архива: {str(e)}"

def main():
    try:
        print("Проверка наличия DISPLAY...")
        if not QApplication.instance():
            print("Создание QApplication...")
            app = QApplication(sys.argv)
        else:
            print("QApplication уже существует...")
            app = QApplication.instance()

        print("Доступные стили Qt:", QStyleFactory.keys())
        
        if 'Windows' in QStyleFactory.keys():
            print("Установка стиля Windows...")
            app.setStyle('Windows')
        elif 'Fusion' in QStyleFactory.keys():
            print("Установка стиля Fusion...")
            app.setStyle('Fusion')
        
        print("Текущий стиль:", app.style().objectName())

        print("Проверка доступности графического окружения...")
        if not app.primaryScreen():
            raise RuntimeError("Не удалось получить доступ к экрану")

        print("Создание главного окна...")
        window = MainWindow()
        
        # Устанавливаем окно по центру экрана
        screen = app.primaryScreen().geometry()
        window.setGeometry(
            (screen.width() - window.width()) // 2,
            (screen.height() - window.height()) // 2,
            window.width(),
            window.height()
        )
        
        print("Отображение окна...")
        window.show()
        window.raise_()
        window.activateWindow()
        
        print("Запуск главного цикла приложения...")
        return app.exec()
    except Exception as e:
        print(f"Критическая ошибка при запуске приложения: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    print("Старт программы")
    sys.exit(main()) 