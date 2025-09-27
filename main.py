import sys
import math
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QPushButton, QLabel, QComboBox, QDoubleSpinBox, QGroupBox,
                               QGridLayout, QSpinBox, QColorDialog, QMessageBox)
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QFont

class LineSegment:
    """Класс для хранения информации об отрезке"""
    def __init__(self, start_point, end_point, color=QColor(255, 0, 0), width=2):
        self.start_point = start_point
        self.end_point = end_point
        self.color = color
        self.width = width

class CoordinateSystemWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.grid_step = 20
        self.background_color = QColor(255, 255, 255)
        self.grid_color = QColor(200, 200, 200)
        self.axis_color = QColor(0, 0, 0)
        self.line_color = QColor(255, 0, 0)
        self.line_width = 2
        
        # Хранилище всех отрезков
        self.lines = []
        
        # Текущий рисуемый отрезок
        self.current_line = None
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
        
        # Рисуем все сохраненные отрезки
        for line in self.lines:
            self.draw_saved_line(painter, line)
        
        # Рисуем текущий отрезок (если он есть)
        if self.current_line:
            self.draw_saved_line(painter, self.current_line)
        
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
    
    def draw_saved_line(self, painter, line):
        """Рисует сохраненный отрезок"""
        painter.setPen(QPen(line.color, line.width))
        
        center_x = self.width() // 2
        center_y = self.height() // 2
        
        # Преобразуем математические координаты в экранные
        screen_start = QPointF(
            center_x + line.start_point.x(),
            center_y - line.start_point.y()
        )
        screen_end = QPointF(
            center_x + line.end_point.x(),
            center_y - line.end_point.y()
        )
        
        painter.drawLine(screen_start, screen_end)
        
        # Рисуем точки начала и конца
        painter.setBrush(line.color)
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
                # Начинаем новый отрезок
                self.current_line = LineSegment(
                    QPointF(math_x, math_y),
                    QPointF(math_x, math_y),
                    self.line_color,
                    self.line_width
                )
                self.is_drawing = True
            else:
                # Заканчиваем рисование текущего отрезка
                if self.current_line:
                    self.current_line.end_point = QPointF(math_x, math_y)
                    self.lines.append(self.current_line)
                    self.current_line = None
                self.is_drawing = False
                self.current_point = None
            self.update()
    
    def mouseMoveEvent(self, event):
        if self.is_drawing and self.current_line:
            center_x = self.width() // 2
            center_y = self.height() // 2
            
            math_x = event.position().x() - center_x
            math_y = center_y - event.position().y()
            
            self.current_point = QPointF(math_x, math_y)
            self.current_line.end_point = QPointF(math_x, math_y)
            self.update()
    
    def start_new_line(self):
        """Начинает новый отрезок"""
        if self.is_drawing and self.current_line:
            # Сохраняем текущий отрезок если он есть
            self.lines.append(self.current_line)
        
        self.is_drawing = True
        self.current_point = None
        self.current_line = None
    
    def delete_last_line(self):
        """Удаляет последний добавленный отрезок"""
        if self.lines:
            self.lines.pop()
            self.update()
    
    def delete_all_lines(self):
        """Удаляет все отрезки"""
        self.lines.clear()
        self.current_line = None
        self.is_drawing = False
        self.current_point = None
        self.update()
    
    def set_grid_step(self, step):
        self.grid_step = step
        self.update()
    
    def set_line_color(self, color):
        self.line_color = color
        if self.current_line:
            self.current_line.color = color
    
    def set_background_color(self, color):
        self.background_color = color
        self.update()
    
    def set_grid_color(self, color):
        self.grid_color = color
        self.update()
    
    def set_line_width(self, width):
        self.line_width = width
        if self.current_line:
            self.current_line.width = width
    
    def get_current_points(self):
        """Возвращает текущие точки (для информационной панели)"""
        if self.current_line:
            return self.current_line.start_point, self.current_line.end_point
        elif self.lines:
            last_line = self.lines[-1]
            return last_line.start_point, last_line.end_point
        else:
            return QPointF(0, 0), QPointF(0, 0)
    
    def set_points_from_input(self, start_point, end_point):
        """Установка точек из числового ввода"""
        if self.is_drawing:
            # Если мы в режиме рисования, обновляем текущий отрезок
            if not self.current_line:
                self.current_line = LineSegment(start_point, end_point, self.line_color, self.line_width)
            else:
                self.current_line.start_point = start_point
                self.current_line.end_point = end_point
        else:
            # Создаем новый отрезок
            new_line = LineSegment(start_point, end_point, self.line_color, self.line_width)
            self.lines.append(new_line)
        
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
        
        self.finish_btn = QPushButton("Завершить отрезок")
        self.finish_btn.clicked.connect(self.finish_current_line)
        
        self.delete_last_btn = QPushButton("Удалить последний")
        self.delete_last_btn.clicked.connect(self.delete_last_line)
        
        self.delete_all_btn = QPushButton("Удалить все")
        self.delete_all_btn.clicked.connect(self.delete_all_lines)
        
        tools_layout.addWidget(self.line_btn)
        tools_layout.addWidget(self.finish_btn)
        tools_layout.addWidget(self.delete_last_btn)
        tools_layout.addWidget(self.delete_all_btn)
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
        
        self.angle_label = QLabel("°" if self.angle_units == "degrees" else "rad")
        
        polar_layout.addWidget(QLabel("r:"))
        polar_layout.addWidget(self.radius_spin)
        polar_layout.addWidget(QLabel("θ:"))
        polar_layout.addWidget(self.angle_spin)
        polar_layout.addWidget(self.angle_label)
        self.polar_group.setLayout(polar_layout)
        self.polar_group.hide()
        
        input_layout.addWidget(self.cartesian_group, 1, 1, 1, 4)
        input_layout.addWidget(self.polar_group, 1, 1, 1, 4)
        
        # Кнопка применения координат
        self.apply_coords_btn = QPushButton("Применить координаты")
        self.apply_coords_btn.clicked.connect(self.apply_coordinates)
        input_layout.addWidget(self.apply_coords_btn, 2, 0, 1, 5)
        
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
        
        # Толщина линии
        width_layout = QHBoxLayout()
        width_layout.addWidget(QLabel("Толщина линии:"))
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 10)
        self.width_spin.setValue(2)
        self.width_spin.valueChanged.connect(self.change_line_width)
        width_layout.addWidget(self.width_spin)
        settings_layout.addLayout(width_layout)
        
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
        
        # Информация о количестве отрезков
        self.lines_count_label = QLabel("Отрезков на экране: 0")
        left_panel.addWidget(self.lines_count_label)
        
        left_panel.addStretch()
        
        # Правая часть с рабочей областью и информацией
        right_panel = QVBoxLayout()
        
        # Рабочая область
        self.canvas = CoordinateSystemWidget()
        right_panel.addWidget(self.canvas)
        
        # Информационная панель
        info_group = QGroupBox("Информация о текущем отрезке")
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
        self.angle_info_label = QLabel("0.00°")
        info_layout.addWidget(self.angle_info_label, 3, 1)
        
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
        """Начинает новый отрезок"""
        self.canvas.start_new_line()
        self.update_info()
    
    def finish_current_line(self):
        """Завершает текущий отрезок и сохраняет его"""
        if self.canvas.is_drawing and self.canvas.current_line:
            self.canvas.lines.append(self.canvas.current_line)
            self.canvas.current_line = None
            self.canvas.is_drawing = False
            self.canvas.current_point = None
            self.canvas.update()
            self.update_info()
    
    def delete_last_line(self):
        """Удаляет последний отрезок"""
        self.canvas.delete_last_line()
        self.update_info()
    
    def delete_all_lines(self):
        """Удаляет все отрезки"""
        self.canvas.delete_all_lines()
        self.update_info()
    
    def apply_coordinates(self):
        """Применяет координаты из полей ввода"""
        start_point = QPointF(self.start_x_spin.value(), self.start_y_spin.value())
        
        if self.coordinate_system == "cartesian":
            end_point = QPointF(self.end_x_spin.value(), self.end_y_spin.value())
        else:
            # Преобразуем полярные координаты в декартовы
            radius = self.radius_spin.value()
            angle = self.angle_spin.value()
            
            if self.angle_units == "degrees":
                angle_rad = math.radians(angle)
            else:
                angle_rad = angle
            
            end_x = radius * math.cos(angle_rad)
            end_y = radius * math.sin(angle_rad)
            end_point = QPointF(end_x, end_y)
        
        self.canvas.set_points_from_input(start_point, end_point)
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
    
    def change_line_width(self, width):
        self.canvas.set_line_width(width)
    
    def change_line_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.canvas.set_line_color(color)
            self.canvas.update()
    
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
        self.angle_label.setText("°" if self.angle_units == "degrees" else "rad")
        
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
            self.apply_coordinates()
    
    def on_polar_changed(self):
        """Обработчик изменения полярных координат"""
        if self.coordinate_system == "polar":
            self.apply_coordinates()
    
    def update_info(self):
        """Обновляет информационную панель"""
        start_point, end_point = self.canvas.get_current_points()
        start_x, start_y = start_point.x(), start_point.y()
        end_x, end_y = end_point.x(), end_point.y()
        
        # Обновляем счетчик отрезков
        total_lines = len(self.canvas.lines)
        if self.canvas.current_line:
            total_lines += 1
        self.lines_count_label.setText(f"Отрезков на экране: {total_lines}")
        
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
                self.angle_info_label.setText(f"{angle:.2f}°")
            else:
                self.angle_info_label.setText(f"{angle_rad:.2f} rad")
        else:
            self.angle_info_label.setText("0.00°" if self.angle_units == "degrees" else "0.00 rad")

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()