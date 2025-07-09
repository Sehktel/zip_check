from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QSpinBox, QCheckBox,
    QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox
)
from PyQt6.QtCore import Qt
from settings_manager import SettingsManager

class SettingsDialog(QDialog):
    """
    Диалог настроек приложения
    """
    def __init__(self, settings_manager: SettingsManager, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.setWindowTitle("Настройки")
        self.setMinimumWidth(600)
        self.setup_ui()
        
    def setup_ui(self):
        """Настройка интерфейса"""
        layout = QVBoxLayout(self)
        
        # Группа настроек директории
        dir_group = QGroupBox("Директория по умолчанию")
        dir_layout = QHBoxLayout()
        self.dir_edit = QLineEdit(self.settings_manager.get_default_directory())
        self.dir_btn = QPushButton("Обзор...")
        self.dir_btn.clicked.connect(self.select_directory)
        dir_layout.addWidget(self.dir_edit)
        dir_layout.addWidget(self.dir_btn)
        dir_group.setLayout(dir_layout)
        layout.addWidget(dir_group)
        
        # Группа общих настроек
        general_group = QGroupBox("Общие настройки")
        general_layout = QVBoxLayout()
        
        # Настройка количества потоков
        threads_layout = QHBoxLayout()
        threads_label = QLabel("Максимальное количество потоков:")
        self.threads_spin = QSpinBox()
        self.threads_spin.setMinimum(1)
        self.threads_spin.setMaximum(32)
        self.threads_spin.setValue(self.settings_manager.get_max_threads())
        threads_layout.addWidget(threads_label)
        threads_layout.addWidget(self.threads_spin)
        threads_layout.addStretch()
        general_layout.addLayout(threads_layout)
        
        # Настройка рекурсивного сканирования
        self.recursive_check = QCheckBox("Рекурсивное сканирование подпапок")
        self.recursive_check.setChecked(self.settings_manager.get_recursive_scan())
        general_layout.addWidget(self.recursive_check)
        
        general_group.setLayout(general_layout)
        layout.addWidget(general_group)
        
        # Группа настроек архивов
        archives_group = QGroupBox("Настройки типов архивов")
        archives_layout = QVBoxLayout()
        
        # Таблица типов архивов
        self.archives_table = QTableWidget()
        self.archives_table.setColumnCount(4)
        self.archives_table.setHorizontalHeaderLabels(["Тип", "Включен", "Метод проверки", "Расширения"])
        self.archives_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.archives_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        
        # Заполняем таблицу
        archive_types = self.settings_manager.get_archive_types()
        self.archives_table.setRowCount(len(archive_types))
        for i, (archive_type, settings) in enumerate(archive_types.items()):
            # Тип архива
            type_item = QTableWidgetItem(settings["description"])
            type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.archives_table.setItem(i, 0, type_item)
            
            # Включен/выключен
            enabled_check = QTableWidgetItem()
            enabled_check.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            enabled_check.setCheckState(Qt.CheckState.Checked if settings["enabled"] else Qt.CheckState.Unchecked)
            self.archives_table.setItem(i, 1, enabled_check)
            
            # Метод проверки
            method_item = QTableWidgetItem(settings["check_method"])
            method_item.setFlags(method_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.archives_table.setItem(i, 2, method_item)
            
            # Расширения
            extensions_item = QTableWidgetItem(", ".join(settings["extensions"]))
            self.archives_table.setItem(i, 3, extensions_item)
        
        archives_layout.addWidget(self.archives_table)
        archives_group.setLayout(archives_layout)
        layout.addWidget(archives_group)
        
        # Кнопки
        buttons_layout = QHBoxLayout()
        save_btn = QPushButton("Сохранить")
        save_btn.clicked.connect(self.save_settings)
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addStretch()
        buttons_layout.addWidget(save_btn)
        buttons_layout.addWidget(cancel_btn)
        layout.addLayout(buttons_layout)
        
    def select_directory(self):
        """Выбор директории по умолчанию"""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Выберите директорию по умолчанию",
            self.dir_edit.text()
        )
        if directory:
            self.dir_edit.setText(directory)
            
    def save_settings(self):
        """Сохранение настроек"""
        # Сохраняем директорию
        self.settings_manager.settings["default_directory"] = self.dir_edit.text()
        
        # Сохраняем общие настройки
        self.settings_manager.settings["max_threads"] = self.threads_spin.value()
        self.settings_manager.settings["recursive_scan"] = self.recursive_check.isChecked()
        
        # Сохраняем настройки архивов
        archive_types = self.settings_manager.settings["archive_types"]
        for i, (archive_type, settings) in enumerate(archive_types.items()):
            settings["enabled"] = self.archives_table.item(i, 1).checkState() == Qt.CheckState.Checked
            settings["extensions"] = [ext.strip() for ext in self.archives_table.item(i, 3).text().split(",")]
        
        # Сохраняем в файл
        if self.settings_manager.save_settings():
            self.accept()
        else:
            QMessageBox.warning(self, "Ошибка", "Не удалось сохранить настройки") 