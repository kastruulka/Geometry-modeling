"""
Рефакторенная версия виджета системы координат
Использует разделение ответственностей согласно ООП
"""
import math
from PySide6.QtWidgets import QWidget, QMenu
from PySide6.QtCore import Qt, QPointF, QPoint, Signal, QTimer
from PySide6.QtGui import QPainter, QPen, QColor, QTransform

from core.viewport import Viewport
from core.scene import Scene
from core.selection import SelectionManager
from core.renderer import SceneRenderer
from core.snapping import SnapManager, SnapPoint
from widgets.line_segment import LineSegment
from widgets.line_style import LineStyleManager
from widgets.primitives import Circle, Arc, Ellipse, Polygon, Spline
from widgets.dimensions import LinearDimension, RadialDimension, AngularDimension


class CoordinateSystemWidget(QWidget):
    """Виджет для отображения и взаимодействия с системой координат"""
    
    view_changed = Signal()  # сигнал при изменении вида
    context_menu_requested = Signal(QPoint)  # сигнал для запроса контекстного меню
    selection_changed = Signal(list)  # сигнал при изменении выделения
    line_finished = Signal()  # сигнал при завершении рисования отрезка
    rectangle_drawing_started = Signal(str)  # сигнал при начале рисования прямоугольника (передает метод)

    dimension_mode_cancelled = Signal()

    def __init__(self, style_manager=None):
        super().__init__()

        # Создаем компоненты
        self.viewport = Viewport(self.width(), self.height())
        self.scene = Scene()
        self.selection_manager = SelectionManager()
        self.renderer = SceneRenderer(self.viewport, self.scene, self.selection_manager)
        self.snap_manager = SnapManager(tolerance=15.0)  # Увеличиваем tolerance для лучшей видимости привязок

        # Менеджер стилей
        self.style_manager = style_manager

        # Менеджер слоёв
        self.layer_manager = None
        
        # Текущая точка привязки для визуализации
        self.current_snap_point = None
        
        # Параметры навигации
        self.pan_mode = False
        self.last_mouse_pos = None
        
        # Параметры выделения рамкой
        self.is_selecting = False
        self.selection_start = None
        self.selection_end = None
        self.right_button_press_pos = None
        self.right_button_press_time = None
        self.right_button_click_count = 0
        self.right_button_click_timer = None
        self.last_left_click_time = 0
        self.last_left_click_pos = None
        self.last_left_click_time = 0
        self.last_left_click_pos = None
        
        # Координаты курсора
        self.cursor_world_coords = None
        
        # Точки ввода для визуализации (для окружности, дуги, эллипса, прямоугольника)
        self.input_points = []  # Список точек для отображения
        
        # Настройки отрисовки
        self.line_color = QColor(0, 0, 0)
        self.line_width = 2
        
        # Тип создаваемого примитива
        self.primitive_type = 'line'  # 'line', 'circle', 'arc', 'rectangle', 'ellipse', 'polygon', 'spline', 'dimension'
        # Метод создания окружности
        self.circle_creation_method = 'center_radius'  # 'center_radius', 'center_diameter', 'two_points', 'three_points'
        # Метод создания дуги
        self.arc_creation_method = 'three_points'  # 'three_points', 'center_angles'
        # Метод создания прямоугольника
        self.rectangle_creation_method = 'two_points'  # 'two_points', 'point_size', 'center_size', 'with_fillets'
        # Метод создания многоугольника
        self.polygon_creation_method = 'center_radius_vertices'  # 'center_radius_vertices'
        self.polygon_num_vertices = 3
        self.dimension_creation_type = 'horizontal'
        self.dimension_points = []
        self.dimension_line_refs = []
        self.dimension_preview_object = None
        
        # Режим редактирования (перемещение точек)
        self.editing_mode = False
        self.edit_dialog = None  # Ссылка на окно редактирования
        self.dragging_point = None  # 'start' или 'end' - какая точка перемещается
        self.drag_start_pos = None  # Позиция начала перетаскивания

        # Подключаем сигналы
        self.selection_manager.selection_changed.connect(self._on_selection_changed)
        
        self.setMinimumSize(600, 400)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.NoContextMenu)
    
    def set_layer_manager(self, layer_manager):
        """Устанавливает менеджер слоёв и обновляет renderer."""
        self.layer_manager = layer_manager
        self.renderer.layer_manager = layer_manager

    def set_editing_mode(self, enabled, edit_dialog=None):
        """Устанавливает режим редактирования (перемещение точек)"""
        self.editing_mode = enabled
        self.edit_dialog = edit_dialog
        if not enabled:
            self.dragging_point = None
            self.drag_start_pos = None
        self.update()
    
    def _on_selection_changed(self, selected_objects):
        """Обработчик изменения выделения"""
        self.selection_changed.emit(selected_objects)
        self.update()
    
    def resizeEvent(self, event):
        """Обработчик изменения размера виджета"""
        super().resizeEvent(event)
        self.viewport.set_size(self.width(), self.height())
        self.update()
    
    def paintEvent(self, event):
        """Отрисовка виджета"""
        self._sync_associated_dimensions()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Сначала рисуем сцену через renderer
        self.renderer.draw(painter)
        
        # Затем рисуем точки ввода (поверх сцены)
        if self.input_points:
            self._draw_input_points(painter)

        if self.dimension_preview_object is not None:
            self.dimension_preview_object.draw(painter, self.viewport.get_scale())
        
        # Рисуем точку привязки (поверх всего)
        if self.current_snap_point:
            self._draw_snap_point(painter)
        
        # Рисуем точки редактирования (в режиме редактирования)
        if self.editing_mode:
            self._draw_editing_points(painter)

        # В конце рисуем рамку выделения (в экранных координатах)
        if self.is_selecting and self.selection_start and self.selection_end:
            self._draw_selection_rect(painter)
    
    def _draw_selection_rect(self, painter):
        """Рисует рамку выделения"""
        if not self.selection_start or not self.selection_end:
            return
        
        # Рисуем рамку в экранных координатах (без трансформации)
        painter.save()  # Сохраняем текущее состояние
        painter.resetTransform()  # Сбрасываем трансформацию для отрисовки в экранных координатах
        
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QPen, QColor
        from PySide6.QtCore import Qt
        
        # Создаем прямоугольник из экранных координат напрямую
        screen_rect = QRectF(
            min(self.selection_start.x(), self.selection_end.x()),
            min(self.selection_start.y(), self.selection_end.y()),
            abs(self.selection_end.x() - self.selection_start.x()),
            abs(self.selection_end.y() - self.selection_start.y())
        )
        
        # Рисуем рамку
        selection_pen = QPen(QColor(0, 100, 255), 1, Qt.DashLine)
        painter.setPen(selection_pen)
        painter.setBrush(QColor(0, 100, 255, 30))  # Полупрозрачная заливка
        painter.drawRect(screen_rect)
        
        painter.restore()  # Восстанавливаем состояние
    
    def _apply_snapping(self, point: QPointF, exclude_object=None) -> QPointF:
        """
        Применяет привязку к точке
        Args:
            point: Исходная точка
            exclude_object: Объект, который нужно исключить из привязки (например, редактируемый объект)
        Returns:
            Привязанная точка (или исходная, если привязка не найдена)
        """
        if not self.snap_manager.enabled:
            self.current_snap_point = None
            return point
        
        # Получаем все объекты, исключая текущий рисуемый и редактируемый
        objects = self.scene.get_objects()
        current_obj = self.scene.get_current_object()
        
        # Исключаем объект для привязки (приоритет у exclude_object)
        obj_to_exclude = exclude_object if exclude_object is not None else current_obj
        
        # Получаем статические точки привязки
        snap_points = self.snap_manager.get_snap_points(objects, exclude_object=obj_to_exclude)
        
        # Получаем начальную точку для динамических привязок
        start_point = None
        if self.scene.is_drawing():
            drawing_type = getattr(self.scene, '_drawing_type', None)
            if drawing_type == 'line':
                current_line = self.scene.get_current_line()
                if current_line:
                    start_point = current_line.start_point
            elif drawing_type == 'arc':
                start_point = getattr(self.scene, '_arc_start_point', None)
        
        # Добавляем динамические точки привязки
        if start_point:
            dynamic_points = self.snap_manager.get_dynamic_snap_points(
                point, objects, exclude_object=obj_to_exclude, start_point=start_point
            )
            snap_points.extend(dynamic_points)
        
        # Находим ближайшую точку привязки
        scale_factor = self.viewport.get_scale()
        result = self.snap_manager.find_nearest_snap(point, snap_points, scale_factor)
        
        if result:
            snapped_point, snap_point = result
            self.current_snap_point = snap_point
            return snapped_point
        else:
            self.current_snap_point = None
            return point
    
    def _draw_input_points(self, painter):
        """Рисует точки ввода для визуализации"""
        if not self.input_points:
            return
        
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Применяем трансформацию viewport
        # После renderer.draw() трансформация может быть сброшена, поэтому применяем заново
        transform = self.viewport.get_total_transform()
        painter.setTransform(transform)
        
        # Цвет и стиль точек
        point_color = QColor(255, 100, 0)  # Оранжевый цвет для точек ввода
        point_pen = QPen(point_color, 1.5)
        painter.setPen(point_pen)
        painter.setBrush(QColor(255, 150, 50, 220))  # Полупрозрачная оранжевая заливка
        
        # Размер точки в мировых координатах
        scale_factor = self.viewport.get_scale()
        # Размер точки в мировых координатах (примерно 4 пикселя на экране)
        point_size = max(4.0 / scale_factor, 0.5)  # Минимальный размер 0.5 в мировых координатах
        
        for point in self.input_points:
            if point is None:
                continue
            # Рисуем точку в мировых координатах
            # Используем drawEllipse с центром в точке и радиусом point_size
            from PySide6.QtCore import QRectF
            rect = QRectF(
                point.x() - point_size,
                point.y() - point_size,
                point_size * 2,
                point_size * 2
            )
            painter.drawEllipse(rect)
        
        painter.restore()
    
    def _draw_editing_points(self, painter):
        """Рисует точки редактирования для выделенных объектов"""
        selected = self.selection_manager.get_selected_objects()
        if len(selected) != 1:
            return
        
        obj = selected[0]
        painter.save()
        painter.resetTransform()  # Сбрасываем трансформацию для рисования в экранных координатах
        
        # Радиус точки в экранных координатах
        point_radius = 8.0
        
        from widgets.primitives import Circle, Rectangle
        if isinstance(obj, LineSegment):
            # Рисуем точки для отрезка
            start_screen = self.viewport.world_to_screen(obj.start_point)
            end_screen = self.viewport.world_to_screen(obj.end_point)
            
            # Рисуем начальную точку (зеленая)
            painter.setPen(QPen(QColor(0, 200, 0), 2))
            painter.setBrush(QColor(0, 255, 0, 200))
            painter.drawEllipse(start_screen, point_radius, point_radius)
            
            # Рисуем конечную точку (красная)
            painter.setPen(QPen(QColor(200, 0, 0), 2))
            painter.setBrush(QColor(255, 0, 0, 200))
            painter.drawEllipse(end_screen, point_radius, point_radius)
            
            # Если точка перемещается, подсвечиваем её
            if self.dragging_point == 'start':
                painter.setPen(QPen(QColor(0, 255, 0), 3))
                painter.setBrush(QColor(0, 255, 0, 150))
                painter.drawEllipse(start_screen, point_radius + 3, point_radius + 3)
            elif self.dragging_point == 'end':
                painter.setPen(QPen(QColor(255, 0, 0), 3))
                painter.setBrush(QColor(255, 0, 0, 150))
                painter.drawEllipse(end_screen, point_radius + 3, point_radius + 3)
        elif isinstance(obj, Circle):
            # Рисуем центр окружности (синий)
            center_screen = self.viewport.world_to_screen(obj.center)
            painter.setPen(QPen(QColor(0, 0, 200), 2))
            painter.setBrush(QColor(0, 0, 255, 200))
            painter.drawEllipse(center_screen, point_radius, point_radius)
            
            # Рисуем крайнюю точку на окружности для изменения радиуса (оранжевая)
            # Точка находится справа от центра (0°)
            radius_point_world = QPointF(obj.center.x() + obj.radius, obj.center.y())
            radius_point_screen = self.viewport.world_to_screen(radius_point_world)
            painter.setPen(QPen(QColor(255, 165, 0), 2))
            painter.setBrush(QColor(255, 165, 0, 200))
            painter.drawEllipse(radius_point_screen, point_radius, point_radius)
            
            # Если центр перемещается, подсвечиваем его
            if self.dragging_point == 'center':
                painter.setPen(QPen(QColor(0, 0, 255), 3))
                painter.setBrush(QColor(0, 0, 255, 150))
                painter.drawEllipse(center_screen, point_radius + 3, point_radius + 3)
            # Если крайняя точка перемещается, подсвечиваем её
            elif self.dragging_point == 'radius':
                painter.setPen(QPen(QColor(255, 165, 0), 3))
                painter.setBrush(QColor(255, 165, 0, 150))
                painter.drawEllipse(radius_point_screen, point_radius + 3, point_radius + 3)
        elif isinstance(obj, Rectangle):
            # Рисуем углы прямоугольника
            top_left_screen = self.viewport.world_to_screen(obj.top_left)
            bottom_right_screen = self.viewport.world_to_screen(obj.bottom_right)
            top_right_screen = self.viewport.world_to_screen(QPointF(obj.bottom_right.x(), obj.top_left.y()))
            bottom_left_screen = self.viewport.world_to_screen(QPointF(obj.top_left.x(), obj.bottom_right.y()))
            
            # Вычисляем центр прямоугольника
            bbox = obj.get_bounding_box()
            center_world = QPointF(bbox.center().x(), bbox.center().y())
            center_screen = self.viewport.world_to_screen(center_world)
            
            # Рисуем центр прямоугольника (фиолетовый)
            painter.setPen(QPen(QColor(128, 0, 128), 2))
            painter.setBrush(QColor(128, 0, 128, 200))
            painter.drawEllipse(center_screen, point_radius, point_radius)
            
            # Верхний левый угол (зеленый)
            painter.setPen(QPen(QColor(0, 200, 0), 2))
            painter.setBrush(QColor(0, 255, 0, 200))
            painter.drawEllipse(top_left_screen, point_radius, point_radius)
            
            # Верхний правый угол (красный)
            painter.setPen(QPen(QColor(200, 0, 0), 2))
            painter.setBrush(QColor(255, 0, 0, 200))
            painter.drawEllipse(top_right_screen, point_radius, point_radius)
            
            # Нижний правый угол (синий)
            painter.setPen(QPen(QColor(0, 0, 200), 2))
            painter.setBrush(QColor(0, 0, 255, 200))
            painter.drawEllipse(bottom_right_screen, point_radius, point_radius)
            
            # Нижний левый угол (желтый)
            painter.setPen(QPen(QColor(200, 200, 0), 2))
            painter.setBrush(QColor(255, 255, 0, 200))
            painter.drawEllipse(bottom_left_screen, point_radius, point_radius)
            
            # Подсвечиваем перемещаемую точку
            if self.dragging_point == 'center':
                painter.setPen(QPen(QColor(128, 0, 128), 3))
                painter.setBrush(QColor(128, 0, 128, 150))
                painter.drawEllipse(center_screen, point_radius + 3, point_radius + 3)
            elif self.dragging_point == 'top_left':
                painter.setPen(QPen(QColor(0, 255, 0), 3))
                painter.setBrush(QColor(0, 255, 0, 150))
                painter.drawEllipse(top_left_screen, point_radius + 3, point_radius + 3)
            elif self.dragging_point == 'top_right':
                painter.setPen(QPen(QColor(255, 0, 0), 3))
                painter.setBrush(QColor(255, 0, 0, 150))
                painter.drawEllipse(top_right_screen, point_radius + 3, point_radius + 3)
            elif self.dragging_point == 'bottom_right':
                painter.setPen(QPen(QColor(0, 0, 255), 3))
                painter.setBrush(QColor(0, 0, 255, 150))
                painter.drawEllipse(bottom_right_screen, point_radius + 3, point_radius + 3)
            elif self.dragging_point == 'bottom_left':
                painter.setPen(QPen(QColor(255, 255, 0), 3))
                painter.setBrush(QColor(255, 255, 0, 150))
                painter.drawEllipse(bottom_left_screen, point_radius + 3, point_radius + 3)
        elif isinstance(obj, Arc):
            # Рисуем точки редактирования дуги
            center_screen = self.viewport.world_to_screen(obj.center)
            
            # Вычисляем средний угол для точки радиуса
            mid_angle = self._arc_mid_angle(obj.start_angle, obj.end_angle)
            
            # Получаем точки на дуге для начального, конечного углов и середины
            start_point = obj.get_point_at_angle(obj.start_angle)
            end_point = obj.get_point_at_angle(obj.end_angle)
            mid_point = obj.get_point_at_angle(mid_angle)
            
            start_point_screen = self.viewport.world_to_screen(start_point)
            end_point_screen = self.viewport.world_to_screen(end_point)
            mid_point_screen = self.viewport.world_to_screen(mid_point)
            
            # Центр дуги (синий)
            painter.setPen(QPen(QColor(0, 0, 200), 2))
            painter.setBrush(QColor(0, 0, 255, 200))
            painter.drawEllipse(center_screen, point_radius, point_radius)
            
            # Начальная точка дуги (зеленая)
            painter.setPen(QPen(QColor(0, 200, 0), 2))
            painter.setBrush(QColor(0, 255, 0, 200))
            painter.drawEllipse(start_point_screen, point_radius, point_radius)
            
            # Конечная точка дуги (красная)
            painter.setPen(QPen(QColor(200, 0, 0), 2))
            painter.setBrush(QColor(255, 0, 0, 200))
            painter.drawEllipse(end_point_screen, point_radius, point_radius)
            
            # Точка для изменения радиуса (оранжевая) - в середине дуги
            painter.setPen(QPen(QColor(255, 165, 0), 2))
            painter.setBrush(QColor(255, 165, 0, 200))
            painter.drawEllipse(mid_point_screen, point_radius, point_radius)
            
            # Подсвечиваем перемещаемую точку
            if self.dragging_point == 'center':
                painter.setPen(QPen(QColor(0, 0, 255), 3))
                painter.setBrush(QColor(0, 0, 255, 150))
                painter.drawEllipse(center_screen, point_radius + 3, point_radius + 3)
            elif self.dragging_point == 'start_angle':
                painter.setPen(QPen(QColor(0, 255, 0), 3))
                painter.setBrush(QColor(0, 255, 0, 150))
                painter.drawEllipse(start_point_screen, point_radius + 3, point_radius + 3)
            elif self.dragging_point == 'end_angle':
                painter.setPen(QPen(QColor(255, 0, 0), 3))
                painter.setBrush(QColor(255, 0, 0, 150))
                painter.drawEllipse(end_point_screen, point_radius + 3, point_radius + 3)
            elif self.dragging_point == 'radius':
                painter.setPen(QPen(QColor(255, 165, 0), 3))
                painter.setBrush(QColor(255, 165, 0, 150))
                painter.drawEllipse(mid_point_screen, point_radius + 3, point_radius + 3)
        elif isinstance(obj, Ellipse):
            # Рисуем точки редактирования эллипса
            center_screen = self.viewport.world_to_screen(obj.center)
            
            # Точки на осях для изменения радиусов
            # Горизонтальная ось (X) - справа от центра
            radius_x_point = QPointF(obj.center.x() + obj.radius_x, obj.center.y())
            # Вертикальная ось (Y) - сверху от центра
            radius_y_point = QPointF(obj.center.x(), obj.center.y() - obj.radius_y)
            
            radius_x_screen = self.viewport.world_to_screen(radius_x_point)
            radius_y_screen = self.viewport.world_to_screen(radius_y_point)
            
            # Центр эллипса (синий)
            painter.setPen(QPen(QColor(0, 0, 200), 2))
            painter.setBrush(QColor(0, 0, 255, 200))
            painter.drawEllipse(center_screen, point_radius, point_radius)
            
            # Точка на горизонтальной оси (оранжевая)
            painter.setPen(QPen(QColor(255, 165, 0), 2))
            painter.setBrush(QColor(255, 165, 0, 200))
            painter.drawEllipse(radius_x_screen, point_radius, point_radius)
            
            # Точка на вертикальной оси (оранжевая)
            painter.setPen(QPen(QColor(255, 165, 0), 2))
            painter.setBrush(QColor(255, 165, 0, 200))
            painter.drawEllipse(radius_y_screen, point_radius, point_radius)
            
            # Подсвечиваем перемещаемую точку
            if self.dragging_point == 'center':
                painter.setPen(QPen(QColor(0, 0, 255), 3))
                painter.setBrush(QColor(0, 0, 255, 150))
                painter.drawEllipse(center_screen, point_radius + 3, point_radius + 3)
            elif self.dragging_point == 'radius_x':
                painter.setPen(QPen(QColor(255, 165, 0), 3))
                painter.setBrush(QColor(255, 165, 0, 150))
                painter.drawEllipse(radius_x_screen, point_radius + 3, point_radius + 3)
            elif self.dragging_point == 'radius_y':
                painter.setPen(QPen(QColor(255, 165, 0), 3))
                painter.setBrush(QColor(255, 165, 0, 150))
                painter.drawEllipse(radius_y_screen, point_radius + 3, point_radius + 3)
        elif isinstance(obj, Polygon):
            # Рисуем точки редактирования многоугольника
            center_screen = self.viewport.world_to_screen(obj.center)
            
            # Точка для изменения радиуса - на окружности, справа от центра (0°)
            # Для описанного многоугольника нужно учесть тип построения
            if hasattr(obj, 'construction_type') and obj.construction_type == "circumscribed":
                # Для описанного: radius - это расстояние до сторон, нужно найти радиус описанной окружности
                if obj.num_vertices > 2:
                    effective_radius = obj.radius / math.cos(math.pi / obj.num_vertices)
                else:
                    effective_radius = obj.radius
            else:
                effective_radius = obj.radius
            
            radius_point = QPointF(obj.center.x() + effective_radius, obj.center.y())
            radius_point_screen = self.viewport.world_to_screen(radius_point)
            
            # Центр многоугольника (синий)
            painter.setPen(QPen(QColor(0, 0, 200), 2))
            painter.setBrush(QColor(0, 0, 255, 200))
            painter.drawEllipse(center_screen, point_radius, point_radius)
            
            # Точка для изменения радиуса (оранжевая)
            painter.setPen(QPen(QColor(255, 165, 0), 2))
            painter.setBrush(QColor(255, 165, 0, 200))
            painter.drawEllipse(radius_point_screen, point_radius, point_radius)
            
            # Подсвечиваем перемещаемую точку
            if self.dragging_point == 'center':
                painter.setPen(QPen(QColor(0, 0, 255), 3))
                painter.setBrush(QColor(0, 0, 255, 150))
                painter.drawEllipse(center_screen, point_radius + 3, point_radius + 3)
            elif self.dragging_point == 'radius':
                painter.setPen(QPen(QColor(255, 165, 0), 3))
                painter.setBrush(QColor(255, 165, 0, 150))
                painter.drawEllipse(radius_point_screen, point_radius + 3, point_radius + 3)
        elif isinstance(obj, Spline):
            # Рисуем контрольные точки сплайна
            colors = [
                QColor(0, 255, 0),    # Зеленая
                QColor(255, 0, 0),    # Красная
                QColor(0, 0, 255),    # Синяя
                QColor(255, 165, 0),  # Оранжевая
                QColor(255, 0, 255),  # Пурпурная
                QColor(0, 255, 255),  # Голубая
                QColor(255, 255, 0),  # Желтая
                QColor(128, 128, 128) # Серая
            ]
            
            for i, point in enumerate(obj.control_points):
                point_screen = self.viewport.world_to_screen(point)
                color = colors[i % len(colors)]
                
                # Подсвечиваем перемещаемую точку
                if self.dragging_point == f'point_{i}':
                    painter.setPen(QPen(color, 3))
                    painter.setBrush(QColor(color.red(), color.green(), color.blue(), 150))
                    painter.drawEllipse(point_screen, point_radius + 3, point_radius + 3)
                else:
                    painter.setPen(QPen(color, 2))
                    painter.setBrush(QColor(color.red(), color.green(), color.blue(), 200))
                    painter.drawEllipse(point_screen, point_radius, point_radius)
        elif isinstance(obj, LinearDimension):
            self._draw_dimension_grips(painter, obj, point_radius)
        elif isinstance(obj, RadialDimension):
            self._draw_dimension_grips(painter, obj, point_radius)
        elif isinstance(obj, AngularDimension):
            self._draw_dimension_grips(painter, obj, point_radius)

        painter.restore()
    
    def _find_spline_insertion_index(self, spline, point: QPointF) -> int:
        """Находит индекс для вставки новой контрольной точки сплайна"""
        if len(spline.control_points) == 0:
            return 0
        
        if len(spline.control_points) == 1:
            return 1
        
        # Находим ближайший сегмент между контрольными точками
        min_dist = float('inf')
        best_index = len(spline.control_points)
        
        for i in range(len(spline.control_points) - 1):
            p1 = spline.control_points[i]
            p2 = spline.control_points[i + 1]
            
            # Вычисляем расстояние от точки до сегмента
            dx = p2.x() - p1.x()
            dy = p2.y() - p1.y()
            seg_len_sq = dx*dx + dy*dy
            
            if seg_len_sq < 1e-10:
                # Точки совпадают, используем расстояние до одной из них
                dist = math.sqrt((point.x() - p1.x())**2 + (point.y() - p1.y())**2)
            else:
                # Проекция точки на сегмент
                t = ((point.x() - p1.x()) * dx + (point.y() - p1.y()) * dy) / seg_len_sq
                t = max(0, min(1, t))
                
                # Ближайшая точка на сегменте
                closest_x = p1.x() + t * dx
                closest_y = p1.y() + t * dy
                
                # Расстояние до сегмента
                dist = math.sqrt((point.x() - closest_x)**2 + (point.y() - closest_y)**2)
            
            if dist < min_dist:
                min_dist = dist
                best_index = i + 1
        return best_index
    
    def _draw_snap_point(self, painter):
        """Рисует текущую точку привязки"""
        if not self.current_snap_point:
            return
        
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Применяем трансформацию viewport
        transform = self.viewport.get_total_transform()
        painter.setTransform(transform)
        
        # Цвет и стиль точки привязки
        from core.snapping import SnapType
        if self.current_snap_point.snap_type == SnapType.END:
            snap_color = QColor(255, 0, 0)  # Красный для конца
        elif self.current_snap_point.snap_type == SnapType.MIDDLE:
            snap_color = QColor(0, 255, 0)  # Зеленый для середины
        elif self.current_snap_point.snap_type == SnapType.CENTER:
            snap_color = QColor(0, 0, 255)  # Синий для центра
        elif self.current_snap_point.snap_type == SnapType.VERTEX:
            snap_color = QColor(255, 165, 0)  # Оранжевый для вершины
        elif self.current_snap_point.snap_type == SnapType.INTERSECTION:
            snap_color = QColor(255, 0, 255)  # Пурпурный для пересечения
        else:
            snap_color = QColor(128, 128, 128)  # Серый по умолчанию
        
        # Рисуем крестик для точки привязки
        scale_factor = self.viewport.get_scale()
        snap_size = max(8.0 / scale_factor, 1.0)  # Размер крестика
        
        snap_pen = QPen(snap_color, 2.0 / scale_factor)
        painter.setPen(snap_pen)
        
        point = self.current_snap_point.point
        painter.drawLine(
            point.x() - snap_size, point.y(),
            point.x() + snap_size, point.y()
        )
        painter.drawLine(
            point.x(), point.y() - snap_size,
            point.x(), point.y() + snap_size
        )
        
        # Рисуем круг вокруг точки
        painter.setBrush(Qt.NoBrush)
        circle_pen = QPen(snap_color, 1.0 / scale_factor, Qt.DashLine)
        painter.setPen(circle_pen)
        from PySide6.QtCore import QRectF
        circle_rect = QRectF(
            point.x() - snap_size * 1.5,
            point.y() - snap_size * 1.5,
            snap_size * 3,
            snap_size * 3
        )
        painter.drawEllipse(circle_rect)
        
        painter.restore()
    
    def set_input_points(self, points):
        """Устанавливает точки ввода для визуализации"""
        self.input_points = points if points else []
        self.update()
    
    def clear_input_points(self):
        """Очищает точки ввода"""
        self.input_points = []
        self.dimension_points = []
        self.dimension_line_refs = []
        self.dimension_preview_object = None
        self.update()
    
    def show_context_menu(self, position):
        """Показывает контекстное меню"""
        menu = QMenu(self)
        
        zoom_in_action = menu.addAction("Увеличить")
        zoom_in_action.triggered.connect(self.zoom_in)
        
        zoom_out_action = menu.addAction("Уменьшить")
        zoom_out_action.triggered.connect(self.zoom_out)
        
        menu.addSeparator()
        
        show_all_action = menu.addAction("Показать всё")
        show_all_action.triggered.connect(self.show_all)
        
        reset_view_action = menu.addAction("Сбросить вид")
        reset_view_action.triggered.connect(self.reset_view)
        
        menu.addSeparator()
        
        rotate_left_action = menu.addAction("Повернуть налево")
        rotate_left_action.triggered.connect(lambda: self.rotate_left(15))
        
        rotate_right_action = menu.addAction("Повернуть направо")
        rotate_right_action.triggered.connect(lambda: self.rotate_right(15))
        
        menu.exec_(self.mapToGlobal(position))
    
    def mousePressEvent(self, event):
        """Обработчик нажатия кнопки мыши"""
        if event.button() == Qt.LeftButton:
            if self.pan_mode:
                self.last_mouse_pos = event.position()
            elif self.editing_mode:
                # Режим редактирования - проверяем, кликнули ли по редактируемым точкам
                world_pos = self.viewport.screen_to_world(event.position())
                world_pos = self._apply_snapping(world_pos)
                
                obj = self._single_selected_object()
                if obj is not None:
                    from widgets.primitives import Circle, Rectangle, Arc, Ellipse, Spline
                    tolerance = self._editing_tolerance()  # ?????????????????????????? ?? ?????????????? ??????????????????????
                    
                    
                    if isinstance(obj, LineSegment):
                        line = obj
                        if self._try_start_named_point_drag(world_pos, tolerance, [
                            ('start', line.start_point),
                            ('end', line.end_point),
                        ]):
                            return
                    elif isinstance(obj, Circle):
                        circle = obj
                        # Проверяем, кликнули ли по крайней точке окружности (для изменения радиуса)
                        # Точка находится справа от центра (0°)
                        radius_point = QPointF(circle.center.x() + circle.radius, circle.center.y())
                        if self._try_start_named_point_drag(world_pos, tolerance, [
                            ('center', circle.center),
                            ('radius', radius_point),
                        ]):
                            return
                    elif isinstance(obj, Rectangle):
                        from widgets.primitives import Rectangle
                        rect = obj
                        # Вычисляем центр прямоугольника
                        bbox = rect.get_bounding_box()
                        center = QPointF(bbox.center().x(), bbox.center().y())
                        
                        if self._try_start_named_point_drag(world_pos, tolerance, [('center', center)]):
                            return

                        # Проверяем, кликнули ли по углам прямоугольника
                        top_left = rect.top_left
                        bottom_right = rect.bottom_right
                        top_right = QPointF(bottom_right.x(), top_left.y())
                        bottom_left = QPointF(top_left.x(), bottom_right.y())

                        if self._try_start_named_point_drag(world_pos, tolerance, [
                            ('top_left', top_left),
                            ('top_right', top_right),
                            ('bottom_right', bottom_right),
                            ('bottom_left', bottom_left),
                        ]):
                            return
                    elif isinstance(obj, Arc):
                        arc = obj
                        if self._try_start_named_point_drag(world_pos, tolerance, [('center', arc.center)]):
                            return

                        # Вычисляем средний угол для точки радиуса
                        mid_angle = self._arc_mid_angle(arc.start_angle, arc.end_angle)
                        
                        # Получаем точки на дуге
                        start_point = arc.get_point_at_angle(arc.start_angle)
                        end_point = arc.get_point_at_angle(arc.end_angle)
                        mid_point = arc.get_point_at_angle(mid_angle)
                        
                        if self._try_start_named_point_drag(world_pos, tolerance, [
                            ('start_angle', start_point),
                            ('end_angle', end_point),
                            ('radius', mid_point),
                        ]):
                            return
                    elif isinstance(obj, Ellipse):
                        ellipse = obj
                        if self._try_start_named_point_drag(world_pos, tolerance, [('center', ellipse.center)]):
                            return

                        # Точки на осях для изменения радиусов
                        radius_x_point = QPointF(ellipse.center.x() + ellipse.radius_x, ellipse.center.y())
                        radius_y_point = QPointF(ellipse.center.x(), ellipse.center.y() - ellipse.radius_y)

                        if self._try_start_named_point_drag(world_pos, tolerance, [
                            ('radius_x', radius_x_point),
                            ('radius_y', radius_y_point),
                        ]):
                            return
                    elif isinstance(obj, Polygon):
                        polygon = obj
                        if self._try_start_named_point_drag(world_pos, tolerance, [('center', polygon.center)]):
                            return

                        # Точка для изменения радиуса - на окружности, справа от центра
                        if hasattr(polygon, 'construction_type') and polygon.construction_type == "circumscribed":
                            if polygon.num_vertices > 2:
                                effective_radius = polygon.radius / math.cos(math.pi / polygon.num_vertices)
                            else:
                                effective_radius = polygon.radius
                        else:
                            effective_radius = polygon.radius
                        
                        radius_point = QPointF(polygon.center.x() + effective_radius, polygon.center.y())
                        if self._try_start_named_point_drag(world_pos, tolerance, [('radius', radius_point)]):
                            return
                    elif isinstance(obj, Spline):
                        spline = obj
                        # Проверяем, кликнули ли по контрольным точкам
                        clicked_on_point = False
                        for i, point in enumerate(spline.control_points):
                            if self._distance_to_point(world_pos, point) <= tolerance:
                                # Левый клик - начинаем перемещение
                                clicked_on_point = True
                                self._begin_drag(f'point_{i}', world_pos)
                                return
                        
                        # Если кликнули по сплайну (но не по точке), добавляем новую точку
                        # Проверяем расстояние до сплайна (используем больший tolerance для удобства)
                        if not clicked_on_point and spline.contains_point(world_pos, tolerance * 3):
                            # Находим ближайший сегмент между контрольными точками
                            insert_index = self._find_spline_insertion_index(spline, world_pos)
                            # Вставляем точку в найденное место
                            spline.control_points.insert(insert_index, QPointF(world_pos))
                            if self.edit_dialog:
                                self.edit_dialog.update_spline_info()
                            self.update()
                            return
                    elif isinstance(obj, LinearDimension):
                        if self._try_start_dimension_grip_drag(obj, world_pos, tolerance):
                            return
                    elif isinstance(obj, RadialDimension):
                        if self._try_start_dimension_grip_drag(obj, world_pos, tolerance):
                            return
                    elif isinstance(obj, AngularDimension):
                        if self._try_start_dimension_grip_drag(obj, world_pos, tolerance):
                            return

                # В режиме редактирования не начинаем рисование нового объекта
                # Просто выходим, если клик не попал по точкам
                return
            else:
                world_pos = self.viewport.screen_to_world(event.position())
                
                # Применяем привязку
                world_pos = self._apply_snapping(world_pos)

                if self.primitive_type == 'dimension':
                    self._handle_dimension_click(world_pos)
                    return
                
                # Проверяем, есть ли активная точка привязки
                # Если есть - начинаем рисование из этой точки, не проверяя клик по объекту
                has_active_snap = self.current_snap_point is not None
                
                # Проверяем, кликнули ли по существующему объекту (для выделения)
                # Но только если мы не рисуем новый объект И нет активной точки привязки
                if not self.scene.is_drawing() and not has_active_snap:
                    selectable = self.scene.get_objects()
                    if self.layer_manager:
                        selectable = [o for o in selectable
                                      if self.layer_manager.is_layer_visible(getattr(o, '_layer_name', '0'))
                                      and not self.layer_manager.is_layer_locked(getattr(o, '_layer_name', '0'))]
                    clicked_obj = self.selection_manager.find_object_at_point(
                        world_pos, selectable
                    )
                    if clicked_obj:
                        # Клик по объекту - выделяем его
                        # Если зажат Ctrl, добавляем к выделению, иначе просто выделяем
                        add_to_selection = bool(event.modifiers() & Qt.ControlModifier)
                        self.selection_manager.select_object(clicked_obj, add_to_selection)
                        self.update()
                        # Прерываем выполнение - не начинаем рисование нового объекта
                        return
                    else:
                        # Клик не по объекту - снимаем выделение (если не Ctrl)
                        if not (event.modifiers() & Qt.ControlModifier):
                            self.selection_manager.clear_selection()
                        self.update()
                
                # Начинаем рисование нового объекта
                # Если есть активная точка привязки, начинаем из неё
                # Если нет - начинаем из текущей позиции мыши
                if not self.scene.is_drawing():
                    self._start_new_drawing(world_pos)
                else:
                    # Для дуги и эллипса нужны три клика, для остальных - два
                    if self.primitive_type == 'arc':
                        # Проверяем метод создания дуги
                        method = self.arc_creation_method
                        if method == 'three_points':
                            # Для трех точек нужно три клика
                            if self.scene._arc_end_point is None:
                                # Второй клик - фиксируем конечную точку
                                self.scene._arc_end_point = world_pos
                                # Очищаем временную точку
                                if hasattr(self.scene, '_temp_arc_end_point'):
                                    self.scene._temp_arc_end_point = None
                                # Обновляем объект для предпросмотра
                                self.scene.update_current_object(world_pos)
                            else:
                                # Третий клик - точка высоты, завершаем
                                self._update_and_finish_current_drawing(world_pos)
                        elif method == 'center_angles':
                            # Для центра и углов - второй клик определяет радиус
                            if self.scene._arc_radius == 0.0:
                                # Второй клик - фиксируем радиус
                                dx = world_pos.x() - self.scene._arc_center.x()
                                dy = world_pos.y() - self.scene._arc_center.y()
                                self.scene._arc_radius = math.sqrt(dx*dx + dy*dy)
                                self.scene.update_current_object(world_pos)
                            else:
                                # Радиус уже установлен, завершаем (углы задаются через UI)
                                self._finish_current_drawing()
                    elif self.primitive_type == 'circle':
                        # Проверяем метод создания окружности
                        method = self.circle_creation_method
                        if method == 'three_points':
                            # Для трех точек нужно три клика
                            if self.scene._circle_point2 is None:
                                # Второй клик - фиксируем вторую точку
                                self.scene._circle_point2 = world_pos
                                self.scene.update_current_object(world_pos)
                            else:
                                # Третий клик - завершаем
                                self.scene._circle_point3 = world_pos
                                self._update_and_finish_current_drawing(world_pos)
                        else:
                            # Для остальных методов - завершаем при втором клике
                            self._update_and_finish_current_drawing(world_pos)
                    elif self.primitive_type == 'ellipse':
                        # Проверяем этап создания эллипса
                        if hasattr(self.scene, '_ellipse_end_point') and self.scene._ellipse_end_point is None:
                            # Второй клик - фиксируем конечную точку
                            self.scene._ellipse_end_point = world_pos
                            # Очищаем временную точку
                            if hasattr(self.scene, '_temp_ellipse_end_point'):
                                self.scene._temp_ellipse_end_point = None
                            # Не обновляем объект здесь, так как третья точка еще не установлена
                            # Обновление произойдет при движении мыши
                        else:
                            # Третий клик - точка высоты, завершаем
                            self._update_and_finish_current_drawing(world_pos)
                    elif self.primitive_type == 'polygon':
                        # Для многоугольника второй клик завершает создание (радиус определяется)
                        self._update_and_finish_current_drawing(world_pos)
                    elif self.primitive_type == 'spline':
                        # Для сплайна левый клик добавляет контрольную точку
                        # Проверяем, не был ли это двойной клик (обрабатывается в mouseDoubleClickEvent)
                        current_time = event.timestamp()
                        is_double_click = (self.last_left_click_time > 0 and 
                                         current_time - self.last_left_click_time < 300 and
                                         self.last_left_click_pos and
                                         (world_pos - self.last_left_click_pos).manhattanLength() < 5)
                        
                        if not is_double_click:
                            # Проверяем tolerance для привязки к начальной точке
                            tolerance = 10.0 / self.viewport.get_scale()
                            is_closed = self.scene.add_spline_control_point(world_pos, tolerance)
                            if is_closed:
                                # Если сплайн замкнут, завершаем создание
                                self._finish_current_drawing()
                            self.update()
                            self.last_left_click_time = current_time
                            self.last_left_click_pos = world_pos
                        # Если это двойной клик, не добавляем точку и не обновляем время
                        # (двойной клик обработается в mouseDoubleClickEvent)
                    elif self.primitive_type == 'rectangle':
                        # Проверяем метод создания прямоугольника
                        method = self.rectangle_creation_method
                        if method == 'point_size' or method == 'center_size':
                            # Для этих методов первый клик устанавливает точку/центр
                            # Размеры должны быть установлены из UI (через сигнал rectangle_drawing_started)
                            # Проверяем размеры после небольшой задержки, чтобы дать время сигналу обработаться
                            def check_and_finish():
                                if (self.scene.is_drawing() and 
                                    self.scene._drawing_type == 'rectangle' and
                                    self.scene._rectangle_width > 0.0 and 
                                    self.scene._rectangle_height > 0.0):
                                    self._finish_current_drawing()
                                    self.update()
                            QTimer.singleShot(10, check_and_finish)
                            # Обновляем предпросмотр
                            self.scene.update_current_object(world_pos)
                        else:
                            # Для остальных методов (two_points, with_fillets) - завершаем при втором клике
                            self._update_and_finish_current_drawing(world_pos)
                    else:
                        # Для остальных примитивов - завершаем при втором клике
                        self._update_and_finish_current_drawing(world_pos)
                
                self.update()
        
        elif event.button() == Qt.RightButton:
            # Проверяем, находимся ли мы в режиме редактирования
            if self.editing_mode:
                world_pos = self.viewport.screen_to_world(event.position())
                world_pos = self._apply_snapping(world_pos)
                
                # Получаем выделенные объекты
                obj = self._single_selected_object()
                if obj is not None:
                    from widgets.primitives import Spline

                    if isinstance(obj, Spline):
                        spline = obj
                        tolerance = self._editing_tolerance()
                        
                        # Проверяем, кликнули ли по контрольным точкам
                        for i, point in enumerate(spline.control_points):
                            if self._distance_to_point(world_pos, point) <= tolerance:
                                # Правый клик - выбираем точку для удаления
                                if self.edit_dialog:
                                    self.edit_dialog.set_selected_spline_point(i)
                                self.update()
                                return
            
            # Правая кнопка - сохраняем позицию для определения клика/перетаскивания
            if self.primitive_type == 'dimension':
                if self.dimension_points:
                    self.dimension_points = []
                    self.dimension_line_refs = []
                    self.input_points = []
                    self.update()
                else:
                    self.primitive_type = 'line'
                    self.dimension_mode_cancelled.emit()
                return

            self.right_button_press_pos = event.position()
            self.right_button_press_time = event.timestamp()
            
            self.right_button_click_count += 1
            
            if self.right_button_click_count == 1:
                if self.right_button_click_timer:
                    self.right_button_click_timer.stop()
                self.right_button_click_timer = QTimer()
                self.right_button_click_timer.setSingleShot(True)
                self.right_button_click_timer.timeout.connect(self._handle_single_right_click)
                # Уменьшаем время таймера для более быстрой реакции
                self.right_button_click_timer.start(200)
            elif self.right_button_click_count == 2:
                if self.right_button_click_timer:
                    self.right_button_click_timer.stop()
                self.right_button_click_count = 0
                pos_point = QPoint(int(event.position().x()), int(event.position().y()))
                self.show_context_menu(pos_point)
                return
        
        elif event.button() == Qt.MiddleButton:
            self.last_mouse_pos = event.position()
    
    def mouseMoveEvent(self, event):
        """Обработчик движения мыши"""
        world_pos = self.viewport.screen_to_world(event.position())
        self.cursor_world_coords = world_pos
        
        # Применяем привязку для отображения при наведении (даже без перетаскивания)
        # Это обновит self.current_snap_point для визуализации
        self._apply_snapping(world_pos)

        # Обновляем виджет для отображения точки привязки
        if self.primitive_type == 'dimension':
            self._build_dimension_preview(world_pos)
        self.update()
        
        self.view_changed.emit()
        
        # Обработка перемещения точек в режиме редактирования
        if self.editing_mode and self.dragging_point and (event.buttons() & Qt.LeftButton):
            obj = self._single_selected_object()
            if obj is not None:
                from widgets.primitives import Circle, Rectangle, Arc, Ellipse, Polygon, Spline
                world_pos = self._apply_snapping(world_pos, exclude_object=obj)
                
                if isinstance(obj, LineSegment):
                    line = obj
                    if self.dragging_point == 'start':
                        line.start_point = QPointF(world_pos)
                        self._update_edit_dialog_line_point('start', world_pos)
                    elif self.dragging_point == 'end':
                        line.end_point = QPointF(world_pos)
                        self._update_edit_dialog_line_point('end', world_pos)
                elif isinstance(obj, Circle):
                    circle = obj
                    if self.dragging_point == 'center':
                        circle.center = QPointF(world_pos)
                        if self.edit_dialog:
                            self._set_point_spin_pair(
                                self.edit_dialog.circle_center_x_spin,
                                self.edit_dialog.circle_center_y_spin,
                                world_pos,
                            )
                    elif self.dragging_point == 'radius':
                        # Вычисляем новый радиус как расстояние от центра до новой позиции
                        dx = world_pos.x() - circle.center.x()
                        dy = world_pos.y() - circle.center.y()
                        new_radius = math.sqrt(dx*dx + dy*dy)
                        # Минимальный радиус
                        if new_radius < 0.01:
                            new_radius = 0.01
                        circle.radius = new_radius
                        if self.edit_dialog:
                            self._set_spin_value_safely(self.edit_dialog.circle_radius_spin, new_radius)
                            self._set_spin_value_safely(self.edit_dialog.circle_diameter_spin, new_radius * 2)
                elif isinstance(obj, Rectangle):
                    from widgets.primitives import Rectangle
                    rect = obj
                    if self.dragging_point == 'center':
                        # Перемещаем весь прямоугольник, сохраняя размеры
                        bbox = rect.get_bounding_box()
                        old_center = QPointF(bbox.center().x(), bbox.center().y())
                        dx = world_pos.x() - old_center.x()
                        dy = world_pos.y() - old_center.y()
                        
                        # Сдвигаем оба угла на одинаковое смещение
                        rect.top_left = QPointF(rect.top_left.x() + dx, rect.top_left.y() + dy)
                        rect.bottom_right = QPointF(rect.bottom_right.x() + dx, rect.bottom_right.y() + dy)
                        self._update_edit_dialog_rectangle(rect)
                    elif self.dragging_point == 'top_left':
                        rect.top_left = QPointF(world_pos)
                        self._update_edit_dialog_rectangle(rect)
                    elif self.dragging_point == 'top_right':
                        rect.top_left = QPointF(rect.top_left.x(), world_pos.y())
                        rect.bottom_right = QPointF(world_pos.x(), rect.bottom_right.y())
                        self._update_edit_dialog_rectangle(rect)
                    elif self.dragging_point == 'bottom_right':
                        rect.bottom_right = QPointF(world_pos)
                        self._update_edit_dialog_rectangle(rect)
                    elif self.dragging_point == 'bottom_left':
                        rect.top_left = QPointF(world_pos.x(), rect.top_left.y())
                        rect.bottom_right = QPointF(rect.bottom_right.x(), world_pos.y())
                        self._update_edit_dialog_rectangle(rect)
                elif isinstance(obj, Arc):
                    arc = obj
                    if self.dragging_point == 'center':
                        # Перемещаем центр дуги
                        arc.center = QPointF(world_pos)
                        if self.edit_dialog:
                            self._set_point_spin_pair(
                                self.edit_dialog.arc_center_x_spin,
                                self.edit_dialog.arc_center_y_spin,
                                world_pos,
                            )
                    elif self.dragging_point == 'radius':
                        # Изменяем радиус дуги
                        # Вычисляем расстояние от центра до новой позиции
                        dx = world_pos.x() - arc.center.x()
                        dy = world_pos.y() - arc.center.y()
                        new_radius = math.sqrt(dx*dx + dy*dy)
                        # Минимальный радиус
                        if new_radius < 0.01:
                            new_radius = 0.01
                        # Сохраняем пропорции радиусов
                        ratio = arc.radius_y / arc.radius_x if arc.radius_x > 0 else 1.0
                        arc.radius_x = new_radius
                        arc.radius_y = new_radius * ratio
                        arc.radius = max(arc.radius_x, arc.radius_y)
                        self._update_edit_dialog_arc_radii(arc.radius_x, arc.radius_y)
                    elif self.dragging_point == 'start_angle':
                        # Изменяем начальный угол
                        dx = world_pos.x() - arc.center.x()
                        dy = world_pos.y() - arc.center.y()
                        # Вычисляем угол в градусах
                        angle_rad = math.atan2(dy, dx)
                        new_angle = math.degrees(angle_rad)
                        # Нормализуем угол в диапазон [0, 360)
                        if new_angle < 0:
                            new_angle += 360
                        arc.start_angle = new_angle
                        self._update_edit_dialog_arc_angles('arc_start_angle_spin', new_angle)
                    elif self.dragging_point == 'end_angle':
                        # Изменяем конечный угол
                        dx = world_pos.x() - arc.center.x()
                        dy = world_pos.y() - arc.center.y()
                        # Вычисляем угол в градусах
                        angle_rad = math.atan2(dy, dx)
                        new_angle = math.degrees(angle_rad)
                        # Нормализуем угол в диапазон [0, 360)
                        if new_angle < 0:
                            new_angle += 360
                        arc.end_angle = new_angle
                        self._update_edit_dialog_arc_angles('arc_end_angle_spin', new_angle)
                elif isinstance(obj, Ellipse):
                    ellipse = obj
                    if self.dragging_point == 'center':
                        # Перемещаем центр эллипса
                        ellipse.center = QPointF(world_pos)
                        if self.edit_dialog:
                            self._set_point_spin_pair(
                                self.edit_dialog.ellipse_center_x_spin,
                                self.edit_dialog.ellipse_center_y_spin,
                                world_pos,
                            )
                    elif self.dragging_point == 'radius_x':
                        # Изменяем горизонтальный радиус
                        dx = world_pos.x() - ellipse.center.x()
                        new_radius_x = abs(dx)
                        # Минимальный радиус
                        if new_radius_x < 0.01:
                            new_radius_x = 0.01
                        ellipse.radius_x = new_radius_x
                        if self.edit_dialog:
                            self._set_spin_value_safely(self.edit_dialog.ellipse_radius_x_spin, new_radius_x)
                    elif self.dragging_point == 'radius_y':
                        # Изменяем вертикальный радиус
                        dy = ellipse.center.y() - world_pos.y()  # Инвертируем, так как Y растет вниз
                        new_radius_y = abs(dy)
                        # Минимальный радиус
                        if new_radius_y < 0.01:
                            new_radius_y = 0.01
                        ellipse.radius_y = new_radius_y
                        if self.edit_dialog:
                            self._set_spin_value_safely(self.edit_dialog.ellipse_radius_y_spin, new_radius_y)
                elif isinstance(obj, Polygon):
                    polygon = obj
                    if self.dragging_point == 'center':
                        # Перемещаем центр многоугольника
                        polygon.center = QPointF(world_pos)
                        if self.edit_dialog:
                            self._set_point_spin_pair(
                                self.edit_dialog.polygon_center_x_spin,
                                self.edit_dialog.polygon_center_y_spin,
                                world_pos,
                            )
                    elif self.dragging_point == 'radius':
                        # Изменяем радиус многоугольника
                        # Вычисляем расстояние от центра до новой позиции
                        dx = world_pos.x() - polygon.center.x()
                        dy = world_pos.y() - polygon.center.y()
                        new_radius = math.sqrt(dx*dx + dy*dy)
                        # Минимальный радиус
                        if new_radius < 0.01:
                            new_radius = 0.01
                        
                        # Для описанного многоугольника нужно пересчитать радиус
                        if hasattr(polygon, 'construction_type') and polygon.construction_type == "circumscribed":
                            # new_radius - это радиус описанной окружности, нужно найти радиус вписанной
                            if polygon.num_vertices > 2:
                                polygon.radius = new_radius * math.cos(math.pi / polygon.num_vertices)
                            else:
                                polygon.radius = new_radius
                        else:
                            # Для вписанного многоугольника new_radius - это и есть нужный радиус
                            polygon.radius = new_radius
                        
                        if self.edit_dialog:
                            self._set_spin_value_safely(self.edit_dialog.polygon_radius_spin, polygon.radius)
                elif isinstance(obj, Spline):
                    spline = obj
                    # Проверяем, какая точка перемещается
                    if self.dragging_point and self.dragging_point.startswith('point_'):
                        try:
                            point_index = int(self.dragging_point.split('_')[1])
                            if 0 <= point_index < len(spline.control_points):
                                # Перемещаем контрольную точку
                                spline.control_points[point_index] = QPointF(world_pos)
                                # Обновляем информацию в окне редактирования
                                if self.edit_dialog:
                                    self.edit_dialog.update_spline_info()
                        except (ValueError, IndexError):
                            pass
                elif isinstance(obj, LinearDimension):
                    if self.dragging_point == 'start':
                        self._clear_dimension_association(obj)
                        obj.start = QPointF(world_pos)
                    elif self.dragging_point == 'end':
                        self._clear_dimension_association(obj)
                        obj.end = QPointF(world_pos)
                    elif self.dragging_point == 'text':
                        constrained = self._constrain_dimension_text_position(obj, QPointF(world_pos))
                        obj.set_text_position(constrained, obj.get_default_text_position())
                    elif self.dragging_point == 'offset':
                        if obj.dimension_type == 'horizontal':
                            reference = max(obj.start.y(), obj.end.y()) if world_pos.y() >= (obj.start.y() + obj.end.y()) / 2.0 else min(obj.start.y(), obj.end.y())
                            obj.offset = world_pos.y() - reference
                        elif obj.dimension_type == 'vertical':
                            reference = max(obj.start.x(), obj.end.x()) if world_pos.x() >= (obj.start.x() + obj.end.x()) / 2.0 else min(obj.start.x(), obj.end.x())
                            obj.offset = world_pos.x() - reference
                        else:
                            dx = obj.end.x() - obj.start.x()
                            dy = obj.end.y() - obj.start.y()
                            length = math.hypot(dx, dy)
                            obj.offset = 0.0 if length < 1e-9 else ((world_pos.x() - obj.start.x()) * (-dy) + (world_pos.y() - obj.start.y()) * dx) / length
                elif isinstance(obj, RadialDimension):
                    if self.dragging_point == 'radius_point':
                        source = getattr(obj, '_source_object', None)
                        if isinstance(source, (Circle, Arc)):
                            snapped = self._radius_point_from_object(source, world_pos)
                            obj.radius_point = QPointF(snapped) if snapped is not None else QPointF(world_pos)
                            obj.center = QPointF(source.center)
                        else:
                            obj.radius_point = QPointF(world_pos)
                    elif self.dragging_point == 'text':
                        constrained = self._constrain_dimension_text_position(obj, QPointF(world_pos))
                        obj.set_text_position(constrained, obj.get_default_text_position())
                    elif self.dragging_point == 'leader':
                        obj.leader_point = QPointF(world_pos)
                elif isinstance(obj, AngularDimension):
                    if self.dragging_point == 'ray_start':
                        self._clear_dimension_association(obj)
                        obj.ray_start = QPointF(world_pos)
                    elif self.dragging_point == 'ray_end':
                        self._clear_dimension_association(obj)
                        obj.ray_end = QPointF(world_pos)
                    elif self.dragging_point == 'text':
                        constrained = self._constrain_dimension_text_position(obj, QPointF(world_pos))
                        obj.set_text_position(constrained, obj.get_default_text_position())
                    elif self.dragging_point == 'radius':
                        obj.radius = max(10.0, math.hypot(world_pos.x() - obj.vertex.x(), world_pos.y() - obj.vertex.y()))

                self.update_associated_dimensions(obj)
                self.update()
                return
        
        # Для сплайна проверяем привязку к начальной точке при создании
        if self.primitive_type == 'spline' and self.scene.is_drawing():
            if len(self.scene._spline_control_points) >= 2:
                # Проверяем расстояние до первой точки
                first_point = self.scene._spline_control_points[0]
                dx = world_pos.x() - first_point.x()
                dy = world_pos.y() - first_point.y()
                distance = math.sqrt(dx*dx + dy*dy)
                tolerance = 10.0 / self.viewport.get_scale()
                
                if distance <= tolerance:
                    # Привязываем к начальной точке для замыкания
                    world_pos = QPointF(first_point)
                    # Устанавливаем специальную точку привязки для визуализации
                    from core.snapping import SnapPoint, SnapType
                    self.current_snap_point = SnapPoint(first_point, SnapType.END, "Начало сплайна")
                    self.update()
                else:
                    # Применяем обычную привязку
                    if not (event.buttons() & Qt.RightButton) and not self.pan_mode and not (event.buttons() & Qt.MiddleButton):
                        self._refresh_snap_hover(world_pos)
            else:
                # Применяем обычную привязку
                if not (event.buttons() & Qt.RightButton) and not self.pan_mode and not (event.buttons() & Qt.MiddleButton):
                    self._refresh_snap_hover(world_pos)
        elif not (event.buttons() & Qt.RightButton) and not self.pan_mode and not (event.buttons() & Qt.MiddleButton):
            # Применяем привязку при наведении мыши (даже если не рисуем)
            # Это нужно для визуализации точек привязки
            # В режиме редактирования исключаем редактируемый объект из привязки
            exclude_obj = self._single_selected_object() if self.editing_mode else None

            # Применяем привязку для визуализации, но не изменяем world_pos если не рисуем
            self._refresh_snap_hover(world_pos, exclude_object=exclude_obj)
        
        # Проверяем, началось ли перетаскивание правой кнопкой
        if (event.buttons() & Qt.RightButton and self.right_button_press_pos):
            delta = (event.position() - self.right_button_press_pos).manhattanLength()
            if delta > 3:
                if self.right_button_click_timer:
                    self.right_button_click_timer.stop()
                self.right_button_click_count = 0
                
                # Начинаем выделение рамкой
                if not self.is_selecting:
                    if not (event.modifiers() & Qt.ControlModifier):
                        self.selection_manager.clear_selection()
                    self.is_selecting = True
                    self.selection_start = self.right_button_press_pos
                    self.selection_end = event.position()
                else:
                    self.selection_end = event.position()
                self.update()
                return
        
        # Обновляем выделение рамкой
        if self.is_selecting and self.selection_start and (event.buttons() & Qt.RightButton):
            self.selection_end = event.position()
            self.update()
            return
        
        if self.pan_mode and event.buttons() & Qt.LeftButton:
            if self.last_mouse_pos:
                delta = event.position() - self.last_mouse_pos
                self.viewport.pan(delta)
                self.last_mouse_pos = event.position()
                self.view_changed.emit()
                self.update()
        elif event.buttons() & Qt.MiddleButton:
            if self.last_mouse_pos:
                delta = event.position() - self.last_mouse_pos
                self.viewport.pan(delta)
                self.last_mouse_pos = event.position()
                self.view_changed.emit()
                self.update()
        elif self.scene.is_drawing():
            # Обновляем объект при движении мыши во время рисования
            world_pos = self.viewport.screen_to_world(event.position())
            
            # Применяем привязку
            world_pos = self._apply_snapping(world_pos)
            self._update_active_drawing_preview(world_pos)
            
            self.update()
    
    def _handle_single_right_click(self):
        """Обрабатывает одинарный клик ПКМ"""
        self.right_button_click_count = 0
        
        # Отменяем рисование, если оно активно
        self._cancel_current_drawing()
        
        # Очищаем выделение рамкой, если оно было начато
        if self.is_selecting:
            self._clear_selection_rect()
            self.update()
        
        self._clear_right_click_state()
    
    def mouseDoubleClickEvent(self, event):
        """Обработчик двойного клика мыши"""
        if event.button() == Qt.LeftButton:
            if not self.pan_mode and self.primitive_type == 'spline' and self.scene.is_drawing():
                # Для сплайна двойной клик завершает создание
                # Удаляем последнюю точку, если она была добавлена при первом клике двойного клика
                if (self.last_left_click_time > 0 and 
                    event.timestamp() - self.last_left_click_time < 300 and
                    len(self.scene._spline_control_points) > 0):
                    # Удаляем последнюю точку, которая была добавлена при первом клике
                    self.scene._spline_control_points.pop()
                    if self.scene._current_object:
                        from widgets.primitives import Spline
                        if isinstance(self.scene._current_object, Spline):
                            self.scene._current_object.control_points = self.scene._spline_control_points.copy()
                
                world_pos = self.viewport.screen_to_world(event.position())
                # Применяем привязку
                world_pos = self._apply_snapping(world_pos)
                
                # Проверяем количество зафиксированных точек
                self._finish_spline_double_click()
                return
        
        # Для остальных случаев вызываем стандартную обработку
        super().mouseDoubleClickEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Обработчик отпускания кнопки мыши"""
        # Завершаем перемещение точки в режиме редактирования
        if event.button() == Qt.LeftButton and self.editing_mode and self.dragging_point:
            self._finish_edit_drag()
            self.update()
            return
        if event.button() == Qt.RightButton:
            # Вычисляем расстояние перемещения от начала нажатия
            if self.right_button_press_pos:
                delta = (event.position() - self.right_button_press_pos).manhattanLength()
            else:
                delta = 0
            
            # Проверяем, было ли движение мыши (выделение рамкой)
            if self.is_selecting and self.selection_start and self.selection_end:
                if delta > 3:  # Было движение - обрабатываем выделение
                    # Преобразуем экранные координаты в мировые
                    start_world = self.viewport.screen_to_world(self.selection_start)
                    end_world = self.viewport.screen_to_world(self.selection_end)
                    
                    from PySide6.QtCore import QRectF
                    selection_rect = QRectF(
                        min(start_world.x(), end_world.x()),
                        min(start_world.y(), end_world.y()),
                        abs(end_world.x() - start_world.x()),
                        abs(end_world.y() - start_world.y())
                    )
                    
                    if selection_rect.width() > 1 and selection_rect.height() > 1:
                        add_to_selection = bool(event.modifiers() & Qt.ControlModifier)
                        self.selection_manager.select_objects_in_rect(
                            selection_rect, self.scene.get_objects(), add_to_selection
                        )
                    
                    # Останавливаем таймер, так как это было выделение, а не клик
                    self._stop_right_click_timer()
                
                # Всегда очищаем выделение рамкой при отпускании
                self._clear_selection_rect()
            else:
                # Не было выделения - проверяем, был ли это клик
                if delta <= 3:
                    # Это был клик без движения - отменяем рисование сразу
                    if self.scene.is_drawing():
                        self._cancel_current_drawing(update=False)
                        # Останавливаем таймер, так как уже обработали
                        self._stop_right_click_timer()
                    # Если таймер еще работает, пусть он тоже сработает (на случай, если рисование не было активно)
                else:
                    # Было движение, но выделение не началось - останавливаем таймер
                    self._stop_right_click_timer()
            
            # Очищаем позицию нажатия
            self._clear_right_click_state()
            self.update()
        
        if event.button() in (Qt.LeftButton, Qt.MiddleButton):
            self.last_mouse_pos = None
    
    def wheelEvent(self, event):
        """Обработчик колесика мыши"""
        zoom_factor = 1.1
        if event.angleDelta().y() > 0:
            self.viewport.zoom_at_point(event.position(), zoom_factor)
        else:
            self.viewport.zoom_at_point(event.position(), 1.0 / zoom_factor)
        self.view_changed.emit()
        self.update()
    
    def set_pan_mode(self, enabled):
        """Устанавливает режим панорамирования"""
        self.pan_mode = enabled
        self.view_changed.emit()
    
    def zoom_in(self):
        """Увеличивает масштаб"""
        self.viewport.zoom_in()
        self.view_changed.emit()
        self.update()
    
    def zoom_out(self):
        """Уменьшает масштаб"""
        self.viewport.zoom_out()
        self.view_changed.emit()
        self.update()
    
    def show_all(self):
        """Показывает все отрезки"""
        points = self.scene.get_all_points()
        if not points:
            self.reset_view()
            return
        
        from PySide6.QtCore import QRectF, QPointF
        
        min_x = min(p.x() for p in points)
        max_x = max(p.x() for p in points)
        min_y = min(p.y() for p in points)
        max_y = max(p.y() for p in points)
        
        scene_center = QPointF((min_x + max_x) / 2, (min_y + max_y) / 2)
        scene_width = max_x - min_x
        scene_height = max_y - min_y
        
        corners = [
            QPointF(min_x, min_y),
            QPointF(max_x, min_y),
            QPointF(max_x, max_y),
            QPointF(min_x, max_y)
        ]
        
        if abs(self.viewport.rotation_angle) > 0.01:
            rotation_transform = QTransform()
            rotation_transform.rotate(self.viewport.rotation_angle)
            
            rotated_corners = []
            for corner in corners:
                relative = corner - scene_center
                rotated_relative = rotation_transform.map(relative)
                rotated_corners.append(rotated_relative + scene_center)
            
            rotated_min_x = min(p.x() for p in rotated_corners)
            rotated_max_x = max(p.x() for p in rotated_corners)
            rotated_min_y = min(p.y() for p in rotated_corners)
            rotated_max_y = max(p.y() for p in rotated_corners)
            
            rotated_width = rotated_max_x - rotated_min_x
            rotated_height = rotated_max_y - rotated_min_y
        else:
            rotated_width = scene_width
            rotated_height = scene_height
        
        padding_x = rotated_width * 0.2 if rotated_width > 0 else 10
        padding_y = rotated_height * 0.2 if rotated_height > 0 else 10
        rotated_width += 2 * padding_x
        rotated_height += 2 * padding_y
        
        widget_width = self.width()
        widget_height = self.height()
        
        if rotated_width <= 0 or rotated_height <= 0:
            new_scale = 1.0
        else:
            scale_x = widget_width / rotated_width
            scale_y = widget_height / rotated_height
            new_scale = min(scale_x, scale_y) * 0.9
            new_scale = max(self.viewport.min_scale, min(self.viewport.max_scale, new_scale))
        
        self.viewport.scale_factor = new_scale
        
        widget_center = QPointF(self.width() / 2, self.height() / 2)
        
        rotation_scale_transform = QTransform()
        rotation_scale_transform.rotate(self.viewport.rotation_angle)
        rotation_scale_transform.scale(self.viewport.scale_factor, -self.viewport.scale_factor)
        inv_rotation_scale, success = rotation_scale_transform.inverted()
        
        if success:
            rotated_scaled_center = rotation_scale_transform.map(scene_center)
            self.viewport.translation = QPointF(-rotated_scaled_center.x(), -rotated_scaled_center.y())
        else:
            self.viewport.translation = QPointF(-scene_center.x() * self.viewport.scale_factor, 
                                              scene_center.y() * self.viewport.scale_factor)
        
        self.view_changed.emit()
        self.update()
    
    def show_all_preserve_rotation(self):
        """Альтернатива show_all, которая сохраняет текущий поворот"""
        self.show_all()
    
    def reset_view(self):
        """Полностью сбрасывает вид к начальному состоянию"""
        self.viewport.reset()
        self.view_changed.emit()
        self.update()
    
    def rotate_left(self, angle=15):
        """Поворот налево на указанный угол"""
        self.viewport.rotate(angle)
        self.view_changed.emit()
        self.update()
    
    def rotate_right(self, angle=15):
        """Поворот направо на указанный угол"""
        self.viewport.rotate(-angle)
        self.view_changed.emit()
        self.update()
    
    def get_cursor_world_coords(self):
        """Возвращает координаты курсора в мировых координатах"""
        return self.cursor_world_coords
    
    def get_scale(self):
        """Возвращает текущий масштаб"""
        return self.viewport.get_scale()
    
    def get_rotation(self):
        """Возвращает текущий угол поворота"""
        return self.viewport.get_rotation()
    
    def start_new_line(self):
        """Начинает новый отрезок"""
        if self.scene.is_drawing():
            self.scene.finish_drawing()
        self.update()
    
    def delete_last_line(self):
        """Удаляет последний отрезок"""
        self.scene.delete_last_object()
        self.update()
    
    def delete_all_lines(self):
        """Удаляет все отрезки"""
        self.scene.clear()
        self.update()
    
    def set_grid_step(self, step_mm):
        """Устанавливает шаг сетки в миллиметрах"""
        self.renderer.set_grid_step(step_mm)
        self.update()
    
    def set_line_color(self, color):
        """Устанавливает цвет линии"""
        self.line_color = color
        self.update()
    
    def set_background_color(self, color):
        """Устанавливает цвет фона"""
        self.renderer.background_color = color
        self.update()
    
    def set_grid_color(self, color):
        """Устанавливает цвет сетки"""
        self.renderer.grid_color = color
        self.update()
    
    def set_line_width(self, width):
        """Устанавливает ширину линии (устаревший метод)"""
        self.line_width = width
        self.update()
    
    def get_current_points(self):
        """Возвращает текущие точки"""
        current_line = self.scene.get_current_line()
        if current_line:
            return current_line.start_point, current_line.end_point
        lines = self.scene.get_lines()
        if lines:
            last_line = lines[-1]
            return last_line.start_point, last_line.end_point
        from PySide6.QtCore import QPointF
        return QPointF(0, 0), QPointF(0, 0)
    
    def set_points_from_input(self, start_point, end_point, apply=False):
        """Устанавливает точки из ввода (для обратной совместимости с отрезками)"""
        # Создаем предпросмотр/объект только для отрезков
        if self.primitive_type != 'line':
            return

        style = self._current_style()
        
        if apply:
            new_line = LineSegment(start_point, end_point, style=style,
                                  color=self.line_color, width=self.line_width)
            self._apply_legacy_color_if_supported(new_line)
            layer_name = self._current_layer_name()
            if layer_name is not None:
                new_line.layer_name = layer_name
            self.scene.add_object(new_line)
            self.update()
        else:
            if not self.scene.is_drawing():
                self.scene.start_drawing(
                    start_point,
                    drawing_type='line',
                    style=style,
                    color=self.line_color,
                    width=self.line_width,
                    layer_name=self._current_layer_name(),
                )
                current_obj = self.scene.get_current_object()
                if current_obj:
                    self.scene.update_current_object(end_point)
                    self._apply_legacy_color_if_supported(current_obj)
            else:
                current_obj = self.scene.get_current_object()
                if current_obj and isinstance(current_obj, LineSegment):
                    current_obj.start_point = start_point
                    current_obj.end_point = end_point
                    if style and not current_obj.style:
                        current_obj.style = style
                    self._apply_legacy_color_if_supported(current_obj)
            self.update()
    
    def set_primitive_type(self, primitive_type: str):
        """Устанавливает тип создаваемого примитива"""
        self.primitive_type = primitive_type
        if primitive_type != 'dimension':
            self.dimension_points = []
            self.dimension_line_refs = []
            self.dimension_preview_object = None
    
    def set_circle_creation_method(self, method: str):
        """Устанавливает метод создания окружности"""
        self.circle_creation_method = method
    
    def set_arc_creation_method(self, method: str):
        """Устанавливает метод создания дуги"""
        self.arc_creation_method = method
    
    def set_rectangle_creation_method(self, method: str):
        """Устанавливает метод создания прямоугольника"""
        self.rectangle_creation_method = method
    
    def set_ellipse_creation_method(self, method: str):
        """Устанавливает метод создания эллипса"""
        # Метод сохраняется для будущего использования
        # В данный момент эллипс создается через три точки в сцене
        pass
    
    def set_polygon_creation_method(self, method: str):
        """Устанавливает метод создания многоугольника"""
        self.polygon_creation_method = method
    
    def set_polygon_num_vertices(self, num_vertices: int):
        """Устанавливает количество вершин многоугольника"""
        if num_vertices >= 3:
            self.polygon_num_vertices = num_vertices
            # Обновляем текущий объект, если он существует
            if self.scene.is_drawing() and self.scene._drawing_type == 'polygon':
                self.scene.set_polygon_num_vertices(num_vertices)
                self.update()
    
    def set_dimension_creation_type(self, dimension_type: str):
        self.dimension_creation_type = dimension_type
        self._reset_dimension_creation_state()
        self.update()

    def _find_dimension_target_object(self, world_pos: QPointF):
        return self.selection_manager.find_object_at_point(
            world_pos,
            self.scene.get_objects(),
            tolerance=10.0 / max(self.viewport.get_scale(), 1e-6),
        )

    def _radius_point_from_object(self, obj, world_pos: QPointF) -> QPointF | None:
        if not hasattr(obj, 'center'):
            return None
        center = obj.center
        radius = getattr(obj, 'radius', 0.0)
        dx = world_pos.x() - center.x()
        dy = world_pos.y() - center.y()
        length = math.hypot(dx, dy)
        if radius <= 0 or length < 1e-9:
            return None
        return QPointF(center.x() + dx / length * radius, center.y() + dy / length * radius)

    def _infer_linear_dimension_source(self, start: QPointF, end: QPointF):
        tolerance = 1e-3
        for obj in self.scene.get_objects():
            if not isinstance(obj, LineSegment):
                continue
            same_order = (
                math.hypot(obj.start_point.x() - start.x(), obj.start_point.y() - start.y()) <= tolerance and
                math.hypot(obj.end_point.x() - end.x(), obj.end_point.y() - end.y()) <= tolerance
            )
            reverse_order = (
                math.hypot(obj.start_point.x() - end.x(), obj.start_point.y() - end.y()) <= tolerance and
                math.hypot(obj.end_point.x() - start.x(), obj.end_point.y() - start.y()) <= tolerance
            )
            if same_order or reverse_order:
                return obj
        return None

    def _linear_dimension_offset(self, start: QPointF, end: QPointF, reference_point: QPointF, dim_type: str) -> float:
        """Вычисляет смещение линейного размера по точке размещения."""
        if dim_type == 'horizontal':
            mid_y = (start.y() + end.y()) / 2.0
            base_y = max(start.y(), end.y()) if reference_point.y() >= mid_y else min(start.y(), end.y())
            return reference_point.y() - base_y
        if dim_type == 'vertical':
            mid_x = (start.x() + end.x()) / 2.0
            base_x = max(start.x(), end.x()) if reference_point.x() >= mid_x else min(start.x(), end.x())
            return reference_point.x() - base_x

        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy)
        if length < 1e-9:
            return 0.0
        return ((reference_point.x() - start.x()) * (-dy) + (reference_point.y() - start.y()) * dx) / length

    def _dimension_radius_from_point(self, vertex: QPointF, point: QPointF, scale: float = 1.0) -> float:
        """Вычисляет радиус размерной дуги/выноски по точке размещения."""
        return max(10.0, math.hypot(point.x() - vertex.x(), point.y() - vertex.y()) * scale)

    def _arc_mid_angle(self, start_angle: float, end_angle: float) -> float:
        """Возвращает средний угол дуги с учетом перехода через 360 градусов."""
        mid_angle = (start_angle + end_angle) / 2.0
        if start_angle > end_angle:
            span = (360.0 - start_angle) + end_angle
            mid_angle = (start_angle + span / 2.0) % 360.0
        return mid_angle

    def _reset_dimension_creation_state(self):
        """Сбрасывает временное состояние создания размера."""
        self.dimension_points = []
        self.dimension_line_refs = []
        self.input_points = []
        self.dimension_preview_object = None

    def _angular_dimension_from_line_refs(self, line1: LineSegment, click1: QPointF, line2: LineSegment, click2: QPointF):
        """Подготавливает общие данные углового размера между двумя линиями."""
        vertex = self._line_intersection(line1, line2)
        if vertex is None:
            return None

        end_key1 = self._preferred_line_end_key(line1, click1)
        end_key2 = self._preferred_line_end_key(line2, click2)
        ray_start = self._ray_point_from_line_reference(line1, vertex, end_key1, click1)
        ray_end = self._ray_point_from_line_reference(line2, vertex, end_key2, click2)
        return vertex, ray_start, ray_end, end_key1, end_key2

    def _build_dimension_preview(self, world_pos: QPointF):
        dim_type = self.dimension_creation_type
        preview = None

        if dim_type in ('horizontal', 'vertical', 'aligned') and len(self.dimension_points) >= 2:
            start, end = self.dimension_points[:2]
            offset = self._linear_dimension_offset(start, end, world_pos, dim_type)
            preview = LinearDimension(start, end, dimension_type=dim_type, offset=offset)
        elif dim_type in ('radius', 'diameter') and len(self.dimension_points) >= 2:
            center, radius_point = self.dimension_points[:2]
            preview = RadialDimension(center, radius_point, dimension_type=dim_type, leader_point=world_pos)
        elif dim_type == 'angle':
            if len(self.dimension_line_refs) >= 2:
                line1, click1 = self.dimension_line_refs[0]
                line2, click2 = self.dimension_line_refs[1]
                angle_data = self._angular_dimension_from_line_refs(line1, click1, line2, click2)
                if angle_data is not None:
                    vertex, ray_start, ray_end, _, _ = angle_data
                    radius = self._dimension_radius_from_point(vertex, world_pos)
                    preview = AngularDimension(vertex, ray_start, ray_end, radius=radius)
            elif len(self.dimension_points) >= 2:
                vertex, ray_start = self.dimension_points[:2]
                preview = AngularDimension(vertex, ray_start, world_pos, radius=self._dimension_radius_from_point(vertex, world_pos, 0.6))

        self.dimension_preview_object = preview

    def _linear_dimension_offset_handle(self, obj: LinearDimension) -> QPointF:
        geom = obj._geometry()
        arrow1_tip = geom[6]
        arrow2_tip = geom[7]
        return QPointF((arrow1_tip.x() + arrow2_tip.x()) / 2.0, (arrow1_tip.y() + arrow2_tip.y()) / 2.0)

    def _linear_dimension_start_handle(self, obj: LinearDimension) -> QPointF:
        return QPointF(obj.start)

    def _linear_dimension_end_handle(self, obj: LinearDimension) -> QPointF:
        return QPointF(obj.end)

    def _angular_dimension_radius_handle(self, obj: AngularDimension) -> QPointF:
        a1, a2, span = obj._angles()
        mid_angle = a1 + span / 2.0
        return QPointF(
            obj.vertex.x() + obj.radius * math.cos(mid_angle),
            obj.vertex.y() + obj.radius * math.sin(mid_angle),
        )

    def _radial_dimension_attachment_handle(self, obj: RadialDimension) -> QPointF:
        return QPointF(obj.radius_point)

    def _angular_dimension_start_handle(self, obj: AngularDimension) -> QPointF:
        return QPointF(obj.ray_start)

    def _angular_dimension_end_handle(self, obj: AngularDimension) -> QPointF:
        return QPointF(obj.ray_end)

    def _clear_dimension_association(self, obj):
        if isinstance(obj, LinearDimension):
            obj._source_object = None
        elif isinstance(obj, AngularDimension):
            obj._source_lines = None
            obj._source_line_clicks = None
            obj._source_line_end_keys = None

    def _dimension_text_handle(self, obj) -> QPointF:
        if hasattr(obj, 'get_text_position'):
            return QPointF(obj.get_text_position())
        return QPointF()

    def _dimension_grips(self, obj):
        grips = []
        if isinstance(obj, LinearDimension):
            grips.extend([
                ('start', self._linear_dimension_start_handle(obj), QColor(0, 255, 0)),
                ('end', self._linear_dimension_end_handle(obj), QColor(255, 0, 0)),
                ('offset', self._linear_dimension_offset_handle(obj), QColor(180, 0, 180)),
                ('text', self._dimension_text_handle(obj), QColor(0, 180, 255)),
            ])
        elif isinstance(obj, RadialDimension):
            grips.append(('radius_point', self._radial_dimension_attachment_handle(obj), QColor(255, 165, 0)))
            leader_handle = QPointF(obj.leader_point) if obj.leader_point is not None else QPointF(obj.radius_point)
            grips.append(('leader', leader_handle, QColor(180, 0, 180)))
            grips.append(('text', self._dimension_text_handle(obj), QColor(0, 180, 255)))
        elif isinstance(obj, AngularDimension):
            grips.extend([
                ('ray_start', self._angular_dimension_start_handle(obj), QColor(0, 255, 0)),
                ('ray_end', self._angular_dimension_end_handle(obj), QColor(255, 0, 0)),
                ('radius', self._angular_dimension_radius_handle(obj), QColor(180, 0, 180)),
                ('text', self._dimension_text_handle(obj), QColor(0, 180, 255)),
            ])
        return grips

    def _draw_dimension_grips(self, painter, obj, point_radius: float):
        for grip_name, grip_world, color in self._dimension_grips(obj):
            grip_screen = self.viewport.world_to_screen(grip_world)
            painter.setPen(QPen(color, 2))
            painter.setBrush(QColor(color.red(), color.green(), color.blue(), 200))
            painter.drawEllipse(grip_screen, point_radius, point_radius)
            if self.dragging_point == grip_name:
                painter.setPen(QPen(color, 3))
                painter.setBrush(QColor(color.red(), color.green(), color.blue(), 150))
                painter.drawEllipse(grip_screen, point_radius + 3, point_radius + 3)

    def _try_start_dimension_grip_drag(self, obj, world_pos: QPointF, tolerance: float) -> bool:
        for grip_name, grip_world, _ in self._dimension_grips(obj):
            if self._distance_to_point(world_pos, grip_world) <= tolerance:
                self._begin_drag(grip_name, world_pos)
                return True
        return False

    def _single_selected_object(self):
        """Возвращает единственный выделенный объект или None."""
        selected = self.selection_manager.get_selected_objects()
        if len(selected) != 1:
            return None
        return selected[0]

    def _editing_tolerance(self) -> float:
        """Толерантность захвата editing-grip в мировых координатах."""
        return 10.0 / self.viewport.get_scale()

    def _distance_to_point(self, world_pos: QPointF, point: QPointF) -> float:
        """Расстояние между двумя мировыми точками."""
        return math.hypot(world_pos.x() - point.x(), world_pos.y() - point.y())

    def _begin_drag(self, grip_name: str, world_pos: QPointF):
        """Запускает перетаскивание editing-grip."""
        self.dragging_point = grip_name
        self.drag_start_pos = world_pos
        if self.edit_dialog:
            self.edit_dialog.set_dragging_point(grip_name)

    def _try_start_named_point_drag(self, world_pos: QPointF, tolerance: float, named_points) -> bool:
        """Запускает drag для ближайшей контрольной точки из списка."""
        best_name = None
        best_distance = None

        for grip_name, point in named_points:
            distance = self._distance_to_point(world_pos, point)
            if best_distance is None or distance < best_distance:
                best_name = grip_name
                best_distance = distance

        if best_distance is not None and best_distance <= tolerance:
            self._begin_drag(best_name, world_pos)
            return True

        return False

    def _set_spin_value_safely(self, spin_box, value: float):
        """Обновляет spin-box без лишних сигналов."""
        spin_box.blockSignals(True)
        spin_box.setValue(value)
        spin_box.blockSignals(False)

    def _set_point_spin_pair(self, spin_x, spin_y, point: QPointF):
        """Обновляет пару spin-box для координат точки."""
        self._set_spin_value_safely(spin_x, point.x())
        self._set_spin_value_safely(spin_y, point.y())

    def _update_edit_dialog_line_point(self, prefix: str, point: QPointF):
        """Синхронизирует точку отрезка с окном редактирования."""
        if not self.edit_dialog:
            return
        self._set_point_spin_pair(
            getattr(self.edit_dialog, f'{prefix}_x_spin'),
            getattr(self.edit_dialog, f'{prefix}_y_spin'),
            point,
        )
        if self.edit_dialog.polar_group.isVisible():
            self.edit_dialog.update_polar_from_cartesian()

    def _update_edit_dialog_rectangle(self, rect):
        """Синхронизирует параметры прямоугольника с окном редактирования."""
        if not self.edit_dialog:
            return
        self._set_point_spin_pair(
            self.edit_dialog.rect_top_left_x_spin,
            self.edit_dialog.rect_top_left_y_spin,
            rect.top_left,
        )
        self._set_point_spin_pair(
            self.edit_dialog.rect_bottom_right_x_spin,
            self.edit_dialog.rect_bottom_right_y_spin,
            rect.bottom_right,
        )
        bbox = rect.get_bounding_box()
        self._set_spin_value_safely(self.edit_dialog.rect_width_spin, bbox.width())
        self._set_spin_value_safely(self.edit_dialog.rect_height_spin, bbox.height())

    def _update_edit_dialog_arc_angles(self, attr_name: str, angle: float):
        """Синхронизирует один из углов дуги с окном редактирования."""
        if not self.edit_dialog:
            return
        self._set_spin_value_safely(getattr(self.edit_dialog, attr_name), angle)

    def _update_edit_dialog_arc_radii(self, radius_x: float, radius_y: float):
        """Синхронизирует радиусы дуги с окном редактирования."""
        if not self.edit_dialog:
            return
        self._set_spin_value_safely(self.edit_dialog.arc_radius_x_spin, radius_x)
        self._set_spin_value_safely(self.edit_dialog.arc_radius_y_spin, radius_y)

    def _emit_line_finished_if_created(self, obj) -> bool:
        """Эмитит сигнал завершения, если объект успешно создан."""
        if obj:
            self.line_finished.emit()
            return True
        return False

    def _apply_legacy_color_if_supported(self, obj):
        """Проставляет legacy-цвет объекту, если он поддерживается."""
        if obj and hasattr(obj, '_legacy_color'):
            obj._legacy_color = self.line_color

    def _finish_current_drawing(self) -> bool:
        """Завершает текущее рисование и эмитит сигнал при успехе."""
        return self._emit_line_finished_if_created(self.scene.finish_drawing())

    def _update_current_object_if_present(self, world_pos: QPointF) -> bool:
        """Обновляет текущий объект, если он уже существует."""
        current_obj = self.scene.get_current_object()
        if current_obj:
            self.scene.update_current_object(world_pos)
            return True
        return False

    def _update_and_finish_current_drawing(self, world_pos: QPointF, *, require_current_object: bool = False) -> bool:
        """Обновляет текущий объект и завершает построение."""
        updated = self._update_current_object_if_present(world_pos)
        if require_current_object and not updated:
            return False
        return self._finish_current_drawing()

    def _current_drawing_kwargs(self) -> dict:
        """Собирает дополнительные параметры для старта рисования текущего примитива."""
        kwargs = {}
        if self.primitive_type == 'circle':
            kwargs['circle_method'] = self.circle_creation_method
        elif self.primitive_type == 'arc':
            kwargs['arc_method'] = self.arc_creation_method
        elif self.primitive_type == 'rectangle':
            kwargs['rectangle_method'] = self.rectangle_creation_method
        elif self.primitive_type == 'polygon':
            kwargs['polygon_method'] = self.polygon_creation_method
            kwargs['num_vertices'] = self.polygon_num_vertices
        return kwargs

    def _current_layer_name(self):
        """Возвращает имя текущего слоя или None."""
        if self.layer_manager:
            return self.layer_manager.get_current_layer_name()
        return None

    def _current_style(self):
        """Возвращает текущий активный стиль или None."""
        if self.style_manager:
            return self.style_manager.get_current_style()
        return None

    def _start_new_drawing(self, world_pos: QPointF):
        """Запускает создание нового примитива и обновляет preview."""
        self.selection_manager.clear_selection()
        self.scene.start_drawing(
            world_pos,
            drawing_type=self.primitive_type,
            style=self._current_style(),
            color=self.line_color,
            width=self.line_width,
            layer_name=self._current_layer_name(),
            **self._current_drawing_kwargs(),
        )
        if self.primitive_type == 'rectangle':
            self.rectangle_drawing_started.emit(self.rectangle_creation_method)
        self._update_current_object_if_present(world_pos)
        self._apply_legacy_color_if_supported(self.scene.get_current_object())

    def _refresh_snap_hover(self, world_pos: QPointF, exclude_object=None):
        """Обновляет визуализацию привязки и перерисовывает виджет только при изменении состояния."""
        had_snap_point = self.current_snap_point is not None
        self._apply_snapping(world_pos, exclude_object=exclude_object)
        has_snap_point = self.current_snap_point is not None
        if had_snap_point != has_snap_point:
            self.update()

    def _update_active_drawing_preview(self, world_pos: QPointF):
        """Обновляет preview текущего примитива во время рисования."""
        if self.primitive_type == 'arc':
            method = self.arc_creation_method
            if method == 'three_points':
                if self.scene._arc_end_point is None:
                    self.scene._temp_arc_end_point = world_pos
                self.scene.update_current_object(world_pos)
            elif method == 'center_angles' and self.scene._arc_radius == 0.0:
                self.scene.update_current_object(world_pos)
            return

        if self.primitive_type == 'circle':
            self.scene.update_current_object(world_pos)
            return

        if self.primitive_type == 'ellipse':
            if hasattr(self.scene, '_ellipse_end_point') and self.scene._ellipse_end_point is None:
                self.scene._temp_ellipse_end_point = world_pos
            self.scene.update_current_object(world_pos)
            return

        self.scene.update_current_object(world_pos)

    def _cancel_current_drawing(self, *, update: bool = True):
        """Отменяет текущее рисование, если оно активно."""
        if self.scene.is_drawing():
            self.scene.cancel_drawing()
            if update:
                self.update()

    def _clear_selection_rect(self):
        """Сбрасывает состояние выделения рамкой."""
        self.is_selecting = False
        self.selection_start = None
        self.selection_end = None

    def _clear_right_click_state(self):
        """Сбрасывает состояние правой кнопки мыши."""
        self.right_button_press_pos = None
        self.right_button_press_time = None

    def _stop_right_click_timer(self):
        """Останавливает таймер правого клика и сбрасывает счетчик."""
        if self.right_button_click_timer:
            self.right_button_click_timer.stop()
        self.right_button_click_count = 0

    def _finish_edit_drag(self):
        """Завершает перетаскивание editing-grip."""
        self.dragging_point = None
        self.drag_start_pos = None
        if self.edit_dialog:
            self.edit_dialog.set_dragging_point(None)

    def _finish_spline_double_click(self) -> bool:
        """Завершает построение сплайна по двойному клику."""
        if len(self.scene._spline_control_points) >= 2:
            self._finish_current_drawing()
        else:
            self._cancel_current_drawing(update=False)
        self.update()
        self.last_left_click_time = 0
        self.last_left_click_pos = None
        return True

    def _constrain_dimension_text_position(self, obj, world_pos: QPointF) -> QPointF:
        current = self._dimension_text_handle(obj)

        if isinstance(obj, LinearDimension):
            if obj.dimension_type == 'horizontal':
                return QPointF(world_pos.x(), current.y())
            if obj.dimension_type == 'vertical':
                return QPointF(current.x(), world_pos.y())
            dx = obj.end.x() - obj.start.x()
            dy = obj.end.y() - obj.start.y()
        elif isinstance(obj, RadialDimension):
            if obj.leader_point is not None:
                dx = obj.leader_point.x() - obj.center.x()
                dy = obj.leader_point.y() - obj.center.y()
            else:
                dx = obj.radius_point.x() - obj.center.x()
                dy = obj.radius_point.y() - obj.center.y()
        elif isinstance(obj, AngularDimension):
            angle_deg = obj.get_text_angle() if hasattr(obj, 'get_text_angle') else 0.0
            angle_rad = math.radians(angle_deg)
            dx = math.cos(angle_rad)
            dy = math.sin(angle_rad)
        else:
            return QPointF(world_pos)

        length = math.hypot(dx, dy)
        if length < 1e-9:
            return QPointF(world_pos)

        ux = dx / length
        uy = dy / length
        projection = (world_pos.x() - current.x()) * ux + (world_pos.y() - current.y()) * uy
        return QPointF(current.x() + ux * projection, current.y() + uy * projection)

    def _preferred_line_end_key(self, line: LineSegment, click_point: QPointF) -> str:
        start_dist = math.hypot(line.start_point.x() - click_point.x(), line.start_point.y() - click_point.y())
        end_dist = math.hypot(line.end_point.x() - click_point.x(), line.end_point.y() - click_point.y())
        return 'start' if start_dist <= end_dist else 'end'

    def _ray_point_from_line_reference(self, line: LineSegment, vertex: QPointF, preferred_key: str | None = None, click_point: QPointF | None = None) -> QPointF:
        preferred = line.start_point if preferred_key != 'end' else line.end_point
        alternate = line.end_point if preferred == line.start_point else line.start_point
        dx = preferred.x() - vertex.x()
        dy = preferred.y() - vertex.y()
        length = math.hypot(dx, dy)
        if length < 1e-9:
            dx = alternate.x() - vertex.x()
            dy = alternate.y() - vertex.y()
            length = math.hypot(dx, dy)
        if length < 1e-9 and click_point is not None:
            dx = click_point.x() - vertex.x()
            dy = click_point.y() - vertex.y()
            length = math.hypot(dx, dy)
        if length < 1e-9:
            dx = line.end_point.x() - line.start_point.x()
            dy = line.end_point.y() - line.start_point.y()
            length = math.hypot(dx, dy)
        if length < 1e-9:
            return QPointF(vertex)
        scale = max(20.0, min(line.get_bounding_box().width() + line.get_bounding_box().height(), 100.0)) / length
        return QPointF(vertex.x() + dx * scale, vertex.y() + dy * scale)

    def _sync_associated_dimensions(self, changed_obj=None):
        for obj in self.scene.get_objects():
            if isinstance(obj, LinearDimension):
                source = getattr(obj, '_source_object', None)
                if isinstance(source, LineSegment) and (changed_obj is None or source is changed_obj):
                    obj.start = QPointF(source.start_point)
                    obj.end = QPointF(source.end_point)
            elif isinstance(obj, RadialDimension):
                source = getattr(obj, '_source_object', None)
                if isinstance(source, (Circle, Arc)) and (changed_obj is None or source is changed_obj):
                    axis_point = obj.leader_point if obj.leader_point is not None else obj.radius_point
                    radius_point = self._radius_point_from_object(source, axis_point)
                    if radius_point is not None:
                        obj.center = QPointF(source.center)
                        obj.radius_point = QPointF(radius_point)
            elif isinstance(obj, AngularDimension):
                source_lines = getattr(obj, '_source_lines', None)
                source_clicks = getattr(obj, '_source_line_clicks', None)
                source_end_keys = getattr(obj, '_source_line_end_keys', None)
                if not source_lines or not source_clicks:
                    continue

                line1, line2 = source_lines
                click1, click2 = source_clicks
                if not isinstance(line1, LineSegment) or not isinstance(line2, LineSegment):
                    continue
                if changed_obj is not None and changed_obj not in source_lines:
                    continue

                vertex = self._line_intersection(line1, line2)
                if vertex is None:
                    continue

                obj.vertex = QPointF(vertex)
                key1 = source_end_keys[0] if source_end_keys else None
                key2 = source_end_keys[1] if source_end_keys else None
                obj.ray_start = self._ray_point_from_line_reference(line1, vertex, key1, click1)
                obj.ray_end = self._ray_point_from_line_reference(line2, vertex, key2, click2)

    def update_associated_dimensions(self, changed_obj):
        self._sync_associated_dimensions(changed_obj)
        self.update()

    def _find_radial_dimension_target(self, world_pos: QPointF):
        tolerance = 10.0 / max(self.viewport.get_scale(), 1e-6)
        best_match = None
        best_distance = float('inf')

        for obj in reversed(self.scene.get_objects()):
            if not isinstance(obj, (Circle, Arc)):
                continue
            radius_point = self._radius_point_from_object(obj, world_pos)
            if radius_point is None:
                continue

            center = obj.center
            radial_distance = abs(math.hypot(world_pos.x() - center.x(), world_pos.y() - center.y()) - getattr(obj, 'radius', 0.0))

            candidates = [radius_point]
            if isinstance(obj, Circle):
                candidates.extend([
                    QPointF(center.x() + obj.radius, center.y()),
                    QPointF(center.x() - obj.radius, center.y()),
                    QPointF(center.x(), center.y() + obj.radius),
                    QPointF(center.x(), center.y() - obj.radius),
                ])
            elif isinstance(obj, Arc):
                candidates.extend([
                    obj.get_point_at_angle(obj.start_angle),
                    obj.get_point_at_angle(obj.end_angle),
                ])
                candidates.append(obj.get_point_at_angle(self._arc_mid_angle(obj.start_angle, obj.end_angle)))

            point_distance = min(
                math.hypot(world_pos.x() - candidate.x(), world_pos.y() - candidate.y())
                for candidate in candidates
            )
            match_distance = min(radial_distance, point_distance)
            if match_distance <= tolerance and match_distance < best_distance:
                best_match = (obj, radius_point)
                best_distance = match_distance

        return best_match

    def _finalize_dimension(self, obj):
        if obj:
            self._reset_dimension_creation_state()
            self.line_finished.emit()
            self.update()

    def _line_intersection(self, line1: LineSegment, line2: LineSegment) -> QPointF | None:
        x1, y1 = line1.start_point.x(), line1.start_point.y()
        x2, y2 = line1.end_point.x(), line1.end_point.y()
        x3, y3 = line2.start_point.x(), line2.start_point.y()
        x4, y4 = line2.end_point.x(), line2.end_point.y()
        denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if abs(denom) < 1e-9:
            return None
        px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / denom
        py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / denom
        return QPointF(px, py)

    def _ray_point_from_line_click(self, line: LineSegment, vertex: QPointF, click_point: QPointF) -> QPointF:
        preferred_key = self._preferred_line_end_key(line, click_point)
        return self._ray_point_from_line_reference(line, vertex, preferred_key, click_point)

    def _handle_dimension_click(self, world_pos: QPointF):
        selected_obj = self._find_dimension_target_object(world_pos)
        dim_type = self.dimension_creation_type

        if dim_type in ('radius', 'diameter') and not self.dimension_points:
            radial_target = None
            if isinstance(selected_obj, (Circle, Arc)):
                radius_point = self._radius_point_from_object(selected_obj, world_pos)
                if radius_point is not None:
                    radial_target = (selected_obj, radius_point)
            if radial_target is None:
                radial_target = self._find_radial_dimension_target(world_pos)
            if radial_target is not None:
                target_obj, radius_point = radial_target
                self.dimension_points = [QPointF(target_obj.center), QPointF(radius_point)]
                self.input_points = [QPointF(radius_point)]
                self.update()
                return

        if dim_type == 'angle' and len(self.dimension_line_refs) < 2 and isinstance(selected_obj, LineSegment):
            self.dimension_line_refs.append((selected_obj, QPointF(world_pos)))
            self.input_points = [QPointF(item[1]) for item in self.dimension_line_refs]
            self.update()
            return

        self.dimension_points.append(QPointF(world_pos))
        self.input_points = [QPointF(p) for p in self.dimension_points]

        if dim_type in ('horizontal', 'vertical', 'aligned') and len(self.dimension_points) >= 3:
            start, end, offset_point = self.dimension_points[:3]
            offset = self._linear_dimension_offset(start, end, offset_point, dim_type)
            obj = self.scene.add_linear_dimension(start, end, dimension_type=dim_type, offset=offset)
            obj._source_object = self._infer_linear_dimension_source(start, end)
            self._finalize_dimension(obj)
            return

        if dim_type in ('radius', 'diameter') and len(self.dimension_points) >= 3:
            center, radius_point, leader_point = self.dimension_points[:3]
            obj = self.scene.add_radial_dimension(center, radius_point, dimension_type=dim_type, leader_point=leader_point)
            radial_target = self._find_radial_dimension_target(radius_point)
            obj._source_object = radial_target[0] if radial_target is not None else None
            self._finalize_dimension(obj)
            return

        if dim_type == 'angle':
            if len(self.dimension_line_refs) >= 2 and len(self.dimension_points) >= 1:
                line1, click1 = self.dimension_line_refs[0]
                line2, click2 = self.dimension_line_refs[1]
                angle_data = self._angular_dimension_from_line_refs(line1, click1, line2, click2)
                if angle_data is not None:
                    vertex, ray_start, ray_end, end_key1, end_key2 = angle_data
                    placement = self.dimension_points[0]
                    radius = self._dimension_radius_from_point(vertex, placement)
                    obj = self.scene.add_angular_dimension(vertex, ray_start, ray_end, radius=radius)
                    obj._source_lines = (line1, line2)
                    obj._source_line_clicks = (QPointF(click1), QPointF(click2))
                    obj._source_line_end_keys = (end_key1, end_key2)
                    self._finalize_dimension(obj)
                    return
            elif len(self.dimension_points) >= 3:
                vertex, ray_start, ray_end = self.dimension_points[:3]
                dist1 = math.hypot(ray_start.x() - vertex.x(), ray_start.y() - vertex.y())
                dist2 = math.hypot(ray_end.x() - vertex.x(), ray_end.y() - vertex.y())
                positive = [distance for distance in (dist1, dist2) if distance > 1e-9]
                radius = min(positive) if positive else 20.0
                obj = self.scene.add_angular_dimension(vertex, ray_start, ray_end, radius=max(10.0, radius * 0.6))
                self._finalize_dimension(obj)
                return

        self.update()

    # Свойства для обратной совместимости
    @property
    def lines(self):
        """Свойство для обратной совместимости"""
        return self.scene.get_lines()
    
    @property
    def current_line(self):
        """Свойство для обратной совместимости"""
        return self.scene.get_current_line()
    
    @property
    def is_drawing(self):
        """Свойство для обратной совместимости"""
        return self.scene.is_drawing()
    
    @property
    def selected_lines(self):
        """Свойство для обратной совместимости"""
        return self.selection_manager.get_selected_lines()
