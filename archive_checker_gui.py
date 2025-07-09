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
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from check_archives import ArchiveChecker
import logging
from pathlib import Path
import zipfile
import zlib
import subprocess

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ArchiveCheckerWorker(QThread):
    """
    Отдельный поток для проверки архивов
    """
    progress_signal = pyqtSignal(str)
    progress_percent_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(dict)
    stats_signal = pyqtSignal(dict)
    
    def __init__(self, directory, extensions, recursive=True):
        super().__init__()
        self.directory = directory
        self.extensions = extensions
        self.recursive = recursive
        self.start_time = None
        self.total_files = 0
        self.processed_files = 0
        self.stop_flag = False
        
        # Создаем handler для отправки логов в GUI
        self.log_handler = GUILogHandler(self.progress_signal)
        self.logger = logging.getLogger(__name__)
        self.logger.addHandler(self.log_handler)

    def stop(self):
        """Остановка проверки"""
        self.stop_flag = True
        self.logger.info("Остановка проверки...")

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

    def run(self):
        try:
            self.start_time = time.time()
            self.total_files = self.count_archives()
            self.processed_files = 0
            self.stop_flag = False
            
            class ProgressArchiveChecker(ArchiveChecker):
                def __init__(self, directory, worker):
                    super().__init__(directory)
                    self.worker = worker
                
                def check_archives(self):
                    if not self.directory.exists():
                        raise FileNotFoundError(f"Директория {self.directory} не существует")
                    
                    # Создаем словарь методов проверки для каждого типа архива
                    check_methods = {
                        '.zip': self.check_zip,
                        '.7z': self.check_7z,
                        '.rar': self.check_rar,
                        '.r00': self.check_rar,  # Многотомные RAR архивы
                        '.part1.rar': self.check_rar,  # Новый формат многотомных RAR
                        '.001': self.check_rar  # Другой формат многотомных архивов
                    }
                    
                    # Функция для проверки файла
                    def check_file(file_path):
                        if self.worker.stop_flag:
                            return False
                            
                        # Определяем метод проверки
                        check_method = None
                        for ext, method in check_methods.items():
                            if file_path.name.lower().endswith(ext):
                                check_method = method
                                break
                        
                        if check_method:
                            is_valid, error_msg = check_method(file_path)
                            
                            if not is_valid:
                                self.corrupted_archives[str(file_path)] = error_msg
                                self.worker.logger.error(f"Проверка архива: {file_path.name}; Ошибка: {error_msg}")
                            else:
                                self.worker.logger.info(f"Проверка архива: {file_path.name}; OK!")
                            
                            # Обновляем прогресс
                            self.worker.processed_files += 1
                            progress = int((self.worker.processed_files / self.worker.total_files) * 100)
                            self.worker.progress_percent_signal.emit(progress)
                            
                            # Обновляем статистику
                            elapsed_time = time.time() - self.worker.start_time
                            stats = {
                                'total_files': self.worker.total_files,
                                'processed_files': self.worker.processed_files,
                                'corrupted_files': len(self.corrupted_archives),
                                'elapsed_time': int(elapsed_time),
                                'avg_time_per_file': round(elapsed_time / self.worker.processed_files, 2) if self.worker.processed_files > 0 else 0
                            }
                            self.worker.stats_signal.emit(stats)
                        return not self.worker.stop_flag
                    
                    # Обходим файлы
                    if self.worker.recursive:
                        for file_path in self.directory.rglob("*"):
                            if any(file_path.name.lower().endswith(ext.lower()) for ext in self.worker.extensions):
                                if not check_file(file_path):
                                    break
                    else:
                        for file_path in self.directory.iterdir():
                            if file_path.is_file() and any(file_path.name.lower().endswith(ext.lower()) for ext in self.worker.extensions):
                                if not check_file(file_path):
                                    break
                    
                    return self.corrupted_archives
            
            checker = ProgressArchiveChecker(self.directory, self)
            corrupted = checker.check_archives()
            self.finished_signal.emit(corrupted)
            
        except Exception as e:
            self.logger.error(f"Ошибка: {str(e)}")
            self.finished_signal.emit({})
        finally:
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
        self.setWindowTitle("Проверка целостности архивов")
        self.setMinimumSize(800, 600)
        
        # Устанавливаем стиль
        if sys.platform == 'win32':
            QApplication.setStyle(QStyleFactory.create('Fusion'))
        
        # Создаем центральный виджет и его layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        self.setup_ui(layout)
        self.current_stats = {}
        
        # Устанавливаем директорию по умолчанию
        default_dir = Path("D:/Telegram Desktop")
        if default_dir.exists():
            self.dir_edit.setText(str(default_dir))

    def setup_ui(self, layout):
        # Группа настроек директории
        dir_group = QGroupBox("Настройки директории")
        dir_layout = QGridLayout()
        
        # Поле для ввода пути
        self.dir_edit = QLineEdit()
        self.dir_edit.setPlaceholderText("Путь к директории с архивами")
        dir_layout.addWidget(self.dir_edit, 0, 0, 1, 2)
        
        # Кнопка выбора директории
        select_dir_btn = QPushButton("Обзор...")
        select_dir_btn.clicked.connect(self.select_directory)
        dir_layout.addWidget(select_dir_btn, 0, 2)
        
        # Флажок рекурсивной проверки
        self.recursive_check = QCheckBox("Проверять поддиректории")
        self.recursive_check.setChecked(True)
        dir_layout.addWidget(self.recursive_check, 1, 0)
        
        dir_group.setLayout(dir_layout)
        layout.addWidget(dir_group)
        
        # Группа настроек расширений
        ext_group = QGroupBox("Расширения архивов")
        ext_layout = QVBoxLayout()
        
        # Поле для ввода расширений
        self.ext_edit = QLineEdit()
        self.ext_edit.setPlaceholderText("Введите расширения через запятую (например: .zip, .rar, .7z, .r00, .part1.rar, .001)")
        self.ext_edit.setText(".zip, .rar, .7z, .r00, .part1.rar, .001")
        ext_layout.addWidget(self.ext_edit)
        
        ext_group.setLayout(ext_layout)
        layout.addWidget(ext_group)
        
        # Панель с кнопками и форматом отчета
        control_panel = QHBoxLayout()
        
        # Кнопки управления
        button_layout = QHBoxLayout()
        self.check_btn = QPushButton("Начать проверку")
        self.check_btn.clicked.connect(self.start_check)
        button_layout.addWidget(self.check_btn)
        
        self.stop_btn = QPushButton("Остановить")
        self.stop_btn.clicked.connect(self.stop_check)
        self.stop_btn.setEnabled(False)
        button_layout.addWidget(self.stop_btn)
        
        control_panel.addLayout(button_layout)
        
        control_panel.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        
        self.report_format = QComboBox()
        self.report_format.addItems(['TXT', 'HTML', 'JSON', 'CSV'])
        control_panel.addWidget(QLabel("Формат отчета:"))
        control_panel.addWidget(self.report_format)
        
        layout.addLayout(control_panel)
        
        # Статистика
        self.stats_label = QLabel("Статистика проверки:")
        layout.addWidget(self.stats_label)
        
        # Прогресс
        progress_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.hide()
        progress_layout.addWidget(self.progress_bar)
        
        self.progress_label = QLabel("0%")
        self.progress_label.hide()
        progress_layout.addWidget(self.progress_label)
        
        layout.addLayout(progress_layout)
        
        # Область для логов
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        layout.addWidget(self.log_area)

    def select_directory(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            "Выберите директорию с архивами",
            os.path.expanduser("~")
        )
        if directory:
            self.dir_edit.setText(directory)
            self.check_btn.setEnabled(True)
            self.log_area.clear()
            self.stats_label.setText("Статистика проверки:")
    
    def get_extensions(self):
        """Получение списка расширений из поля ввода"""
        extensions = [ext.strip() for ext in self.ext_edit.text().split(',')]
        return [ext if ext.startswith('.') else f'.{ext}' for ext in extensions]
    
    def stop_check(self):
        """Остановка проверки архивов"""
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.stop_btn.setEnabled(False)
            self.check_btn.setText("Начать проверку")

    def start_check(self):
        directory = self.dir_edit.text()
        if not directory:
            QMessageBox.warning(self, "Ошибка", "Выберите директорию для проверки")
            return
        
        extensions = self.get_extensions()
        if not extensions:
            QMessageBox.warning(self, "Ошибка", "Укажите хотя бы одно расширение файла")
            return
        
        self.check_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.show()
        self.progress_label.show()
        self.progress_bar.setValue(0)
        self.progress_label.setText("0%")
        self.log_area.clear()
        
        self.worker = ArchiveCheckerWorker(
            directory,
            extensions,
            self.recursive_check.isChecked()
        )
        self.worker.progress_signal.connect(self.update_log)
        self.worker.progress_percent_signal.connect(self.update_progress)
        self.worker.stats_signal.connect(self.update_stats)
        self.worker.finished_signal.connect(self.check_finished)
        self.worker.start()
    
    def update_stats(self, stats):
        self.current_stats = stats
        stats_text = (
            f"Всего архивов: {stats['total_files']}\n"
            f"Проверено: {stats['processed_files']}\n"
            f"Повреждено: {stats['corrupted_files']}\n"
            f"Прошло времени: {stats['elapsed_time']} сек\n"
            f"Среднее время на файл: {stats['avg_time_per_file']} сек"
        )
        self.stats_label.setText(f"Статистика проверки:\n{stats_text}")
    
    def update_progress(self, percent):
        self.progress_bar.setValue(percent)
        self.progress_label.setText(f"{percent}%")
    
    def update_log(self, message):
        self.log_area.append(message)
        scrollbar = self.log_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
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
    
    def save_report_html(self, corrupted_archives, report_path):
        html_content = f"""
        <html>
        <head>
            <title>Отчет о проверке архивов</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1 {{ color: #333; }}
                .stats {{ background-color: #f5f5f5; padding: 10px; border-radius: 5px; }}
                .error {{ color: #d9534f; }}
                .archive {{ margin: 10px 0; padding: 10px; border: 1px solid #ddd; }}
            </style>
        </head>
        <body>
            <h1>Отчет о проверке архивов</h1>
            <p><strong>Дата проверки:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p><strong>Директория:</strong> {self.dir_edit.text()}</p>
            <p><strong>Расширения:</strong> {', '.join(self.get_extensions())}</p>
            <p><strong>Рекурсивная проверка:</strong> {'Да' if self.recursive_check.isChecked() else 'Нет'}</p>
            
            <h2>Статистика</h2>
            <div class="stats">
        """
        
        for key, value in self.current_stats.items():
            html_content += f"<p><strong>{key}:</strong> {value}</p>\n"
        
        html_content += """
            </div>
            <h2>Поврежденные архивы</h2>
        """
        
        for archive_path, error in corrupted_archives.items():
            html_content += f"""
            <div class="archive">
                <p><strong>Файл:</strong> {archive_path}</p>
                <p class="error"><strong>Ошибка:</strong> {error}</p>
            </div>
            """
        
        html_content += """
        </body>
        </html>
        """
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
    
    def save_report_json(self, corrupted_archives, report_path):
        report_data = {
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'directory': self.dir_edit.text(),
            'extensions': self.get_extensions(),
            'recursive': self.recursive_check.isChecked(),
            'statistics': self.current_stats,
            'corrupted_archives': {
                path: error for path, error in corrupted_archives.items()
            }
        }
        
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)

    def save_report_csv(self, corrupted_archives, report_path):
        """
        Сохранение отчета в CSV формате
        """
        with open(report_path, 'w', encoding='utf-8') as f:
            # Заголовок
            f.write("Файл;Статус;Описание ошибки\n")
            
            # Проходим по всем файлам в директории
            for root, _, files in os.walk(self.dir_edit.text()):
                for file in files:
                    if any(file.lower().endswith(ext.lower()) for ext in self.get_extensions()):
                        full_path = os.path.join(root, file)
                        if full_path in corrupted_archives:
                            f.write(f"{full_path};Ошибка;{corrupted_archives[full_path]}\n")
                        else:
                            f.write(f"{full_path};OK;\n")

    def check_finished(self, corrupted_archives):
        self.progress_bar.hide()
        self.progress_label.hide()
        self.check_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        
        total_files = self.current_stats.get('total_files', 0)
        if self.worker.stop_flag:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setWindowTitle("Проверка остановлена")
            msg.setText(f"Проверка была остановлена.\nПроверено {self.current_stats.get('processed_files', 0)} из {total_files} файлов.")
            msg.exec()
        elif corrupted_archives:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("Результаты проверки")
            msg.setText(f"Найдено {len(corrupted_archives)} поврежденных архивов!")
            
            details = "Подробная информация:\n\n"
            for path, error in corrupted_archives.items():
                details += f"Файл: {path}\nОшибка: {error}\n{'='*50}\n"
            
            msg.setDetailedText(details)
            msg.exec()
            
            # Сохраняем отчет в выбранном формате
            format_ext = self.report_format.currentText().lower()
            report_path = os.path.join(
                self.dir_edit.text(),
                f"corrupted_archives_report.{format_ext}"
            )
            
            save_methods = {
                'txt': self.save_report_txt,
                'html': self.save_report_html,
                'json': self.save_report_json,
                'csv': self.save_report_csv
            }
            
            save_methods[format_ext](corrupted_archives, report_path)
            self.update_log(f"\nОтчет сохранен в файл: {report_path}")
        else:
            QMessageBox.information(
                self,
                "Результаты проверки",
                "Все архивы корректны!"
            )

class ArchiveChecker:
    """
    Базовый класс для проверки архивов
    """
    def __init__(self, directory):
        self.directory = Path(directory)
        self.corrupted_archives = {}

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
        """
        Проверка ZIP архива
        """
        try:
            with zipfile.ZipFile(file_path, 'r') as zip_file:
                # Проверяем, не является ли архив многотомным
                if zip_file.comment and b'span multiple disks' in zip_file.comment:
                    # Ищем все части архива
                    parts = self.find_multipart_files(file_path)
                    if parts:
                        # Проверяем последовательность частей
                        is_sequence_valid, error_msg = self.check_multipart_sequence(parts)
                        if not is_sequence_valid:
                            return False, f"Многотомный ZIP архив: {error_msg}"
                        return False, "Многотомный ZIP архив. Все части найдены, но формат не поддерживается. Используйте RAR или 7z."
                    return False, "Многотомный ZIP архив: не найдены все части архива"
                
                # Проверяем каждый файл в архиве
                for file_info in zip_file.infolist():
                    if file_info.filename.endswith('/'):  # пропускаем директории
                        continue
                    try:
                        # Проверяем CRC файла
                        with zip_file.open(file_info.filename) as f:
                            while f.read(8192):  # читаем файл блоками по 8KB
                                pass
                    except (zipfile.BadZipFile, zlib.error) as e:
                        return False, f"Ошибка при проверке файла {file_info.filename}: {str(e)}"
                return True, ""
        except zipfile.BadZipFile as e:
            if 'span multiple disks' in str(e):
                # Ищем все части архива
                parts = self.find_multipart_files(file_path)
                if parts:
                    # Проверяем последовательность частей
                    is_sequence_valid, error_msg = self.check_multipart_sequence(parts)
                    if not is_sequence_valid:
                        return False, f"Многотомный ZIP архив: {error_msg}"
                    return False, "Многотомный ZIP архив. Все части найдены, но формат не поддерживается. Используйте RAR или 7z."
                return False, "Многотомный ZIP архив: не найдены все части архива"
            return False, f"Поврежденный ZIP архив: {str(e)}"
        except Exception as e:
            return False, str(e)

    def check_rar(self, file_path):
        """
        Проверка RAR архива
        """
        try:
            # Проверяем, является ли файл частью многотомного архива
            if any(pattern in file_path.name.lower() for pattern in ['.part', '.r00', '.001']):
                parts = self.find_multipart_files(file_path)
                is_sequence_valid, error_msg = self.check_multipart_sequence(parts)
                if not is_sequence_valid:
                    return False, f"Многотомный RAR архив: {error_msg}"
                
                # Используем первую часть для проверки
                file_path = parts[0]
            
            # Проверяем архив с помощью unrar
            result = subprocess.run(
                ['unrar', 't', str(file_path)],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                error_msg = result.stderr or result.stdout
                return False, f"Ошибка при проверке RAR архива: {error_msg}"
            
            return True, ""
        except Exception as e:
            return False, str(e)

    def check_7z(self, file_path):
        """
        Проверка 7Z архива
        """
        try:
            # Проверяем, является ли файл частью многотомного архива
            if '.001' in file_path.name.lower():
                parts = self.find_multipart_files(file_path)
                is_sequence_valid, error_msg = self.check_multipart_sequence(parts)
                if not is_sequence_valid:
                    return False, f"Многотомный 7Z архив: {error_msg}"
                
                # Используем первую часть для проверки
                file_path = parts[0]
            
            # Проверяем архив с помощью 7z
            result = subprocess.run(
                ['7z', 't', str(file_path)],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                error_msg = result.stderr or result.stdout
                return False, f"Ошибка при проверке 7Z архива: {error_msg}"
            
            return True, ""
        except Exception as e:
            return False, str(e)

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