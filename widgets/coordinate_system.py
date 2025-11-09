import math
from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import Qt, QPointF, Signal
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QTransform

from .line_segment import LineSegment


class CoordinateSystemWidget(QWidget):
    view_changed = Signal()  # Сигнал при изменении вида

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
        self.transform = QTransform()
        self.base_transform = QTransform()
        self.translation = QPointF(0, 0)

        # Масштаб и поворот
        self.scale_factor = 1.0
        self.min_scale = 0.1
        self.max_scale = 10.0
        self.rotation_angle = 0.0  # в градусах

        # Координаты курсора
        self.cursor_world_coords = None

        self.setMinimumSize(600, 400)
        self.setMouseTracking(True)

    # ----------------------- РИСОВАНИЕ -----------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # ✅ Фон рисуем без трансформации (иначе заливает только часть)
        painter.fillRect(self.rect(), self.background_color)

        # ✅ Применяем текущее преобразование
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

        transform = self.get_total_transform().inverted()[0]
        visible_rect = transform.mapRect(self.rect())

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
        transform = self.get_total_transform().inverted()[0]
        visible_rect = transform.mapRect(self.rect())

        painter.drawLine(visible_rect.left(), 0, visible_rect.right(), 0)
        painter.drawLine(0, visible_rect.top(), 0, visible_rect.bottom())

        painter.setFont(QFont("Arial", 10))
        painter.drawText(visible_rect.right() - 20, 15, "X")
        painter.drawText(5, visible_rect.top() + 15, "Y")
        painter.drawText(5, 15, "0")

    def draw_saved_line(self, painter, line):
        painter.setPen(QPen(line.color, line.width))
        painter.drawLine(line.start_point, line.end_point)
        painter.setBrush(line.color)
        painter.drawEllipse(line.start_point, 4 / self.scale_factor, 4 / self.scale_factor)
        painter.drawEllipse(line.end_point, 4 / self.scale_factor, 4 / self.scale_factor)

    def draw_current_point(self, painter):
        painter.setPen(QPen(Qt.blue, 2))
        painter.setBrush(Qt.blue)
        painter.drawEllipse(self.current_point, 3 / self.scale_factor, 3 / self.scale_factor)

    # ----------------------- СОБЫТИЯ МЫШИ -----------------------

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
                self.translation += delta
                self.last_mouse_pos = event.position()
                self.update()
        elif event.buttons() & Qt.MiddleButton:
            if self.last_mouse_pos:
                delta = event.position() - self.last_mouse_pos
                self.translation += delta
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

    # ----------------------- ТРАНСФОРМАЦИИ -----------------------

    def zoom_at_point(self, screen_point, factor):
        old_scale = self.scale_factor
        self.scale_factor *= factor
        self.scale_factor = max(self.min_scale, min(self.max_scale, self.scale_factor))

        world_point = self.screen_to_world(screen_point)
        scale_change = self.scale_factor / old_scale

        self.update_base_transform()
        new_screen_point = self.world_to_screen(world_point)
        delta = screen_point - new_screen_point
        self.translation += delta

        self.view_changed.emit()
        self.update()

    def update_base_transform(self):
        self.base_transform = QTransform()
        self.base_transform.scale(self.scale_factor, self.scale_factor)
        self.base_transform.rotate(self.rotation_angle)

    def get_total_transform(self):
        transform = QTransform()
        transform.translate(self.width() / 2, self.height() / 2)
        transform.translate(self.translation.x(), self.translation.y())
        transform = transform * self.base_transform
        return transform

    def screen_to_world(self, screen_point):
        transform = self.get_total_transform().inverted()[0]
        return transform.map(screen_point)

    def world_to_screen(self, world_point):
        transform = self.get_total_transform()
        return transform.map(world_point)

    # ----------------------- НАВИГАЦИЯ -----------------------

    def set_pan_mode(self, enabled):
        self.pan_mode = enabled
        self.view_changed.emit()

    def zoom_in(self):
        self.zoom_at_point(QPointF(self.width() / 2, self.height() / 2), 1.2)

    def zoom_out(self):
        self.zoom_at_point(QPointF(self.width() / 2, self.height() / 2), 1.0 / 1.2)

    def show_all(self):
        if not self.lines:
            return

        min_x = min(line.start_point.x() for line in self.lines)
        max_x = max(line.start_point.x() for line in self.lines)
        min_y = min(line.start_point.y() for line in self.lines)
        max_y = max(line.start_point.y() for line in self.lines)

        for line in self.lines:
            min_x = min(min_x, line.end_point.x())
            max_x = max(max_x, line.end_point.x())
            min_y = min(min_y, line.end_point.y())
            max_y = max(max_y, line.end_point.y())

        padding = 20
        min_x -= padding
        max_x += padding
        min_y -= padding
        max_y += padding

        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2
        width = max_x - min_x
        height = max_y - min_y

        scale_x = self.width() / width if width > 0 else 1
        scale_y = self.height() / height if height > 0 else 1
        new_scale = min(scale_x, scale_y) * 0.9

        self.scale_factor = max(self.min_scale, min(self.max_scale, new_scale))
        self.rotation_angle = 0
        self.translation = QPointF(-center_x * self.scale_factor, -center_y * self.scale_factor)

        self.update_base_transform()
        self.view_changed.emit()
        self.update()

    def reset_view(self):
        self.scale_factor = 1.0
        self.rotation_angle = 0
        self.translation = QPointF(0, 0)
        self.update_base_transform()
        self.view_changed.emit()
        self.update()

    # ----------------------- ВРАЩЕНИЕ -----------------------

    def rotate(self, angle, screen_point: QPointF | None = None):
        """Вращает вид на указанный угол вокруг screen_point. При Shift — привязка к 90°."""
        if screen_point is None:
            screen_point = QPointF(self.width() / 2, self.height() / 2)

        world_point = self.screen_to_world(screen_point)

        tentative_angle = self.rotation_angle + angle
        modifiers = QApplication.keyboardModifiers()
        if modifiers & Qt.ShiftModifier:
            tentative_angle = round(tentative_angle / 90.0) * 90.0

        self.rotation_angle = tentative_angle
        self.update_base_transform()

        new_screen_point = self.world_to_screen(world_point)
        delta = screen_point - new_screen_point
        self.translation += delta

        self.view_changed.emit()
        self.update()

    def rotate_left(self, angle=15):
        self.rotate(angle, QPointF(self.width() / 2, self.height() / 2))

    def rotate_right(self, angle=15):
        self.rotate(-angle, QPointF(self.width() / 2, self.height() / 2))

    # ----------------------- СЛУЖЕБНЫЕ -----------------------

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
