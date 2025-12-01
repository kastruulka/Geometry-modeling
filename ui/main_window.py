import sys
import math
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QPushButton, QLabel, QComboBox, QDoubleSpinBox, QGroupBox,
                               QGridLayout, QSpinBox, QColorDialog, QMessageBox, QToolBar,
                               QStatusBar, QMenu, QSizePolicy, QSplitter, QScrollArea)
from PySide6.QtCore import QPointF, Qt, QSize
from PySide6.QtGui import QColor, QAction, QIcon, QKeySequence

from widgets.coordinate_system import CoordinateSystemWidget
from widgets.line_style import LineStyleManager
from ui.style_panels import ObjectPropertiesPanel, StyleManagementPanel, StyleComboBox

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Построение отрезков в различных системах координат")
        self.setGeometry(100, 100, 1200, 800)
        
        self.coordinate_system = "cartesian"  # "cartesian" или "polar"
        self.angle_units = "degrees"  # "degrees" или "radians"
        
        # Создаем менеджер стилей
        self.style_manager = LineStyleManager()
        
        # сначала создаем canvas
        self.canvas = CoordinateSystemWidget(style_manager=self.style_manager)
        
        # Выделенные объекты
        self.selected_objects = []
        
        self.init_ui()
        self.update_info()
    
    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        
        # меню
        self.create_menus()
        
        # панель инструментов
        self.create_toolbar()
        
        # панель инструментов стилей
        self.create_style_toolbar()
        
        # строка состояния
        self.create_statusbar()
        
        # Используем Splitter для разделения панелей
        main_splitter = QSplitter(Qt.Horizontal)
        
        # Левая панель с настройками
        left_widget = QWidget()
        left_panel = QVBoxLayout(left_widget)
        left_panel.setSpacing(10)
        
        # Обёртка в скролл для левой панели
        scroll_area = QScrollArea()
        scroll_area.setWidget(left_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # панель инструментов
        tools_group = QGroupBox("Инструменты")
        tools_layout = QVBoxLayout()
        
        # Выбор типа примитива
        primitive_layout = QHBoxLayout()
        primitive_layout.addWidget(QLabel("Тип примитива:"))
        self.primitive_combo = QComboBox()
        self.primitive_combo.addItems(["Отрезок", "Окружность", "Дуга", "Прямоугольник", "Эллипс"])
        self.primitive_combo.currentTextChanged.connect(self.change_primitive_type)
        primitive_layout.addWidget(self.primitive_combo)
        tools_layout.addLayout(primitive_layout)
        
        # Выбор метода создания окружности (скрыто по умолчанию)
        circle_method_layout = QHBoxLayout()
        circle_method_layout.addWidget(QLabel("Способ создания:"))
        self.circle_method_combo = QComboBox()
        self.circle_method_combo.addItems([
            "Центр и радиус",
            "Центр и диаметр",
            "Две точки",
            "Три точки на окружности"
        ])
        self.circle_method_combo.currentTextChanged.connect(self.change_circle_method)
        circle_method_layout.addWidget(self.circle_method_combo)
        self.circle_method_widget = QWidget()
        self.circle_method_widget.setLayout(circle_method_layout)
        self.circle_method_widget.hide()
        tools_layout.addWidget(self.circle_method_widget)
        
        # Выбор метода создания дуги (скрыто по умолчанию)
        arc_method_layout = QHBoxLayout()
        arc_method_layout.addWidget(QLabel("Способ создания:"))
        self.arc_method_combo = QComboBox()
        self.arc_method_combo.addItems([
            "Три точки (начало, вторая точка, конец)",
            "Центр, начальный угол, конечный угол"
        ])
        self.arc_method_combo.currentTextChanged.connect(self.change_arc_method)
        arc_method_layout.addWidget(self.arc_method_combo)
        self.arc_method_widget = QWidget()
        self.arc_method_widget.setLayout(arc_method_layout)
        self.arc_method_widget.hide()
        tools_layout.addWidget(self.arc_method_widget)
        
        # Выбор метода создания прямоугольника (скрыто по умолчанию)
        rectangle_method_layout = QHBoxLayout()
        rectangle_method_layout.addWidget(QLabel("Способ создания:"))
        self.rectangle_method_combo = QComboBox()
        self.rectangle_method_combo.addItems([
            "Две противоположные точки",
            "Одна точка, ширина и высота",
            "Центр, ширина и высота",
            "С фасками/скруглениями при создании"
        ])
        self.rectangle_method_combo.currentTextChanged.connect(self.change_rectangle_method)
        rectangle_method_layout.addWidget(self.rectangle_method_combo)
        self.rectangle_method_widget = QWidget()
        self.rectangle_method_widget.setLayout(rectangle_method_layout)
        self.rectangle_method_widget.hide()
        tools_layout.addWidget(self.rectangle_method_widget)

        self.delete_last_btn = QPushButton("Удалить последний")
        self.delete_last_btn.clicked.connect(self.delete_last_line)

        self.delete_all_btn = QPushButton("Удалить все")
        self.delete_all_btn.clicked.connect(self.delete_all_lines)

        tools_layout.addWidget(self.delete_last_btn)
        tools_layout.addWidget(self.delete_all_btn)
        tools_group.setLayout(tools_layout)
        left_panel.addWidget(tools_group)
        
        # панель ввода координат
        input_group = QGroupBox("Ввод координат")
        input_layout = QGridLayout()
        
        # начальная точка (всегда в декартовых координатах)
        self.start_point_label_widget = QLabel("Начальная точка (x, y):")
        input_layout.addWidget(self.start_point_label_widget, 0, 0)
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
        
        # конечная точка (зависит от системы координат)
        input_layout.addWidget(QLabel("Конечная точка:"), 1, 0)
        
        # декартовы координаты
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
        
        # полярные координаты
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
        
        # Группы для окружности
        # Центр и радиус
        self.circle_center_radius_group = QWidget()
        circle_cr_layout = QHBoxLayout()
        circle_cr_layout.addWidget(QLabel("Радиус:"))
        self.circle_radius_spin = QDoubleSpinBox()
        self.circle_radius_spin.setRange(0, 1000)
        self.circle_radius_spin.setDecimals(2)
        self.circle_radius_spin.setSingleStep(10)
        self.circle_radius_spin.setValue(50)
        self.circle_radius_spin.valueChanged.connect(self.on_circle_coordinates_changed)
        circle_cr_layout.addWidget(self.circle_radius_spin)
        self.circle_center_radius_group.setLayout(circle_cr_layout)
        self.circle_center_radius_group.hide()
        
        # Центр и диаметр
        self.circle_center_diameter_group = QWidget()
        circle_cd_layout = QHBoxLayout()
        circle_cd_layout.addWidget(QLabel("Диаметр:"))
        self.circle_diameter_spin = QDoubleSpinBox()
        self.circle_diameter_spin.setRange(0, 1000)
        self.circle_diameter_spin.setDecimals(2)
        self.circle_diameter_spin.setSingleStep(10)
        self.circle_diameter_spin.setValue(100)
        self.circle_diameter_spin.valueChanged.connect(self.on_circle_coordinates_changed)
        circle_cd_layout.addWidget(self.circle_diameter_spin)
        self.circle_center_diameter_group.setLayout(circle_cd_layout)
        self.circle_center_diameter_group.hide()
        
        # Две точки
        self.circle_two_points_group = QWidget()
        circle_2p_layout = QGridLayout()
        circle_2p_layout.addWidget(QLabel("Вторая точка:"), 0, 0)
        self.circle_point2_x_spin = QDoubleSpinBox()
        self.circle_point2_x_spin.setRange(-1000, 1000)
        self.circle_point2_x_spin.setDecimals(2)
        self.circle_point2_x_spin.setSingleStep(10)
        self.circle_point2_x_spin.valueChanged.connect(self.on_circle_coordinates_changed)
        self.circle_point2_y_spin = QDoubleSpinBox()
        self.circle_point2_y_spin.setRange(-1000, 1000)
        self.circle_point2_y_spin.setDecimals(2)
        self.circle_point2_y_spin.setSingleStep(10)
        self.circle_point2_y_spin.valueChanged.connect(self.on_circle_coordinates_changed)
        circle_2p_layout.addWidget(QLabel("x:"), 0, 1)
        circle_2p_layout.addWidget(self.circle_point2_x_spin, 0, 2)
        circle_2p_layout.addWidget(QLabel("y:"), 0, 3)
        circle_2p_layout.addWidget(self.circle_point2_y_spin, 0, 4)
        self.circle_two_points_group.setLayout(circle_2p_layout)
        self.circle_two_points_group.hide()
        
        # Три точки
        self.circle_three_points_group = QWidget()
        circle_3p_layout = QGridLayout()
        circle_3p_layout.addWidget(QLabel("Вторая точка:"), 0, 0)
        self.circle_point2_x_spin_3p = QDoubleSpinBox()
        self.circle_point2_x_spin_3p.setRange(-1000, 1000)
        self.circle_point2_x_spin_3p.setDecimals(2)
        self.circle_point2_x_spin_3p.setSingleStep(10)
        self.circle_point2_x_spin_3p.valueChanged.connect(self.on_circle_coordinates_changed)
        self.circle_point2_y_spin_3p = QDoubleSpinBox()
        self.circle_point2_y_spin_3p.setRange(-1000, 1000)
        self.circle_point2_y_spin_3p.setDecimals(2)
        self.circle_point2_y_spin_3p.setSingleStep(10)
        self.circle_point2_y_spin_3p.valueChanged.connect(self.on_circle_coordinates_changed)
        circle_3p_layout.addWidget(QLabel("x:"), 0, 1)
        circle_3p_layout.addWidget(self.circle_point2_x_spin_3p, 0, 2)
        circle_3p_layout.addWidget(QLabel("y:"), 0, 3)
        circle_3p_layout.addWidget(self.circle_point2_y_spin_3p, 0, 4)
        
        circle_3p_layout.addWidget(QLabel("Третья точка:"), 1, 0)
        self.circle_point3_x_spin = QDoubleSpinBox()
        self.circle_point3_x_spin.setRange(-1000, 1000)
        self.circle_point3_x_spin.setDecimals(2)
        self.circle_point3_x_spin.setSingleStep(10)
        self.circle_point3_x_spin.valueChanged.connect(self.on_circle_coordinates_changed)
        self.circle_point3_y_spin = QDoubleSpinBox()
        self.circle_point3_y_spin.setRange(-1000, 1000)
        self.circle_point3_y_spin.setDecimals(2)
        self.circle_point3_y_spin.setSingleStep(10)
        self.circle_point3_y_spin.valueChanged.connect(self.on_circle_coordinates_changed)
        circle_3p_layout.addWidget(QLabel("x:"), 1, 1)
        circle_3p_layout.addWidget(self.circle_point3_x_spin, 1, 2)
        circle_3p_layout.addWidget(QLabel("y:"), 1, 3)
        circle_3p_layout.addWidget(self.circle_point3_y_spin, 1, 4)
        self.circle_three_points_group.setLayout(circle_3p_layout)
        self.circle_three_points_group.hide()
        
        # Группы для дуги
        # Три точки
        self.arc_three_points_group = QWidget()
        arc_3p_layout = QGridLayout()
        arc_3p_layout.addWidget(QLabel("Вторая точка:"), 0, 0)
        self.arc_point2_x_spin = QDoubleSpinBox()
        self.arc_point2_x_spin.setRange(-1000, 1000)
        self.arc_point2_x_spin.setDecimals(2)
        self.arc_point2_x_spin.setSingleStep(10)
        self.arc_point2_x_spin.valueChanged.connect(self.on_arc_coordinates_changed)
        self.arc_point2_y_spin = QDoubleSpinBox()
        self.arc_point2_y_spin.setRange(-1000, 1000)
        self.arc_point2_y_spin.setDecimals(2)
        self.arc_point2_y_spin.setSingleStep(10)
        self.arc_point2_y_spin.valueChanged.connect(self.on_arc_coordinates_changed)
        arc_3p_layout.addWidget(QLabel("x:"), 0, 1)
        arc_3p_layout.addWidget(self.arc_point2_x_spin, 0, 2)
        arc_3p_layout.addWidget(QLabel("y:"), 0, 3)
        arc_3p_layout.addWidget(self.arc_point2_y_spin, 0, 4)
        
        arc_3p_layout.addWidget(QLabel("Третья точка:"), 1, 0)
        self.arc_point3_x_spin = QDoubleSpinBox()
        self.arc_point3_x_spin.setRange(-1000, 1000)
        self.arc_point3_x_spin.setDecimals(2)
        self.arc_point3_x_spin.setSingleStep(10)
        self.arc_point3_x_spin.valueChanged.connect(self.on_arc_coordinates_changed)
        self.arc_point3_y_spin = QDoubleSpinBox()
        self.arc_point3_y_spin.setRange(-1000, 1000)
        self.arc_point3_y_spin.setDecimals(2)
        self.arc_point3_y_spin.setSingleStep(10)
        self.arc_point3_y_spin.valueChanged.connect(self.on_arc_coordinates_changed)
        arc_3p_layout.addWidget(QLabel("x:"), 1, 1)
        arc_3p_layout.addWidget(self.arc_point3_x_spin, 1, 2)
        arc_3p_layout.addWidget(QLabel("y:"), 1, 3)
        arc_3p_layout.addWidget(self.arc_point3_y_spin, 1, 4)
        self.arc_three_points_group.setLayout(arc_3p_layout)
        self.arc_three_points_group.hide()
        
        # Центр, начальный угол, конечный угол
        self.arc_center_angles_group = QWidget()
        arc_ca_layout = QGridLayout()
        arc_ca_layout.addWidget(QLabel("Радиус:"), 0, 0)
        self.arc_radius_spin = QDoubleSpinBox()
        self.arc_radius_spin.setRange(0, 1000)
        self.arc_radius_spin.setDecimals(2)
        self.arc_radius_spin.setSingleStep(10)
        self.arc_radius_spin.setValue(50)
        self.arc_radius_spin.valueChanged.connect(self.on_arc_coordinates_changed)
        arc_ca_layout.addWidget(self.arc_radius_spin, 0, 1, 1, 4)
        
        arc_ca_layout.addWidget(QLabel("Начальный угол:"), 1, 0)
        self.arc_start_angle_spin = QDoubleSpinBox()
        self.arc_start_angle_spin.setRange(-360, 360)
        self.arc_start_angle_spin.setDecimals(2)
        self.arc_start_angle_spin.setSingleStep(15)
        self.arc_start_angle_spin.setValue(0)
        self.arc_start_angle_spin.valueChanged.connect(self.on_arc_coordinates_changed)
        arc_ca_layout.addWidget(self.arc_start_angle_spin, 1, 1, 1, 2)
        arc_ca_layout.addWidget(QLabel("°"), 1, 3)
        
        arc_ca_layout.addWidget(QLabel("Конечный угол:"), 2, 0)
        self.arc_end_angle_spin = QDoubleSpinBox()
        self.arc_end_angle_spin.setRange(-360, 360)
        self.arc_end_angle_spin.setDecimals(2)
        self.arc_end_angle_spin.setSingleStep(15)
        self.arc_end_angle_spin.setValue(90)
        self.arc_end_angle_spin.valueChanged.connect(self.on_arc_coordinates_changed)
        arc_ca_layout.addWidget(self.arc_end_angle_spin, 2, 1, 1, 2)
        arc_ca_layout.addWidget(QLabel("°"), 2, 3)
        self.arc_center_angles_group.setLayout(arc_ca_layout)
        self.arc_center_angles_group.hide()
        
        input_layout.addWidget(self.cartesian_group, 1, 1, 1, 4)
        input_layout.addWidget(self.polar_group, 1, 1, 1, 4)
        input_layout.addWidget(self.circle_center_radius_group, 1, 1, 1, 4)
        input_layout.addWidget(self.circle_center_diameter_group, 1, 1, 1, 4)
        input_layout.addWidget(self.circle_two_points_group, 1, 1, 1, 4)
        input_layout.addWidget(self.circle_three_points_group, 1, 1, 2, 4)
        input_layout.addWidget(self.arc_three_points_group, 1, 1, 2, 4)
        input_layout.addWidget(self.arc_center_angles_group, 1, 1, 3, 4)
        
        # Группы для прямоугольника
        # Две противоположные точки (используем существующие поля end_x_spin и end_y_spin)
        # Одна точка, ширина и высота
        self.rectangle_point_size_group = QWidget()
        rect_ps_layout = QGridLayout()
        rect_ps_layout.addWidget(QLabel("Ширина:"), 0, 0)
        self.rectangle_width_spin = QDoubleSpinBox()
        self.rectangle_width_spin.setRange(0, 1000)
        self.rectangle_width_spin.setDecimals(2)
        self.rectangle_width_spin.setSingleStep(10)
        self.rectangle_width_spin.setValue(100)
        self.rectangle_width_spin.valueChanged.connect(self.on_rectangle_coordinates_changed)
        rect_ps_layout.addWidget(self.rectangle_width_spin, 0, 1, 1, 4)
        
        rect_ps_layout.addWidget(QLabel("Высота:"), 1, 0)
        self.rectangle_height_spin = QDoubleSpinBox()
        self.rectangle_height_spin.setRange(0, 1000)
        self.rectangle_height_spin.setDecimals(2)
        self.rectangle_height_spin.setSingleStep(10)
        self.rectangle_height_spin.setValue(100)
        self.rectangle_height_spin.valueChanged.connect(self.on_rectangle_coordinates_changed)
        rect_ps_layout.addWidget(self.rectangle_height_spin, 1, 1, 1, 4)
        self.rectangle_point_size_group.setLayout(rect_ps_layout)
        self.rectangle_point_size_group.hide()
        
        # Центр, ширина и высота
        self.rectangle_center_size_group = QWidget()
        rect_cs_layout = QGridLayout()
        rect_cs_layout.addWidget(QLabel("Ширина:"), 0, 0)
        self.rectangle_center_width_spin = QDoubleSpinBox()
        self.rectangle_center_width_spin.setRange(0, 1000)
        self.rectangle_center_width_spin.setDecimals(2)
        self.rectangle_center_width_spin.setSingleStep(10)
        self.rectangle_center_width_spin.setValue(100)
        self.rectangle_center_width_spin.valueChanged.connect(self.on_rectangle_coordinates_changed)
        rect_cs_layout.addWidget(self.rectangle_center_width_spin, 0, 1, 1, 4)
        
        rect_cs_layout.addWidget(QLabel("Высота:"), 1, 0)
        self.rectangle_center_height_spin = QDoubleSpinBox()
        self.rectangle_center_height_spin.setRange(0, 1000)
        self.rectangle_center_height_spin.setDecimals(2)
        self.rectangle_center_height_spin.setSingleStep(10)
        self.rectangle_center_height_spin.setValue(100)
        self.rectangle_center_height_spin.valueChanged.connect(self.on_rectangle_coordinates_changed)
        rect_cs_layout.addWidget(self.rectangle_center_height_spin, 1, 1, 1, 4)
        self.rectangle_center_size_group.setLayout(rect_cs_layout)
        self.rectangle_center_size_group.hide()
        
        # С фасками/скруглениями
        self.rectangle_fillets_group = QWidget()
        rect_fill_layout = QGridLayout()
        rect_fill_layout.addWidget(QLabel("Вторая точка:"), 0, 0)
        self.rectangle_fillet_point2_x_spin = QDoubleSpinBox()
        self.rectangle_fillet_point2_x_spin.setRange(-1000, 1000)
        self.rectangle_fillet_point2_x_spin.setDecimals(2)
        self.rectangle_fillet_point2_x_spin.setSingleStep(10)
        self.rectangle_fillet_point2_x_spin.valueChanged.connect(self.on_rectangle_coordinates_changed)
        self.rectangle_fillet_point2_y_spin = QDoubleSpinBox()
        self.rectangle_fillet_point2_y_spin.setRange(-1000, 1000)
        self.rectangle_fillet_point2_y_spin.setDecimals(2)
        self.rectangle_fillet_point2_y_spin.setSingleStep(10)
        self.rectangle_fillet_point2_y_spin.valueChanged.connect(self.on_rectangle_coordinates_changed)
        rect_fill_layout.addWidget(QLabel("x:"), 0, 1)
        rect_fill_layout.addWidget(self.rectangle_fillet_point2_x_spin, 0, 2)
        rect_fill_layout.addWidget(QLabel("y:"), 0, 3)
        rect_fill_layout.addWidget(self.rectangle_fillet_point2_y_spin, 0, 4)
        
        rect_fill_layout.addWidget(QLabel("Радиус скругления:"), 1, 0)
        self.rectangle_fillet_radius_spin = QDoubleSpinBox()
        self.rectangle_fillet_radius_spin.setRange(0, 1000)
        self.rectangle_fillet_radius_spin.setDecimals(2)
        self.rectangle_fillet_radius_spin.setSingleStep(5)
        self.rectangle_fillet_radius_spin.setValue(10)
        self.rectangle_fillet_radius_spin.valueChanged.connect(self.on_rectangle_coordinates_changed)
        rect_fill_layout.addWidget(self.rectangle_fillet_radius_spin, 1, 1, 1, 4)
        self.rectangle_fillets_group.setLayout(rect_fill_layout)
        self.rectangle_fillets_group.hide()
        
        input_layout.addWidget(self.circle_three_points_group, 1, 1, 2, 4)
        input_layout.addWidget(self.arc_three_points_group, 1, 1, 2, 4)
        input_layout.addWidget(self.arc_center_angles_group, 1, 1, 3, 4)
        input_layout.addWidget(self.rectangle_point_size_group, 1, 1, 2, 4)
        input_layout.addWidget(self.rectangle_center_size_group, 1, 1, 2, 4)
        input_layout.addWidget(self.rectangle_fillets_group, 1, 1, 2, 4)
        
        # кнопка применения координат
        self.apply_coords_btn = QPushButton("Применить координаты")
        self.apply_coords_btn.clicked.connect(self.apply_coordinates)
        input_layout.addWidget(self.apply_coords_btn, 4, 0, 1, 5)
        
        input_group.setLayout(input_layout)
        left_panel.addWidget(input_group)
        
        # панель настроек
        settings_group = QGroupBox("Настройки")
        settings_layout = QVBoxLayout()
        
        # система координат
        coord_layout = QHBoxLayout()
        coord_layout.addWidget(QLabel("Система координат:"))
        self.coord_combo = QComboBox()
        self.coord_combo.addItems(["Декартова", "Полярная"])
        self.coord_combo.currentTextChanged.connect(self.change_coordinate_system)
        coord_layout.addWidget(self.coord_combo)
        settings_layout.addLayout(coord_layout)
        
        # единицы измерения углов
        angle_layout = QHBoxLayout()
        angle_layout.addWidget(QLabel("Единицы углов:"))
        self.angle_combo = QComboBox()
        self.angle_combo.addItems(["Градусы", "Радианы"])
        self.angle_combo.currentTextChanged.connect(self.change_angle_units)
        angle_layout.addWidget(self.angle_combo)
        settings_layout.addLayout(angle_layout)
        
        # шаг сетки (в миллиметрах)
        grid_layout = QHBoxLayout()
        grid_layout.addWidget(QLabel("Шаг сетки:"))
        self.grid_spin = QDoubleSpinBox()
        self.grid_spin.setRange(0.1, 100.0)
        self.grid_spin.setDecimals(1)
        self.grid_spin.setSingleStep(1.0)
        self.grid_spin.setValue(20.0)  # 20 мм по умолчанию
        self.grid_spin.valueChanged.connect(self.change_grid_step)
        grid_layout.addWidget(self.grid_spin)
        settings_layout.addLayout(grid_layout)
        
        # цвета
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
        
        # информация о количестве отрезков
        self.lines_count_label = QLabel("Отрезков на экране: 0")
        left_panel.addWidget(self.lines_count_label)
        
        # Добавляем панели стилей
        # Панель свойств объекта
        self.object_properties_panel = ObjectPropertiesPanel(self.style_manager)
        self.object_properties_panel.style_changed.connect(self.on_object_style_changed)
        # Устанавливаем ссылку на canvas для доступа к линиям
        self.object_properties_panel.canvas = self.canvas
        # Подключаем сигнал изменения выделения
        self.canvas.selection_changed.connect(self.on_selection_changed)
        # Скрываем панель по умолчанию (пока нет выделенных объектов)
        self.object_properties_panel.hide()
        left_panel.addWidget(self.object_properties_panel)
        
        # Панель управления стилями
        self.style_management_panel = StyleManagementPanel(self.style_manager)
        left_panel.addWidget(self.style_management_panel)
        
        left_panel.addStretch()
        
        # правая часть с рабочей областью и информацией
        right_widget = QWidget()
        right_panel = QVBoxLayout(right_widget)
        
        # рабочая область
        right_panel.addWidget(self.canvas)
        
        # информационная панель
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
        
        # Добавляем виджеты в splitter
        main_splitter.addWidget(scroll_area)
        main_splitter.addWidget(right_widget)
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 3)
        
        main_layout.addWidget(main_splitter)
        
        # инициализация значений
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
        
        # подключаем сигналы от canvas для обновления статусбара
        self.canvas.view_changed.connect(self.update_statusbar)
        # подключаем сигнал завершения рисования отрезка для обновления информации
        self.canvas.line_finished.connect(self.update_info)
        # подключаем сигнал начала рисования прямоугольника для установки размеров
        self.canvas.rectangle_drawing_started.connect(self.update_rectangle_on_drawing_start)
        self.update_statusbar()
    
    def create_context_menu(self, position):
        # контекстное меню для рабочей области
        menu = QMenu(self)
        
        # команды навигации
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
        
        # инструменты
        pan_action = menu.addAction("Панорамирование")
        pan_action.setCheckable(True)
        pan_action.setChecked(self.pan_action.isChecked())
        pan_action.triggered.connect(self.pan_action.toggle)
        
        menu.exec_(self.mapToGlobal(position))
    
    def rotate_left(self):
        # поворот налево
        self.canvas.rotate_left(15)
        
    def rotate_right(self):
        # поворот направо
        self.canvas.rotate_right(15)
    
    def create_menus(self):
        menubar = self.menuBar()
        
        # меню "Вид"
        view_menu = menubar.addMenu("Вид")
        
        # действия для навигации
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
        # панель инструментов навигации
        toolbar = QToolBar("Навигация")
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)
        
        # инструмент "Рука" для панорамирования
        self.pan_action = QAction("🖑", self)
        self.pan_action.setCheckable(True)
        self.pan_action.setToolTip("Панорамирование (Пробел)")
        self.pan_action.setShortcut(Qt.Key_Space)
        self.pan_action.toggled.connect(self.canvas.set_pan_mode)
        toolbar.addAction(self.pan_action)
        
        toolbar.addSeparator()
        
        # увеличение
        zoom_in_action = QAction("🞢", self)
        zoom_in_action.setToolTip("Увеличить")
        zoom_in_action.triggered.connect(self.canvas.zoom_in)
        toolbar.addAction(zoom_in_action)
        
        # уменьшение
        zoom_out_action = QAction("‒", self)
        zoom_out_action.setToolTip("Уменьшить")
        zoom_out_action.triggered.connect(self.canvas.zoom_out)
        toolbar.addAction(zoom_out_action)
        
        # показать всё сохраняя поворот
        show_all_action = QAction("ⓘ", self)
        show_all_action.setToolTip("Показать всё (сохранить поворот)")
        show_all_action.triggered.connect(self.canvas.show_all)
        toolbar.addAction(show_all_action)
        
        toolbar.addSeparator()
        
        # поворот налево
        rotate_left_action = QAction("↶", self)
        rotate_left_action.setToolTip("Повернуть налево")
        rotate_left_action.triggered.connect(self.rotate_left)
        toolbar.addAction(rotate_left_action)
        
        # поворот направо
        rotate_right_action = QAction("↷", self)
        rotate_right_action.setToolTip("Повернуть направо")
        rotate_right_action.triggered.connect(self.rotate_right)
        toolbar.addAction(rotate_right_action)
        
        # сброс вида
        reset_view_action = QAction("⟲", self)
        reset_view_action.setToolTip("Сбросить вид")
        reset_view_action.triggered.connect(self.canvas.reset_view)
        toolbar.addAction(reset_view_action)
    
    def create_style_toolbar(self):
        """Создает панель инструментов для стилей линий"""
        style_toolbar = QToolBar("Стили линий")
        style_toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(style_toolbar)
        
        # Выпадающий список текущего стиля
        style_label = QLabel("Текущий стиль:")
        style_toolbar.addWidget(style_label)
        
        self.current_style_combo = StyleComboBox(self.style_manager)
        self.current_style_combo.currentIndexChanged.connect(self.on_current_style_changed)
        style_toolbar.addWidget(self.current_style_combo)
        
        style_toolbar.addSeparator()
        
        # Кнопки быстрого доступа к популярным стилям
        popular_styles = ["Сплошная основная", "Сплошная тонкая", "Штриховая", "Штрихпунктирная тонкая"]
        
        for style_name in popular_styles:
            style = self.style_manager.get_style(style_name)
            if style:
                action = QAction(style_name, self)
                action.setToolTip(f"Установить стиль: {style_name}")
                action.triggered.connect(lambda checked, name=style_name: self.set_current_style(name))
                style_toolbar.addAction(action)
    
    def on_current_style_changed(self):
        """Обработчик изменения текущего стиля"""
        style = self.current_style_combo.get_current_style()
        if style:
            self.style_manager.set_current_style(style.name)
    
    def set_current_style(self, style_name):
        """Устанавливает текущий стиль"""
        self.style_manager.set_current_style(style_name)
        index = self.current_style_combo.findText(style_name)
        if index >= 0:
            self.current_style_combo.setCurrentIndex(index)
    
    def on_object_style_changed(self, style):
        """Обработчик изменения стиля объекта"""
        # Обновляем отрисовку
        self.canvas.update()
    
    def on_selection_changed(self, selected_lines):
        """Обработчик изменения выделения"""
        # Обновляем выделенные объекты
        self.selected_objects = selected_lines
        # Показываем или скрываем панель свойств в зависимости от выделения
        if selected_lines:
            self.object_properties_panel.show()
            # Обновляем панель свойств
            self.object_properties_panel.set_selected_objects(selected_lines)
        else:
            self.object_properties_panel.hide()
    
    def create_statusbar(self):
        # строка состояния
        statusbar = QStatusBar()
        self.setStatusBar(statusbar)
        
        # координаты курсора
        self.cursor_coords_label = QLabel("Координаты: (0.00, 0.00)")
        statusbar.addPermanentWidget(self.cursor_coords_label)
        
        # масштаб
        self.scale_label = QLabel("Масштаб: 100%")
        statusbar.addPermanentWidget(self.scale_label)
        
        # угол поворота
        self.rotation_label = QLabel("Поворот: 0°")
        statusbar.addPermanentWidget(self.rotation_label)
        
        # активный инструмент
        self.tool_label = QLabel("Инструмент: Рисование")
        statusbar.addWidget(self.tool_label)
    
    def update_statusbar(self):
        # информация в строке состояния
        # координаты курсора (если доступны)
        cursor_pos = self.canvas.get_cursor_world_coords()
        if cursor_pos:
            self.cursor_coords_label.setText(
                f"Координаты: ({cursor_pos.x():.2f}, {cursor_pos.y():.2f})"
            )

        # масштаб
        scale = self.canvas.get_scale() * 100
        self.scale_label.setText(f"Масштаб: {scale:.1f}%")

        # угол поворота
        rotation = self.canvas.get_rotation()
        self.rotation_label.setText(f"Поворот: {rotation:.1f}°")

        # активный инструмент
        if self.pan_action.isChecked():
            self.tool_label.setText("Инструмент: Панорамирование")
        else:
            self.tool_label.setText("Инструмент: Рисование")

    
    def start_new_line(self):
        # начинает новый отрезок
        # если уже рисуем отрезок, сохраняем его
        if self.canvas.is_drawing and self.canvas.current_line:
            # берем текущее положение мыши как конечную точку
            if self.canvas.current_point:
                self.canvas.current_line.end_point = self.canvas.current_point
                self.canvas.lines.append(self.canvas.current_line)
        
        # начинаем новый отрезок
        self.canvas.start_new_line()
        
        # сбрасываем значения в полях ввода для нового отрезка
        self.start_x_spin.blockSignals(True)
        self.start_y_spin.blockSignals(True)
        self.end_x_spin.blockSignals(True)
        self.end_y_spin.blockSignals(True)
        self.radius_spin.blockSignals(True)
        self.angle_spin.blockSignals(True)
        
        # устанавливаем начальную точку в текущее положение курсора, если доступно
        cursor_pos = self.canvas.get_cursor_world_coords()
        if cursor_pos:
            self.start_x_spin.setValue(cursor_pos.x())
            self.start_y_spin.setValue(cursor_pos.y())
        else:
            self.start_x_spin.setValue(0)
            self.start_y_spin.setValue(0)
        
        # сбрасываем конечные точки
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
        # завершает текущий отрезок и сохраняет его
        if self.canvas.is_drawing and self.canvas.current_line:
            self.canvas.lines.append(self.canvas.current_line)
            self.canvas.current_line = None
            self.canvas.is_drawing = False
            self.canvas.current_point = None
            self.canvas.update()
            self.update_info()
    
    def delete_last_line(self):
        # удаление последний отрезок
        self.canvas.delete_last_line()
        self.update_info()
    
    def delete_all_lines(self):
        #  удаляет все отрезки
        self.canvas.delete_all_lines()
        self.update_info()
    
    def apply_coordinates(self):
        # координаты из полей ввода и фикс объекта
        start_point = QPointF(self.start_x_spin.value(), self.start_y_spin.value())
        
        # Проверяем, создаем ли мы окружность, дугу или прямоугольник
        if self.canvas.primitive_type == 'circle':
            self.apply_circle_coordinates(start_point)
            return
        elif self.canvas.primitive_type == 'arc':
            self.apply_arc_coordinates(start_point)
            return
        elif self.canvas.primitive_type == 'rectangle':
            self.apply_rectangle_coordinates(start_point)
            return
        
        # Для остальных примитивов (отрезок и т.д.)
        if self.coordinate_system == "cartesian":
            end_point = QPointF(self.end_x_spin.value(), self.end_y_spin.value())
        else:
            # преобразуем полярные координаты в декартовы ОТНОСИТЕЛЬНО НАЧАЛЬНОЙ ТОЧКИ
            radius = self.radius_spin.value()
            angle = self.angle_spin.value()
            
            if self.angle_units == "degrees":
                angle_rad = math.radians(angle)
            else:
                angle_rad = angle
            
            # вычисляем смещение от начальной точки
            delta_x = radius * math.cos(angle_rad)
            delta_y = radius * math.sin(angle_rad)
            
            # конечная точка = начальная + смещение
            end_x = start_point.x() + delta_x
            end_y = start_point.y() + delta_y
            end_point = QPointF(end_x, end_y)
        
        # фиксируем отрезок (apply=True)
        self.canvas.set_points_from_input(start_point, end_point, apply=True)
    
    def apply_circle_coordinates(self, center_point):
        """Применяет координаты для создания окружности"""
        from widgets.primitives import Circle
        
        # Отменяем текущее рисование, если оно есть
        if self.canvas.scene.is_drawing():
            self.canvas.scene.cancel_drawing()
        
        method_name = self.circle_method_combo.currentText()
        style = None
        if self.style_manager:
            style = self.style_manager.get_current_style()
        
        if method_name == "Центр и радиус":
            radius = self.circle_radius_spin.value()
            circle = Circle(center_point, radius, style=style, 
                          color=self.canvas.line_color, width=self.canvas.line_width)
            self.canvas.scene.add_object(circle)
        elif method_name == "Центр и диаметр":
            diameter = self.circle_diameter_spin.value()
            radius = diameter / 2.0
            circle = Circle(center_point, radius, style=style,
                          color=self.canvas.line_color, width=self.canvas.line_width)
            self.canvas.scene.add_object(circle)
        elif method_name == "Две точки":
            point2 = QPointF(self.circle_point2_x_spin.value(), self.circle_point2_y_spin.value())
            import math
            dx = point2.x() - center_point.x()
            dy = point2.y() - center_point.y()
            radius = math.sqrt(dx*dx + dy*dy) / 2.0
            center_x = (center_point.x() + point2.x()) / 2.0
            center_y = (center_point.y() + point2.y()) / 2.0
            center = QPointF(center_x, center_y)
            circle = Circle(center, radius, style=style,
                          color=self.canvas.line_color, width=self.canvas.line_width)
            self.canvas.scene.add_object(circle)
        elif method_name == "Три точки на окружности":
            point2 = QPointF(self.circle_point2_x_spin_3p.value(), self.circle_point2_y_spin_3p.value())
            point3 = QPointF(self.circle_point3_x_spin.value(), self.circle_point3_y_spin.value())
            # Используем метод из Scene для вычисления окружности по трем точкам
            import math
            # Вычисляем центр и радиус окружности по трем точкам
            x1, y1 = center_point.x(), center_point.y()
            x2, y2 = point2.x(), point2.y()
            x3, y3 = point3.x(), point3.y()
            
            A = x1 * (y2 - y3) - y1 * (x2 - x3) + (x2 * y3 - x3 * y2)
            
            if abs(A) < 1e-10:
                # Точки коллинеарны
                return
            
            B = (x1*x1 + y1*y1) * (y3 - y2) + (x2*x2 + y2*y2) * (y1 - y3) + (x3*x3 + y3*y3) * (y2 - y1)
            C = (x1*x1 + y1*y1) * (x2 - x3) + (x2*x2 + y2*y2) * (x3 - x1) + (x3*x3 + y3*y3) * (x1 - x2)
            
            center_x = -B / (2 * A)
            center_y = -C / (2 * A)
            center = QPointF(center_x, center_y)
            
            dx = x1 - center_x
            dy = y1 - center_y
            radius = math.sqrt(dx*dx + dy*dy)
            if center and radius > 0:
                circle = Circle(center, radius, style=style,
                              color=self.canvas.line_color, width=self.canvas.line_width)
                self.canvas.scene.add_object(circle)
        
        self.canvas.update()
        # Автоматически показываем все объекты с сохранением поворота
        self.canvas.show_all_preserve_rotation()
        
        # Убеждаемся, что нет активного рисования
        if self.canvas.scene.is_drawing():
            self.canvas.scene.cancel_drawing()
        
        # Сбрасываем значения для следующей окружности
        self.start_x_spin.blockSignals(True)
        self.start_y_spin.blockSignals(True)
        self.start_x_spin.setValue(0)
        self.start_y_spin.setValue(0)
        self.start_x_spin.blockSignals(False)
        self.start_y_spin.blockSignals(False)
        
        # Сбрасываем значения в зависимости от метода
        method_name = self.circle_method_combo.currentText()
        if method_name == "Центр и радиус":
            self.circle_radius_spin.blockSignals(True)
            self.circle_radius_spin.setValue(50)
            self.circle_radius_spin.blockSignals(False)
        elif method_name == "Центр и диаметр":
            self.circle_diameter_spin.blockSignals(True)
            self.circle_diameter_spin.setValue(100)
            self.circle_diameter_spin.blockSignals(False)
        elif method_name == "Две точки":
            self.circle_point2_x_spin.blockSignals(True)
            self.circle_point2_y_spin.blockSignals(True)
            self.circle_point2_x_spin.setValue(100)
            self.circle_point2_y_spin.setValue(0)
            self.circle_point2_x_spin.blockSignals(False)
            self.circle_point2_y_spin.blockSignals(False)
        elif method_name == "Три точки на окружности":
            self.circle_point2_x_spin_3p.blockSignals(True)
            self.circle_point2_y_spin_3p.blockSignals(True)
            self.circle_point3_x_spin.blockSignals(True)
            self.circle_point3_y_spin.blockSignals(True)
            self.circle_point2_x_spin_3p.setValue(100)
            self.circle_point2_y_spin_3p.setValue(0)
            self.circle_point3_x_spin.setValue(0)
            self.circle_point3_y_spin.setValue(100)
            self.circle_point2_x_spin_3p.blockSignals(False)
            self.circle_point2_y_spin_3p.blockSignals(False)
            self.circle_point3_x_spin.blockSignals(False)
            self.circle_point3_y_spin.blockSignals(False)
        
        self.update_info()
    
    def apply_arc_coordinates(self, start_point):
        """Применяет координаты для создания дуги"""
        from widgets.primitives import Arc
        
        # Отменяем текущее рисование, если оно есть
        if self.canvas.scene.is_drawing():
            self.canvas.scene.cancel_drawing()
        
        method_name = self.arc_method_combo.currentText()
        style = None
        if self.style_manager:
            style = self.style_manager.get_current_style()
        
        if method_name == "Три точки (начало, вторая точка, конец)":
            point2 = QPointF(self.arc_point2_x_spin.value(), self.arc_point2_y_spin.value())
            point3 = QPointF(self.arc_point3_x_spin.value(), self.arc_point3_y_spin.value())
            # Вычисляем параметры дуги по трем точкам
            result = self.canvas.scene._calculate_ellipse_arc_from_three_points(
                start_point, point2, point3
            )
            if len(result) == 6 and result[0] is not None:
                center, radius_x, radius_y, start_angle, end_angle, rotation_angle = result
                if radius_x > 0 and radius_y > 0:
                    arc = Arc(center, radius_x, radius_y, start_angle, end_angle, style=style,
                            color=self.canvas.line_color, width=self.canvas.line_width, rotation_angle=rotation_angle)
                    self.canvas.scene.add_object(arc)
        elif method_name == "Центр, начальный угол, конечный угол":
            radius = self.arc_radius_spin.value()
            start_angle = self.arc_start_angle_spin.value()
            end_angle = self.arc_end_angle_spin.value()
            arc = Arc(start_point, radius, radius, start_angle, end_angle, style=style,
                     color=self.canvas.line_color, width=self.canvas.line_width, rotation_angle=0.0)
            self.canvas.scene.add_object(arc)
        
        self.canvas.update()
        # Автоматически показываем все объекты с сохранением поворота
        self.canvas.show_all_preserve_rotation()
        
        # Убеждаемся, что нет активного рисования
        if self.canvas.scene.is_drawing():
            self.canvas.scene.cancel_drawing()
        
        # Сбрасываем значения для следующей дуги
        self.start_x_spin.blockSignals(True)
        self.start_y_spin.blockSignals(True)
        self.start_x_spin.setValue(0)
        self.start_y_spin.setValue(0)
        self.start_x_spin.blockSignals(False)
        self.start_y_spin.blockSignals(False)
        
        # Сбрасываем значения в зависимости от метода
        if method_name == "Три точки (начало, вторая точка, конец)":
            self.arc_point2_x_spin.blockSignals(True)
            self.arc_point2_y_spin.blockSignals(True)
            self.arc_point3_x_spin.blockSignals(True)
            self.arc_point3_y_spin.blockSignals(True)
            self.arc_point2_x_spin.setValue(100)
            self.arc_point2_y_spin.setValue(0)
            self.arc_point3_x_spin.setValue(0)
            self.arc_point3_y_spin.setValue(100)
            self.arc_point2_x_spin.blockSignals(False)
            self.arc_point2_y_spin.blockSignals(False)
            self.arc_point3_x_spin.blockSignals(False)
            self.arc_point3_y_spin.blockSignals(False)
        elif method_name == "Центр, начальный угол, конечный угол":
            self.arc_radius_spin.blockSignals(True)
            self.arc_start_angle_spin.blockSignals(True)
            self.arc_end_angle_spin.blockSignals(True)
            self.arc_radius_spin.setValue(50)
            self.arc_start_angle_spin.setValue(0)
            self.arc_end_angle_spin.setValue(90)
            self.arc_radius_spin.blockSignals(False)
            self.arc_start_angle_spin.blockSignals(False)
            self.arc_end_angle_spin.blockSignals(False)
        
        self.update_info()
    
    def apply_rectangle_coordinates(self, start_point):
        """Применяет координаты для создания прямоугольника"""
        from widgets.primitives import Rectangle
        
        # Отменяем текущее рисование, если оно есть
        if self.canvas.scene.is_drawing():
            self.canvas.scene.cancel_drawing()
        
        method_name = self.rectangle_method_combo.currentText()
        style = None
        if self.style_manager:
            style = self.style_manager.get_current_style()
        
        if method_name == "Две противоположные точки":
            # Используем обычные поля для конечной точки
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
                delta_x = radius * math.cos(angle_rad)
                delta_y = radius * math.sin(angle_rad)
                end_point = QPointF(start_point.x() + delta_x, start_point.y() + delta_y)
            rectangle = Rectangle(start_point, end_point, style=style,
                                 color=self.canvas.line_color, width=self.canvas.line_width)
            self.canvas.scene.add_object(rectangle)
        elif method_name == "Одна точка, ширина и высота":
            width = self.rectangle_width_spin.value()
            height = self.rectangle_height_spin.value()
            end_point = QPointF(start_point.x() + width, start_point.y() + height)
            rectangle = Rectangle(start_point, end_point, style=style,
                                color=self.canvas.line_color, width=self.canvas.line_width)
            self.canvas.scene.add_object(rectangle)
        elif method_name == "Центр, ширина и высота":
            width = self.rectangle_center_width_spin.value()
            height = self.rectangle_center_height_spin.value()
            half_width = width / 2.0
            half_height = height / 2.0
            top_left = QPointF(start_point.x() - half_width, start_point.y() - half_height)
            bottom_right = QPointF(start_point.x() + half_width, start_point.y() + half_height)
            rectangle = Rectangle(top_left, bottom_right, style=style,
                                color=self.canvas.line_color, width=self.canvas.line_width)
            self.canvas.scene.add_object(rectangle)
        elif method_name == "С фасками/скруглениями при создании":
            # Используем обычные поля для конечной точки
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
                delta_x = radius * math.cos(angle_rad)
                delta_y = radius * math.sin(angle_rad)
                end_point = QPointF(start_point.x() + delta_x, start_point.y() + delta_y)
            fillet_radius = self.rectangle_fillet_radius_spin.value()
            rectangle = Rectangle(start_point, end_point, style=style,
                                color=self.canvas.line_color, width=self.canvas.line_width,
                                fillet_radius=fillet_radius)
            self.canvas.scene.add_object(rectangle)
        
        self.canvas.update()
        # Автоматически показываем все объекты с сохранением поворота
        self.canvas.show_all_preserve_rotation()
        
        # Убеждаемся, что нет активного рисования
        if self.canvas.scene.is_drawing():
            self.canvas.scene.cancel_drawing()
        
        # Сбрасываем значения для следующего прямоугольника
        self.start_x_spin.blockSignals(True)
        self.start_y_spin.blockSignals(True)
        self.start_x_spin.setValue(0)
        self.start_y_spin.setValue(0)
        self.start_x_spin.blockSignals(False)
        self.start_y_spin.blockSignals(False)
        
        # Сбрасываем значения в зависимости от метода
        if method_name == "Две противоположные точки":
            self.end_x_spin.blockSignals(True)
            self.end_y_spin.blockSignals(True)
            self.end_x_spin.setValue(100)
            self.end_y_spin.setValue(100)
            self.end_x_spin.blockSignals(False)
            self.end_y_spin.blockSignals(False)
        elif method_name == "Одна точка, ширина и высота":
            self.rectangle_width_spin.blockSignals(True)
            self.rectangle_height_spin.blockSignals(True)
            self.rectangle_width_spin.setValue(100)
            self.rectangle_height_spin.setValue(100)
            self.rectangle_width_spin.blockSignals(False)
            self.rectangle_height_spin.blockSignals(False)
        elif method_name == "Центр, ширина и высота":
            self.rectangle_center_width_spin.blockSignals(True)
            self.rectangle_center_height_spin.blockSignals(True)
            self.rectangle_center_width_spin.setValue(100)
            self.rectangle_center_height_spin.setValue(100)
            self.rectangle_center_width_spin.blockSignals(False)
            self.rectangle_center_height_spin.blockSignals(False)
        elif method_name == "С фасками/скруглениями при создании":
            self.end_x_spin.blockSignals(True)
            self.end_y_spin.blockSignals(True)
            self.rectangle_fillet_radius_spin.blockSignals(True)
            self.end_x_spin.setValue(100)
            self.end_y_spin.setValue(100)
            self.rectangle_fillet_radius_spin.setValue(10)
            self.end_x_spin.blockSignals(False)
            self.end_y_spin.blockSignals(False)
            self.rectangle_fillet_radius_spin.blockSignals(False)
        
        self.update_info()
    
    def change_coordinate_system(self, system):
        self.coordinate_system = "polar" if system == "Полярная" else "cartesian"
        self.update_input_fields()
        self.update_info()
    
    def change_primitive_type(self, primitive_name):
        """Изменяет тип создаваемого примитива"""
        primitive_map = {
            "Отрезок": "line",
            "Окружность": "circle",
            "Дуга": "arc",
            "Прямоугольник": "rectangle",
            "Эллипс": "ellipse"
        }
        primitive_type = primitive_map.get(primitive_name, "line")
        self.canvas.set_primitive_type(primitive_type)
        
        # Показываем/скрываем выбор метода создания окружности или дуги
        if primitive_type == "circle":
            self.circle_method_widget.show()
            self.arc_method_widget.hide()
            self.update_circle_input_fields()
        elif primitive_type == "arc":
            self.circle_method_widget.hide()
            self.arc_method_widget.show()
            self.rectangle_method_widget.hide()
            # Убеждаемся, что комбобокс имеет правильное значение
            if self.arc_method_combo.currentIndex() < 0:
                self.arc_method_combo.setCurrentIndex(0)
            # Явно вызываем обновление полей ввода
            self.change_arc_method(self.arc_method_combo.currentText())
        elif primitive_type == "rectangle":
            self.circle_method_widget.hide()
            self.arc_method_widget.hide()
            self.rectangle_method_widget.show()
            # Убеждаемся, что комбобокс имеет правильное значение
            if self.rectangle_method_combo.currentIndex() < 0:
                self.rectangle_method_combo.setCurrentIndex(0)
            # Явно вызываем обновление полей ввода
            self.change_rectangle_method(self.rectangle_method_combo.currentText())
        else:
            self.circle_method_widget.hide()
            self.arc_method_widget.hide()
            self.rectangle_method_widget.hide()
            # Восстанавливаем метку для не-окружности/дуги/прямоугольника
            self.start_point_label_widget.setText("Начальная точка (x, y):")
            # Скрываем все группы окружности
            self.circle_center_radius_group.hide()
            self.circle_center_diameter_group.hide()
            self.circle_two_points_group.hide()
            self.circle_three_points_group.hide()
            # Скрываем все группы дуги
            self.arc_three_points_group.hide()
            self.arc_center_angles_group.hide()
            # Скрываем все группы прямоугольника
            self.rectangle_point_size_group.hide()
            self.rectangle_center_size_group.hide()
            self.rectangle_fillets_group.hide()
            # Показываем обычные поля ввода
            if self.coordinate_system == "cartesian":
                self.cartesian_group.show()
                self.polar_group.hide()
            else:
                self.cartesian_group.hide()
                self.polar_group.show()
    
    def change_circle_method(self, method_name):
        """Изменяет метод создания окружности"""
        method_map = {
            "Центр и радиус": "center_radius",
            "Центр и диаметр": "center_diameter",
            "Две точки": "two_points",
            "Три точки на окружности": "three_points"
        }
        method = method_map.get(method_name, "center_radius")
        self.canvas.set_circle_creation_method(method)
        self.update_circle_input_fields()
    
    def change_arc_method(self, method_name):
        """Изменяет метод создания дуги"""
        method_map = {
            "Три точки (начало, вторая точка, конец)": "three_points",
            "Центр, начальный угол, конечный угол": "center_angles"
        }
        method = method_map.get(method_name, "three_points")
        self.canvas.set_arc_creation_method(method)
        self.update_arc_input_fields()
    
    def update_arc_input_fields(self):
        """Обновляет отображение полей ввода в зависимости от метода создания дуги"""
        # Обновляем метку для дуги
        self.start_point_label_widget.setText("Начальная точка (x, y):")
        
        # Скрываем все группы
        self.cartesian_group.hide()
        self.polar_group.hide()
        self.arc_three_points_group.hide()
        self.arc_center_angles_group.hide()
        
        # Показываем нужную группу
        method_name = self.arc_method_combo.currentText()
        if method_name == "Три точки (начало, вторая точка, конец)":
            self.arc_three_points_group.show()
        elif method_name == "Центр, начальный угол, конечный угол":
            self.start_point_label_widget.setText("Центр (x, y):")
            self.arc_center_angles_group.show()
    
    def on_arc_coordinates_changed(self):
        """Обработчик изменения координат дуги"""
        # Предпросмотр дуги при изменении параметров
        pass
    
    def change_rectangle_method(self, method_name):
        """Изменяет метод создания прямоугольника"""
        method_map = {
            "Две противоположные точки": "two_points",
            "Одна точка, ширина и высота": "point_size",
            "Центр, ширина и высота": "center_size",
            "С фасками/скруглениями при создании": "with_fillets"
        }
        method = method_map.get(method_name, "two_points")
        self.canvas.set_rectangle_creation_method(method)
        self.update_rectangle_input_fields()
    
    def update_rectangle_input_fields(self):
        """Обновляет отображение полей ввода в зависимости от метода создания прямоугольника"""
        # Обновляем метку для прямоугольника
        self.start_point_label_widget.setText("Начальная точка (x, y):")
        
        # Скрываем все группы
        self.cartesian_group.hide()
        self.polar_group.hide()
        self.rectangle_point_size_group.hide()
        self.rectangle_center_size_group.hide()
        self.rectangle_fillets_group.hide()
        
        # Показываем нужную группу
        method_name = self.rectangle_method_combo.currentText()
        if method_name == "Две противоположные точки":
            # Используем обычные поля для конечной точки
            if self.coordinate_system == "cartesian":
                self.cartesian_group.show()
                self.polar_group.hide()
            else:
                self.cartesian_group.hide()
                self.polar_group.show()
        elif method_name == "Одна точка, ширина и высота":
            self.rectangle_point_size_group.show()
        elif method_name == "Центр, ширина и высота":
            self.start_point_label_widget.setText("Центр (x, y):")
            self.rectangle_center_size_group.show()
        elif method_name == "С фасками/скруглениями при создании":
            # Используем обычные поля для конечной точки + радиус скругления
            if self.coordinate_system == "cartesian":
                self.cartesian_group.show()
                self.polar_group.hide()
            else:
                self.cartesian_group.hide()
                self.polar_group.show()
            self.rectangle_fillets_group.show()
    
    def on_rectangle_coordinates_changed(self):
        """Обработчик изменения координат прямоугольника"""
        # Обновляем размеры прямоугольника в сцене, если идет рисование
        if self.canvas.scene.is_drawing() and self.canvas.scene._drawing_type == 'rectangle':
            method_name = self.rectangle_method_combo.currentText()
            if method_name == "Одна точка, ширина и высота":
                width = self.rectangle_width_spin.value()
                height = self.rectangle_height_spin.value()
                if width > 0 and height > 0:
                    self.canvas.scene.set_rectangle_size(width, height)
                    self.canvas.update()
            elif method_name == "Центр, ширина и высота":
                width = self.rectangle_center_width_spin.value()
                height = self.rectangle_center_height_spin.value()
                if width > 0 and height > 0:
                    self.canvas.scene.set_rectangle_size(width, height)
                    self.canvas.update()
            elif method_name == "С фасками/скруглениями при создании":
                radius = self.rectangle_fillet_radius_spin.value()
                if radius > 0:
                    self.canvas.scene.set_rectangle_fillet_radius(radius)
                    self.canvas.update()
    
    def update_rectangle_on_drawing_start(self, method: str):
        """Обновляет параметры прямоугольника при начале рисования"""
        if self.canvas.scene.is_drawing() and self.canvas.scene._drawing_type == 'rectangle':
            if method == 'point_size':
                width = self.rectangle_width_spin.value()
                height = self.rectangle_height_spin.value()
                if width > 0 and height > 0:
                    self.canvas.scene.set_rectangle_size(width, height)
                    self.canvas.update()
            elif method == 'center_size':
                width = self.rectangle_center_width_spin.value()
                height = self.rectangle_center_height_spin.value()
                if width > 0 and height > 0:
                    self.canvas.scene.set_rectangle_size(width, height)
                    self.canvas.update()
            elif method == 'with_fillets':
                radius = self.rectangle_fillet_radius_spin.value()
                if radius > 0:
                    self.canvas.scene.set_rectangle_fillet_radius(radius)
                    self.canvas.update()
    
    def update_circle_input_fields(self):
        """Обновляет отображение полей ввода в зависимости от метода создания окружности"""
        # Обновляем метку для окружности
        self.start_point_label_widget.setText("Центр (x, y):")
        
        # Скрываем все группы
        self.cartesian_group.hide()
        self.polar_group.hide()
        self.circle_center_radius_group.hide()
        self.circle_center_diameter_group.hide()
        self.circle_two_points_group.hide()
        self.circle_three_points_group.hide()
        
        # Показываем нужную группу
        method_name = self.circle_method_combo.currentText()
        if method_name == "Центр и радиус":
            self.circle_center_radius_group.show()
        elif method_name == "Центр и диаметр":
            self.circle_center_diameter_group.show()
        elif method_name == "Две точки":
            self.circle_two_points_group.show()
        elif method_name == "Три точки на окружности":
            self.circle_three_points_group.show()
    
    def on_circle_coordinates_changed(self):
        """Обработчик изменения координат окружности"""
        # Предпросмотр окружности при изменении параметров
        pass
    
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
        #  обновляет отображение полей ввода в зависимости от системы координат
        if self.coordinate_system == "cartesian":
            self.cartesian_group.show()
            self.polar_group.hide()
        else:
            self.cartesian_group.hide()
            self.polar_group.show()
            
            # при переключении на полярные координаты преобразуем текущие декартовы координаты
            # ОТНОСИТЕЛЬНО НАЧАЛЬНОЙ ТОЧКИ
            start_x = self.start_x_spin.value()
            start_y = self.start_y_spin.value()
            end_x = self.end_x_spin.value()
            end_y = self.end_y_spin.value()
            
            # вычисляем смещение от начальной точки
            delta_x = end_x - start_x
            delta_y = end_y - start_y
            
            # преобразуем смещение в полярные координаты
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
        # обновляет единицы измерения углов
        self.angle_label.setText("°" if self.angle_units == "degrees" else "rad")
        
        # конвертируем угол при смене единиц измерения
        if self.coordinate_system == "polar":
            current_angle = self.angle_spin.value()
            if self.angle_units == "degrees":
                # были радианы, стали градусы
                current_angle = math.degrees(current_angle)
            else:
                # были градусы, стали радианы
                current_angle = math.radians(current_angle)
            
            self.angle_spin.blockSignals(True)
            self.angle_spin.setValue(current_angle)
            self.angle_spin.blockSignals(False)
    
    def on_coordinates_changed(self):
        # обработчик изменения декартовых координат только предпросмотр
        # Показываем предпросмотр только для отрезков
        if self.canvas.primitive_type != 'line':
            return
        if self.coordinate_system == "cartesian":
            self.preview_coordinates()

    def on_polar_changed(self):
        # обработчик изменения полярных координат только предпросмотр
        # Показываем предпросмотр только для отрезков
        if self.canvas.primitive_type != 'line':
            return
        if self.coordinate_system == "polar":
            self.preview_coordinates()

    def preview_coordinates(self):
        # предпросмотр отрезка без сохранения
        # Показываем предпросмотр только для отрезков
        if self.canvas.primitive_type != 'line':
            return
        
        start_point = QPointF(self.start_x_spin.value(), self.start_y_spin.value())
        
        if self.coordinate_system == "cartesian":
            end_point = QPointF(self.end_x_spin.value(), self.end_y_spin.value())
        else:
            # преобразуем полярные координаты в декартовы ОТНОСИТЕЛЬНО НАЧАЛЬНОЙ ТОЧКИ
            radius = self.radius_spin.value()
            angle = self.angle_spin.value()
            
            if self.angle_units == "degrees":
                angle_rad = math.radians(angle)
            else:
                angle_rad = angle
            
            # вычисляем смещение от начальной точки
            delta_x = radius * math.cos(angle_rad)
            delta_y = radius * math.sin(angle_rad)
            
            # конечная точка = начальная + смещение
            end_x = start_point.x() + delta_x
            end_y = start_point.y() + delta_y
            end_point = QPointF(end_x, end_y)
        
        # только предпросмотр без сохранения (apply=False)
        self.canvas.set_points_from_input(start_point, end_point, apply=False)
        self.update_info()
    
    def update_info(self):
        # обновляет информационную панель
        start_point, end_point = self.canvas.get_current_points()
        start_x, start_y = start_point.x(), start_point.y()
        end_x, end_y = end_point.x(), end_point.y()
        
        # обновляем счетчик отрезков
        total_lines = len(self.canvas.lines)
        if self.canvas.current_line:
            total_lines += 1
        self.lines_count_label.setText(f"Отрезков на экране: {total_lines}")
        
        # отображаем координаты в информационной панели
        if self.coordinate_system == "cartesian":
            self.start_point_label.setText(f"({start_x:.2f}, {start_y:.2f})")
            self.end_point_label.setText(f"({end_x:.2f}, {end_y:.2f})")
        else:
            # преобразуем в полярные координаты ОТНОСИТЕЛЬНО НАЧАЛЬНОЙ ТОЧКИ
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
        
        # вычисляем длину отрезка
        dx = end_x - start_x
        dy = end_y - start_y
        length = math.sqrt(dx**2 + dy**2)
        self.length_label.setText(f"{length:.2f}")
        
        # вычисляем угол наклона
        if dx != 0 or dy != 0:
            angle_rad = math.atan2(dy, dx)
            if self.angle_units == "degrees":
                angle = math.degrees(angle_rad)
                self.angle_info_label.setText(f"{angle:.2f}°")
            else:
                self.angle_info_label.setText(f"{angle_rad:.2f} rad")
        else:
            self.angle_info_label.setText("0.00°" if self.angle_units == "degrees" else "0.00 rad")