"""
UI панели для управления стилями линий
"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
                               QGroupBox, QPushButton, QDoubleSpinBox, QListWidget,
                               QListWidgetItem, QMessageBox, QDialog, QFormLayout,
                               QDialogButtonBox, QLineEdit, QCheckBox)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPainter, QPen, QColor, QPixmap

from widgets.line_style import LineStyleManager, LineType


class StylePreviewWidget(QWidget):
    """Виджет для отображения превью стиля линии"""
    def __init__(self, style=None, width=100, height=20, parent=None):
        super().__init__(parent)
        self.style = style
        self.preview_width = width
        self.preview_height = height
        self.setFixedSize(width, height)
    
    def set_style(self, style):
        self.style = style
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        if self.style:
            pen = self.style.get_pen()
            painter.setPen(pen)
            
            # Рисуем линию
            y = self.height() // 2
            margin = 5
            painter.drawLine(margin, y, self.width() - margin, y)
        else:
            # Рисуем пустую линию
            painter.setPen(QPen(QColor(200, 200, 200), 1))
            y = self.height() // 2
            margin = 5
            painter.drawLine(margin, y, self.width() - margin, y)


class StyleComboBox(QComboBox):
    """ComboBox с превью стилей"""
    def __init__(self, style_manager, parent=None):
        super().__init__(parent)
        self.style_manager = style_manager
        self.setup_combobox()
        
        # Подключаем сигналы менеджера стилей
        if style_manager:
            style_manager.style_added.connect(self.refresh_styles)
            style_manager.style_removed.connect(self.refresh_styles)
            style_manager.style_changed.connect(self.refresh_styles)
    
    def setup_combobox(self):
        """Настраивает ComboBox с превью"""
        self.clear()
        if not self.style_manager:
            return
        
        for style in self.style_manager.get_all_styles():
            self.addItem(style.name, style.name)
            # Создаем превью для каждого стиля
            preview = StylePreviewWidget(style, 80, 16)
            pixmap = QPixmap(80, 16)
            pixmap.fill(Qt.white)
            preview.render(pixmap)
            self.setItemIcon(self.count() - 1, self._create_icon_from_style(style))
    
    def _create_icon_from_style(self, style):
        """Создает иконку из стиля"""
        pixmap = QPixmap(80, 16)
        pixmap.fill(Qt.white)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        if style:
            pen = style.get_pen()
            painter.setPen(pen)
            painter.drawLine(5, 8, 75, 8)
        
        painter.end()
        return pixmap
    
    def refresh_styles(self):
        """Обновляет список стилей"""
        current_text = self.currentText()
        self.setup_combobox()
        # Восстанавливаем выбор
        index = self.findText(current_text)
        if index >= 0:
            self.setCurrentIndex(index)
    
    def get_current_style(self):
        """Возвращает текущий выбранный стиль"""
        style_name = self.currentData()
        if style_name and self.style_manager:
            return self.style_manager.get_style(style_name)
        return None


class ObjectPropertiesPanel(QGroupBox):
    """Панель свойств объекта"""
    style_changed = Signal(object)  # Сигнал при изменении стиля
    
    def __init__(self, style_manager, parent=None):
        super().__init__("Свойства объекта", parent)
        self.style_manager = style_manager
        self.selected_objects = []
        self.canvas = None  # Будет установлен извне
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Выбор стиля
        style_label = QLabel("Стиль линии:")
        layout.addWidget(style_label)
        
        self.style_combo = StyleComboBox(self.style_manager)
        self.style_combo.currentIndexChanged.connect(self.on_style_changed)
        layout.addWidget(self.style_combo)
        
        # Информация о текущем стиле
        self.style_info_label = QLabel("")
        self.style_info_label.setWordWrap(True)
        layout.addWidget(self.style_info_label)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def set_selected_objects(self, objects):
        """Устанавливает выделенные объекты"""
        self.selected_objects = objects
        self.update_display()
    
    def update_display(self):
        """Обновляет отображение панели"""
        if not self.selected_objects:
            self.style_combo.setCurrentIndex(-1)
            self.style_info_label.setText("Нет выделенных объектов")
            return
        
        # Проверяем, все ли объекты имеют один стиль
        styles = set()
        for obj in self.selected_objects:
            if hasattr(obj, 'style') and obj.style:
                styles.add(obj.style.name)
            elif hasattr(obj, 'style_name') and obj.style_name:
                styles.add(obj.style_name)
        
        if len(styles) == 1:
            # Все объекты имеют один стиль
            style_name = list(styles)[0]
            index = self.style_combo.findText(style_name)
            if index >= 0:
                self.style_combo.setCurrentIndex(index)
            self.style_info_label.setText(f"Стиль: {style_name}")
        elif len(styles) > 1:
            # Разные стили
            self.style_combo.setCurrentIndex(-1)
            self.style_info_label.setText("Разные стили")
        else:
            # Нет стилей
            self.style_combo.setCurrentIndex(-1)
            self.style_info_label.setText("Стиль не назначен")
    
    def on_style_changed(self):
        """Обработчик изменения стиля"""
        style = self.style_combo.get_current_style()
        if not style:
            return
        
        # Применяем стиль только к выделенным объектам
        if style and self.selected_objects:
            # Применяем стиль ко всем выделенным объектам
            for obj in self.selected_objects:
                if hasattr(obj, 'style'):
                    obj.style = style
            # Обновляем отображение панели
            self.update_display()
            # Отправляем сигнал об изменении стиля
            self.style_changed.emit(style)
            # Обновляем canvas
            if self.canvas:
                self.canvas.update()


class StyleManagementPanel(QGroupBox):
    """Панель управления стилями"""
    def __init__(self, style_manager, parent=None):
        super().__init__("Управление стилями", parent)
        self.style_manager = style_manager
        self.init_ui()
        
        # Подключаем сигналы
        if style_manager:
            style_manager.style_added.connect(self.refresh_list)
            style_manager.style_removed.connect(self.refresh_list)
            style_manager.style_changed.connect(self.refresh_list)
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Список стилей
        self.style_list = QListWidget()
        self.style_list.itemClicked.connect(self.on_style_selected)
        layout.addWidget(self.style_list)
        
        # Кнопки управления
        buttons_layout = QHBoxLayout()
        
        self.edit_btn = QPushButton("Редактировать")
        self.edit_btn.clicked.connect(self.edit_selected_style)
        buttons_layout.addWidget(self.edit_btn)
        
        self.add_btn = QPushButton("Создать")
        self.add_btn.clicked.connect(self.create_style)
        buttons_layout.addWidget(self.add_btn)
        
        self.delete_btn = QPushButton("Удалить")
        self.delete_btn.clicked.connect(self.delete_selected_style)
        buttons_layout.addWidget(self.delete_btn)
        
        layout.addLayout(buttons_layout)
        
        self.setLayout(layout)
        self.refresh_list()
    
    def refresh_list(self):
        """Обновляет список стилей"""
        self.style_list.clear()
        if not self.style_manager:
            return
        
        for style in self.style_manager.get_all_styles():
            item = QListWidgetItem(style.name)
            item.setData(Qt.UserRole, style.name)
            
            # Создаем превью
            preview = StylePreviewWidget(style, 100, 20)
            pixmap = QPixmap(100, 20)
            pixmap.fill(Qt.white)
            preview.render(pixmap)
            item.setIcon(self._create_icon_from_style(style))
            
            # Отмечаем базовые стили ГОСТ
            if style.is_gost_base:
                item.setForeground(QColor(100, 100, 100))
            
            self.style_list.addItem(item)
    
    def _create_icon_from_style(self, style):
        """Создает иконку из стиля"""
        pixmap = QPixmap(100, 20)
        pixmap.fill(Qt.white)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        if style:
            pen = style.get_pen()
            painter.setPen(pen)
            painter.drawLine(5, 10, 95, 10)
        
        painter.end()
        return pixmap
    
    def on_style_selected(self, item):
        """Обработчик выбора стиля"""
        self.edit_btn.setEnabled(True)
        style_name = item.data(Qt.UserRole)
        style = self.style_manager.get_style(style_name)
        if style and style.is_gost_base:
            self.delete_btn.setEnabled(False)
        else:
            self.delete_btn.setEnabled(True)
    
    def edit_selected_style(self):
        """Редактирует выбранный стиль"""
        item = self.style_list.currentItem()
        if not item:
            return
        
        style_name = item.data(Qt.UserRole)
        style = self.style_manager.get_style(style_name)
        if not style:
            return
        
        dialog = StyleEditDialog(style, self.style_manager, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh_list()
    
    def create_style(self):
        """Создает новый стиль"""
        dialog = StyleEditDialog(None, self.style_manager, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh_list()
    
    def delete_selected_style(self):
        """Удаляет выбранный стиль"""
        item = self.style_list.currentItem()
        if not item:
            return
        
        style_name = item.data(Qt.UserRole)
        style = self.style_manager.get_style(style_name)
        
        if not style:
            return
        
        if style.is_gost_base:
            QMessageBox.warning(self, "Ошибка", "Нельзя удалять базовые стили ГОСТ")
            return
        
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Удалить стиль '{style_name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                self.style_manager.remove_style(style_name)
            except ValueError as e:
                QMessageBox.warning(self, "Ошибка", str(e))


class StyleEditDialog(QDialog):
    """Диалог редактирования стиля"""
    def __init__(self, style=None, style_manager=None, parent=None):
        super().__init__(parent)
        self.style = style
        self.style_manager = style_manager
        self.is_new = style is None
        self.init_ui()
    
    def init_ui(self):
        self.setWindowTitle("Редактировать стиль" if not self.is_new else "Создать стиль")
        layout = QFormLayout()
        
        # Имя стиля
        self.name_edit = QLineEdit()
        if self.style:
            self.name_edit.setText(self.style.name)
            if self.style.is_gost_base:
                self.name_edit.setEnabled(False)
        layout.addRow("Название:", self.name_edit)
        
        # Тип линии
        self.type_combo = QComboBox()
        for line_type in LineType:
            self.type_combo.addItem(line_type.name, line_type)
        if self.style:
            index = self.type_combo.findData(self.style.line_type)
            if index >= 0:
                self.type_combo.setCurrentIndex(index)
            if self.style.is_gost_base:
                self.type_combo.setEnabled(False)
        layout.addRow("Тип линии:", self.type_combo)
        
        # Толщина
        self.thickness_spin = QDoubleSpinBox()
        self.thickness_spin.setRange(0.25, 1.4)
        self.thickness_spin.setDecimals(2)
        self.thickness_spin.setSingleStep(0.1)
        self.thickness_spin.setSuffix(" мм")
        if self.style:
            self.thickness_spin.setValue(self.style.thickness_mm)
        else:
            self.thickness_spin.setValue(0.8)
        layout.addRow("Толщина:", self.thickness_spin)
        
        # Длина штриха
        self.dash_length_spin = QDoubleSpinBox()
        self.dash_length_spin.setRange(0.1, 50.0)
        self.dash_length_spin.setDecimals(2)
        self.dash_length_spin.setSingleStep(0.5)
        self.dash_length_spin.setSuffix(" мм")
        if self.style:
            self.dash_length_spin.setValue(self.style.dash_length)
        else:
            self.dash_length_spin.setValue(5.0)
        layout.addRow("Длина штриха:", self.dash_length_spin)
        
        # Расстояние между штрихами
        self.dash_gap_spin = QDoubleSpinBox()
        self.dash_gap_spin.setRange(0.1, 50.0)
        self.dash_gap_spin.setDecimals(2)
        self.dash_gap_spin.setSingleStep(0.5)
        self.dash_gap_spin.setSuffix(" мм")
        if self.style:
            self.dash_gap_spin.setValue(self.style.dash_gap)
        else:
            self.dash_gap_spin.setValue(2.5)
        layout.addRow("Расстояние между штрихами:", self.dash_gap_spin)
        
        # Превью
        self.preview_widget = StylePreviewWidget(None, 200, 30)
        layout.addRow("Превью:", self.preview_widget)
        
        # Кнопки
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        
        self.setLayout(layout)
        
        # Обновляем превью при изменении параметров
        self.type_combo.currentIndexChanged.connect(self.update_preview)
        self.thickness_spin.valueChanged.connect(self.update_preview)
        self.dash_length_spin.valueChanged.connect(self.update_preview)
        self.dash_gap_spin.valueChanged.connect(self.update_preview)
        
        self.update_preview()
    
    def update_preview(self):
        """Обновляет превью стиля"""
        from widgets.line_style import LineStyle
        
        # Создаем временный стиль для превью
        temp_style = LineStyle(
            name="preview",
            line_type=self.type_combo.currentData(),
            thickness_mm=self.thickness_spin.value(),
            dash_length=self.dash_length_spin.value(),
            dash_gap=self.dash_gap_spin.value()
        )
        self.preview_widget.set_style(temp_style)
    
    def accept(self):
        """Применяет изменения"""
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Ошибка", "Введите название стиля")
            return
        
        try:
            if self.is_new:
                # Создаем новый стиль
                from widgets.line_style import LineStyle
                new_style = LineStyle(
                    name=name,
                    line_type=self.type_combo.currentData(),
                    thickness_mm=self.thickness_spin.value(),
                    dash_length=self.dash_length_spin.value(),
                    dash_gap=self.dash_gap_spin.value(),
                    is_gost_base=False
                )
                self.style_manager.add_style(new_style)
            else:
                # Обновляем существующий стиль
                if not self.style.is_gost_base:
                    if name != self.style.name:
                        self.style_manager.rename_style(self.style.name, name)
                
                self.style.line_type = self.type_combo.currentData()
                self.style.thickness_mm = self.thickness_spin.value()
                self.style.dash_length = self.dash_length_spin.value()
                self.style.dash_gap = self.dash_gap_spin.value()
            
            super().accept()
        except ValueError as e:
            QMessageBox.warning(self, "Ошибка", str(e))

