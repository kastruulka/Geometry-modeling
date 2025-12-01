"""
Класс для отрисовки объектов сцены
"""
import math
from typing import List
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QTransform, QPainterPath, Qt

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.viewport import Viewport
    from core.scene import Scene
    from core.selection import SelectionManager
from widgets.line_segment import LineSegment
from widgets.line_style import LineType


class LineRenderer:
    """Класс для отрисовки линий различных типов"""
    
    @staticmethod
    def draw_line(painter: QPainter, line: LineSegment, scale_factor: float = 1.0, 
                 is_selected: bool = False):
        """Отрисовывает линию с учетом стиля"""
        # Сохраняем текущее состояние brush
        old_brush = painter.brush()
        
        if line.style:
            pen = line.style.get_pen(scale_factor=scale_factor)
            # Если у линии есть legacy цвет, используем его вместо цвета стиля
            if hasattr(line, '_legacy_color') and line._legacy_color != line.style.color:
                pen.setColor(line._legacy_color)
            # Если линия выделена, делаем её более заметной
            if is_selected:
                pen.setWidthF(pen.widthF() * 1.5)
                color = pen.color()
                color.setAlpha(255)
                pen.setColor(color)
            
            line_type = line.style.line_type
            
            # Устанавливаем brush перед отрисовкой линии
            painter.setBrush(Qt.NoBrush)
            
            # Для специальных типов линий нужна специальная отрисовка
            if line_type == LineType.SOLID_WAVY:
                LineRenderer._draw_wavy_line(painter, line.start_point, line.end_point, pen)
            elif line_type == LineType.SOLID_THIN_BROKEN:
                LineRenderer._draw_broken_line(painter, line.start_point, line.end_point, pen)
            elif line_type == LineType.DASHED:
                LineRenderer._draw_dashed_line(painter, line.start_point, line.end_point, pen, line.style)
            elif line_type in [LineType.DASH_DOT_THICK, LineType.DASH_DOT_THIN, LineType.DASH_DOT_TWO_DOTS]:
                LineRenderer._draw_dash_dot_line(painter, line.start_point, line.end_point, pen, line.style)
            else:
                # Обычные сплошные линии
                painter.setPen(pen)
                painter.drawLine(line.start_point, line.end_point)
        else:
            # Обратная совместимость - используем старый способ
            pen = QPen(line.color, line.width)
            if is_selected:
                pen.setWidthF(pen.widthF() * 1.5)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)  # Убеждаемся, что brush не мешает
            painter.drawLine(line.start_point, line.end_point)
        
        # Рисуем точки на концах
        painter.setPen(Qt.NoPen)  # Убираем обводку для точек
        if is_selected:
            painter.setBrush(QColor(0, 100, 255))  # Синий для выделенных
        else:
            # Используем цвет линии для точек
            point_color = line.color if hasattr(line, 'color') else QColor(0, 0, 0)
            painter.setBrush(point_color)
        point_size = max(2, 4 / scale_factor)  # минимальный размер точки
        painter.drawEllipse(line.start_point, point_size, point_size)
        painter.drawEllipse(line.end_point, point_size, point_size)
        
        # Восстанавливаем brush
        painter.setBrush(old_brush)
    
    @staticmethod
    def _draw_wavy_line(painter: QPainter, start_point: QPointF, end_point: QPointF, pen: QPen):
        """Отрисовывает волнистую линию (плавная синусоида)"""
        dx = end_point.x() - start_point.x()
        dy = end_point.y() - start_point.y()
        length = math.sqrt(dx*dx + dy*dy)
        angle = math.atan2(dy, dx)
        
        if length < 1:
            return
        
        # Амплитуда волны согласно ГОСТ
        main_thickness_mm = 0.8
        line_thickness_mm = pen.widthF() * 25.4 / 96
        amplitude_mm = (main_thickness_mm / 2.5) * (line_thickness_mm / 0.4)
        amplitude_px = (amplitude_mm * 96) / 25.4
        
        wave_length_px = amplitude_px * 5
        num_waves = max(1, int(length / wave_length_px))
        actual_wave_length = length / num_waves if num_waves > 0 else length
        
        path = QPainterPath()
        cos_angle = math.cos(angle)
        sin_angle = math.sin(angle)
        perp_cos = -sin_angle
        perp_sin = cos_angle
        
        num_points = max(50, int(length / 2))
        
        for i in range(num_points + 1):
            t = i / num_points
            along_line = t * length
            wave_phase = (along_line / actual_wave_length) * 2 * math.pi
            wave_offset = amplitude_px * math.sin(wave_phase)
            
            x = start_point.x() + along_line * cos_angle + wave_offset * perp_cos
            y = start_point.y() + along_line * sin_angle + wave_offset * perp_sin
            
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
    
    @staticmethod
    def _draw_broken_line(painter: QPainter, start_point: QPointF, end_point: QPointF, pen: QPen):
        """Отрисовывает сплошную линию с изломами (острые углы, зигзаг)"""
        dx = end_point.x() - start_point.x()
        dy = end_point.y() - start_point.y()
        length = math.sqrt(dx*dx + dy*dy)
        angle = math.atan2(dy, dx)
        
        if length < 1:
            return
        
        zigzag_height_mm = 3.5
        zigzag_width_mm = 4.0
        dpi = 96
        zigzag_height = (zigzag_height_mm * dpi) / 25.4
        zigzag_length = (zigzag_width_mm * dpi) / 25.4
        
        if zigzag_length > length * 0.8:
            zigzag_length = length * 0.8
        
        straight_length = (length - zigzag_length) / 2
        
        cos_angle = math.cos(angle)
        sin_angle = math.sin(angle)
        perp_cos = -sin_angle
        perp_sin = cos_angle
        
        path = QPainterPath()
        path.moveTo(start_point)
        
        zigzag_start = QPointF(
            start_point.x() + straight_length * cos_angle,
            start_point.y() + straight_length * sin_angle
        )
        path.lineTo(zigzag_start)
        
        segment_length_along = zigzag_length / 3
        
        point1 = QPointF(
            zigzag_start.x() + segment_length_along * cos_angle + (zigzag_height / 2) * perp_cos,
            zigzag_start.y() + segment_length_along * sin_angle + (zigzag_height / 2) * perp_sin
        )
        path.lineTo(point1)
        
        point2 = QPointF(
            point1.x() + segment_length_along * cos_angle - zigzag_height * perp_cos,
            point1.y() + segment_length_along * sin_angle - zigzag_height * perp_sin
        )
        path.lineTo(point2)
        
        zigzag_end = QPointF(
            zigzag_start.x() + zigzag_length * cos_angle,
            zigzag_start.y() + zigzag_length * sin_angle
        )
        path.lineTo(zigzag_end)
        path.lineTo(end_point)
        
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
    
    @staticmethod
    def _draw_dashed_line(painter: QPainter, start_point: QPointF, end_point: QPointF, 
                         pen: QPen, style):
        """Отрисовывает штриховую линию вручную"""
        dx = end_point.x() - start_point.x()
        dy = end_point.y() - start_point.y()
        length = math.sqrt(dx*dx + dy*dy)
        
        if length < 0.1:
            return
        
        dash_length = style.dash_length
        dash_gap = style.dash_gap
        
        cos_angle = dx / length
        sin_angle = dy / length
        
        current_pos = 0.0
        painter.setPen(pen)
        
        while current_pos < length:
            dash_end = min(current_pos + dash_length, length)
            start_seg = QPointF(
                start_point.x() + current_pos * cos_angle,
                start_point.y() + current_pos * sin_angle
            )
            end_seg = QPointF(
                start_point.x() + dash_end * cos_angle,
                start_point.y() + dash_end * sin_angle
            )
            painter.drawLine(start_seg, end_seg)
            current_pos += dash_length + dash_gap
    
    @staticmethod
    def _draw_dash_dot_line(painter: QPainter, start_point: QPointF, end_point: QPointF, 
                           pen: QPen, style):
        """Отрисовывает штрихпунктирную линию вручную"""
        dx = end_point.x() - start_point.x()
        dy = end_point.y() - start_point.y()
        length = math.sqrt(dx*dx + dy*dy)
        
        if length < 0.1:
            return
        
        dash_length = style.dash_length
        dash_gap = style.dash_gap
        dot_length = style.thickness_mm * 0.5
        
        if style.line_type == LineType.DASH_DOT_TWO_DOTS:
            pattern = [dash_length, dash_gap, dot_length, dash_gap, dot_length, dash_gap]
        else:
            pattern = [dash_length, dash_gap, dot_length, dash_gap]
        
        cos_angle = dx / length
        sin_angle = dy / length
        
        current_pos = 0.0
        pattern_index = 0
        painter.setPen(pen)
        
        while current_pos < length:
            segment_length = pattern[pattern_index % len(pattern)]
            segment_end = min(current_pos + segment_length, length)
            
            is_gap = (segment_length == dash_gap)
            
            if not is_gap:
                start_seg = QPointF(
                    start_point.x() + current_pos * cos_angle,
                    start_point.y() + current_pos * sin_angle
                )
                end_seg = QPointF(
                    start_point.x() + segment_end * cos_angle,
                    start_point.y() + segment_end * sin_angle
                )
                painter.drawLine(start_seg, end_seg)
            
            current_pos += segment_length
            pattern_index += 1


class SceneRenderer:
    """Класс для отрисовки всей сцены"""
    
    def __init__(self, viewport, scene, selection_manager):
        self.viewport = viewport
        self.scene = scene
        self.selection_manager = selection_manager
        
        # Настройки отрисовки
        self.background_color = QColor(255, 255, 255)
        self.grid_color = QColor(200, 200, 200)
        self.axis_color = QColor(0, 0, 0)
        self.grid_step = 20.0  # в миллиметрах
    
    def draw(self, painter: QPainter):
        """Отрисовывает всю сцену"""
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Фон (рисуем без трансформации)
        from PySide6.QtCore import QRect
        painter.save()  # Сохраняем состояние
        painter.resetTransform()  # Сбрасываем трансформацию для фона
        painter.fillRect(QRect(0, 0, self.viewport.width, self.viewport.height), self.background_color)
        painter.restore()  # Восстанавливаем состояние
        
        # Применяем трансформацию
        transform = self.viewport.get_total_transform()
        painter.setTransform(transform)
        
        # Сетка
        self._draw_grid(painter)
        
        # Оси координат
        self._draw_axes(painter)
        
        # Объекты сцены
        scale_factor = self.viewport.get_scale()
        for obj in self.scene.get_objects():
            if isinstance(obj, LineSegment):
                is_selected = self.selection_manager.is_selected(obj)
                LineRenderer.draw_line(painter, obj, scale_factor, is_selected)
        
        # Текущий рисуемый отрезок
        current_line = self.scene.get_current_line()
        if current_line:
            LineRenderer.draw_line(painter, current_line, scale_factor, False)
        
        # Подсветка выделенных объектов
        for obj in self.selection_manager.get_selected_objects():
            if isinstance(obj, LineSegment):
                self._draw_selection_highlight(painter, obj)
    
    def _draw_grid(self, painter: QPainter):
        """Отрисовывает сетку"""
        import math
        from PySide6.QtCore import QRectF
        
        painter.setPen(QPen(self.grid_color, 1, Qt.DotLine))
        
        visible_rect = self.viewport.get_visible_rect()
        
        start_x = math.floor(visible_rect.left() / self.grid_step) * self.grid_step
        end_x = math.ceil(visible_rect.right() / self.grid_step) * self.grid_step
        start_y = math.floor(visible_rect.top() / self.grid_step) * self.grid_step
        end_y = math.ceil(visible_rect.bottom() / self.grid_step) * self.grid_step
        
        # Вертикальные линии
        x = start_x
        while x <= end_x:
            painter.drawLine(x, visible_rect.top(), x, visible_rect.bottom())
            x += self.grid_step
        
        # Горизонтальные линии
        y = start_y
        while y <= end_y:
            painter.drawLine(visible_rect.left(), y, visible_rect.right(), y)
            y += self.grid_step
    
    def _draw_axes(self, painter: QPainter):
        """Отрисовывает оси координат"""
        from PySide6.QtGui import QFont
        
        painter.setPen(QPen(self.axis_color, 2))
        
        visible_rect = self.viewport.get_visible_rect()
        
        # Оси координат
        painter.drawLine(visible_rect.left(), 0, visible_rect.right(), 0)  # X axis
        painter.drawLine(0, visible_rect.top(), 0, visible_rect.bottom())  # Y axis
        
        # Подписи осей
        saved_transform = painter.transform()
        painter.resetTransform()
        
        widget_rect = QRectF(0, 0, self.viewport.width, self.viewport.height)
        widget_corners = [
            QPointF(widget_rect.left(), widget_rect.top()),
            QPointF(widget_rect.right(), widget_rect.top()),
            QPointF(widget_rect.right(), widget_rect.bottom()),
            QPointF(widget_rect.left(), widget_rect.bottom())
        ]
        inv_transform, success = self.viewport.get_total_transform().inverted()
        if success:
            world_corners = [inv_transform.map(corner) for corner in widget_corners]
            world_right = max(c.x() for c in world_corners)
            world_top = max(c.y() for c in world_corners)
        else:
            world_right = visible_rect.right()
            world_top = visible_rect.top()
        
        x_pos_world = QPointF(world_right - 20, 15)
        x_pos_screen = saved_transform.map(x_pos_world)
        y_pos_world = QPointF(15, world_top - 15)
        y_pos_screen = saved_transform.map(y_pos_world)
        zero_pos_world = QPointF(15, 15)
        zero_pos_screen = saved_transform.map(zero_pos_world)
        
        painter.setFont(QFont("Arial", 10))
        painter.setPen(QPen(self.axis_color))
        painter.drawText(int(x_pos_screen.x()), int(x_pos_screen.y()), "X")
        painter.drawText(int(y_pos_screen.x()), int(y_pos_screen.y()), "Y")
        painter.drawText(int(zero_pos_screen.x()), int(zero_pos_screen.y()), "0")
        
        painter.setTransform(saved_transform)
    
    def _draw_selection_highlight(self, painter: QPainter, line: LineSegment):
        """Рисует подсветку выделенной линии"""
        highlight_pen = QPen(QColor(0, 100, 255), 1, Qt.DashLine)
        painter.setPen(highlight_pen)
        painter.setBrush(Qt.NoBrush)
        
        margin = 3.0 / self.viewport.get_scale()
        min_x = min(line.start_point.x(), line.end_point.x()) - margin
        max_x = max(line.start_point.x(), line.end_point.x()) + margin
        min_y = min(line.start_point.y(), line.end_point.y()) - margin
        max_y = max(line.start_point.y(), line.end_point.y()) + margin
        
        painter.drawRect(min_x, min_y, max_x - min_x, max_y - min_y)
    
    def set_grid_step(self, step_mm: float):
        """Устанавливает шаг сетки в миллиметрах"""
        self.grid_step = step_mm

