import sys
import math
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QPushButton, QLabel, QComboBox, QDoubleSpinBox, QGroupBox,
                               QGridLayout, QSpinBox, QColorDialog, QMessageBox, QToolBar,
                               QStatusBar, QMenu, QSizePolicy)
from PySide6.QtCore import QPointF, Qt, QSize
from PySide6.QtGui import QColor, QAction, QIcon, QKeySequence

from widgets.coordinate_system import CoordinateSystemWidget

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Построение отрезков в различных системах координат")
        self.setGeometry(100, 100, 1000, 700)
        
        self.coordinate_system = "cartesian"  # "cartesian" или "polar"
        self.angle_units = "degrees"  # "degrees" или "radians"
        
        # Сначала создаем canvas
        self.canvas = CoordinateSystemWidget()
        
        self.init_ui()
        self.update_info()
    
    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        
        # Создаем меню
        self.create_menus()
        
        # Создаем панель инструментов
        self.create_toolbar()
        
        # Создаем строку состояния
        self.create_statusbar()
        
        # Левая панель с настройками
        left_panel = QVBoxLayout()
        left_panel.setSpacing(10)
        
        # Панель инструментов
        tools_group = QGroupBox("Инструменты")
        tools_layout = QVBoxLayout()

        self.new_line_btn = QPushButton("Сохранить отрезок")
        self.new_line_btn.clicked.connect(self.start_new_line)

        self.delete_last_btn = QPushButton("Удалить последний")
        self.delete_last_btn.clicked.connect(self.delete_last_line)

        self.delete_all_btn = QPushButton("Удалить все")
        self.delete_all_btn.clicked.connect(self.delete_all_lines)

        tools_layout.addWidget(self.new_line_btn)
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
        self.start_x_spin.blockSignals(True)
        self.start_y_spin.blockSignals(True)
        self.end_x_spin.blockSignals(True)
        self.end_y_spin.blockSignals(True)
        self.radius_spin.blockSignals(True)
        self.angle_spin.blockSignals(True)
        
        self.start_x_spin.setValue(0)
        self.start_y_spin.setValue(0)
        self.end_x_spin.setValue(100)
        self.end_y_spin.setValue(100)
        self.radius_spin.setValue(100)
        self.angle_spin.setValue(45)
        
        self.start_x_spin.blockSignals(False)
        self.start_y_spin.blockSignals(False)
        self.end_x_spin.blockSignals(False)
        self.end_y_spin.blockSignals(False)
        self.radius_spin.blockSignals(False)
        self.angle_spin.blockSignals(False)
        
        # Подключаем сигналы от canvas для обновления статусбара
        self.canvas.view_changed.connect(self.update_statusbar)
        self.update_statusbar()
    
    def create_context_menu(self, position):
        """Создает контекстное меню для рабочей области"""
        menu = QMenu(self)
        
        # Команды навигации
        zoom_in_action = menu.addAction("Увеличить")
        zoom_in_action.setShortcut(QKeySequence.ZoomIn)
        zoom_in_action.triggered.connect(self.canvas.zoom_in)
        
        zoom_out_action = menu.addAction("Уменьшить")
        zoom_out_action.setShortcut(QKeySequence.ZoomOut)
        zoom_out_action.triggered.connect(self.canvas.zoom_out)
        
        menu.addSeparator()
        
        show_all_action = menu.addAction("Показать всё")
        show_all_action.setShortcut("Ctrl+A")
        show_all_action.triggered.connect(self.canvas.show_all)
        
        reset_view_action = menu.addAction("Сбросить вид")
        reset_view_action.setShortcut("Ctrl+R")
        reset_view_action.triggered.connect(self.canvas.reset_view)
        
        menu.addSeparator()
        
        rotate_left_action = menu.addAction("Повернуть налево")
        rotate_left_action.setShortcut("Ctrl+Left")
        rotate_left_action.triggered.connect(self.rotate_left)
        
        rotate_right_action = menu.addAction("Повернуть направо")
        rotate_right_action.setShortcut("Ctrl+Right")
        rotate_right_action.triggered.connect(self.rotate_right)
        
        menu.addSeparator()
        
        # Инструменты
        pan_action = menu.addAction("Панорамирование")
        pan_action.setCheckable(True)
        pan_action.setChecked(self.pan_action.isChecked())
        pan_action.triggered.connect(self.pan_action.toggle)
        
        menu.exec_(self.mapToGlobal(position))
    
    def rotate_left(self):
        """Поворот налево"""
        print("Поворот налево")  # Отладочное сообщение
        self.canvas.rotate_left(15)
        
    def rotate_right(self):
        """Поворот направо"""
        print("Поворот направо")  # Отладочное сообщение
        self.canvas.rotate_right(15)
    
    def create_menus(self):
        """Создает меню навигации"""
        menubar = self.menuBar()
        
        # Меню "Вид"
        view_menu = menubar.addMenu("Вид")
        
        # Действия для навигации
        zoom_in_action = QAction("Увеличить", self)
        zoom_in_action.setShortcut(QKeySequence.ZoomIn)
        zoom_in_action.triggered.connect(self.canvas.zoom_in)
        view_menu.addAction(zoom_in_action)
        
        zoom_out_action = QAction("Уменьшить", self)
        zoom_out_action.setShortcut(QKeySequence.ZoomOut)
        zoom_out_action.triggered.connect(self.canvas.zoom_out)
        view_menu.addAction(zoom_out_action)
        
        view_menu.addSeparator()
        
        show_all_action = QAction("Показать всё", self)
        show_all_action.setShortcut("Ctrl+A")
        show_all_action.triggered.connect(self.canvas.show_all)
        view_menu.addAction(show_all_action)
        
        reset_view_action = QAction("Сбросить вид", self)
        reset_view_action.setShortcut("Ctrl+R")
        reset_view_action.triggered.connect(self.canvas.reset_view)
        view_menu.addAction(reset_view_action)
        
        view_menu.addSeparator()
        
        rotate_left_action = QAction("Повернуть налево", self)
        rotate_left_action.setShortcut("Ctrl+Left")
        rotate_left_action.triggered.connect(self.rotate_left)
        view_menu.addAction(rotate_left_action)
        
        rotate_right_action = QAction("Повернуть направо", self)
        rotate_right_action.setShortcut("Ctrl+Right")
        rotate_right_action.triggered.connect(self.rotate_right)
        view_menu.addAction(rotate_right_action)
    
    def create_toolbar(self):
        """Создает панель инструментов навигации"""
        toolbar = QToolBar("Навигация")
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)
        
        # Инструмент "Рука" для панорамирования
        self.pan_action = QAction("🖑", self)
        self.pan_action.setCheckable(True)
        self.pan_action.setToolTip("Панорамирование (Пробел)")
        self.pan_action.setShortcut(Qt.Key_Space)
        self.pan_action.toggled.connect(self.canvas.set_pan_mode)
        toolbar.addAction(self.pan_action)
        
        toolbar.addSeparator()
        
        # Увеличение
        zoom_in_action = QAction("🞢", self)
        zoom_in_action.setToolTip("Увеличить")
        zoom_in_action.triggered.connect(self.canvas.zoom_in)
        toolbar.addAction(zoom_in_action)
        
        # Уменьшение
        zoom_out_action = QAction("‒", self)
        zoom_out_action.setToolTip("Уменьшить")
        zoom_out_action.triggered.connect(self.canvas.zoom_out)
        toolbar.addAction(zoom_out_action)
        
        # Показать всё
        show_all_action = QAction("ⓘ", self)
        show_all_action.setToolTip("Показать всё")
        show_all_action.triggered.connect(self.canvas.show_all)
        toolbar.addAction(show_all_action)
        
        toolbar.addSeparator()
        
        # Поворот налево
        rotate_left_action = QAction("↶", self)
        rotate_left_action.setToolTip("Повернуть налево")
        rotate_left_action.triggered.connect(self.rotate_left)
        toolbar.addAction(rotate_left_action)
        
        # Поворот направо
        rotate_right_action = QAction("↷", self)
        rotate_right_action.setToolTip("Повернуть направо")
        rotate_right_action.triggered.connect(self.rotate_right)
        toolbar.addAction(rotate_right_action)
        
        # Сброс вида
        reset_view_action = QAction("⟲", self)
        reset_view_action.setToolTip("Сбросить вид")
        reset_view_action.triggered.connect(self.canvas.reset_view)
        toolbar.addAction(reset_view_action)
    
    def create_statusbar(self):
        """Создает строку состояния"""
        statusbar = QStatusBar()
        self.setStatusBar(statusbar)
        
        # Координаты курсора
        self.cursor_coords_label = QLabel("Координаты: (0.00, 0.00)")
        statusbar.addPermanentWidget(self.cursor_coords_label)
        
        # Масштаб
        self.scale_label = QLabel("Масштаб: 100%")
        statusbar.addPermanentWidget(self.scale_label)
        
        # Угол поворота
        self.rotation_label = QLabel("Поворот: 0°")
        statusbar.addPermanentWidget(self.rotation_label)
        
        # Активный инструмент
        self.tool_label = QLabel("Инструмент: Рисование")
        statusbar.addWidget(self.tool_label)
    
    def update_statusbar(self):
        """Обновляет информацию в строке состояния"""
        # Координаты курсора (если доступны)
        cursor_pos = self.canvas.get_cursor_world_coords()
        if cursor_pos:
            self.cursor_coords_label.setText(
                f"Координаты: ({cursor_pos.x():.2f}, {cursor_pos.y():.2f})"
            )

        # Масштаб
        scale = self.canvas.get_scale() * 100
        self.scale_label.setText(f"Масштаб: {scale:.1f}%")

        # Угол поворота
        rotation = self.canvas.get_rotation()
        self.rotation_label.setText(f"Поворот: {rotation:.1f}°")

        # Активный инструмент
        if self.pan_action.isChecked():
            self.tool_label.setText("Инструмент: Панорамирование")
        else:
            self.tool_label.setText("Инструмент: Рисование")

    
    def start_new_line(self):
        """Начинает новый отрезок"""
        # Если уже рисуем отрезок, сохраняем его
        if self.canvas.is_drawing and self.canvas.current_line:
            # Берем текущее положение мыши как конечную точку
            if self.canvas.current_point:
                self.canvas.current_line.end_point = self.canvas.current_point
                self.canvas.lines.append(self.canvas.current_line)
        
        # Начинаем новый отрезок
        self.canvas.start_new_line()
        
        # Сбрасываем значения в полях ввода для нового отрезка
        self.start_x_spin.blockSignals(True)
        self.start_y_spin.blockSignals(True)
        self.end_x_spin.blockSignals(True)
        self.end_y_spin.blockSignals(True)
        self.radius_spin.blockSignals(True)
        self.angle_spin.blockSignals(True)
        
        # Устанавливаем начальную точку в текущее положение курсора, если доступно
        cursor_pos = self.canvas.get_cursor_world_coords()
        if cursor_pos:
            self.start_x_spin.setValue(cursor_pos.x())
            self.start_y_spin.setValue(cursor_pos.y())
        else:
            self.start_x_spin.setValue(0)
            self.start_y_spin.setValue(0)
        
        # Сбрасываем конечные точки
        self.end_x_spin.setValue(100)
        self.end_y_spin.setValue(100)
        self.radius_spin.setValue(100)
        self.angle_spin.setValue(45)
        
        self.start_x_spin.blockSignals(False)
        self.start_y_spin.blockSignals(False)
        self.end_x_spin.blockSignals(False)
        self.end_y_spin.blockSignals(False)
        self.radius_spin.blockSignals(False)
        self.angle_spin.blockSignals(False)
        
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
        """Применяет координаты из полей ввода и фиксирует отрезок"""
        start_point = QPointF(self.start_x_spin.value(), self.start_y_spin.value())
        
        if self.coordinate_system == "cartesian":
            end_point = QPointF(self.end_x_spin.value(), self.end_y_spin.value())
        else:
            # Преобразуем полярные координаты в декартовы ОТНОСИТЕЛЬНО НАЧАЛЬНОЙ ТОЧКИ
            radius = self.radius_spin.value()
            angle = self.angle_spin.value()
            
            if self.angle_units == "degrees":
                angle_rad = math.radians(angle)
            else:
                angle_rad = angle
            
            # Вычисляем смещение от начальной точки
            delta_x = radius * math.cos(angle_rad)
            delta_y = radius * math.sin(angle_rad)
            
            # Конечная точка = начальная + смещение
            end_x = start_point.x() + delta_x
            end_y = start_point.y() + delta_y
            end_point = QPointF(end_x, end_y)
        
        # Фиксируем отрезок (apply=True)
        self.canvas.set_points_from_input(start_point, end_point, apply=True)
        
        # Очищаем текущий отрезок после фиксации
        self.canvas.current_line = None
        self.canvas.is_drawing = False
        
        # АВТОМАТИЧЕСКИ ПОКАЗЫВАЕМ ВСЕ ОТРЕЗКИ
        self.canvas.show_all()
        
        # Сбрасываем значения для следующего отрезка
        self.start_x_spin.blockSignals(True)
        self.start_y_spin.blockSignals(True)
        self.end_x_spin.blockSignals(True)
        self.end_y_spin.blockSignals(True)
        self.radius_spin.blockSignals(True)
        self.angle_spin.blockSignals(True)
        
        self.start_x_spin.setValue(0)
        self.start_y_spin.setValue(0)
        self.end_x_spin.setValue(100)
        self.end_y_spin.setValue(100)
        self.radius_spin.setValue(100)
        self.angle_spin.setValue(45)
        
        self.start_x_spin.blockSignals(False)
        self.start_y_spin.blockSignals(False)
        self.end_x_spin.blockSignals(False)
        self.end_y_spin.blockSignals(False)
        self.radius_spin.blockSignals(False)
        self.angle_spin.blockSignals(False)
        
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
            # ОТНОСИТЕЛЬНО НАЧАЛЬНОЙ ТОЧКИ
            start_x = self.start_x_spin.value()
            start_y = self.start_y_spin.value()
            end_x = self.end_x_spin.value()
            end_y = self.end_y_spin.value()
            
            # Вычисляем смещение от начальной точки
            delta_x = end_x - start_x
            delta_y = end_y - start_y
            
            # Преобразуем смещение в полярные координаты
            radius = math.sqrt(delta_x**2 + delta_y**2)
            angle = math.atan2(delta_y, delta_x)
            
            if self.angle_units == "degrees":
                angle = math.degrees(angle)
            
            self.radius_spin.blockSignals(True)
            self.angle_spin.blockSignals(True)
            self.radius_spin.setValue(radius)
            self.angle_spin.setValue(angle)
            self.radius_spin.blockSignals(False)
            self.angle_spin.blockSignals(False)
    
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
        """Обработчик изменения декартовых координат - только предпросмотр"""
        if self.coordinate_system == "cartesian":
            self.preview_coordinates()

    def on_polar_changed(self):
        """Обработчик изменения полярных координат - только предпросмотр"""
        if self.coordinate_system == "polar":
            self.preview_coordinates()

    def preview_coordinates(self):
        """Предпросмотр отрезка без сохранения"""
        start_point = QPointF(self.start_x_spin.value(), self.start_y_spin.value())
        
        if self.coordinate_system == "cartesian":
            end_point = QPointF(self.end_x_spin.value(), self.end_y_spin.value())
        else:
            # Преобразуем полярные координаты в декартовы ОТНОСИТЕЛЬНО НАЧАЛЬНОЙ ТОЧКИ
            radius = self.radius_spin.value()
            angle = self.angle_spin.value()
            
            if self.angle_units == "degrees":
                angle_rad = math.radians(angle)
            else:
                angle_rad = angle
            
            # Вычисляем смещение от начальной точки
            delta_x = radius * math.cos(angle_rad)
            delta_y = radius * math.sin(angle_rad)
            
            # Конечная точка = начальная + смещение
            end_x = start_point.x() + delta_x
            end_y = start_point.y() + delta_y
            end_point = QPointF(end_x, end_y)
        
        # Только предпросмотр без сохранения (apply=False)
        self.canvas.set_points_from_input(start_point, end_point, apply=False)
        self.update_info()
    
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
            # Преобразуем в полярные координаты ОТНОСИТЕЛЬНО НАЧАЛЬНОЙ ТОЧКИ
            delta_x = end_x - start_x
            delta_y = end_y - start_y
            
            r = math.sqrt(delta_x**2 + delta_y**2)
            theta = math.atan2(delta_y, delta_x)
            
            if self.angle_units == "degrees":
                theta = math.degrees(theta)
                self.start_point_label.setText(f"({start_x:.2f}, {start_y:.2f})")
                self.end_point_label.setText(f"(Δr={r:.2f}, Δθ={theta:.2f}°)")
            else:
                self.start_point_label.setText(f"({start_x:.2f}, {start_y:.2f})")
                self.end_point_label.setText(f"(Δr={r:.2f}, Δθ={theta:.2f} rad)")
        
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