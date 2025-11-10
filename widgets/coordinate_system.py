import math
from PySide6.QtWidgets import QWidget, QApplication, QMenu
from PySide6.QtCore import Qt, QPointF, QPoint, Signal, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QTransform

from .line_segment import LineSegment


class CoordinateSystemWidget(QWidget):
    view_changed = Signal()  # Сигнал при изменении вида
    context_menu_requested = Signal(QPoint)  # Сигнал для запроса контекстного меню

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

        # Параметры навигации
        self.pan_mode = False
        self.last_mouse_pos = None
        
        # Единая система трансформаций
        self.scale_factor = 1.0
        self.min_scale = 0.1
        self.max_scale = 10.0
        self.rotation_angle = 0.0  # в градусах
        self.translation = QPointF(0, 0)
        
        # Центр сцены (мировые координаты)
        self.scene_center = QPointF(0, 0)

        # Координаты курсора
        self.cursor_world_coords = None

        self.setMinimumSize(600, 400)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)  # Включаем контекстное меню
        self.customContextMenuRequested.connect(self.show_context_menu)

    def show_context_menu(self, position):
        """Показывает контекстное меню"""
        menu = QMenu(self)
        
        # Команды навигации
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
        
        # Показываем меню в позиции клика
        menu.exec_(self.mapToGlobal(position))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Фон рисуем без трансформации
        painter.fillRect(self.rect(), self.background_color)

        # Применяем текущее преобразование
        transform = self.get_total_transform()
        painter.setTransform(transform)

        # Рисуем сетку
        self.draw_grid(painter)

        # Рисуем оси координат
        self.draw_axes(painter)

        # Рисуем все сохраненные отрезки
        for line in self.lines:
            self.draw_saved_line(painter, line)

        # Рисуем текущий отрезок (если есть)
        if self.current_line:
            self.draw_saved_line(painter, self.current_line)

        # Рисуем текущую точку при рисовании
        if self.is_drawing and self.current_point:
            self.draw_current_point(painter)

    def draw_grid(self, painter):
        painter.setPen(QPen(self.grid_color, 1, Qt.DotLine))

        # Получаем видимую область в мировых координатах
        transform, success = self.get_total_transform().inverted()
        if not success:
            return
            
        visible_rect = transform.mapRect(QRectF(self.rect()))

        start_x = math.floor(visible_rect.left() / self.grid_step) * self.grid_step
        end_x = math.ceil(visible_rect.right() / self.grid_step) * self.grid_step
        start_y = math.floor(visible_rect.top() / self.grid_step) * self.grid_step
        end_y = math.ceil(visible_rect.bottom() / self.grid_step) * self.grid_step

        # Вертикальные линии
        for x in range(int(start_x), int(end_x) + self.grid_step, self.grid_step):
            painter.drawLine(x, visible_rect.top(), x, visible_rect.bottom())

        # Горизонтальные линии
        for y in range(int(start_y), int(end_y) + self.grid_step, self.grid_step):
            painter.drawLine(visible_rect.left(), y, visible_rect.right(), y)

    def draw_axes(self, painter):
        painter.setPen(QPen(self.axis_color, 2))
        
        # Получаем видимую область
        transform, success = self.get_total_transform().inverted()
        if not success:
            return
            
        visible_rect = transform.mapRect(QRectF(self.rect()))

        # Оси координат
        painter.drawLine(visible_rect.left(), 0, visible_rect.right(), 0)  # X axis
        painter.drawLine(0, visible_rect.top(), 0, visible_rect.bottom())  # Y axis

        # Подписи осей
        painter.setFont(QFont("Arial", 10))
        painter.drawText(visible_rect.right() - 20, 15, "X")
        painter.drawText(5, visible_rect.top() + 15, "Y")
        painter.drawText(5, 15, "0")

    def draw_saved_line(self, painter, line):
        painter.setPen(QPen(line.color, line.width))
        painter.drawLine(line.start_point, line.end_point)
        painter.setBrush(line.color)
        point_size = max(2, 4 / self.scale_factor)  # Минимальный размер точки
        painter.drawEllipse(line.start_point, point_size, point_size)
        painter.drawEllipse(line.end_point, point_size, point_size)

    def draw_current_point(self, painter):
        painter.setPen(QPen(Qt.blue, 2))
        painter.setBrush(Qt.blue)
        point_size = max(2, 3 / self.scale_factor)  # Минимальный размер точки
        painter.drawEllipse(self.current_point, point_size, point_size)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.pan_mode:
                self.last_mouse_pos = event.position()
            else:
                world_pos = self.screen_to_world(event.position())
                if not self.is_drawing:
                    self.current_line = LineSegment(world_pos, world_pos, self.line_color, self.line_width)
                    self.is_drawing = True
                else:
                    if self.current_line:
                        self.current_line.end_point = world_pos
                        self.lines.append(self.current_line)
                        self.current_line = None
                    self.is_drawing = False

                self.current_point = world_pos
                self.update()

        elif event.button() == Qt.MiddleButton:
            self.last_mouse_pos = event.position()

    def mouseMoveEvent(self, event):
        self.cursor_world_coords = self.screen_to_world(event.position())
        self.view_changed.emit()

        if self.pan_mode and event.buttons() & Qt.LeftButton:
            if self.last_mouse_pos:
                delta = event.position() - self.last_mouse_pos
                # Панорамирование в мировых координатах
                transform, success = self.get_total_transform().inverted()
                if success:
                    delta_world = transform.map(delta) - transform.map(QPointF(0, 0))
                    self.translation += delta_world
                self.last_mouse_pos = event.position()
                self.update()
        elif event.buttons() & Qt.MiddleButton:
            if self.last_mouse_pos:
                delta = event.position() - self.last_mouse_pos
                transform, success = self.get_total_transform().inverted()
                if success:
                    delta_world = transform.map(delta) - transform.map(QPointF(0, 0))
                    self.translation += delta_world
                self.last_mouse_pos = event.position()
                self.update()
        elif self.is_drawing and self.current_line and event.buttons() & Qt.LeftButton:
            world_pos = self.screen_to_world(event.position())
            self.current_point = world_pos
            self.current_line.end_point = world_pos
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() in (Qt.LeftButton, Qt.MiddleButton):
            self.last_mouse_pos = None

    def wheelEvent(self, event):
        zoom_factor = 1.1
        if event.angleDelta().y() > 0:
            self.zoom_at_point(event.position(), zoom_factor)
        else:
            self.zoom_at_point(event.position(), 1.0 / zoom_factor)

    def zoom_at_point(self, screen_point, factor):
        """Масштабирование относительно точки с сохранением положения этой точки"""
        world_point_before = self.screen_to_world(screen_point)
        
        # Применяем масштаб
        self.scale_factor *= factor
        self.scale_factor = max(self.min_scale, min(self.max_scale, self.scale_factor))
        
        world_point_after = self.screen_to_world(screen_point)
        
        # Корректируем трансляцию для сохранения положения точки
        delta = world_point_after - world_point_before
        self.translation -= delta

        self.view_changed.emit()
        self.update()

    def get_total_transform(self):
        """Возвращает полную матрицу преобразования"""
        transform = QTransform()
        
        # 1. Центрирование (перевод в центр виджета)
        transform.translate(self.width() / 2, self.height() / 2)
        
        # 2. Трансляция (панорамирование)
        transform.translate(self.translation.x(), self.translation.y())
        
        # 3. Масштабирование
        transform.scale(self.scale_factor, self.scale_factor)
        
        # 4. Поворот вокруг центра
        transform.rotate(self.rotation_angle)
        
        return transform

    def screen_to_world(self, screen_point):
        """Преобразует экранные координаты в мировые"""
        transform, success = self.get_total_transform().inverted()
        if success:
            return transform.map(screen_point)
        return screen_point

    def world_to_screen(self, world_point):
        """Преобразует мировые координаты в экранные"""
        transform = self.get_total_transform()
        return transform.map(world_point)

    def set_pan_mode(self, enabled):
        self.pan_mode = enabled
        self.view_changed.emit()

    def zoom_in(self):
        self.zoom_at_point(QPointF(self.width() / 2, self.height() / 2), 1.2)

    def zoom_out(self):
        self.zoom_at_point(QPointF(self.width() / 2, self.height() / 2), 1.0 / 1.2)

    def show_all(self):
        """Показывает все отрезки с правильным учетом поворота"""
        if not self.lines and not self.current_line:
            self.reset_view()
            return

        # Собираем все точки
        all_points = []
        for line in self.lines:
            all_points.append(line.start_point)
            all_points.append(line.end_point)
        if self.current_line:
            all_points.append(self.current_line.start_point)
            all_points.append(self.current_line.end_point)

        if not all_points:
            return

        # Вычисляем bounding box всех точек
        min_x = min(p.x() for p in all_points)
        max_x = max(p.x() for p in all_points)
        min_y = min(p.y() for p in all_points)
        max_y = max(p.y() for p in all_points)

        # Добавляем отступ
        padding = 50
        min_x -= padding
        max_x += padding
        min_y -= padding
        max_y += padding

        # Вычисляем центр и размеры сцены
        scene_width = max_x - min_x
        scene_height = max_y - min_y
        scene_center = QPointF((min_x + max_x) / 2, (min_y + max_y) / 2)

        # Вычисляем масштаб для вписывания в виджет
        widget_width = self.width()
        widget_height = self.height()
        
        scale_x = widget_width / scene_width if scene_width > 0 else 1.0
        scale_y = widget_height / scene_height if scene_height > 0 else 1.0
        
        new_scale = min(scale_x, scale_y) * 0.9  # 90% от размера для отступов
        new_scale = max(self.min_scale, min(self.max_scale, new_scale))

        # Устанавливаем новые параметры
        self.scale_factor = new_scale
        self.translation = QPointF(0, 0)  # Сбрасываем трансляцию
        
        # Центрируем сцену
        self.center_on_point(scene_center)

        self.view_changed.emit()
        self.update()

    def center_on_point(self, world_point):
        """Центрирует вид на указанной мировой точке"""
        # Преобразуем мировую точку в экранные координаты с текущими настройками
        screen_pos = self.world_to_screen(world_point)
        
        # Вычисляем смещение для центрирования
        center_screen = QPointF(self.width() / 2, self.height() / 2)
        delta_screen = center_screen - screen_pos
        
        # Преобразуем экранное смещение в мировое
        transform, success = self.get_total_transform().inverted()
        if success:
            delta_world = transform.map(delta_screen) - transform.map(QPointF(0, 0))
            self.translation += delta_world

    def reset_view(self):
        """Полностью сбрасывает вид к начальному состоянию"""
        self.scale_factor = 1.0
        self.rotation_angle = 0
        self.translation = QPointF(0, 0)
        self.view_changed.emit()
        self.update()

    def rotate(self, angle):
        """Вращает вид вокруг центра экрана"""
        # Сохраняем текущий центр экрана в мировых координатах
        screen_center = QPointF(self.width() / 2, self.height() / 2)
        world_center_before = self.screen_to_world(screen_center)
        
        # Применяем поворот
        self.rotation_angle += angle
        
        # Получаем новое положение центра
        world_center_after = self.screen_to_world(screen_center)
        
        # Корректируем трансляцию для сохранения центра
        delta = world_center_after - world_center_before
        self.translation -= delta

        self.view_changed.emit()
        self.update()

    def rotate_left(self, angle=15):
        """Поворот налево на указанный угол"""
        self.rotate(angle)

    def rotate_right(self, angle=15):
        """Поворот направо на указанный угол"""
        self.rotate(-angle)

    def get_cursor_world_coords(self):
        return self.cursor_world_coords

    def get_scale(self):
        return self.scale_factor

    def get_rotation(self):
        return self.rotation_angle

    def start_new_line(self):
        if self.is_drawing and self.current_line and self.current_point:
            self.current_line.end_point = self.current_point
            self.lines.append(self.current_line)
        self.is_drawing = True
        self.current_point = None
        self.current_line = None
        self.update()

    def delete_last_line(self):
        if self.lines:
            self.lines.pop()
            self.update()

    def delete_all_lines(self):
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
        if self.current_line:
            return self.current_line.start_point, self.current_line.end_point
        elif self.lines:
            last_line = self.lines[-1]
            return last_line.start_point, last_line.end_point
        else:
            return QPointF(0, 0), QPointF(0, 0)

    def set_points_from_input(self, start_point, end_point, apply=False):
        if apply:
            new_line = LineSegment(start_point, end_point, self.line_color, self.line_width)
            self.lines.append(new_line)
            self.update()
        else:
            if not self.current_line:
                self.current_line = LineSegment(start_point, end_point, self.line_color, self.line_width)
            else:
                self.current_line.start_point = start_point
                self.current_line.end_point = end_point
            self.update()