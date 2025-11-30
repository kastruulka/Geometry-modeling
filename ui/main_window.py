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
        
        # панель ввода координат
        input_group = QGroupBox("Ввод координат")
        input_layout = QGridLayout()
        
        # начальная точка (всегда в декартовых координатах)
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
        
        input_layout.addWidget(self.cartesian_group, 1, 1, 1, 4)
        input_layout.addWidget(self.polar_group, 1, 1, 1, 4)
        
        # кнопка применения координат
        self.apply_coords_btn = QPushButton("Применить координаты")
        self.apply_coords_btn.clicked.connect(self.apply_coordinates)
        input_layout.addWidget(self.apply_coords_btn, 2, 0, 1, 5)
        
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
        # координаты из полей ввода и фикс отрезка
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
        
        # фиксируем отрезок (apply=True)
        self.canvas.set_points_from_input(start_point, end_point, apply=True)
        
        # очищаем текущий отрезок после фиксации
        self.canvas.current_line = None
        self.canvas.is_drawing = False
        
        # АВТОМАТИЧЕСКИ ПОКАЗЫВАЕМ ВСЕ ОТРЕЗКИ С СОХРАНЕНИЕМ ПОВОРОТА
        self.canvas.show_all_preserve_rotation()
        
        # сбрасываем значения для следующего отрезка
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
        if self.coordinate_system == "cartesian":
            self.preview_coordinates()

    def on_polar_changed(self):
        # обработчик изменения полярных координат только предпросмотр
        if self.coordinate_system == "polar":
            self.preview_coordinates()

    def preview_coordinates(self):
        # предпросмотр отрезка без сохранения
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