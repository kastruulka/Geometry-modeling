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


class CoordinateSystemWidget(QWidget):
    """Виджет для отображения и взаимодействия с системой координат"""
    
    view_changed = Signal()  # сигнал при изменении вида
    context_menu_requested = Signal(QPoint)  # сигнал для запроса контекстного меню
    selection_changed = Signal(list)  # сигнал при изменении выделения
    line_finished = Signal()  # сигнал при завершении рисования отрезка
    rectangle_drawing_started = Signal(str)  # сигнал при начале рисования прямоугольника (передает метод)
    
    def __init__(self, style_manager=None):
        super().__init__()
        
        # Создаем компоненты
        self.viewport = Viewport(self.width(), self.height())
        self.scene = Scene()
        self.selection_manager = SelectionManager()
        self.renderer = SceneRenderer(self.viewport, self.scene, self.selection_manager)
        self.snap_manager = SnapManager(tolerance=10.0)
        
        # Менеджер стилей
        self.style_manager = style_manager
        
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
        
        # Координаты курсора
        self.cursor_world_coords = None
        
        # Точки ввода для визуализации (для окружности, дуги, эллипса, прямоугольника)
        self.input_points = []  # Список точек для отображения
        
        # Настройки отрисовки
        self.line_color = QColor(0, 0, 0)
        self.line_width = 2
        
        # Тип создаваемого примитива
        self.primitive_type = 'line'  # 'line', 'circle', 'arc', 'rectangle', 'ellipse', 'polygon'
        # Метод создания окружности
        self.circle_creation_method = 'center_radius'  # 'center_radius', 'center_diameter', 'two_points', 'three_points'
        # Метод создания дуги
        self.arc_creation_method = 'three_points'  # 'three_points', 'center_angles'
        # Метод создания прямоугольника
        self.rectangle_creation_method = 'two_points'  # 'two_points', 'point_size', 'center_size', 'with_fillets'
        # Метод создания многоугольника
        self.polygon_creation_method = 'center_radius_vertices'  # 'center_radius_vertices'
        self.polygon_num_vertices = 3
        
        # Подключаем сигналы
        self.selection_manager.selection_changed.connect(self._on_selection_changed)
        
        self.setMinimumSize(600, 400)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.NoContextMenu)
    
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
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Сначала рисуем сцену через renderer
        self.renderer.draw(painter)
        
        # Затем рисуем точки ввода (поверх сцены)
        if self.input_points:
            self._draw_input_points(painter)
        
        # Рисуем точку привязки (поверх всего)
        if self.current_snap_point:
            self._draw_snap_point(painter)
        
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
    
    def _apply_snapping(self, point: QPointF) -> QPointF:
        """
        Применяет привязку к точке
        Args:
            point: Исходная точка
        Returns:
            Привязанная точка (или исходная, если привязка не найдена)
        """
        if not self.snap_manager.enabled:
            self.current_snap_point = None
            return point
        
        # Получаем все объекты, исключая текущий рисуемый
        objects = self.scene.get_objects()
        current_obj = self.scene.get_current_object()
        
        # Получаем статические точки привязки
        snap_points = self.snap_manager.get_snap_points(objects, exclude_object=current_obj)
        
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
                point, objects, exclude_object=current_obj, start_point=start_point
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
            else:
                world_pos = self.viewport.screen_to_world(event.position())
                
                # Применяем привязку
                world_pos = self._apply_snapping(world_pos)
                
                # Проверяем, есть ли активная точка привязки
                # Если есть - начинаем рисование из этой точки, не проверяя клик по объекту
                has_active_snap = self.current_snap_point is not None
                
                # Проверяем, кликнули ли по существующему объекту (для выделения)
                # Но только если мы не рисуем новый объект И нет активной точки привязки
                if not self.scene.is_drawing() and not has_active_snap:
                    clicked_obj = self.selection_manager.find_object_at_point(
                        world_pos, self.scene.get_objects()
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
                    # Снимаем выделение при начале рисования нового объекта
                    self.selection_manager.clear_selection()
                    # Используем стиль из менеджера, если доступен
                    style = None
                    if self.style_manager:
                        style = self.style_manager.get_current_style()
                    # Передаем метод создания окружности, дуги или прямоугольника
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
                    self.scene.start_drawing(world_pos, drawing_type=self.primitive_type,
                                            style=style, color=self.line_color, width=self.line_width, **kwargs)
                    # Эмитируем сигнал о начале рисования прямоугольника (после start_drawing)
                    if self.primitive_type == 'rectangle':
                        self.rectangle_drawing_started.emit(self.rectangle_creation_method)
                    # Обновляем объект для предпросмотра
                    self.scene.update_current_object(world_pos)
                    current_obj = self.scene.get_current_object()
                    if current_obj and hasattr(current_obj, '_legacy_color'):
                        current_obj._legacy_color = self.line_color
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
                                self.scene.update_current_object(world_pos)
                                obj = self.scene.finish_drawing()
                                if obj:
                                    self.line_finished.emit()
                        elif method == 'center_angles':
                            # Для центра и углов - второй клик определяет радиус
                            if self.scene._arc_radius == 0.0:
                                # Второй клик - фиксируем радиус
                                import math
                                dx = world_pos.x() - self.scene._arc_center.x()
                                dy = world_pos.y() - self.scene._arc_center.y()
                                self.scene._arc_radius = math.sqrt(dx*dx + dy*dy)
                                self.scene.update_current_object(world_pos)
                            else:
                                # Радиус уже установлен, завершаем (углы задаются через UI)
                                obj = self.scene.finish_drawing()
                                if obj:
                                    self.line_finished.emit()
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
                                self.scene.update_current_object(world_pos)
                                obj = self.scene.finish_drawing()
                                if obj:
                                    self.line_finished.emit()
                        else:
                            # Для остальных методов - завершаем при втором клике
                            current_obj = self.scene.get_current_object()
                            if current_obj:
                                self.scene.update_current_object(world_pos)
                            obj = self.scene.finish_drawing()
                            if obj:
                                self.line_finished.emit()
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
                            self.scene.update_current_object(world_pos)
                            obj = self.scene.finish_drawing()
                            if obj:
                                self.line_finished.emit()
                    elif self.primitive_type == 'polygon':
                        # Для многоугольника второй клик завершает создание (радиус определяется)
                        self.scene.update_current_object(world_pos)
                        obj = self.scene.finish_drawing()
                        if obj:
                            self.line_finished.emit()
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
                                    obj = self.scene.finish_drawing()
                                    if obj:
                                        self.line_finished.emit()
                                    self.update()
                            QTimer.singleShot(10, check_and_finish)
                            # Обновляем предпросмотр
                            self.scene.update_current_object(world_pos)
                        else:
                            # Для остальных методов (two_points, with_fillets) - завершаем при втором клике
                            current_obj = self.scene.get_current_object()
                            if current_obj:
                                self.scene.update_current_object(world_pos)
                            obj = self.scene.finish_drawing()
                            if obj:
                                self.line_finished.emit()
                    else:
                        # Для остальных примитивов - завершаем при втором клике
                        current_obj = self.scene.get_current_object()
                        if current_obj:
                            # Обновляем объект перед завершением
                            self.scene.update_current_object(world_pos)
                        obj = self.scene.finish_drawing()
                        if obj:
                            self.line_finished.emit()
                
                self.update()
        
        elif event.button() == Qt.RightButton:
            # Правая кнопка - сохраняем позицию для определения клика/перетаскивания
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
        self.view_changed.emit()
        
        # Применяем привязку при наведении мыши (даже если не рисуем)
        # Это нужно для визуализации точек привязки
        if not (event.buttons() & Qt.RightButton) and not self.pan_mode and not (event.buttons() & Qt.MiddleButton):
            # Сохраняем предыдущее состояние привязки
            had_snap_point = self.current_snap_point is not None
            # Применяем привязку для визуализации, но не изменяем world_pos если не рисуем
            self._apply_snapping(world_pos)
            # Обновляем виджет если состояние привязки изменилось
            has_snap_point = self.current_snap_point is not None
            if had_snap_point != has_snap_point:
                self.update()
        
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
            
            # Для дуги и эллипса во время второго этапа показываем предпросмотр конечной точки
            if self.primitive_type == 'arc':
                method = self.arc_creation_method
                if method == 'three_points':
                    # Обновляем конечную точку для предпросмотра (временно, только для отображения)
                    if self.scene._arc_end_point is None:
                        # Второй этап - обновляем предпросмотр конечной точки (точка еще не зафиксирована)
                        # Сохраняем временно для отображения
                        self.scene._temp_arc_end_point = world_pos
                        # Обновляем предпросмотр линии
                        self.scene.update_current_object(world_pos)
                    elif self.scene._arc_end_point is not None:
                        # Третий этап - обновляем высоту (крайние точки уже зафиксированы)
                        self.scene.update_current_object(world_pos)
                elif method == 'center_angles':
                    # Для метода центр+углы обновляем радиус при движении мыши
                    if self.scene._arc_radius == 0.0:
                        self.scene.update_current_object(world_pos)
            elif self.primitive_type == 'circle':
                # Обновляем окружность при движении мыши
                method = self.circle_creation_method
                if method == 'three_points':
                    if self.scene._circle_point2 is None:
                        # Второй этап - предпросмотр второй точки
                        self.scene.update_current_object(world_pos)
                    elif self.scene._circle_point2 is not None:
                        # Третий этап - предпросмотр третьей точки
                        self.scene.update_current_object(world_pos)
                else:
                    # Для остальных методов - обычное обновление
                    self.scene.update_current_object(world_pos)
            elif self.primitive_type == 'ellipse':
                # Обновляем конечную точку для предпросмотра (временно, только для отображения)
                if hasattr(self.scene, '_ellipse_end_point') and self.scene._ellipse_end_point is None:
                    # Второй этап - обновляем предпросмотр конечной точки (точка еще не зафиксирована)
                    # Сохраняем временно для отображения
                    self.scene._temp_ellipse_end_point = world_pos
                    # Обновляем предпросмотр эллипса
                    self.scene.update_current_object(world_pos)
                elif hasattr(self.scene, '_ellipse_end_point') and self.scene._ellipse_end_point is not None:
                    # Третий этап - обновляем высоту (крайние точки уже зафиксированы)
                    self.scene.update_current_object(world_pos)
            else:
                self.scene.update_current_object(world_pos)
            
            self.update()
    
    def _handle_single_right_click(self):
        """Обрабатывает одинарный клик ПКМ"""
        self.right_button_click_count = 0
        
        # Отменяем рисование, если оно активно
        if self.scene.is_drawing():
            self.scene.cancel_drawing()
            self.update()
        
        # Очищаем выделение рамкой, если оно было начато
        if self.is_selecting:
            self.is_selecting = False
            self.selection_start = None
            self.selection_end = None
            self.update()
        
        self.right_button_press_pos = None
        self.right_button_press_time = None
    
    def mouseReleaseEvent(self, event):
        """Обработчик отпускания кнопки мыши"""
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
                    if self.right_button_click_timer:
                        self.right_button_click_timer.stop()
                    self.right_button_click_count = 0
                
                # Всегда очищаем выделение рамкой при отпускании
                self.is_selecting = False
                self.selection_start = None
                self.selection_end = None
            else:
                # Не было выделения - проверяем, был ли это клик
                if delta <= 3:
                    # Это был клик без движения - отменяем рисование сразу
                    if self.scene.is_drawing():
                        self.scene.cancel_drawing()
                        # Останавливаем таймер, так как уже обработали
                        if self.right_button_click_timer:
                            self.right_button_click_timer.stop()
                        self.right_button_click_count = 0
                    # Если таймер еще работает, пусть он тоже сработает (на случай, если рисование не было активно)
                else:
                    # Было движение, но выделение не началось - останавливаем таймер
                    if self.right_button_click_timer:
                        self.right_button_click_timer.stop()
                    self.right_button_click_count = 0
            
            # Очищаем позицию нажатия
            self.right_button_press_pos = None
            self.right_button_press_time = None
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
        
        style = None
        if self.style_manager:
            style = self.style_manager.get_current_style()
        
        if apply:
            new_line = LineSegment(start_point, end_point, style=style, 
                                  color=self.line_color, width=self.line_width)
            if hasattr(new_line, '_legacy_color'):
                new_line._legacy_color = self.line_color
            self.scene.add_object(new_line)
            self.update()
        else:
            if not self.scene.is_drawing():
                self.scene.start_drawing(start_point, drawing_type='line', style=style,
                                       color=self.line_color, width=self.line_width)
                current_obj = self.scene.get_current_object()
                if current_obj:
                    self.scene.update_current_object(end_point)
                    if hasattr(current_obj, '_legacy_color'):
                        current_obj._legacy_color = self.line_color
            else:
                current_obj = self.scene.get_current_object()
                if current_obj and isinstance(current_obj, LineSegment):
                    current_obj.start_point = start_point
                    current_obj.end_point = end_point
                    if style and not current_obj.style:
                        current_obj.style = style
                    if hasattr(current_obj, '_legacy_color'):
                        current_obj._legacy_color = self.line_color
            self.update()
    
    def set_primitive_type(self, primitive_type: str):
        """Устанавливает тип создаваемого примитива"""
        self.primitive_type = primitive_type
    
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
