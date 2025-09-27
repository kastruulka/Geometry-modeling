import sys
import math
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QPushButton, QLabel, QComboBox, QDoubleSpinBox, QGroupBox,
                               QGridLayout, QSpinBox, QColorDialog, QMessageBox)
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QFont

class CoordinateSystemWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.grid_step = 20
        self.background_color = QColor(255, 255, 255)
        self.grid_color = QColor(200, 200, 200)
        self.axis_color = QColor(0, 0, 0)
        self.line_color = QColor(255, 0, 0)
        self.line_width = 2
        
        self.start_point = QPointF(0, 0)
        self.end_point = QPointF(100, 100)
        self.is_drawing = False
        self.current_point = None
        
        self.setMinimumSize(600, 400)
        self.setMouseTracking(True)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Рисуем фон
        painter.fillRect(self.rect(), self.background_color)
        
        # Рисуем сетку
        self.draw_grid(painter)
        
        # Рисуем оси координат
        self.draw_axes(painter)
        
        # Рисуем отрезок
        if self.start_point and self.end_point:
            self.draw_line(painter)
        
        # Рисуем текущую точку при рисовании
        if self.is_drawing and self.current_point:
            self.draw_current_point(painter)
    
    def draw_grid(self, painter):
        painter.setPen(QPen(self.grid_color, 1, Qt.DotLine))
        
        width = self.width()
        height = self.height()
        center_x = width // 2
        center_y = height // 2
        
        # Вертикальные линии
        for x in range(center_x % self.grid_step, width, self.grid_step):
            painter.drawLine(x, 0, x, height)
        
        # Горизонтальные линии
        for y in range(center_y % self.grid_step, height, self.grid_step):
            painter.drawLine(0, y, width, y)
    
    def draw_axes(self, painter):
        painter.setPen(QPen(self.axis_color, 2))
        
        width = self.width()
        height = self.height()
        center_x = width // 2
        center_y = height // 2
        
        # Ось X
        painter.drawLine(0, center_y, width, center_y)
        # Ось Y
        painter.drawLine(center_x, 0, center_x, height)
        
        # Подписи осей
        painter.setFont(QFont("Arial", 10))
        painter.drawText(width - 20, center_y - 5, "X")
        painter.drawText(center_x + 5, 20, "Y")
        painter.drawText(center_x + 5, center_y + 15, "0")
    
    def draw_line(self, painter):
        painter.setPen(QPen(self.line_color, self.line_width))
        
        center_x = self.width() // 2
        center_y = self.height() // 2
        
        # Преобразуем математические координаты в экранные
        screen_start = QPointF(
            center_x + self.start_point.x(),
            center_y - self.start_point.y()
        )
        screen_end = QPointF(
            center_x + self.end_point.x(),
            center_y - self.end_point.y()
        )
        
        painter.drawLine(screen_start, screen_end)
        
        # Рисуем точки начала и конца
        painter.setBrush(self.line_color)
        painter.drawEllipse(screen_start, 4, 4)
        painter.drawEllipse(screen_end, 4, 4)
    
    def draw_current_point(self, painter):
        painter.setPen(QPen(Qt.blue, 2))
        painter.setBrush(Qt.blue)
        
        center_x = self.width() // 2
        center_y = self.height() // 2
        
        screen_point = QPointF(
            center_x + self.current_point.x(),
            center_y - self.current_point.y()
        )
        
        painter.drawEllipse(screen_point, 3, 3)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            center_x = self.width() // 2
            center_y = self.height() // 2
            
            # Преобразуем экранные координаты в математические
            math_x = event.position().x() - center_x
            math_y = center_y - event.position().y()
            
            if not self.is_drawing:
                self.start_point = QPointF(math_x, math_y)
                self.is_drawing = True
            else:
                self.end_point = QPointF(math_x, math_y)
                self.is_drawing = False
                self.update()
    
    def mouseMoveEvent(self, event):
        if self.is_drawing:
            center_x = self.width() // 2
            center_y = self.height() // 2
            
            math_x = event.position().x() - center_x
            math_y = center_y - event.position().y()
            
            self.current_point = QPointF(math_x, math_y)
            self.update()
    
    def set_grid_step(self, step):
        self.grid_step = step
        self.update()
    
    def set_line_color(self, color):
        self.line_color = color
        self.update()
    
    def set_background_color(self, color):
        self.background_color = color
        self.update()
    
    def set_grid_color(self, color):
        self.grid_color = color
        self.update()
    
    def set_points(self, start_point, end_point):
        """Установка точек извне"""
        self.start_point = start_point
        self.end_point = end_point
        self.is_drawing = False
        self.current_point = None
        self.update()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Построение отрезков в различных системах координат")
        self.setGeometry(100, 100, 1000, 700)
        
        self.coordinate_system = "cartesian"  # "cartesian" или "polar"
        self.angle_units = "degrees"  # "degrees" или "radians"
        
        self.init_ui()
        self.update_info()
    
    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        
        # Левая панель с настройками
        left_panel = QVBoxLayout()
        left_panel.setSpacing(10)
        
        # Панель инструментов
        tools_group = QGroupBox("Инструменты")
        tools_layout = QVBoxLayout()
        
        self.line_btn = QPushButton("Новый отрезок")
        self.line_btn.clicked.connect(self.start_new_line)
        
        self.delete_btn = QPushButton("Удалить отрезок")
        self.delete_btn.clicked.connect(self.delete_line)
        
        tools_layout.addWidget(self.line_btn)
        tools_layout.addWidget(self.delete_btn)
        tools_group.setLayout(tools_layout)
        left_panel.addWidget(tools_group)
        
        # Панель ввода координат
        input_group = QGroupBox("Ввод координат")
        input_layout = QGridLayout()
        
        # Начальная точка (всегда в декартовых координатах)
        input_layout.addWidget(QLabel("Начальная точка (x, y):"), 0, 0)
        self.start_x_spin = QDoubleSpinBox()
        self.start_x_spin.setRange(-1000, 1000)
        self.start_x_spin.setDecimals(2)
        self.start_x_spin.setSingleStep(10)
        self.start_x_spin.valueChanged.connect(self.on_coordinates_changed)
        
        self.start_y_spin = QDoubleSpinBox()
        self.start_y_spin.setRange(-1000, 1000)
        self.start_y_spin.setDecimals(2)
        self.start_y_spin.setSingleStep(10)
        self.start_y_spin.valueChanged.connect(self.on_coordinates_changed)
        
        input_layout.addWidget(QLabel("x:"), 0, 1)
        input_layout.addWidget(self.start_x_spin, 0, 2)
        input_layout.addWidget(QLabel("y:"), 0, 3)
        input_layout.addWidget(self.start_y_spin, 0, 4)
        
        # Конечная точка (зависит от системы координат)
        input_layout.addWidget(QLabel("Конечная точка:"), 1, 0)
        
        # Декартовы координаты
        self.cartesian_group = QWidget()
        cartesian_layout = QHBoxLayout()
        self.end_x_spin = QDoubleSpinBox()
        self.end_x_spin.setRange(-1000, 1000)
        self.end_x_spin.setDecimals(2)
        self.end_x_spin.setSingleStep(10)
        self.end_x_spin.valueChanged.connect(self.on_coordinates_changed)
        
        self.end_y_spin = QDoubleSpinBox()
        self.end_y_spin.setRange(-1000, 1000)
        self.end_y_spin.setDecimals(2)
        self.end_y_spin.setSingleStep(10)
        self.end_y_spin.valueChanged.connect(self.on_coordinates_changed)
        
        cartesian_layout.addWidget(QLabel("x:"))
        cartesian_layout.addWidget(self.end_x_spin)
        cartesian_layout.addWidget(QLabel("y:"))
        cartesian_layout.addWidget(self.end_y_spin)
        self.cartesian_group.setLayout(cartesian_layout)
        
        # Полярные координаты
        self.polar_group = QWidget()
        polar_layout = QHBoxLayout()
        self.radius_spin = QDoubleSpinBox()
        self.radius_spin.setRange(0, 1000)
        self.radius_spin.setDecimals(2)
        self.radius_spin.setSingleStep(10)
        self.radius_spin.valueChanged.connect(self.on_polar_changed)
        
        self.angle_spin = QDoubleSpinBox()
        self.angle_spin.setRange(-360, 360)
        self.angle_spin.setDecimals(2)
        self.angle_spin.setSingleStep(15)
        self.angle_spin.valueChanged.connect(self.on_polar_changed)
        
        polar_layout.addWidget(QLabel("r:"))
        polar_layout.addWidget(self.radius_spin)
        polar_layout.addWidget(QLabel("θ:"))
        polar_layout.addWidget(self.angle_spin)
        polar_layout.addWidget(QLabel("°" if self.angle_units == "degrees" else "rad"))
        self.polar_group.setLayout(polar_layout)
        self.polar_group.hide()
        
        input_layout.addWidget(self.cartesian_group, 1, 1, 1, 4)
        input_layout.addWidget(self.polar_group, 1, 1, 1, 4)
        
        input_group.setLayout(input_layout)
        left_panel.addWidget(input_group)
        
        # Панель настроек
        settings_group = QGroupBox("Настройки")
        settings_layout = QVBoxLayout()
        
        # Система координат
        coord_layout = QHBoxLayout()
        coord_layout.addWidget(QLabel("Система координат:"))
        self.coord_combo = QComboBox()
        self.coord_combo.addItems(["Декартова", "Полярная"])
        self.coord_combo.currentTextChanged.connect(self.change_coordinate_system)
        coord_layout.addWidget(self.coord_combo)
        settings_layout.addLayout(coord_layout)
        
        # Единицы измерения углов
        angle_layout = QHBoxLayout()
        angle_layout.addWidget(QLabel("Единицы углов:"))
        self.angle_combo = QComboBox()
        self.angle_combo.addItems(["Градусы", "Радианы"])
        self.angle_combo.currentTextChanged.connect(self.change_angle_units)
        angle_layout.addWidget(self.angle_combo)
        settings_layout.addLayout(angle_layout)
        
        # Шаг сетки
        grid_layout = QHBoxLayout()
        grid_layout.addWidget(QLabel("Шаг сетки:"))
        self.grid_spin = QSpinBox()
        self.grid_spin.setRange(5, 100)
        self.grid_spin.setValue(20)
        self.grid_spin.valueChanged.connect(self.change_grid_step)
        grid_layout.addWidget(self.grid_spin)
        settings_layout.addLayout(grid_layout)
        
        # Цвета
        color_layout = QVBoxLayout()
        self.line_color_btn = QPushButton("Цвет отрезка")
        self.line_color_btn.clicked.connect(self.change_line_color)
        
        self.bg_color_btn = QPushButton("Цвет фона")
        self.bg_color_btn.clicked.connect(self.change_background_color)
        
        self.grid_color_btn = QPushButton("Цвет сетки")
        self.grid_color_btn.clicked.connect(self.change_grid_color)
        
        color_layout.addWidget(self.line_color_btn)
        color_layout.addWidget(self.bg_color_btn)
        color_layout.addWidget(self.grid_color_btn)
        settings_layout.addLayout(color_layout)
        
        settings_group.setLayout(settings_layout)
        left_panel.addWidget(settings_group)
        left_panel.addStretch()
        
        # Правая часть с рабочей областью и информацией
        right_panel = QVBoxLayout()
        
        # Рабочая область
        self.canvas = CoordinateSystemWidget()
        right_panel.addWidget(self.canvas)
        
        # Информационная панель
        info_group = QGroupBox("Информация")
        info_layout = QGridLayout()
        
        info_layout.addWidget(QLabel("Начальная точка:"), 0, 0)
        self.start_point_label = QLabel("(0.00, 0.00)")
        info_layout.addWidget(self.start_point_label, 0, 1)
        
        info_layout.addWidget(QLabel("Конечная точка:"), 1, 0)
        self.end_point_label = QLabel("(0.00, 0.00)")
        info_layout.addWidget(self.end_point_label, 1, 1)
        
        info_layout.addWidget(QLabel("Длина отрезка:"), 2, 0)
        self.length_label = QLabel("0.00")
        info_layout.addWidget(self.length_label, 2, 1)
        
        info_layout.addWidget(QLabel("Угол наклона:"), 3, 0)
        self.angle_label = QLabel("0.00°")
        info_layout.addWidget(self.angle_label, 3, 1)
        
        info_group.setLayout(info_layout)
        right_panel.addWidget(info_group)
        
        main_layout.addLayout(left_panel, 1)
        main_layout.addLayout(right_panel, 3)
        
        # Инициализация значений
        self.start_x_spin.setValue(0)
        self.start_y_spin.setValue(0)
        self.end_x_spin.setValue(100)
        self.end_y_spin.setValue(100)
        self.radius_spin.setValue(100)
        self.angle_spin.setValue(45)
    
    def start_new_line(self):
        self.canvas.is_drawing = True
        self.canvas.current_point = None
        self.update_info()
    
    def delete_line(self):
        self.canvas.start_point = QPointF(0, 0)
        self.canvas.end_point = QPointF(0, 0)
        self.canvas.is_drawing = False
        self.canvas.current_point = None
        self.canvas.update()
        
        # Сброс полей ввода
        self.start_x_spin.setValue(0)
        self.start_y_spin.setValue(0)
        self.end_x_spin.setValue(0)
        self.end_y_spin.setValue(0)
        self.radius_spin.setValue(0)
        self.angle_spin.setValue(0)
        
        self.update_info()
    
    def change_coordinate_system(self, system):
        self.coordinate_system = "polar" if system == "Полярная" else "cartesian"
        self.update_input_fields()
        self.update_info()
    
    def change_angle_units(self, units):
        self.angle_units = "radians" if units == "Радианы" else "degrees"
        self.update_angle_units()
        self.update_info()
    
    def change_grid_step(self, step):
        self.canvas.set_grid_step(step)
    
    def change_line_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.canvas.set_line_color(color)
    
    def change_background_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.canvas.set_background_color(color)
    
    def change_grid_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.canvas.set_grid_color(color)
    
    def update_input_fields(self):
        """Обновляет отображение полей ввода в зависимости от системы координат"""
        if self.coordinate_system == "cartesian":
            self.cartesian_group.show()
            self.polar_group.hide()
        else:
            self.cartesian_group.hide()
            self.polar_group.show()
            
            # При переключении на полярные координаты преобразуем текущие декартовы координаты
            end_x = self.end_x_spin.value()
            end_y = self.end_y_spin.value()
            
            radius = math.sqrt(end_x**2 + end_y**2)
            angle = math.atan2(end_y, end_x)
            
            if self.angle_units == "degrees":
                angle = math.degrees(angle)
            
            self.radius_spin.setValue(radius)
            self.angle_spin.setValue(angle)
    
    def update_angle_units(self):
        """Обновляет единицы измерения углов"""
        angle_label = self.polar_group.layout().itemAt(4).widget()
        angle_label.setText("°" if self.angle_units == "degrees" else "rad")
        
        # Конвертируем угол при смене единиц измерения
        if self.coordinate_system == "polar":
            current_angle = self.angle_spin.value()
            if self.angle_units == "degrees":
                # Были радианы, стали градусы
                current_angle = math.degrees(current_angle)
            else:
                # Были градусы, стали радианы
                current_angle = math.radians(current_angle)
            
            self.angle_spin.blockSignals(True)
            self.angle_spin.setValue(current_angle)
            self.angle_spin.blockSignals(False)
    
    def on_coordinates_changed(self):
        """Обработчик изменения декартовых координат"""
        if self.coordinate_system == "cartesian":
            start_point = QPointF(self.start_x_spin.value(), self.start_y_spin.value())
            end_point = QPointF(self.end_x_spin.value(), self.end_y_spin.value())
            self.canvas.set_points(start_point, end_point)
            self.update_info()
    
    def on_polar_changed(self):
        """Обработчик изменения полярных координат"""
        if self.coordinate_system == "polar":
            # Начальная точка всегда в декартовых координатах
            start_point = QPointF(self.start_x_spin.value(), self.start_y_spin.value())
            
            # Конечная точка в полярных координатах
            radius = self.radius_spin.value()
            angle = self.angle_spin.value()
            
            # Преобразуем в декартовы координаты
            if self.angle_units == "degrees":
                angle_rad = math.radians(angle)
            else:
                angle_rad = angle
            
            end_x = radius * math.cos(angle_rad)
            end_y = radius * math.sin(angle_rad)
            end_point = QPointF(end_x, end_y)
            
            self.canvas.set_points(start_point, end_point)
            self.update_info()
            
            # Обновляем декартовы координаты для согласованности
            self.end_x_spin.blockSignals(True)
            self.end_y_spin.blockSignals(True)
            self.end_x_spin.setValue(end_x)
            self.end_y_spin.setValue(end_y)
            self.end_x_spin.blockSignals(False)
            self.end_y_spin.blockSignals(False)
    
    def update_info(self):
        """Обновляет информационную панель"""
        start_x, start_y = self.canvas.start_point.x(), self.canvas.start_point.y()
        end_x, end_y = self.canvas.end_point.x(), self.canvas.end_point.y()
        
        # Обновляем поля ввода
        self.start_x_spin.blockSignals(True)
        self.start_y_spin.blockSignals(True)
        self.start_x_spin.setValue(start_x)
        self.start_y_spin.setValue(start_y)
        self.start_x_spin.blockSignals(False)
        self.start_y_spin.blockSignals(False)
        
        # Отображаем координаты в информационной панели
        if self.coordinate_system == "cartesian":
            self.start_point_label.setText(f"({start_x:.2f}, {start_y:.2f})")
            self.end_point_label.setText(f"({end_x:.2f}, {end_y:.2f})")
        else:
            # Преобразуем в полярные координаты для отображения
            r1 = math.sqrt(start_x**2 + start_y**2)
            theta1 = math.atan2(start_y, start_x)
            
            r2 = math.sqrt(end_x**2 + end_y**2)
            theta2 = math.atan2(end_y, end_x)
            
            if self.angle_units == "degrees":
                theta1 = math.degrees(theta1)
                theta2 = math.degrees(theta2)
                self.start_point_label.setText(f"(r={r1:.2f}, θ={theta1:.2f}°)")
                self.end_point_label.setText(f"(r={r2:.2f}, θ={theta2:.2f}°)")
            else:
                self.start_point_label.setText(f"(r={r1:.2f}, θ={theta1:.2f} rad)")
                self.end_point_label.setText(f"(r={r2:.2f}, θ={theta2:.2f} rad)")
        
        # Вычисляем длину отрезка
        dx = end_x - start_x
        dy = end_y - start_y
        length = math.sqrt(dx**2 + dy**2)
        self.length_label.setText(f"{length:.2f}")
        
        # Вычисляем угол наклона
        if dx != 0 or dy != 0:
            angle_rad = math.atan2(dy, dx)
            if self.angle_units == "degrees":
                angle = math.degrees(angle_rad)
                self.angle_label.setText(f"{angle:.2f}°")
            else:
                self.angle_label.setText(f"{angle_rad:.2f} rad")
        else:
            self.angle_label.setText("0.00°" if self.angle_units == "degrees" else "0.00 rad")

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()