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


class PrimitiveRenderer:
    """Класс для отрисовки геометрических примитивов"""
    
    @staticmethod
    def _draw_ellipse_arc(painter: QPainter, arc, pen: QPen):
        """Отрисовывает дугу эллипса с учетом поворота"""
        import math
        from PySide6.QtGui import QPainterPath, QTransform
        from PySide6.QtCore import Qt
        
        # Сохраняем текущее состояние painter
        painter.save()
        
        # Применяем трансформацию: переносим центр в начало координат, поворачиваем, возвращаем
        transform = QTransform()
        transform.translate(arc.center.x(), arc.center.y())
        transform.rotate(math.degrees(arc.rotation_angle))
        painter.setTransform(transform, True)
        
        # Создаем прямоугольник для эллипса (в локальной системе, где хорда горизонтальна)
        rect = QRectF(
            -arc.radius_x,
            -arc.radius_y,
            arc.radius_x * 2,
            arc.radius_y * 2
        )
        
        # Углы уже в локальной системе координат (параметрические углы эллипса)
        # Они хранятся в градусах
        start_angle_deg = arc.start_angle
        end_angle_deg = arc.end_angle
        
        # Вычисляем span_angle
        # Если end_angle < start_angle, это может означать:
        # 1. Дуга проходит через 0/360 (нужно добавить 360)
        # 2. Дуга идет по часовой стрелке (отрицательный span)
        # Различаем по величине: если разница меньше -180, значит это проход через 0/360
        span_angle_deg = end_angle_deg - start_angle_deg
        
        # Если span отрицательный и меньше -180, значит дуга проходит через 0/360
        # и нужно добавить 360 для правильного отображения
        if span_angle_deg < -180:
            span_angle_deg += 360
        # Если span отрицательный и больше -180, это дуга по часовой стрелке
        # Оставляем отрицательный span (Qt arcTo поддерживает отрицательные значения)
        
        # Если span_angle равен 0 или 360, это означает, что дуга не должна рисоваться
        # Но это не должно происходить для нормальной дуги
        if abs(span_angle_deg) < 0.1:
            # Если span слишком мал, не рисуем дугу
            painter.restore()
            return
        
        # Создаем путь дуги
        path = QPainterPath()
        # В Qt arcTo принимает:
        # - rect: прямоугольник, описывающий эллипс
        # - startAngle: начальный угол в градусах (0 = 3 часа, 90 = 12 часов, 180 = 9 часов, 270 = 6 часов)
        # - sweepLength: длина дуги в градусах (положительное = против часовой стрелки)
        # arcMoveTo перемещает текущую точку на дугу, но не рисует линию
        # arcTo рисует дугу от текущей позиции
        path.arcMoveTo(rect, start_angle_deg)
        path.arcTo(rect, start_angle_deg, span_angle_deg)
        
        # Убеждаемся, что путь не пустой
        if path.isEmpty():
            # Если путь пустой, рисуем дугу напрямую через drawArc
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            # drawArc использует углы в 1/16 градуса
            start_angle_16 = int(start_angle_deg * 16)
            span_angle_16 = int(span_angle_deg * 16)
            painter.drawArc(rect, start_angle_16, span_angle_16)
        else:
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
        
        # Восстанавливаем состояние painter
        painter.restore()
    
    @staticmethod
    def draw_circle(painter: QPainter, circle, scale_factor: float = 1.0, is_selected: bool = False):
        """Отрисовывает окружность с поддержкой всех типов линий"""
        from widgets.primitives import Circle
        
        if circle.style:
            pen = circle.style.get_pen(scale_factor=scale_factor)
            if hasattr(circle, '_legacy_color') and circle._legacy_color != circle.style.color:
                pen.setColor(circle._legacy_color)
            if is_selected:
                pen.setWidthF(pen.widthF() * 1.5)
                color = pen.color()
                color.setAlpha(255)
                pen.setColor(color)
            
            line_type = circle.style.line_type
            
            # Для специальных типов линий используем специальную отрисовку
            if line_type == LineType.SOLID_WAVY:
                PrimitiveRenderer._draw_wavy_circle(painter, circle, pen)
            elif line_type == LineType.SOLID_THIN_BROKEN:
                PrimitiveRenderer._draw_broken_circle(painter, circle, pen)
            elif line_type == LineType.DASHED:
                PrimitiveRenderer._draw_dashed_circle(painter, circle, pen, circle.style)
            elif line_type in [LineType.DASH_DOT_THICK, LineType.DASH_DOT_THIN, LineType.DASH_DOT_TWO_DOTS]:
                PrimitiveRenderer._draw_dash_dot_circle(painter, circle, pen, circle.style)
            else:
                # Обычные сплошные линии
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(circle.center, circle.radius, circle.radius)
        else:
            pen = QPen(circle.color, circle.width)
            if is_selected:
                pen.setWidthF(pen.widthF() * 1.5)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(circle.center, circle.radius, circle.radius)
    
    @staticmethod
    def draw_arc(painter: QPainter, arc, scale_factor: float = 1.0, is_selected: bool = False):
        """Отрисовывает дугу эллипса с поддержкой всех типов линий"""
        import math
        
        if arc.style:
            pen = arc.style.get_pen(scale_factor=scale_factor)
            if hasattr(arc, '_legacy_color') and arc._legacy_color != arc.style.color:
                pen.setColor(arc._legacy_color)
            if is_selected:
                pen.setWidthF(pen.widthF() * 1.5)
                color = pen.color()
                color.setAlpha(255)
                pen.setColor(color)
            
            line_type = arc.style.line_type
            
            # Для специальных типов линий используем специальную отрисовку
            if line_type == LineType.SOLID_WAVY:
                PrimitiveRenderer._draw_wavy_arc(painter, arc, pen)
            elif line_type == LineType.SOLID_THIN_BROKEN:
                PrimitiveRenderer._draw_broken_arc(painter, arc, pen)
            elif line_type == LineType.DASHED:
                PrimitiveRenderer._draw_dashed_arc(painter, arc, pen, arc.style)
            elif line_type in [LineType.DASH_DOT_THICK, LineType.DASH_DOT_THIN, LineType.DASH_DOT_TWO_DOTS]:
                PrimitiveRenderer._draw_dash_dot_arc(painter, arc, pen, arc.style)
            else:
                # Обычные сплошные линии
                PrimitiveRenderer._draw_ellipse_arc(painter, arc, pen)
        else:
            pen = QPen(arc.color, arc.width)
            if is_selected:
                pen.setWidthF(pen.widthF() * 1.5)
            PrimitiveRenderer._draw_ellipse_arc(painter, arc, pen)
    
    @staticmethod
    def draw_rectangle(painter: QPainter, rectangle, scale_factor: float = 1.0, is_selected: bool = False):
        """Отрисовывает прямоугольник с поддержкой всех типов линий"""
        if rectangle.style:
            pen = rectangle.style.get_pen(scale_factor=scale_factor)
            if hasattr(rectangle, '_legacy_color') and rectangle._legacy_color != rectangle.style.color:
                pen.setColor(rectangle._legacy_color)
            if is_selected:
                pen.setWidthF(pen.widthF() * 1.5)
                color = pen.color()
                color.setAlpha(255)
                pen.setColor(color)
            
            line_type = rectangle.style.line_type
            
            # Для специальных типов линий используем специальную отрисовку
            if line_type == LineType.SOLID_WAVY:
                PrimitiveRenderer._draw_wavy_rectangle(painter, rectangle, pen)
            elif line_type == LineType.SOLID_THIN_BROKEN:
                PrimitiveRenderer._draw_broken_rectangle(painter, rectangle, pen)
            elif line_type == LineType.DASHED:
                PrimitiveRenderer._draw_dashed_rectangle(painter, rectangle, pen, rectangle.style)
            elif line_type in [LineType.DASH_DOT_THICK, LineType.DASH_DOT_THIN, LineType.DASH_DOT_TWO_DOTS]:
                PrimitiveRenderer._draw_dash_dot_rectangle(painter, rectangle, pen, rectangle.style)
            else:
                # Обычные сплошные линии
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                rect = rectangle.get_bounding_box()
                # Проверяем, есть ли скругление углов
                fillet_radius = getattr(rectangle, 'fillet_radius', 0.0)
                if fillet_radius > 0:
                    # Рисуем прямоугольник со скругленными углами
                    path = QPainterPath()
                    w = rect.width()
                    h = rect.height()
                    r = min(fillet_radius, w / 2, h / 2)  # Ограничиваем радиус
                    path.moveTo(rect.x() + r, rect.y())
                    path.lineTo(rect.x() + w - r, rect.y())
                    path.arcTo(rect.x() + w - 2*r, rect.y(), 2*r, 2*r, 90, -90)
                    path.lineTo(rect.x() + w, rect.y() + h - r)
                    path.arcTo(rect.x() + w - 2*r, rect.y() + h - 2*r, 2*r, 2*r, 0, -90)
                    path.lineTo(rect.x() + r, rect.y() + h)
                    path.arcTo(rect.x(), rect.y() + h - 2*r, 2*r, 2*r, 270, -90)
                    path.lineTo(rect.x(), rect.y() + r)
                    path.arcTo(rect.x(), rect.y(), 2*r, 2*r, 180, -90)
                    path.closeSubpath()
                    painter.drawPath(path)
                else:
                    painter.drawRect(rect)
        else:
            pen = QPen(rectangle.color, rectangle.width)
            if is_selected:
                pen.setWidthF(pen.widthF() * 1.5)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            rect = rectangle.get_bounding_box()
            # Проверяем, есть ли скругление углов
            fillet_radius = getattr(rectangle, 'fillet_radius', 0.0)
            if fillet_radius > 0:
                # Рисуем прямоугольник со скругленными углами
                path = QPainterPath()
                w = rect.width()
                h = rect.height()
                r = min(fillet_radius, w / 2, h / 2)  # Ограничиваем радиус
                path.moveTo(rect.x() + r, rect.y())
                path.lineTo(rect.x() + w - r, rect.y())
                path.arcTo(rect.x() + w - 2*r, rect.y(), 2*r, 2*r, 90, -90)
                path.lineTo(rect.x() + w, rect.y() + h - r)
                path.arcTo(rect.x() + w - 2*r, rect.y() + h - 2*r, 2*r, 2*r, 0, -90)
                path.lineTo(rect.x() + r, rect.y() + h)
                path.arcTo(rect.x(), rect.y() + h - 2*r, 2*r, 2*r, 270, -90)
                path.lineTo(rect.x(), rect.y() + r)
                path.arcTo(rect.x(), rect.y(), 2*r, 2*r, 180, -90)
                path.closeSubpath()
                painter.drawPath(path)
            else:
                painter.drawRect(rect)
    
    @staticmethod
    def draw_ellipse(painter: QPainter, ellipse, scale_factor: float = 1.0, is_selected: bool = False):
        """Отрисовывает эллипс с поддержкой всех типов линий"""
        if ellipse.style:
            pen = ellipse.style.get_pen(scale_factor=scale_factor)
            if hasattr(ellipse, '_legacy_color') and ellipse._legacy_color != ellipse.style.color:
                pen.setColor(ellipse._legacy_color)
            if is_selected:
                pen.setWidthF(pen.widthF() * 1.5)
                color = pen.color()
                color.setAlpha(255)
                pen.setColor(color)
            
            line_type = ellipse.style.line_type
            
            # Для специальных типов линий используем специальную отрисовку
            if line_type == LineType.SOLID_WAVY:
                PrimitiveRenderer._draw_wavy_ellipse(painter, ellipse, pen)
            elif line_type == LineType.SOLID_THIN_BROKEN:
                PrimitiveRenderer._draw_broken_ellipse(painter, ellipse, pen)
            elif line_type == LineType.DASHED:
                PrimitiveRenderer._draw_dashed_ellipse(painter, ellipse, pen, ellipse.style)
            elif line_type in [LineType.DASH_DOT_THICK, LineType.DASH_DOT_THIN, LineType.DASH_DOT_TWO_DOTS]:
                PrimitiveRenderer._draw_dash_dot_ellipse(painter, ellipse, pen, ellipse.style)
            else:
                # Обычные сплошные линии
                PrimitiveRenderer._draw_ellipse_with_rotation(painter, ellipse, pen)
        else:
            pen = QPen(ellipse.color, ellipse.width)
            if is_selected:
                pen.setWidthF(pen.widthF() * 1.5)
            PrimitiveRenderer._draw_ellipse_with_rotation(painter, ellipse, pen)
    
    @staticmethod
    def draw_polygon(painter: QPainter, polygon, scale_factor: float = 1.0, is_selected: bool = False):
        """Отрисовывает многоугольник с поддержкой всех типов линий"""
        from PySide6.QtGui import QPainterPath
        
        vertices = polygon.get_vertices()
        if len(vertices) < 3:
            return
        
        if polygon.style:
            pen = polygon.style.get_pen(scale_factor=scale_factor)
            if hasattr(polygon, '_legacy_color') and polygon._legacy_color != polygon.style.color:
                pen.setColor(polygon._legacy_color)
            if is_selected:
                pen.setWidthF(pen.widthF() * 1.5)
                color = pen.color()
                color.setAlpha(255)
                pen.setColor(color)
            
            line_type = polygon.style.line_type
            
            # Для специальных типов линий используем специальную отрисовку
            if line_type == LineType.SOLID_WAVY:
                PrimitiveRenderer._draw_wavy_polygon(painter, polygon, pen)
            elif line_type == LineType.SOLID_THIN_BROKEN:
                PrimitiveRenderer._draw_broken_polygon(painter, polygon, pen)
            elif line_type == LineType.DASHED:
                PrimitiveRenderer._draw_dashed_polygon(painter, polygon, pen, polygon.style)
            elif line_type in [LineType.DASH_DOT_THICK, LineType.DASH_DOT_THIN, LineType.DASH_DOT_TWO_DOTS]:
                PrimitiveRenderer._draw_dash_dot_polygon(painter, polygon, pen, polygon.style)
            else:
                # Обычные сплошные линии
                path = QPainterPath()
                path.moveTo(vertices[0])
                for i in range(1, len(vertices)):
                    path.lineTo(vertices[i])
                path.closeSubpath()
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(path)
        else:
            pen = QPen(polygon.color, polygon.width)
            if is_selected:
                pen.setWidthF(pen.widthF() * 1.5)
            path = QPainterPath()
            path.moveTo(vertices[0])
            for i in range(1, len(vertices)):
                path.lineTo(vertices[i])
            path.closeSubpath()
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
    
    # Методы специальной отрисовки для окружностей
    @staticmethod
    def _draw_wavy_circle(painter: QPainter, circle, pen: QPen):
        """Отрисовывает волнистую окружность (как отрезок, скрученный в круг)"""
        import math
        from PySide6.QtGui import QPainterPath
        
        circumference = 2 * math.pi * circle.radius
        if circumference < 1:
            return
        
        # Используем тот же алгоритм, что и для отрезков
        main_thickness_mm = 0.8
        line_thickness_mm = pen.widthF() * 25.4 / 96
        amplitude_mm = (main_thickness_mm / 2.5) * (line_thickness_mm / 0.4)
        amplitude_px = (amplitude_mm * 96) / 25.4
        
        wave_length_px = amplitude_px * 5
        num_waves = max(1, int(circumference / wave_length_px))
        actual_wave_length = circumference / num_waves if num_waves > 0 else circumference
        
        path = QPainterPath()
        num_points = max(100, int(circumference / 2))
        
        for i in range(num_points + 1):
            t = i / num_points
            # Позиция вдоль окружности (в радианах)
            angle = 2 * math.pi * t
            # Длина пройденного пути вдоль окружности
            along_circle = t * circumference
            
            # Синусоидальное смещение (как в отрезке)
            wave_phase = (along_circle / actual_wave_length) * 2 * math.pi
            wave_offset = amplitude_px * math.sin(wave_phase)
            
            # Применяем смещение по радиусу (перпендикулярно к окружности)
            radius_with_wave = circle.radius + wave_offset
            x = circle.center.x() + radius_with_wave * math.cos(angle)
            y = circle.center.y() + radius_with_wave * math.sin(angle)
            
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
    
    @staticmethod
    def _draw_broken_circle(painter: QPainter, circle, pen: QPen):
        """Отрисовывает окружность с одним зигзагом"""
        import math
        from PySide6.QtGui import QPainterPath
        
        circumference = 2 * math.pi * circle.radius
        if circumference < 1:
            return
        
        # Параметры зигзага (как в отрезке)
        zigzag_height_mm = 3.5
        zigzag_width_mm = 4.0
        dpi = 96
        zigzag_height = (zigzag_height_mm * dpi) / 25.4
        zigzag_length = (zigzag_width_mm * dpi) / 25.4
        
        # Конвертируем длину зигзага в угол
        zigzag_angle = (zigzag_length / circumference) * 2 * math.pi
        if zigzag_angle > math.pi * 0.8:
            zigzag_angle = math.pi * 0.8
        
        # Угол начала зигзага (в середине окружности)
        start_zigzag_angle = math.pi - zigzag_angle / 2
        end_zigzag_angle = math.pi + zigzag_angle / 2
        
        path = QPainterPath()
        
        # Рисуем первую часть окружности (до зигзага)
        num_points_start = max(20, int(start_zigzag_angle / (2 * math.pi) * 100))
        for i in range(num_points_start + 1):
            angle = 2 * math.pi * i / num_points_start * (start_zigzag_angle / (2 * math.pi))
            x = circle.center.x() + circle.radius * math.cos(angle)
            y = circle.center.y() + circle.radius * math.sin(angle)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        
        # Рисуем зигзаг
        zigzag_start_angle = start_zigzag_angle
        zigzag_mid1_angle = start_zigzag_angle + zigzag_angle / 3
        zigzag_mid2_angle = start_zigzag_angle + 2 * zigzag_angle / 3
        zigzag_end_angle = end_zigzag_angle
        
        # Точка начала зигзага
        p1 = QPointF(
            circle.center.x() + circle.radius * math.cos(zigzag_start_angle),
            circle.center.y() + circle.radius * math.sin(zigzag_start_angle)
        )
        path.lineTo(p1)
        
        # Первая точка зигзага (вверх)
        p2 = QPointF(
            circle.center.x() + (circle.radius + zigzag_height / 2) * math.cos(zigzag_mid1_angle),
            circle.center.y() + (circle.radius + zigzag_height / 2) * math.sin(zigzag_mid1_angle)
        )
        path.lineTo(p2)
        
        # Вторая точка зигзага (вниз)
        p3 = QPointF(
            circle.center.x() + (circle.radius - zigzag_height) * math.cos(zigzag_mid2_angle),
            circle.center.y() + (circle.radius - zigzag_height) * math.sin(zigzag_mid2_angle)
        )
        path.lineTo(p3)
        
        # Конец зигзага
        p4 = QPointF(
            circle.center.x() + circle.radius * math.cos(zigzag_end_angle),
            circle.center.y() + circle.radius * math.sin(zigzag_end_angle)
        )
        path.lineTo(p4)
        
        # Рисуем оставшуюся часть окружности
        remaining_angle = 2 * math.pi - end_zigzag_angle
        num_points_end = max(20, int(remaining_angle / (2 * math.pi) * 100))
        for i in range(1, num_points_end + 1):
            angle = end_zigzag_angle + (remaining_angle * i / num_points_end)
            x = circle.center.x() + circle.radius * math.cos(angle)
            y = circle.center.y() + circle.radius * math.sin(angle)
            path.lineTo(x, y)
        
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
    
    @staticmethod
    def _draw_dashed_circle(painter: QPainter, circle, pen: QPen, style):
        """Отрисовывает штриховую окружность с равномерным распределением"""
        import math
        
        dash_length = style.dash_length
        dash_gap = style.dash_gap
        circumference = 2 * math.pi * circle.radius
        
        if circumference < 0.1:
            return
        
        # Вычисляем, сколько полных паттернов (dash + gap) помещается в окружность
        pattern_length = dash_length + dash_gap
        num_patterns = circumference / pattern_length
        
        # Если паттернов меньше 1, рисуем один штрих
        if num_patterns < 1:
            rect = QRectF(
                circle.center.x() - circle.radius,
                circle.center.y() - circle.radius,
                circle.radius * 2,
                circle.radius * 2
            )
            painter.setPen(pen)
            painter.drawArc(rect, 0, int(360 * 16))
            return
        
        # Равномерно распределяем штрихи и пробелы по всей окружности
        # Учитываем, что окружность замкнута
        num_full_patterns = int(num_patterns)
        remaining_length = circumference - num_full_patterns * pattern_length
        
        # Если остаток больше длины штриха, добавляем еще один штрих
        if remaining_length >= dash_length:
            num_dashes = num_full_patterns + 1
            # Равномерно распределяем оставшееся пространство между пробелами
            total_gap_length = (num_dashes - 1) * dash_gap + remaining_length - dash_length
            if num_dashes > 1:
                adjusted_gap = total_gap_length / (num_dashes - 1)
            else:
                adjusted_gap = dash_gap
        else:
            num_dashes = num_full_patterns
            adjusted_gap = dash_gap + remaining_length / max(1, num_dashes - 1) if num_dashes > 1 else dash_gap
        
        # Вычисляем углы с учетом равномерного распределения
        total_angle = 2 * math.pi
        dash_angle_rad = (dash_length / circumference) * total_angle
        gap_angle_rad = (adjusted_gap / circumference) * total_angle
        
        painter.setPen(pen)
        current_angle_rad = 0
        
        rect = QRectF(
            circle.center.x() - circle.radius,
            circle.center.y() - circle.radius,
            circle.radius * 2,
            circle.radius * 2
        )
        
        for i in range(num_dashes):
            start_angle_rad = current_angle_rad
            end_angle_rad = start_angle_rad + dash_angle_rad
            
            # Ограничиваем конечный угол, чтобы не выйти за пределы окружности
            if end_angle_rad > total_angle:
                end_angle_rad = total_angle
            
            # Рисуем дугу для штриха (углы в 1/16 градуса)
            start_angle_16 = int(start_angle_rad * 16 * 180 / math.pi)
            span_angle_16 = int((end_angle_rad - start_angle_rad) * 16 * 180 / math.pi)
            painter.drawArc(rect, start_angle_16, span_angle_16)
            
            current_angle_rad = end_angle_rad + gap_angle_rad
            
            # Если дошли до конца окружности, выходим
            if current_angle_rad >= total_angle:
                break
    
    @staticmethod
    def _draw_dash_dot_circle(painter: QPainter, circle, pen: QPen, style):
        """Отрисовывает штрихпунктирную окружность"""
        import math
        
        dash_length = style.dash_length
        dash_gap = style.dash_gap
        dot_length = style.thickness_mm * 0.5
        circumference = 2 * math.pi * circle.radius
        
        if circumference < 0.1:
            return
        
        if style.line_type == LineType.DASH_DOT_TWO_DOTS:
            pattern = [dash_length, dash_gap, dot_length, dash_gap, dot_length, dash_gap]
        else:
            pattern = [dash_length, dash_gap, dot_length, dash_gap]
        
        painter.setPen(pen)
        current_angle = 0
        pattern_index = 0
        
        while current_angle < 2 * math.pi:
            segment_length = pattern[pattern_index % len(pattern)]
            segment_angle = (segment_length / circumference) * 2 * math.pi
            
            is_gap = (segment_length == dash_gap)
            
            if not is_gap:
                start_angle = current_angle
                end_angle = current_angle + segment_angle
                
                rect = QRectF(
                    circle.center.x() - circle.radius,
                    circle.center.y() - circle.radius,
                    circle.radius * 2,
                    circle.radius * 2
                )
                painter.drawArc(rect, int(start_angle * 16 * 180 / math.pi), 
                              int((end_angle - start_angle) * 16 * 180 / math.pi))
            
            current_angle += segment_angle
            pattern_index += 1
    
    # Методы специальной отрисовки для прямоугольников
    @staticmethod
    def _draw_wavy_rectangle(painter: QPainter, rectangle, pen: QPen):
        """Отрисовывает волнистый прямоугольник"""
        fillet_radius = getattr(rectangle, 'fillet_radius', 0.0)
        if fillet_radius > 0:
            # Для скругленных углов используем обычную отрисовку со скруглениями
            PrimitiveRenderer.draw_rectangle(painter, rectangle, 1.0, False)
            return
        
        bbox = rectangle.get_bounding_box()
        corners = [
            QPointF(bbox.left(), bbox.top()),
            QPointF(bbox.right(), bbox.top()),
            QPointF(bbox.right(), bbox.bottom()),
            QPointF(bbox.left(), bbox.bottom())
        ]
        
        # Рисуем каждую сторону как волнистую линию
        for i in range(4):
            start = corners[i]
            end = corners[(i + 1) % 4]
            LineRenderer._draw_wavy_line(painter, start, end, pen)
    
    @staticmethod
    def _draw_broken_rectangle(painter: QPainter, rectangle, pen: QPen):
        """Отрисовывает прямоугольник с изломами"""
        fillet_radius = getattr(rectangle, 'fillet_radius', 0.0)
        if fillet_radius > 0:
            # Для скругленных углов используем обычную отрисовку со скруглениями
            PrimitiveRenderer.draw_rectangle(painter, rectangle, 1.0, False)
            return
        
        bbox = rectangle.get_bounding_box()
        corners = [
            QPointF(bbox.left(), bbox.top()),
            QPointF(bbox.right(), bbox.top()),
            QPointF(bbox.right(), bbox.bottom()),
            QPointF(bbox.left(), bbox.bottom())
        ]
        
        # Рисуем каждую сторону как линию с изломами
        for i in range(4):
            start = corners[i]
            end = corners[(i + 1) % 4]
            LineRenderer._draw_broken_line(painter, start, end, pen)
    
    @staticmethod
    def _draw_dashed_rectangle(painter: QPainter, rectangle, pen: QPen, style):
        """Отрисовывает штриховой прямоугольник"""
        fillet_radius = getattr(rectangle, 'fillet_radius', 0.0)
        if fillet_radius > 0:
            # Для скругленных углов используем обычную отрисовку со скруглениями
            PrimitiveRenderer.draw_rectangle(painter, rectangle, 1.0, False)
            return
        
        bbox = rectangle.get_bounding_box()
        corners = [
            QPointF(bbox.left(), bbox.top()),
            QPointF(bbox.right(), bbox.top()),
            QPointF(bbox.right(), bbox.bottom()),
            QPointF(bbox.left(), bbox.bottom())
        ]
        
        # Рисуем каждую сторону как штриховую линию
        for i in range(4):
            start = corners[i]
            end = corners[(i + 1) % 4]
            LineRenderer._draw_dashed_line(painter, start, end, pen, style)
    
    @staticmethod
    def _draw_dash_dot_rectangle(painter: QPainter, rectangle, pen: QPen, style):
        """Отрисовывает штрихпунктирный прямоугольник"""
        fillet_radius = getattr(rectangle, 'fillet_radius', 0.0)
        if fillet_radius > 0:
            # Для скругленных углов используем обычную отрисовку со скруглениями
            PrimitiveRenderer.draw_rectangle(painter, rectangle, 1.0, False)
            return
        
        bbox = rectangle.get_bounding_box()
        corners = [
            QPointF(bbox.left(), bbox.top()),
            QPointF(bbox.right(), bbox.top()),
            QPointF(bbox.right(), bbox.bottom()),
            QPointF(bbox.left(), bbox.bottom())
        ]
        
        # Рисуем каждую сторону как штрихпунктирную линию
        for i in range(4):
            start = corners[i]
            end = corners[(i + 1) % 4]
            LineRenderer._draw_dash_dot_line(painter, start, end, pen, style)
    
    # Методы специальной отрисовки для эллипсов
    @staticmethod
    def _draw_ellipse_with_rotation(painter: QPainter, ellipse, pen: QPen):
        """Отрисовывает эллипс с учетом поворота"""
        import math
        from PySide6.QtGui import QTransform
        from PySide6.QtCore import Qt, QRectF
        
        # Сохраняем состояние painter
        painter.save()
        
        # Применяем трансформацию поворота
        if hasattr(ellipse, 'rotation_angle') and abs(ellipse.rotation_angle) > 1e-6:
            transform = QTransform()
            transform.translate(ellipse.center.x(), ellipse.center.y())
            transform.rotate(math.degrees(ellipse.rotation_angle))
            painter.setTransform(transform, True)
            
            # Рисуем эллипс в локальной системе координат
            rect = QRectF(-ellipse.radius_x, -ellipse.radius_y, 
                         ellipse.radius_x * 2, ellipse.radius_y * 2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(rect)
        else:
            # Без поворота - рисуем напрямую
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(ellipse.center, ellipse.radius_x, ellipse.radius_y)
        
        painter.restore()
    
    @staticmethod
    def _draw_wavy_ellipse(painter: QPainter, ellipse, pen: QPen):
        """Отрисовывает волнистый эллипс (как отрезок, скрученный в эллипс) с учетом поворота"""
        import math
        from PySide6.QtGui import QPainterPath, QTransform
        from PySide6.QtCore import Qt, QPointF
        
        # Сохраняем состояние painter
        painter.save()
        
        # Применяем трансформацию поворота
        rotation_angle = getattr(ellipse, 'rotation_angle', 0.0)
        if abs(rotation_angle) > 1e-6:
            transform = QTransform()
            transform.translate(ellipse.center.x(), ellipse.center.y())
            transform.rotate(math.degrees(rotation_angle))
            painter.setTransform(transform, True)
            center_offset = QPointF(0, 0)
        else:
            center_offset = ellipse.center
        
        # Приблизительная длина окружности эллипса
        a = ellipse.radius_x
        b = ellipse.radius_y
        if (a + b) <= 0 or a <= 0 or b <= 0:
            painter.restore()
            return
        h = ((a - b) / (a + b)) ** 2
        circumference = math.pi * (a + b) * (1 + (3 * h) / (10 + math.sqrt(4 - 3 * h)))
        
        if circumference < 1:
            painter.restore()
            return
        
        # Используем тот же алгоритм, что и для отрезков
        main_thickness_mm = 0.8
        line_thickness_mm = pen.widthF() * 25.4 / 96
        amplitude_mm = (main_thickness_mm / 2.5) * (line_thickness_mm / 0.4)
        amplitude_px = (amplitude_mm * 96) / 25.4
        
        wave_length_px = amplitude_px * 5
        num_waves = max(1, int(circumference / wave_length_px))
        actual_wave_length = circumference / num_waves if num_waves > 0 else circumference
        
        path = QPainterPath()
        num_points = max(100, int(circumference / 2))
        
        for i in range(num_points + 1):
            t = i / num_points
            # Параметрический угол эллипса
            angle = 2 * math.pi * t
            # Длина пройденного пути вдоль эллипса
            along_ellipse = t * circumference
            
            # Синусоидальное смещение (как в отрезке)
            wave_phase = (along_ellipse / actual_wave_length) * 2 * math.pi
            wave_offset = amplitude_px * math.sin(wave_phase)
            
            # Применяем смещение по нормали к эллипсу
            # Нормаль к эллипсу в точке (a*cos(t), b*sin(t)) пропорциональна (b*cos(t), a*sin(t))
            normal_x = b * math.cos(angle)
            normal_y = a * math.sin(angle)
            normal_length = math.sqrt(normal_x * normal_x + normal_y * normal_y)
            if normal_length > 0:
                normal_x /= normal_length
                normal_y /= normal_length
            
            # Точка на эллипсе (в локальной системе координат, если есть поворот)
            base_x = center_offset.x() + ellipse.radius_x * math.cos(angle)
            base_y = center_offset.y() + ellipse.radius_y * math.sin(angle)
            
            # Применяем волну по нормали
            x = base_x + wave_offset * normal_x
            y = base_y + wave_offset * normal_y
            
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        
        painter.restore()
    
    @staticmethod
    def _draw_broken_ellipse(painter: QPainter, ellipse, pen: QPen):
        """Отрисовывает эллипс с одним зигзагом с учетом поворота"""
        import math
        from PySide6.QtGui import QPainterPath, QTransform
        from PySide6.QtCore import QPointF
        
        # Сохраняем состояние painter
        painter.save()
        
        # Применяем трансформацию поворота
        rotation_angle = getattr(ellipse, 'rotation_angle', 0.0)
        if abs(rotation_angle) > 1e-6:
            transform = QTransform()
            transform.translate(ellipse.center.x(), ellipse.center.y())
            transform.rotate(math.degrees(rotation_angle))
            painter.setTransform(transform, True)
            center_offset = QPointF(0, 0)
        else:
            center_offset = ellipse.center
        
        # Приблизительная длина окружности эллипса
        a = ellipse.radius_x
        b = ellipse.radius_y
        if (a + b) <= 0 or a <= 0 or b <= 0:
            painter.restore()
            return
        h = ((a - b) / (a + b)) ** 2
        circumference = math.pi * (a + b) * (1 + (3 * h) / (10 + math.sqrt(4 - 3 * h)))
        
        if circumference < 1:
            painter.restore()
            return
        
        # Параметры зигзага
        zigzag_height_mm = 3.5
        zigzag_width_mm = 4.0
        dpi = 96
        zigzag_height = (zigzag_height_mm * dpi) / 25.4
        zigzag_length = (zigzag_width_mm * dpi) / 25.4
        
        # Конвертируем длину зигзага в угол
        zigzag_angle = (zigzag_length / circumference) * 2 * math.pi
        if zigzag_angle > math.pi * 0.8:
            zigzag_angle = math.pi * 0.8
        
        # Угол начала зигзага (в середине эллипса)
        start_zigzag_angle = math.pi - zigzag_angle / 2
        end_zigzag_angle = math.pi + zigzag_angle / 2
        
        path = QPainterPath()
        
        # Рисуем первую часть эллипса (до зигзага)
        num_points_start = max(20, int(start_zigzag_angle / (2 * math.pi) * 100))
        for i in range(num_points_start + 1):
            angle = 2 * math.pi * i / num_points_start * (start_zigzag_angle / (2 * math.pi))
            x = center_offset.x() + ellipse.radius_x * math.cos(angle)
            y = center_offset.y() + ellipse.radius_y * math.sin(angle)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        
        # Рисуем зигзаг
        zigzag_start_angle = start_zigzag_angle
        zigzag_mid1_angle = start_zigzag_angle + zigzag_angle / 3
        zigzag_mid2_angle = start_zigzag_angle + 2 * zigzag_angle / 3
        zigzag_end_angle = end_zigzag_angle
        
        # Вычисляем нормали для зигзага
        def get_normal(angle):
            normal_x = b * math.cos(angle)
            normal_y = a * math.sin(angle)
            normal_length = math.sqrt(normal_x * normal_x + normal_y * normal_y)
            if normal_length > 0:
                return normal_x / normal_length, normal_y / normal_length
            return math.cos(angle), math.sin(angle)
        
        # Точка начала зигзага
        p1 = QPointF(
            center_offset.x() + ellipse.radius_x * math.cos(zigzag_start_angle),
            center_offset.y() + ellipse.radius_y * math.sin(zigzag_start_angle)
        )
        path.lineTo(p1)
        
        # Первая точка зигзага (вверх)
        norm1_x, norm1_y = get_normal(zigzag_mid1_angle)
        p2 = QPointF(
            center_offset.x() + ellipse.radius_x * math.cos(zigzag_mid1_angle) + (zigzag_height / 2) * norm1_x,
            center_offset.y() + ellipse.radius_y * math.sin(zigzag_mid1_angle) + (zigzag_height / 2) * norm1_y
        )
        path.lineTo(p2)
        
        # Вторая точка зигзага (вниз)
        norm2_x, norm2_y = get_normal(zigzag_mid2_angle)
        p3 = QPointF(
            center_offset.x() + ellipse.radius_x * math.cos(zigzag_mid2_angle) - zigzag_height * norm2_x,
            center_offset.y() + ellipse.radius_y * math.sin(zigzag_mid2_angle) - zigzag_height * norm2_y
        )
        path.lineTo(p3)
        
        # Конец зигзага
        p4 = QPointF(
            center_offset.x() + ellipse.radius_x * math.cos(zigzag_end_angle),
            center_offset.y() + ellipse.radius_y * math.sin(zigzag_end_angle)
        )
        path.lineTo(p4)
        
        # Рисуем оставшуюся часть эллипса
        remaining_angle = 2 * math.pi - end_zigzag_angle
        num_points_end = max(20, int(remaining_angle / (2 * math.pi) * 100))
        for i in range(1, num_points_end + 1):
            angle = end_zigzag_angle + (remaining_angle * i / num_points_end)
            x = center_offset.x() + ellipse.radius_x * math.cos(angle)
            y = center_offset.y() + ellipse.radius_y * math.sin(angle)
            path.lineTo(x, y)
        
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        
        painter.restore()
    
    @staticmethod
    def _draw_dashed_ellipse(painter: QPainter, ellipse, pen: QPen, style):
        """Отрисовывает штриховой эллипс с равномерным распределением и учетом поворота"""
        import math
        from PySide6.QtGui import QTransform
        from PySide6.QtCore import QRectF
        
        # Сохраняем состояние painter
        painter.save()
        
        # Применяем трансформацию поворота
        rotation_angle = getattr(ellipse, 'rotation_angle', 0.0)
        if abs(rotation_angle) > 1e-6:
            transform = QTransform()
            transform.translate(ellipse.center.x(), ellipse.center.y())
            transform.rotate(math.degrees(rotation_angle))
            painter.setTransform(transform, True)
            # В локальной системе координат центр в (0, 0)
            center_x, center_y = 0, 0
        else:
            center_x, center_y = ellipse.center.x(), ellipse.center.y()
        
        dash_length = style.dash_length
        dash_gap = style.dash_gap
        
        # Приблизительная длина окружности эллипса
        a = ellipse.radius_x
        b = ellipse.radius_y
        if (a + b) <= 0 or a <= 0 or b <= 0:
            painter.restore()
            return
        h = ((a - b) / (a + b)) ** 2
        circumference = math.pi * (a + b) * (1 + (3 * h) / (10 + math.sqrt(4 - 3 * h)))
        
        if circumference < 0.1:
            painter.restore()
            return
        
        # Вычисляем, сколько полных паттернов (dash + gap) помещается в окружность
        pattern_length = dash_length + dash_gap
        num_patterns = circumference / pattern_length
        
        # Если паттернов меньше 1, рисуем один штрих
        if num_patterns < 1:
            rect = QRectF(
                center_x - ellipse.radius_x,
                center_y - ellipse.radius_y,
                ellipse.radius_x * 2,
                ellipse.radius_y * 2
            )
            painter.setPen(pen)
            painter.drawArc(rect, 0, int(360 * 16))
            painter.restore()
            return
        
        # Равномерно распределяем штрихи и пробелы по всей окружности
        num_full_patterns = int(num_patterns)
        remaining_length = circumference - num_full_patterns * pattern_length
        
        # Если остаток больше длины штриха, добавляем еще один штрих
        if remaining_length >= dash_length:
            num_dashes = num_full_patterns + 1
            total_gap_length = (num_dashes - 1) * dash_gap + remaining_length - dash_length
            if num_dashes > 1:
                adjusted_gap = total_gap_length / (num_dashes - 1)
            else:
                adjusted_gap = dash_gap
        else:
            num_dashes = num_full_patterns
            adjusted_gap = dash_gap + remaining_length / max(1, num_dashes - 1) if num_dashes > 1 else dash_gap
        
        # Вычисляем углы с учетом равномерного распределения
        total_angle = 2 * math.pi
        dash_angle_rad = (dash_length / circumference) * total_angle
        gap_angle_rad = (adjusted_gap / circumference) * total_angle
        
        painter.setPen(pen)
        current_angle_rad = 0
        
        rect = QRectF(
            center_x - ellipse.radius_x,
            center_y - ellipse.radius_y,
            ellipse.radius_x * 2,
            ellipse.radius_y * 2
        )
        
        for i in range(num_dashes):
            start_angle_rad = current_angle_rad
            end_angle_rad = start_angle_rad + dash_angle_rad
            
            # Ограничиваем конечный угол, чтобы не выйти за пределы окружности
            if end_angle_rad > total_angle:
                end_angle_rad = total_angle
            
            # Рисуем дугу эллипса (углы в 1/16 градуса)
            start_angle_16 = int(start_angle_rad * 16 * 180 / math.pi)
            span_angle_16 = int((end_angle_rad - start_angle_rad) * 16 * 180 / math.pi)
            painter.drawArc(rect, start_angle_16, span_angle_16)
            
            current_angle_rad = end_angle_rad + gap_angle_rad
            
            # Если дошли до конца окружности, выходим
            if current_angle_rad >= total_angle:
                break
        
        painter.restore()
    
    @staticmethod
    def _draw_dash_dot_ellipse(painter: QPainter, ellipse, pen: QPen, style):
        """Отрисовывает штрихпунктирный эллипс с учетом поворота"""
        import math
        from PySide6.QtGui import QTransform
        from PySide6.QtCore import QRectF
        
        # Сохраняем состояние painter
        painter.save()
        
        # Применяем трансформацию поворота
        rotation_angle = getattr(ellipse, 'rotation_angle', 0.0)
        if abs(rotation_angle) > 1e-6:
            transform = QTransform()
            transform.translate(ellipse.center.x(), ellipse.center.y())
            transform.rotate(math.degrees(rotation_angle))
            painter.setTransform(transform, True)
            # В локальной системе координат центр в (0, 0)
            center_x, center_y = 0, 0
        else:
            center_x, center_y = ellipse.center.x(), ellipse.center.y()
        
        dash_length = style.dash_length
        dash_gap = style.dash_gap
        dot_length = style.thickness_mm * 0.5
        
        # Приблизительная длина окружности эллипса
        a = ellipse.radius_x
        b = ellipse.radius_y
        if (a + b) <= 0 or a <= 0 or b <= 0:
            painter.restore()
            return
        h = ((a - b) / (a + b)) ** 2
        circumference = math.pi * (a + b) * (1 + (3 * h) / (10 + math.sqrt(4 - 3 * h)))
        
        if circumference < 0.1:
            painter.restore()
            return
        
        if style.line_type == LineType.DASH_DOT_TWO_DOTS:
            pattern = [dash_length, dash_gap, dot_length, dash_gap, dot_length, dash_gap]
        else:
            pattern = [dash_length, dash_gap, dot_length, dash_gap]
        
        painter.setPen(pen)
        current_angle = 0
        pattern_index = 0
        
        while current_angle < 2 * math.pi:
            segment_length = pattern[pattern_index % len(pattern)]
            segment_angle = (segment_length / circumference) * 2 * math.pi
            
            is_gap = (segment_length == dash_gap)
            
            if not is_gap:
                start_angle = current_angle
                end_angle = current_angle + segment_angle
                
                rect = QRectF(
                    center_x - ellipse.radius_x,
                    center_y - ellipse.radius_y,
                    ellipse.radius_x * 2,
                    ellipse.radius_y * 2
                )
                painter.drawArc(rect, int(start_angle * 16 * 180 / math.pi), 
                              int((end_angle - start_angle) * 16 * 180 / math.pi))
            
            current_angle += segment_angle
            pattern_index += 1
        
        painter.restore()
    
    # Методы специальной отрисовки для дуг
    @staticmethod
    def _draw_wavy_arc(painter: QPainter, arc, pen: QPen):
        """Отрисовывает волнистую дугу эллипса с учетом поворота"""
        import math
        from PySide6.QtGui import QPainterPath, QTransform
        
        # Сохраняем состояние painter
        painter.save()
        
        # Применяем трансформацию поворота
        transform = QTransform()
        transform.translate(arc.center.x(), arc.center.y())
        transform.rotate(math.degrees(arc.rotation_angle))
        painter.setTransform(transform, True)
        
        # Вычисляем span_angle с учетом направления
        span_angle_deg = arc.end_angle - arc.start_angle
        if span_angle_deg < -180:
            span_angle_deg += 360
        elif span_angle_deg > 180:
            span_angle_deg -= 360
        
        # Вычисляем длину дуги эллипса (используем абсолютное значение угла)
        angle_span_deg = abs(span_angle_deg)
        angle_span_rad = math.radians(angle_span_deg)
        # Приблизительная длина дуги эллипса
        avg_radius = (arc.radius_x + arc.radius_y) / 2
        arc_length = angle_span_rad * avg_radius
        
        if arc_length < 1:
            painter.restore()
            return
        
        # Используем тот же алгоритм, что и для отрезков
        main_thickness_mm = 0.8
        line_thickness_mm = pen.widthF() * 25.4 / 96
        amplitude_mm = (main_thickness_mm / 2.5) * (line_thickness_mm / 0.4)
        amplitude_px = (amplitude_mm * 96) / 25.4
        
        wave_length_px = amplitude_px * 5
        num_waves = max(1, int(arc_length / wave_length_px))
        actual_wave_length = arc_length / num_waves if num_waves > 0 else arc_length
        
        path = QPainterPath()
        num_points = max(50, int(arc_length / 2))
        
        for i in range(num_points + 1):
            t = i / num_points
            # Параметрический угол эллипса (в локальной системе)
            # Инвертируем направление для волнистой дуги
            param_angle_deg = arc.start_angle + t * (-span_angle_deg)
            param_angle_rad = math.radians(param_angle_deg)
            # Длина пройденного пути вдоль дуги
            along_arc = t * arc_length
            
            # Синусоидальное смещение (как в отрезке)
            wave_phase = (along_arc / actual_wave_length) * 2 * math.pi
            wave_offset = amplitude_px * math.sin(wave_phase)
            
            # Применяем смещение по нормали к эллипсу
            # Используем вектор от центра к точке на эллипсе как направление нормали
            # Это гарантирует, что нормаль всегда направлена наружу от эллипса
            base_x = arc.radius_x * math.cos(param_angle_rad)
            base_y = arc.radius_y * math.sin(param_angle_rad)
            normal_length = math.sqrt(base_x * base_x + base_y * base_y)
            if normal_length > 0:
                normal_x = base_x / normal_length
                normal_y = base_y / normal_length
            else:
                normal_x = math.cos(param_angle_rad)
                normal_y = math.sin(param_angle_rad)
            
            # Применяем волну по нормали
            x = base_x + wave_offset * normal_x
            y = base_y + wave_offset * normal_y
            
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        
        painter.restore()
    
    @staticmethod
    def _draw_broken_arc(painter: QPainter, arc, pen: QPen):
        """Отрисовывает дугу эллипса с одним зигзагом с учетом поворота"""
        import math
        from PySide6.QtGui import QPainterPath, QTransform
        
        # Сохраняем состояние painter
        painter.save()
        
        # Применяем трансформацию поворота
        transform = QTransform()
        transform.translate(arc.center.x(), arc.center.y())
        transform.rotate(math.degrees(arc.rotation_angle))
        painter.setTransform(transform, True)
        
        # Вычисляем span_angle с учетом направления
        span_angle_deg = arc.end_angle - arc.start_angle
        if span_angle_deg < -180:
            span_angle_deg += 360
        elif span_angle_deg > 180:
            span_angle_deg -= 360
        
        angle_span = abs(span_angle_deg)
        # Приблизительная длина дуги эллипса
        avg_radius = (arc.radius_x + arc.radius_y) / 2
        arc_length = math.radians(angle_span) * avg_radius
        
        if arc_length < 1:
            painter.restore()
            return
        
        # Параметры зигзага
        zigzag_height_mm = 3.5
        zigzag_width_mm = 4.0
        dpi = 96
        zigzag_height = (zigzag_height_mm * dpi) / 25.4
        zigzag_length = (zigzag_width_mm * dpi) / 25.4
        
        # Конвертируем длину зигзага в параметрический угол (используем абсолютное значение)
        zigzag_angle_abs = (zigzag_length / arc_length) * angle_span
        if zigzag_angle_abs > angle_span * 0.8:
            zigzag_angle_abs = angle_span * 0.8
        
        # Угол начала зигзага (в середине дуги)
        # Вычисляем середину с учетом направления
        # Инвертируем направление для ломаной дуги
        mid_angle = arc.start_angle + (-span_angle_deg) / 2
        # Используем инвертированный span_angle_deg для определения направления зигзага
        zigzag_angle = (zigzag_angle_abs / angle_span) * (-span_angle_deg) if angle_span > 0 else 0
        start_zigzag_angle = mid_angle - zigzag_angle / 2
        end_zigzag_angle = mid_angle + zigzag_angle / 2
        
        path = QPainterPath()
        
        # Рисуем первую часть дуги (до зигзага)
        # Определяем, какая точка ближе к началу дуги (с учетом инвертированного направления)
        inverted_span = -span_angle_deg
        if (inverted_span >= 0 and start_zigzag_angle > arc.start_angle) or \
           (inverted_span < 0 and start_zigzag_angle < arc.start_angle):
            num_points_start = max(10, int(abs(start_zigzag_angle - arc.start_angle) / angle_span * 50))
            for i in range(num_points_start + 1):
                param_angle_deg = arc.start_angle + (start_zigzag_angle - arc.start_angle) * i / num_points_start
                param_angle_rad = math.radians(param_angle_deg)
                x = arc.radius_x * math.cos(param_angle_rad)
                y = arc.radius_y * math.sin(param_angle_rad)
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
        
        # Рисуем зигзаг
        zigzag_start_angle = start_zigzag_angle
        zigzag_mid1_angle = start_zigzag_angle + zigzag_angle / 3
        zigzag_mid2_angle = start_zigzag_angle + 2 * zigzag_angle / 3
        zigzag_end_angle = end_zigzag_angle
        
        # Вычисляем нормали для зигзага
        # Используем вектор от центра к точке на эллипсе как направление нормали
        # Это гарантирует, что нормаль всегда направлена наружу от эллипса
        zigzag_offset_sign = 1
        
        def get_normal(param_angle_rad):
            base_x = arc.radius_x * math.cos(param_angle_rad)
            base_y = arc.radius_y * math.sin(param_angle_rad)
            normal_length = math.sqrt(base_x * base_x + base_y * base_y)
            if normal_length > 0:
                normal_x = base_x / normal_length
                normal_y = base_y / normal_length
                return normal_x, normal_y
            return math.cos(param_angle_rad), math.sin(param_angle_rad)
        
        # Точка начала зигзага
        t1 = math.radians(zigzag_start_angle)
        p1 = QPointF(arc.radius_x * math.cos(t1), arc.radius_y * math.sin(t1))
        path.lineTo(p1)
        
        # Первая точка зигзага (вверх)
        t2 = math.radians(zigzag_mid1_angle)
        norm1_x, norm1_y = get_normal(t2)
        p2 = QPointF(
            arc.radius_x * math.cos(t2) + (zigzag_height / 2) * norm1_x * zigzag_offset_sign,
            arc.radius_y * math.sin(t2) + (zigzag_height / 2) * norm1_y * zigzag_offset_sign
        )
        path.lineTo(p2)
        
        # Вторая точка зигзага (вниз)
        t3 = math.radians(zigzag_mid2_angle)
        norm2_x, norm2_y = get_normal(t3)
        p3 = QPointF(
            arc.radius_x * math.cos(t3) - zigzag_height * norm2_x * zigzag_offset_sign,
            arc.radius_y * math.sin(t3) - zigzag_height * norm2_y * zigzag_offset_sign
        )
        path.lineTo(p3)
        
        # Конец зигзага
        t4 = math.radians(zigzag_end_angle)
        p4 = QPointF(arc.radius_x * math.cos(t4), arc.radius_y * math.sin(t4))
        path.lineTo(p4)
        
        # Рисуем оставшуюся часть дуги
        # Вычисляем разность углов от конца зигзага до конца дуги
        # Используем исходное направление (span_angle_deg) для второй части
        angle_diff = arc.end_angle - end_zigzag_angle
        
        # Нормализуем разность углов
        if angle_diff > 180:
            angle_diff -= 360
        elif angle_diff < -180:
            angle_diff += 360
        
        # Если есть остаток дуги (разность углов не равна 0), рисуем вторую часть
        # Проверяем, что остаток идет в правильном направлении (совпадает с исходным направлением)
        if abs(angle_diff) > 0.1:
            # Используем исходное направление для второй части
            # Если исходное направление положительное (против часовой стрелки), то angle_diff должен быть положительным
            # Если исходное направление отрицательное (по часовой стрелке), то angle_diff должен быть отрицательным
            # Но так как мы инвертировали зигзаг, нужно проверить правильность направления
            num_points_end = max(10, int(abs(angle_diff) / angle_span * 50))
            for i in range(1, num_points_end + 1):
                param_angle_deg = end_zigzag_angle + angle_diff * i / num_points_end
                param_angle_rad = math.radians(param_angle_deg)
                x = arc.radius_x * math.cos(param_angle_rad)
                y = arc.radius_y * math.sin(param_angle_rad)
                path.lineTo(x, y)
        
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        
        painter.restore()
    
    @staticmethod
    def _draw_dashed_arc(painter: QPainter, arc, pen: QPen, style):
        """Отрисовывает штриховую дугу эллипса с равномерным распределением и учетом поворота"""
        import math
        from PySide6.QtGui import QTransform, QPainterPath
        
        # Сохраняем состояние painter
        painter.save()
        
        # Применяем трансформацию поворота
        transform = QTransform()
        transform.translate(arc.center.x(), arc.center.y())
        transform.rotate(math.degrees(arc.rotation_angle))
        painter.setTransform(transform, True)
        
        dash_length = style.dash_length
        dash_gap = style.dash_gap
        
        # Вычисляем span_angle с учетом направления
        span_angle_deg = arc.end_angle - arc.start_angle
        if span_angle_deg < -180:
            span_angle_deg += 360
        elif span_angle_deg > 180:
            span_angle_deg -= 360
        
        angle_span_deg = abs(span_angle_deg)
        angle_span_rad = math.radians(angle_span_deg)
        # Приблизительная длина дуги эллипса
        avg_radius = (arc.radius_x + arc.radius_y) / 2
        arc_length = angle_span_rad * avg_radius
        
        if arc_length < 0.1:
            painter.restore()
            return
        
        # Вычисляем, сколько полных паттернов (dash + gap) помещается в дугу
        pattern_length = dash_length + dash_gap
        num_patterns = arc_length / pattern_length
        
        # Если паттернов меньше 1, рисуем один штрих
        if num_patterns < 1:
            rect = QRectF(
                -arc.radius_x,
                -arc.radius_y,
                arc.radius_x * 2,
                arc.radius_y * 2
            )
            painter.setPen(pen)
            path = QPainterPath()
            path.arcMoveTo(rect, arc.start_angle)
            path.arcTo(rect, arc.start_angle, angle_span_deg)
            painter.drawPath(path)
            painter.restore()
            return
        
        # Равномерно распределяем штрихи и пробелы по всей дуге
        num_full_patterns = int(num_patterns)
        remaining_length = arc_length - num_full_patterns * pattern_length
        
        # Если остаток больше длины штриха, добавляем еще один штрих
        if remaining_length >= dash_length:
            num_dashes = num_full_patterns + 1
            total_gap_length = (num_dashes - 1) * dash_gap + remaining_length - dash_length
            if num_dashes > 1:
                adjusted_gap = total_gap_length / (num_dashes - 1)
            else:
                adjusted_gap = dash_gap
        else:
            num_dashes = num_full_patterns
            adjusted_gap = dash_gap + remaining_length / max(1, num_dashes - 1) if num_dashes > 1 else dash_gap
        
        # Вычисляем углы с учетом равномерного распределения
        dash_angle_deg = (dash_length / arc_length) * angle_span_deg
        gap_angle_deg = (adjusted_gap / arc_length) * angle_span_deg
        
        painter.setPen(pen)
        current_angle_deg = arc.start_angle
        
        rect = QRectF(
            -arc.radius_x,
            -arc.radius_y,
            arc.radius_x * 2,
            arc.radius_y * 2
        )
        
        # Определяем направление дуги по знаку span_angle_deg
        direction = 1 if span_angle_deg >= 0 else -1
        end_angle_deg = arc.end_angle
        
        if direction < 0:
            dash_angle_deg = -dash_angle_deg
            gap_angle_deg = -gap_angle_deg
        
        for i in range(num_dashes):
            start_angle_deg = current_angle_deg
            end_angle_deg_calc = start_angle_deg + dash_angle_deg
            
            # Ограничиваем конечный угол, чтобы не выйти за пределы дуги
            if direction > 0:
                if end_angle_deg_calc > end_angle_deg:
                    end_angle_deg_calc = end_angle_deg
            else:
                if end_angle_deg_calc < end_angle_deg:
                    end_angle_deg_calc = end_angle_deg
            
            # Рисуем дугу (в локальной системе координат)
            path = QPainterPath()
            span_angle = end_angle_deg_calc - start_angle_deg
            # Если span отрицательный и больше -180, это нормально для дуги по часовой стрелке
            # Qt arcTo поддерживает отрицательные значения
            path.arcMoveTo(rect, start_angle_deg)
            path.arcTo(rect, start_angle_deg, span_angle)
            painter.drawPath(path)
            
            current_angle_deg = end_angle_deg_calc + gap_angle_deg
            
            # Если дошли до конца дуги, выходим
            if direction > 0:
                if current_angle_deg >= end_angle_deg:
                    break
            else:
                if current_angle_deg <= end_angle_deg:
                    break
        
        painter.restore()
    
    @staticmethod
    def _draw_dash_dot_arc(painter: QPainter, arc, pen: QPen, style):
        """Отрисовывает штрихпунктирную дугу эллипса с учетом поворота"""
        import math
        from PySide6.QtGui import QTransform, QPainterPath
        
        # Сохраняем состояние painter
        painter.save()
        
        # Применяем трансформацию поворота
        transform = QTransform()
        transform.translate(arc.center.x(), arc.center.y())
        transform.rotate(math.degrees(arc.rotation_angle))
        painter.setTransform(transform, True)
        
        dash_length = style.dash_length
        dash_gap = style.dash_gap
        dot_length = style.thickness_mm * 0.5
        # Вычисляем span_angle с учетом направления
        span_angle_deg = arc.end_angle - arc.start_angle
        if span_angle_deg < -180:
            span_angle_deg += 360
        elif span_angle_deg > 180:
            span_angle_deg -= 360
        
        angle_span = abs(span_angle_deg)
        # Приблизительная длина дуги эллипса
        avg_radius = (arc.radius_x + arc.radius_y) / 2
        arc_length = math.radians(angle_span) * avg_radius
        
        if arc_length < 0.1:
            painter.restore()
            return
        
        if style.line_type == LineType.DASH_DOT_TWO_DOTS:
            pattern = [dash_length, dash_gap, dot_length, dash_gap, dot_length, dash_gap]
        else:
            pattern = [dash_length, dash_gap, dot_length, dash_gap]
        
        painter.setPen(pen)
        current_angle = arc.start_angle
        pattern_index = 0
        max_iterations = 1000  # Защита от бесконечного цикла
        
        rect = QRectF(
            -arc.radius_x,
            -arc.radius_y,
            arc.radius_x * 2,
            arc.radius_y * 2
        )
        
        # Определяем направление дуги
        direction = 1 if span_angle_deg >= 0 else -1
        
        iteration = 0
        while iteration < max_iterations:
            if direction > 0:
                if current_angle >= arc.end_angle:
                    break
            else:
                if current_angle <= arc.end_angle:
                    break
            
            segment_length = pattern[pattern_index % len(pattern)]
            segment_angle_abs = (segment_length / arc_length) * angle_span if arc_length > 0 else 0
            segment_angle = segment_angle_abs if direction > 0 else -segment_angle_abs
            
            is_gap = (segment_length == dash_gap)
            
            if not is_gap:
                start_angle = current_angle
                # Ограничиваем конечный угол
                end_angle = current_angle + segment_angle
                if direction > 0:
                    end_angle = min(end_angle, arc.end_angle)
                else:
                    end_angle = max(end_angle, arc.end_angle)
                
                # Рисуем дугу в локальной системе координат
                path = QPainterPath()
                span_angle = end_angle - start_angle
                # Qt arcTo поддерживает отрицательные значения для направления по часовой стрелке
                path.arcMoveTo(rect, start_angle)
                path.arcTo(rect, start_angle, span_angle)
                painter.drawPath(path)
            
            current_angle += segment_angle
            pattern_index += 1
            iteration += 1
        
        painter.restore()
    
    # Методы специальной отрисовки для многоугольников
    @staticmethod
    def _draw_wavy_polygon(painter: QPainter, polygon, pen: QPen):
        """Отрисовывает волнистый многоугольник"""
        vertices = polygon.get_vertices()
        if len(vertices) < 3:
            return
        
        # Рисуем каждую сторону как волнистую линию
        for i in range(len(vertices)):
            start = vertices[i]
            end = vertices[(i + 1) % len(vertices)]
            LineRenderer._draw_wavy_line(painter, start, end, pen)
    
    @staticmethod
    def _draw_broken_polygon(painter: QPainter, polygon, pen: QPen):
        """Отрисовывает многоугольник с изломами"""
        vertices = polygon.get_vertices()
        if len(vertices) < 3:
            return
        
        # Рисуем каждую сторону как линию с изломами
        for i in range(len(vertices)):
            start = vertices[i]
            end = vertices[(i + 1) % len(vertices)]
            LineRenderer._draw_broken_line(painter, start, end, pen)
    
    @staticmethod
    def _draw_dashed_polygon(painter: QPainter, polygon, pen: QPen, style):
        """Отрисовывает штриховой многоугольник"""
        vertices = polygon.get_vertices()
        if len(vertices) < 3:
            return
        
        # Рисуем каждую сторону как штриховую линию
        for i in range(len(vertices)):
            start = vertices[i]
            end = vertices[(i + 1) % len(vertices)]
            LineRenderer._draw_dashed_line(painter, start, end, pen, style)
    
    @staticmethod
    def _draw_dash_dot_polygon(painter: QPainter, polygon, pen: QPen, style):
        """Отрисовывает штрихпунктирный многоугольник"""
        vertices = polygon.get_vertices()
        if len(vertices) < 3:
            return
        
        # Рисуем каждую сторону как штрихпунктирную линию
        for i in range(len(vertices)):
            start = vertices[i]
            end = vertices[(i + 1) % len(vertices)]
            LineRenderer._draw_dash_dot_line(painter, start, end, pen, style)
    

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
            is_selected = self.selection_manager.is_selected(obj)
            if isinstance(obj, LineSegment):
                LineRenderer.draw_line(painter, obj, scale_factor, is_selected)
            elif hasattr(obj, 'draw'):
                # Используем метод draw объекта, если он есть
                obj.draw(painter, scale_factor)
        
        # Текущий рисуемый объект
        current_obj = self.scene.get_current_object()
        if current_obj:
            from widgets.primitives import Arc
            if isinstance(current_obj, Arc) and current_obj.radius == 0:
                # Второй этап создания дуги - показываем линию от начала до конца
                # Получаем точки из scene
                end_point = None
                if hasattr(self.scene, '_arc_end_point') and self.scene._arc_end_point:
                    end_point = self.scene._arc_end_point
                elif hasattr(self.scene, '_temp_arc_end_point') and self.scene._temp_arc_end_point:
                    end_point = self.scene._temp_arc_end_point
                
                if hasattr(self.scene, '_arc_start_point') and self.scene._arc_start_point and end_point:
                    # Рисуем временную линию
                    preview_pen = QPen(QColor(150, 150, 150), 1, Qt.DashLine)
                    painter.setPen(preview_pen)
                    painter.setBrush(Qt.NoBrush)
                    painter.drawLine(self.scene._arc_start_point, end_point)
            elif isinstance(current_obj, LineSegment):
                LineRenderer.draw_line(painter, current_obj, scale_factor, False)
            elif hasattr(current_obj, 'draw'):
                current_obj.draw(painter, scale_factor)
        
        # Подсветка выделенных объектов
        for obj in self.selection_manager.get_selected_objects():
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
    
    def _draw_selection_highlight(self, painter: QPainter, obj):
        """Рисует подсветку выделенного объекта"""
        highlight_pen = QPen(QColor(0, 100, 255), 1, Qt.DashLine)
        painter.setPen(highlight_pen)
        painter.setBrush(Qt.NoBrush)
        
        margin = 3.0 / self.viewport.get_scale()
        bbox = obj.get_bounding_box()
        
        # Расширяем bounding box на margin
        expanded_rect = QRectF(
            bbox.x() - margin,
            bbox.y() - margin,
            bbox.width() + 2 * margin,
            bbox.height() + 2 * margin
        )
        
        painter.drawRect(expanded_rect)
    
    def set_grid_step(self, step_mm: float):
        """Устанавливает шаг сетки в миллиметрах"""
        self.grid_step = step_mm

