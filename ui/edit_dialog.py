"""
Окно редактирования выделенных объектов
"""
import sys
import os
import math

# Добавляем корневую директорию проекта в sys.path, если её там нет
# Это нужно для корректного импорта модулей widgets
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_current_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                               QDoubleSpinBox, QComboBox, QPushButton, QGroupBox,
                               QGridLayout, QWidget)
from PySide6.QtCore import QPointF, Qt, Signal
from widgets.line_segment import LineSegment


class EditDialog(QDialog):
    """Диалоговое окно для редактирования выделенных объектов"""
    
    object_changed = Signal(object)  # Сигнал при изменении объекта
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Редактирование объекта")
        self.setModal(False)  # Немодальное окно, чтобы можно было работать с канвасом
        
        self.editing_object = None
        self.canvas = None
        self.editing_mode = False  # Режим редактирования (перемещение точек)
        self.dragging_point = None  # Какая точка перемещается: 'start' или 'end'
        
        self.init_ui()
    
    def init_ui(self):
        """Инициализация интерфейса"""
        layout = QVBoxLayout()
        
        # Заголовок
        self.title_label = QLabel("Выберите объект для редактирования")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        layout.addWidget(self.title_label)
        
        # Контейнер для содержимого редактирования
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout()
        self.content_widget.setLayout(self.content_layout)
        layout.addWidget(self.content_widget)
        
        # Кнопки
        button_layout = QHBoxLayout()
        self.close_btn = QPushButton("Закрыть")
        self.close_btn.clicked.connect(self.close)
        button_layout.addWidget(self.close_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        self.resize(400, 300)
    
    def set_canvas(self, canvas):
        """Устанавливает канвас для редактирования"""
        self.canvas = canvas
    
    def set_object(self, obj):
        """Устанавливает объект для редактирования"""
        self.editing_object = obj
        
        # Очищаем предыдущее содержимое
        self.clear_content()
        
        if obj is None:
            self.title_label.setText("Выберите объект для редактирования")
            return
        
        if isinstance(obj, LineSegment):
            self.setup_line_editing(obj)
        else:
            # Проверяем тип объекта
            from widgets.primitives import Circle, Rectangle
            if isinstance(obj, Circle):
                self.setup_circle_editing(obj)
            elif isinstance(obj, Rectangle):
                self.setup_rectangle_editing(obj)
            else:
                self.title_label.setText(f"Редактирование: {type(obj).__name__}")
                # Для других типов объектов можно добавить позже
    
    def clear_content(self):
        """Очищает содержимое окна редактирования"""
        while self.content_layout.count():
            child = self.content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
    
    def setup_line_editing(self, line: LineSegment):
        """Настраивает интерфейс редактирования отрезка"""
        self.title_label.setText("Редактирование отрезка")
        
        # Группа способа задания
        method_group = QGroupBox("Способ задания")
        method_layout = QVBoxLayout()
        
        self.line_method_combo = QComboBox()
        self.line_method_combo.addItems([
            "В декартовых координатах (x₁, y₁) и (x₂, y₂)",
            "В полярных координатах (x₁, y₁) и (r₂, θ₂)"
        ])
        self.line_method_combo.currentTextChanged.connect(self.on_line_method_changed)
        method_layout.addWidget(self.line_method_combo)
        
        # Единицы углов (для полярных координат)
        angle_layout = QHBoxLayout()
        angle_layout.addWidget(QLabel("Единицы углов:"))
        self.line_angle_combo = QComboBox()
        self.line_angle_combo.addItems(["Градусы", "Радианы"])
        self.line_angle_combo.currentTextChanged.connect(self.on_line_angle_units_changed)
        angle_layout.addWidget(self.line_angle_combo)
        method_layout.addLayout(angle_layout)
        
        method_group.setLayout(method_layout)
        self.content_layout.addWidget(method_group)
        
        # Начальная точка (всегда в декартовых координатах)
        start_group = QGroupBox("Начальная точка (x₁, y₁)")
        start_layout = QGridLayout()
        
        start_layout.addWidget(QLabel("x₁:"), 0, 0)
        self.start_x_spin = QDoubleSpinBox()
        self.start_x_spin.setRange(-10000, 10000)
        self.start_x_spin.setDecimals(2)
        self.start_x_spin.setSingleStep(10)
        self.start_x_spin.valueChanged.connect(self.on_start_point_changed)
        start_layout.addWidget(self.start_x_spin, 0, 1)
        
        start_layout.addWidget(QLabel("y₁:"), 0, 2)
        self.start_y_spin = QDoubleSpinBox()
        self.start_y_spin.setRange(-10000, 10000)
        self.start_y_spin.setDecimals(2)
        self.start_y_spin.setSingleStep(10)
        self.start_y_spin.valueChanged.connect(self.on_start_point_changed)
        start_layout.addWidget(self.start_y_spin, 0, 3)
        
        start_group.setLayout(start_layout)
        self.content_layout.addWidget(start_group)
        
        # Конечная точка - декартовы координаты
        self.cartesian_group = QGroupBox("Конечная точка (x₂, y₂)")
        cartesian_layout = QGridLayout()
        
        cartesian_layout.addWidget(QLabel("x₂:"), 0, 0)
        self.end_x_spin = QDoubleSpinBox()
        self.end_x_spin.setRange(-10000, 10000)
        self.end_x_spin.setDecimals(2)
        self.end_x_spin.setSingleStep(10)
        self.end_x_spin.valueChanged.connect(self.on_cartesian_end_changed)
        cartesian_layout.addWidget(self.end_x_spin, 0, 1)
        
        cartesian_layout.addWidget(QLabel("y₂:"), 0, 2)
        self.end_y_spin = QDoubleSpinBox()
        self.end_y_spin.setRange(-10000, 10000)
        self.end_y_spin.setDecimals(2)
        self.end_y_spin.setSingleStep(10)
        self.end_y_spin.valueChanged.connect(self.on_cartesian_end_changed)
        cartesian_layout.addWidget(self.end_y_spin, 0, 3)
        
        self.cartesian_group.setLayout(cartesian_layout)
        self.content_layout.addWidget(self.cartesian_group)
        
        # Конечная точка - полярные координаты
        self.polar_group = QGroupBox("Конечная точка (r₂, θ₂)")
        polar_layout = QGridLayout()
        
        polar_layout.addWidget(QLabel("r₂:"), 0, 0)
        self.radius_spin = QDoubleSpinBox()
        self.radius_spin.setRange(0, 10000)
        self.radius_spin.setDecimals(2)
        self.radius_spin.setSingleStep(10)
        self.radius_spin.valueChanged.connect(self.on_polar_end_changed)
        polar_layout.addWidget(self.radius_spin, 0, 1)
        
        polar_layout.addWidget(QLabel("θ₂:"), 0, 2)
        self.angle_spin = QDoubleSpinBox()
        self.angle_spin.setRange(-360, 360)
        self.angle_spin.setDecimals(2)
        self.angle_spin.setSingleStep(15)
        self.angle_spin.valueChanged.connect(self.on_polar_end_changed)
        polar_layout.addWidget(self.angle_spin, 0, 3)
        
        self.angle_label = QLabel("°")
        polar_layout.addWidget(self.angle_label, 0, 4)
        
        self.polar_group.setLayout(polar_layout)
        self.polar_group.hide()
        self.content_layout.addWidget(self.polar_group)
        
        # Режим редактирования
        edit_mode_group = QGroupBox("Режим редактирования")
        edit_mode_layout = QVBoxLayout()
        
        self.edit_mode_label = QLabel("Перемещение точек: Отключено")
        self.edit_mode_label.setStyleSheet("color: gray;")
        edit_mode_layout.addWidget(self.edit_mode_label)
        
        info_label = QLabel("Включите режим редактирования для перемещения точек\nв рабочей области мышью")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; font-size: 9pt;")
        edit_mode_layout.addWidget(info_label)
        
        self.toggle_edit_mode_btn = QPushButton("Включить редактирование")
        self.toggle_edit_mode_btn.clicked.connect(self.toggle_edit_mode)
        edit_mode_layout.addWidget(self.toggle_edit_mode_btn)
        
        edit_mode_group.setLayout(edit_mode_layout)
        self.content_layout.addWidget(edit_mode_group)
        
        # Загружаем данные отрезка
        self.load_line_data(line)
    
    def load_line_data(self, line: LineSegment):
        """Загружает данные отрезка в поля редактирования"""
        # Блокируем сигналы, чтобы не вызывать обработчики при загрузке
        self.start_x_spin.blockSignals(True)
        self.start_y_spin.blockSignals(True)
        self.end_x_spin.blockSignals(True)
        self.end_y_spin.blockSignals(True)
        self.radius_spin.blockSignals(True)
        self.angle_spin.blockSignals(True)
        
        # Начальная точка
        self.start_x_spin.setValue(line.start_point.x())
        self.start_y_spin.setValue(line.start_point.y())
        
        # Конечная точка в декартовых координатах
        self.end_x_spin.setValue(line.end_point.x())
        self.end_y_spin.setValue(line.end_point.y())
        
        # Вычисляем полярные координаты относительно начальной точки
        dx = line.end_point.x() - line.start_point.x()
        dy = line.end_point.y() - line.start_point.y()
        radius = math.sqrt(dx*dx + dy*dy)
        angle_rad = math.atan2(dy, dx)
        angle_deg = math.degrees(angle_rad)
        
        self.radius_spin.setValue(radius)
        self.angle_spin.setValue(angle_deg)
        
        # Устанавливаем способ задания по умолчанию (декартовы координаты)
        self.line_method_combo.setCurrentIndex(0)
        self.line_angle_combo.setCurrentIndex(0)  # Градусы
        
        # Разблокируем сигналы
        self.start_x_spin.blockSignals(False)
        self.start_y_spin.blockSignals(False)
        self.end_x_spin.blockSignals(False)
        self.end_y_spin.blockSignals(False)
        self.radius_spin.blockSignals(False)
        self.angle_spin.blockSignals(False)
    
    def on_line_method_changed(self, method_text):
        """Обработчик изменения способа задания"""
        if "декартовых" in method_text.lower():
            self.cartesian_group.show()
            self.polar_group.hide()
        else:
            self.cartesian_group.hide()
            self.polar_group.show()
            # Обновляем полярные координаты на основе текущих декартовых
            self.update_polar_from_cartesian()
    
    def on_line_angle_units_changed(self, units_text):
        """Обработчик изменения единиц углов"""
        is_degrees = units_text == "Градусы"
        self.angle_label.setText("°" if is_degrees else "rad")
        
        # Конвертируем угол
        if self.polar_group.isVisible():
            current_angle = self.angle_spin.value()
            self.angle_spin.blockSignals(True)
            if is_degrees:
                # Были радианы, стали градусы
                self.angle_spin.setRange(-360, 360)
                self.angle_spin.setValue(math.degrees(current_angle))
            else:
                # Были градусы, стали радианы
                self.angle_spin.setRange(-2 * math.pi, 2 * math.pi)
                self.angle_spin.setValue(math.radians(current_angle))
            self.angle_spin.blockSignals(False)
    
    def update_polar_from_cartesian(self):
        """Обновляет полярные координаты на основе декартовых"""
        start_x = self.start_x_spin.value()
        start_y = self.start_y_spin.value()
        end_x = self.end_x_spin.value()
        end_y = self.end_y_spin.value()
        
        dx = end_x - start_x
        dy = end_y - start_y
        radius = math.sqrt(dx*dx + dy*dy)
        angle_rad = math.atan2(dy, dx)
        
        is_degrees = self.line_angle_combo.currentText() == "Градусы"
        angle = math.degrees(angle_rad) if is_degrees else angle_rad
        
        self.radius_spin.blockSignals(True)
        self.angle_spin.blockSignals(True)
        self.radius_spin.setValue(radius)
        self.angle_spin.setValue(angle)
        self.radius_spin.blockSignals(False)
        self.angle_spin.blockSignals(False)
    
    def update_cartesian_from_polar(self):
        """Обновляет декартовы координаты на основе полярных"""
        start_x = self.start_x_spin.value()
        start_y = self.start_y_spin.value()
        radius = self.radius_spin.value()
        angle = self.angle_spin.value()
        
        is_degrees = self.line_angle_combo.currentText() == "Градусы"
        angle_rad = math.radians(angle) if is_degrees else angle
        
        end_x = start_x + radius * math.cos(angle_rad)
        end_y = start_y + radius * math.sin(angle_rad)
        
        self.end_x_spin.blockSignals(True)
        self.end_y_spin.blockSignals(True)
        self.end_x_spin.setValue(end_x)
        self.end_y_spin.setValue(end_y)
        self.end_x_spin.blockSignals(False)
        self.end_y_spin.blockSignals(False)
    
    def on_start_point_changed(self):
        """Обработчик изменения начальной точки"""
        if not self.editing_object:
            return
        
        start_x = self.start_x_spin.value()
        start_y = self.start_y_spin.value()
        
        # Обновляем объект
        if isinstance(self.editing_object, LineSegment):
            # Вычисляем смещение конечной точки относительно начальной
            old_start = self.editing_object.start_point
            dx = self.editing_object.end_point.x() - old_start.x()
            dy = self.editing_object.end_point.y() - old_start.y()
            
            # Новая конечная точка = новая начальная + смещение
            new_end = QPointF(start_x + dx, start_y + dy)
            
            self.editing_object.start_point = QPointF(start_x, start_y)
            self.editing_object.end_point = new_end
            
            # Обновляем поля конечной точки
            self.end_x_spin.blockSignals(True)
            self.end_y_spin.blockSignals(True)
            self.end_x_spin.setValue(new_end.x())
            self.end_y_spin.setValue(new_end.y())
            self.end_x_spin.blockSignals(False)
            self.end_y_spin.blockSignals(False)
            
            # Обновляем полярные координаты, если они видны
            if self.polar_group.isVisible():
                self.update_polar_from_cartesian()
            
            self.apply_changes()
    
    def on_cartesian_end_changed(self):
        """Обработчик изменения конечной точки в декартовых координатах"""
        if not self.editing_object:
            return
        
        end_x = self.end_x_spin.value()
        end_y = self.end_y_spin.value()
        
        if isinstance(self.editing_object, LineSegment):
            self.editing_object.end_point = QPointF(end_x, end_y)
            
            # Обновляем полярные координаты, если они видны
            if self.polar_group.isVisible():
                self.update_polar_from_cartesian()
            
            self.apply_changes()
    
    def on_polar_end_changed(self):
        """Обработчик изменения конечной точки в полярных координатах"""
        if not self.editing_object:
            return
        
        # Обновляем декартовы координаты на основе полярных
        self.update_cartesian_from_polar()
        
        if isinstance(self.editing_object, LineSegment):
            end_x = self.end_x_spin.value()
            end_y = self.end_y_spin.value()
            self.editing_object.end_point = QPointF(end_x, end_y)
            self.apply_changes()
    
    def toggle_edit_mode(self):
        """Переключает режим редактирования (перемещение точек)"""
        self.editing_mode = not self.editing_mode
        
        # Определяем тип объекта для правильного текста
        from widgets.primitives import Circle, Rectangle
        if isinstance(self.editing_object, LineSegment):
            mode_text = "Перемещение точек"
        elif isinstance(self.editing_object, Circle):
            mode_text = "Перемещение точек"
        elif isinstance(self.editing_object, Rectangle):
            mode_text = "Перемещение углов"
        else:
            mode_text = "Редактирование"
        
        if self.editing_mode:
            self.toggle_edit_mode_btn.setText("Отключить редактирование")
            self.edit_mode_label.setText(f"{mode_text}: Включено")
            self.edit_mode_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.toggle_edit_mode_btn.setText("Включить редактирование")
            self.edit_mode_label.setText(f"{mode_text}: Отключено")
            self.edit_mode_label.setStyleSheet("color: gray;")
            self.dragging_point = None
        
        # Уведомляем канвас о режиме редактирования
        if self.canvas:
            self.canvas.set_editing_mode(self.editing_mode, self)
    
    def is_editing_mode(self):
        """Возвращает True, если режим редактирования включен"""
        return self.editing_mode
    
    def get_dragging_point(self):
        """Возвращает, какую точку перемещают"""
        return self.dragging_point
    
    def set_dragging_point(self, point_type):
        """Устанавливает, какую точку перемещают ('start' или 'end')"""
        self.dragging_point = point_type
    
    def apply_changes(self):
        """Применяет изменения к объекту"""
        if self.editing_object and self.canvas:
            # Обновляем отображение на канвасе
            self.canvas.update()
            # Отправляем сигнал об изменении
            self.object_changed.emit(self.editing_object)
    
    def setup_circle_editing(self, circle):
        """Настраивает интерфейс редактирования окружности"""
        from widgets.primitives import Circle
        
        self.title_label.setText("Редактирование окружности")
        
        # Группа способа задания
        method_group = QGroupBox("Способ задания")
        method_layout = QVBoxLayout()
        
        self.circle_method_combo = QComboBox()
        self.circle_method_combo.addItems([
            "Центр и радиус",
            "Центр и диаметр"
        ])
        self.circle_method_combo.currentTextChanged.connect(self.on_circle_method_changed)
        method_layout.addWidget(self.circle_method_combo)
        
        method_group.setLayout(method_layout)
        self.content_layout.addWidget(method_group)
        
        # Центр окружности
        center_group = QGroupBox("Центр (x, y)")
        center_layout = QGridLayout()
        
        center_layout.addWidget(QLabel("x:"), 0, 0)
        self.circle_center_x_spin = QDoubleSpinBox()
        self.circle_center_x_spin.setRange(-10000, 10000)
        self.circle_center_x_spin.setDecimals(2)
        self.circle_center_x_spin.setSingleStep(10)
        self.circle_center_x_spin.valueChanged.connect(self.on_circle_center_changed)
        center_layout.addWidget(self.circle_center_x_spin, 0, 1)
        
        center_layout.addWidget(QLabel("y:"), 0, 2)
        self.circle_center_y_spin = QDoubleSpinBox()
        self.circle_center_y_spin.setRange(-10000, 10000)
        self.circle_center_y_spin.setDecimals(2)
        self.circle_center_y_spin.setSingleStep(10)
        self.circle_center_y_spin.valueChanged.connect(self.on_circle_center_changed)
        center_layout.addWidget(self.circle_center_y_spin, 0, 3)
        
        center_group.setLayout(center_layout)
        self.content_layout.addWidget(center_group)
        
        # Радиус
        self.circle_radius_group = QGroupBox("Радиус")
        radius_layout = QHBoxLayout()
        
        self.circle_radius_spin = QDoubleSpinBox()
        self.circle_radius_spin.setRange(0.01, 10000)
        self.circle_radius_spin.setDecimals(2)
        self.circle_radius_spin.setSingleStep(10)
        self.circle_radius_spin.valueChanged.connect(self.on_circle_radius_changed)
        radius_layout.addWidget(self.circle_radius_spin)
        
        self.circle_radius_group.setLayout(radius_layout)
        self.content_layout.addWidget(self.circle_radius_group)
        
        # Диаметр
        self.circle_diameter_group = QGroupBox("Диаметр")
        diameter_layout = QHBoxLayout()
        
        self.circle_diameter_spin = QDoubleSpinBox()
        self.circle_diameter_spin.setRange(0.02, 20000)
        self.circle_diameter_spin.setDecimals(2)
        self.circle_diameter_spin.setSingleStep(10)
        self.circle_diameter_spin.valueChanged.connect(self.on_circle_diameter_changed)
        diameter_layout.addWidget(self.circle_diameter_spin)
        
        self.circle_diameter_group.setLayout(diameter_layout)
        self.circle_diameter_group.hide()
        self.content_layout.addWidget(self.circle_diameter_group)
        
        # Режим редактирования
        edit_mode_group = QGroupBox("Режим редактирования")
        edit_mode_layout = QVBoxLayout()
        
        self.edit_mode_label = QLabel("Перемещение точек: Отключено")
        self.edit_mode_label.setStyleSheet("color: gray;")
        edit_mode_layout.addWidget(self.edit_mode_label)
        
        info_label = QLabel("Включите режим редактирования для перемещения центра (синяя точка)\nили крайней точки (оранжевая точка) для изменения радиуса в рабочей области мышью")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; font-size: 9pt;")
        edit_mode_layout.addWidget(info_label)
        
        self.toggle_edit_mode_btn = QPushButton("Включить редактирование")
        self.toggle_edit_mode_btn.clicked.connect(self.toggle_edit_mode)
        edit_mode_layout.addWidget(self.toggle_edit_mode_btn)
        
        edit_mode_group.setLayout(edit_mode_layout)
        self.content_layout.addWidget(edit_mode_group)
        
        # Загружаем данные окружности
        self.load_circle_data(circle)
    
    def load_circle_data(self, circle):
        """Загружает данные окружности в поля редактирования"""
        from widgets.primitives import Circle
        
        # Блокируем сигналы, чтобы не вызывать обработчики при загрузке
        self.circle_center_x_spin.blockSignals(True)
        self.circle_center_y_spin.blockSignals(True)
        self.circle_radius_spin.blockSignals(True)
        self.circle_diameter_spin.blockSignals(True)
        
        # Центр
        self.circle_center_x_spin.setValue(circle.center.x())
        self.circle_center_y_spin.setValue(circle.center.y())
        
        # Радиус и диаметр
        self.circle_radius_spin.setValue(circle.radius)
        self.circle_diameter_spin.setValue(circle.radius * 2)
        
        # Устанавливаем способ задания по умолчанию (радиус)
        self.circle_method_combo.setCurrentIndex(0)
        
        # Разблокируем сигналы
        self.circle_center_x_spin.blockSignals(False)
        self.circle_center_y_spin.blockSignals(False)
        self.circle_radius_spin.blockSignals(False)
        self.circle_diameter_spin.blockSignals(False)
    
    def on_circle_method_changed(self, method_text):
        """Обработчик изменения способа задания окружности"""
        if "радиус" in method_text.lower():
            self.circle_radius_group.show()
            self.circle_diameter_group.hide()
        else:
            self.circle_radius_group.hide()
            self.circle_diameter_group.show()
    
    def on_circle_center_changed(self):
        """Обработчик изменения центра окружности"""
        if not self.editing_object:
            return
        
        from widgets.primitives import Circle
        if isinstance(self.editing_object, Circle):
            center_x = self.circle_center_x_spin.value()
            center_y = self.circle_center_y_spin.value()
            self.editing_object.center = QPointF(center_x, center_y)
            self.apply_changes()
    
    def on_circle_radius_changed(self):
        """Обработчик изменения радиуса окружности"""
        if not self.editing_object:
            return
        
        from widgets.primitives import Circle
        if isinstance(self.editing_object, Circle):
            radius = self.circle_radius_spin.value()
            self.editing_object.radius = radius
            
            # Обновляем диаметр
            self.circle_diameter_spin.blockSignals(True)
            self.circle_diameter_spin.setValue(radius * 2)
            self.circle_diameter_spin.blockSignals(False)
            
            self.apply_changes()
    
    def on_circle_diameter_changed(self):
        """Обработчик изменения диаметра окружности"""
        if not self.editing_object:
            return
        
        from widgets.primitives import Circle
        if isinstance(self.editing_object, Circle):
            diameter = self.circle_diameter_spin.value()
            radius = diameter / 2.0
            self.editing_object.radius = radius
            
            # Обновляем радиус
            self.circle_radius_spin.blockSignals(True)
            self.circle_radius_spin.setValue(radius)
            self.circle_radius_spin.blockSignals(False)
            
            self.apply_changes()
    
    def setup_rectangle_editing(self, rectangle):
        """Настраивает интерфейс редактирования прямоугольника"""
        from widgets.primitives import Rectangle
        
        self.title_label.setText("Редактирование прямоугольника")
        
        # Позиция и размеры
        position_group = QGroupBox("Позиция")
        position_layout = QGridLayout()
        
        position_layout.addWidget(QLabel("Верхний левый угол:"), 0, 0)
        self.rect_top_left_x_spin = QDoubleSpinBox()
        self.rect_top_left_x_spin.setRange(-10000, 10000)
        self.rect_top_left_x_spin.setDecimals(2)
        self.rect_top_left_x_spin.setSingleStep(10)
        self.rect_top_left_x_spin.valueChanged.connect(self.on_rectangle_position_changed)
        position_layout.addWidget(QLabel("x:"), 0, 1)
        position_layout.addWidget(self.rect_top_left_x_spin, 0, 2)
        
        self.rect_top_left_y_spin = QDoubleSpinBox()
        self.rect_top_left_y_spin.setRange(-10000, 10000)
        self.rect_top_left_y_spin.setDecimals(2)
        self.rect_top_left_y_spin.setSingleStep(10)
        self.rect_top_left_y_spin.valueChanged.connect(self.on_rectangle_position_changed)
        position_layout.addWidget(QLabel("y:"), 0, 3)
        position_layout.addWidget(self.rect_top_left_y_spin, 0, 4)
        
        position_layout.addWidget(QLabel("Нижний правый угол:"), 1, 0)
        self.rect_bottom_right_x_spin = QDoubleSpinBox()
        self.rect_bottom_right_x_spin.setRange(-10000, 10000)
        self.rect_bottom_right_x_spin.setDecimals(2)
        self.rect_bottom_right_x_spin.setSingleStep(10)
        self.rect_bottom_right_x_spin.valueChanged.connect(self.on_rectangle_position_changed)
        position_layout.addWidget(QLabel("x:"), 1, 1)
        position_layout.addWidget(self.rect_bottom_right_x_spin, 1, 2)
        
        self.rect_bottom_right_y_spin = QDoubleSpinBox()
        self.rect_bottom_right_y_spin.setRange(-10000, 10000)
        self.rect_bottom_right_y_spin.setDecimals(2)
        self.rect_bottom_right_y_spin.setSingleStep(10)
        self.rect_bottom_right_y_spin.valueChanged.connect(self.on_rectangle_position_changed)
        position_layout.addWidget(QLabel("y:"), 1, 3)
        position_layout.addWidget(self.rect_bottom_right_y_spin, 1, 4)
        
        position_group.setLayout(position_layout)
        self.content_layout.addWidget(position_group)
        
        # Размеры
        size_group = QGroupBox("Размеры")
        size_layout = QGridLayout()
        
        size_layout.addWidget(QLabel("Ширина:"), 0, 0)
        self.rect_width_spin = QDoubleSpinBox()
        self.rect_width_spin.setRange(0.01, 10000)
        self.rect_width_spin.setDecimals(2)
        self.rect_width_spin.setSingleStep(10)
        self.rect_width_spin.valueChanged.connect(self.on_rectangle_size_changed)
        size_layout.addWidget(self.rect_width_spin, 0, 1, 1, 4)
        
        size_layout.addWidget(QLabel("Высота:"), 1, 0)
        self.rect_height_spin = QDoubleSpinBox()
        self.rect_height_spin.setRange(0.01, 10000)
        self.rect_height_spin.setDecimals(2)
        self.rect_height_spin.setSingleStep(10)
        self.rect_height_spin.valueChanged.connect(self.on_rectangle_size_changed)
        size_layout.addWidget(self.rect_height_spin, 1, 1, 1, 4)
        
        size_group.setLayout(size_layout)
        self.content_layout.addWidget(size_group)
        
        # Скругления и фаски
        fillet_group = QGroupBox("Скругления и фаски")
        fillet_layout = QVBoxLayout()
        
        fillet_layout.addWidget(QLabel("Радиус скругления углов:"))
        self.rect_fillet_radius_spin = QDoubleSpinBox()
        self.rect_fillet_radius_spin.setRange(0, 10000)
        self.rect_fillet_radius_spin.setDecimals(2)
        self.rect_fillet_radius_spin.setSingleStep(1)
        self.rect_fillet_radius_spin.valueChanged.connect(self.on_rectangle_fillet_changed)
        fillet_layout.addWidget(self.rect_fillet_radius_spin)
        
        info_label = QLabel("Радиус скругления применяется ко всем углам.\nМаксимальный радиус ограничен половиной меньшей стороны.")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; font-size: 9pt;")
        fillet_layout.addWidget(info_label)
        
        fillet_group.setLayout(fillet_layout)
        self.content_layout.addWidget(fillet_group)
        
        # Режим редактирования
        edit_mode_group = QGroupBox("Режим редактирования")
        edit_mode_layout = QVBoxLayout()
        
        self.edit_mode_label = QLabel("Перемещение углов: Отключено")
        self.edit_mode_label.setStyleSheet("color: gray;")
        edit_mode_layout.addWidget(self.edit_mode_label)
        
        info_label = QLabel("Включите режим редактирования для перемещения центра (фиолетовая точка)\nили углов (зеленый, красный, синий, желтый) прямоугольника в рабочей области мышью")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; font-size: 9pt;")
        edit_mode_layout.addWidget(info_label)
        
        self.toggle_edit_mode_btn = QPushButton("Включить редактирование")
        self.toggle_edit_mode_btn.clicked.connect(self.toggle_edit_mode)
        edit_mode_layout.addWidget(self.toggle_edit_mode_btn)
        
        edit_mode_group.setLayout(edit_mode_layout)
        self.content_layout.addWidget(edit_mode_group)
        
        # Загружаем данные прямоугольника
        self.load_rectangle_data(rectangle)
    
    def load_rectangle_data(self, rectangle):
        """Загружает данные прямоугольника в поля редактирования"""
        from widgets.primitives import Rectangle
        
        # Блокируем сигналы, чтобы не вызывать обработчики при загрузке
        self.rect_top_left_x_spin.blockSignals(True)
        self.rect_top_left_y_spin.blockSignals(True)
        self.rect_bottom_right_x_spin.blockSignals(True)
        self.rect_bottom_right_y_spin.blockSignals(True)
        self.rect_width_spin.blockSignals(True)
        self.rect_height_spin.blockSignals(True)
        self.rect_fillet_radius_spin.blockSignals(True)
        
        # Позиция углов
        self.rect_top_left_x_spin.setValue(rectangle.top_left.x())
        self.rect_top_left_y_spin.setValue(rectangle.top_left.y())
        self.rect_bottom_right_x_spin.setValue(rectangle.bottom_right.x())
        self.rect_bottom_right_y_spin.setValue(rectangle.bottom_right.y())
        
        # Размеры
        bbox = rectangle.get_bounding_box()
        self.rect_width_spin.setValue(bbox.width())
        self.rect_height_spin.setValue(bbox.height())
        
        # Радиус скругления
        self.rect_fillet_radius_spin.setValue(getattr(rectangle, 'fillet_radius', 0.0))
        
        # Разблокируем сигналы
        self.rect_top_left_x_spin.blockSignals(False)
        self.rect_top_left_y_spin.blockSignals(False)
        self.rect_bottom_right_x_spin.blockSignals(False)
        self.rect_bottom_right_y_spin.blockSignals(False)
        self.rect_width_spin.blockSignals(False)
        self.rect_height_spin.blockSignals(False)
        self.rect_fillet_radius_spin.blockSignals(False)
    
    def on_rectangle_position_changed(self):
        """Обработчик изменения позиции прямоугольника"""
        if not self.editing_object:
            return
        
        from widgets.primitives import Rectangle
        if isinstance(self.editing_object, Rectangle):
            top_left_x = self.rect_top_left_x_spin.value()
            top_left_y = self.rect_top_left_y_spin.value()
            bottom_right_x = self.rect_bottom_right_x_spin.value()
            bottom_right_y = self.rect_bottom_right_y_spin.value()
            
            self.editing_object.top_left = QPointF(top_left_x, top_left_y)
            self.editing_object.bottom_right = QPointF(bottom_right_x, bottom_right_y)
            
            # Обновляем размеры
            bbox = self.editing_object.get_bounding_box()
            self.rect_width_spin.blockSignals(True)
            self.rect_height_spin.blockSignals(True)
            self.rect_width_spin.setValue(bbox.width())
            self.rect_height_spin.setValue(bbox.height())
            self.rect_width_spin.blockSignals(False)
            self.rect_height_spin.blockSignals(False)
            
            self.apply_changes()
    
    def on_rectangle_size_changed(self):
        """Обработчик изменения размеров прямоугольника"""
        if not self.editing_object:
            return
        
        from widgets.primitives import Rectangle
        if isinstance(self.editing_object, Rectangle):
            width = self.rect_width_spin.value()
            height = self.rect_height_spin.value()
            
            # Сохраняем верхний левый угол, изменяем нижний правый
            top_left = self.editing_object.top_left
            self.editing_object.bottom_right = QPointF(
                top_left.x() + width,
                top_left.y() + height
            )
            
            # Обновляем поля позиции
            self.rect_bottom_right_x_spin.blockSignals(True)
            self.rect_bottom_right_y_spin.blockSignals(True)
            self.rect_bottom_right_x_spin.setValue(self.editing_object.bottom_right.x())
            self.rect_bottom_right_y_spin.setValue(self.editing_object.bottom_right.y())
            self.rect_bottom_right_x_spin.blockSignals(False)
            self.rect_bottom_right_y_spin.blockSignals(False)
            
            # Проверяем радиус скругления (не должен превышать половину меньшей стороны)
            max_fillet = min(width, height) / 2.0
            current_fillet = getattr(self.editing_object, 'fillet_radius', 0.0)
            if current_fillet > max_fillet:
                self.editing_object.fillet_radius = max_fillet
                self.rect_fillet_radius_spin.blockSignals(True)
                self.rect_fillet_radius_spin.setValue(max_fillet)
                self.rect_fillet_radius_spin.blockSignals(False)
            
            self.apply_changes()
    
    def on_rectangle_fillet_changed(self):
        """Обработчик изменения радиуса скругления"""
        if not self.editing_object:
            return
        
        from widgets.primitives import Rectangle
        if isinstance(self.editing_object, Rectangle):
            fillet_radius = self.rect_fillet_radius_spin.value()
            
            # Проверяем, что радиус не превышает половину меньшей стороны
            bbox = self.editing_object.get_bounding_box()
            max_fillet = min(bbox.width(), bbox.height()) / 2.0
            if fillet_radius > max_fillet:
                fillet_radius = max_fillet
                self.rect_fillet_radius_spin.blockSignals(True)
                self.rect_fillet_radius_spin.setValue(fillet_radius)
                self.rect_fillet_radius_spin.blockSignals(False)
            
            self.editing_object.fillet_radius = fillet_radius
            self.apply_changes()
    
    def closeEvent(self, event):
        """Обработчик закрытия окна"""
        # Отключаем режим редактирования при закрытии
        if self.editing_mode and self.canvas:
            self.editing_mode = False
            self.canvas.set_editing_mode(False, None)
            self.dragging_point = None
        super().closeEvent(event)

