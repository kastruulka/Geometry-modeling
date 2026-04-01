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


# Паттерн для импортированных штриховых/штрих-пунктирных: база для 0.25 мм, масштаб по толщине линии из DXF.
_LEGACY_BASE_WIDTH = 0.94   # 0.25 мм в единицах (96/25.4)
_LEGACY_DASH_LEN = 5.0
_LEGACY_DASH_GAP = 2.5


def _legacy_pattern_style(line_width: float, line_type_enum):
    """Паттерн масштабируется по толщине линии из DXF — зазоры не съедаются, толщина сохраняется."""
    k = max(1.0, line_width / _LEGACY_BASE_WIDTH)
    return type('_LegacyStyle', (), {
        'dash_length': _LEGACY_DASH_LEN * k,
        'dash_gap': _LEGACY_DASH_GAP * k,
        'thickness_mm': 0.8 * k,
        'line_type': line_type_enum,
})()


def _broken_style_params(style=None):
    """Возвращает параметры изломов в пикселях и исходный счетчик из стиля."""
    zigzag_count = style.zigzag_count if style and hasattr(style, 'zigzag_count') else 1
    zigzag_count = max(1, int(zigzag_count))
    zigzag_step_mm = style.zigzag_step_mm if style and hasattr(style, 'zigzag_step_mm') else 4.0

    zigzag_height_mm = 3.5
    zigzag_width_mm = 4.0
    dpi = 96

    return {
        'zigzag_count': zigzag_count,
        'zigzag_height': (zigzag_height_mm * dpi) / 25.4,
        'zigzag_length_single': (zigzag_width_mm * dpi) / 25.4,
        'zigzag_step': (zigzag_step_mm * dpi) / 25.4,
    }


def _fit_broken_pattern(available_length: float, zigzag_count: int,
                        zigzag_length_single: float, zigzag_step: float,
                        limit_ratio: float = 0.9):
    """Поджимает шаг между изломами, если паттерн не помещается."""
    total_zigzag_length = zigzag_length_single * zigzag_count + zigzag_step * (zigzag_count - 1)

    if total_zigzag_length > available_length * limit_ratio:
        max_length = available_length * limit_ratio
        if zigzag_count > 1:
            zigzag_step = (max_length - zigzag_length_single * zigzag_count) / (zigzag_count - 1)
            zigzag_step = max(zigzag_step, zigzag_length_single * 0.5)
        total_zigzag_length = zigzag_length_single * zigzag_count + zigzag_step * (zigzag_count - 1)

    return zigzag_step, total_zigzag_length


def _normalized_arc_span(start_angle: float, end_angle: float) -> float:
    """Нормализует разницу углов дуги к короткому направленному интервалу."""
    span_angle_deg = end_angle - start_angle
    if span_angle_deg < -180:
        span_angle_deg += 360
    elif span_angle_deg > 180:
        span_angle_deg -= 360
    return span_angle_deg


def _ellipse_circumference(radius_x: float, radius_y: float) -> float:
    """Приближенная длина окружности эллипса по формуле Рамануджана."""
    if (radius_x + radius_y) <= 0 or radius_x <= 0 or radius_y <= 0:
        return 0.0
    h = ((radius_x - radius_y) / (radius_x + radius_y)) ** 2
    return math.pi * (radius_x + radius_y) * (1 + (3 * h) / (10 + math.sqrt(4 - 3 * h)))


def _arc_length(radius_x: float, radius_y: float, span_angle_deg: float) -> float:
    """Приближенная длина дуги эллипса через средний радиус."""
    angle_span_rad = math.radians(abs(span_angle_deg))
    avg_radius = (radius_x + radius_y) / 2
    return angle_span_rad * avg_radius


def _wavy_amplitude_px(pen: QPen, style=None) -> float:
    """Возвращает амплитуду волнистой линии в пикселях."""
    if style and hasattr(style, 'wavy_amplitude_mm'):
        amplitude_mm = style.wavy_amplitude_mm
    else:
        main_thickness_mm = 0.8
        line_thickness_mm = pen.widthF() * 25.4 / 96
        amplitude_mm = (main_thickness_mm / 2.5) * (line_thickness_mm / 0.4)
    return (amplitude_mm * 96) / 25.4


def _apply_rotation_transform(painter: QPainter, center: QPointF, rotation_angle: float):
    """Применяет поворот вокруг центра и возвращает локальные координаты центра."""
    if abs(rotation_angle) > 1e-6:
        transform = QTransform()
        transform.translate(center.x(), center.y())
        transform.rotate(math.degrees(rotation_angle))
        painter.setTransform(transform, True)
        return 0.0, 0.0
    return center.x(), center.y()


def _distributed_dash_pattern(total_length: float, dash_length: float, dash_gap: float):
    """Возвращает число штрихов и скорректированный зазор для равномерного распределения."""
    pattern_length = dash_length + dash_gap
    num_patterns = total_length / pattern_length if pattern_length > 0 else 0

    if num_patterns < 1:
        return 0, dash_gap

    num_full_patterns = int(num_patterns)
    remaining_length = total_length - num_full_patterns * pattern_length

    if remaining_length >= dash_length:
        num_dashes = num_full_patterns + 1
        total_gap_length = (num_dashes - 1) * dash_gap + remaining_length - dash_length
        adjusted_gap = total_gap_length / (num_dashes - 1) if num_dashes > 1 else dash_gap
    else:
        num_dashes = num_full_patterns
        adjusted_gap = dash_gap + remaining_length / max(1, num_dashes - 1) if num_dashes > 1 else dash_gap

    return num_dashes, adjusted_gap


def _sample_spline_with_arc_lengths(spline, min_samples: int = 200, factor: int = 40):
    """Возвращает точки сплайна и накопленные длины вдоль него."""
    num_samples = max(min_samples, len(spline.control_points) * factor)
    points = []
    arc_lengths = [0.0]
    total_length = 0.0

    prev_point = spline._get_point_on_spline(0)
    points.append(prev_point)

    for i in range(1, num_samples + 1):
        t = i / num_samples if num_samples > 0 else 0
        curr_point = spline._get_point_on_spline(t)
        points.append(curr_point)

        dx = curr_point.x() - prev_point.x()
        dy = curr_point.y() - prev_point.y()
        segment_length = math.sqrt(dx * dx + dy * dy)
        total_length += segment_length
        arc_lengths.append(total_length)
        prev_point = curr_point

    return points, arc_lengths, total_length


def _point_at_arc_length(points, arc_lengths, target_arc):
    """Находит точку на кривой для заданной длины дуги."""
    if target_arc <= 0:
        return points[0]
    if target_arc >= arc_lengths[-1]:
        return points[-1]

    for i in range(len(arc_lengths) - 1):
        if arc_lengths[i] <= target_arc <= arc_lengths[i + 1]:
            t = (
                (target_arc - arc_lengths[i]) / (arc_lengths[i + 1] - arc_lengths[i])
                if arc_lengths[i + 1] > arc_lengths[i]
                else 0
            )
            return QPointF(
                points[i].x() + t * (points[i + 1].x() - points[i].x()),
                points[i].y() + t * (points[i + 1].y() - points[i].y()),
            )

    return points[-1]


def _normal_from_points(prev_point: QPointF, next_point: QPointF):
    dx = next_point.x() - prev_point.x()
    dy = next_point.y() - prev_point.y()
    length = math.hypot(dx, dy)
    if length > 0.001:
        return -dy / length, dx / length
    return 0.0, 1.0


def _spline_normal_at_index(points, index: int):
    if not points:
        return 0.0, 1.0
    if index <= 0:
        if len(points) > 1:
            return _normal_from_points(points[0], points[1])
        return 0.0, 1.0
    if index >= len(points) - 1:
        return _normal_from_points(points[-2], points[-1])
    return _normal_from_points(points[index - 1], points[index + 1])


def _spline_normal_at_arc_length(points, arc_lengths, target_arc):
    if not points:
        return 0.0, 1.0
    idx = 0
    for i in range(len(arc_lengths)):
        if arc_lengths[i] >= target_arc:
            idx = i
            break
    return _spline_normal_at_index(points, idx)


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
                LineRenderer._draw_wavy_line(painter, line.start_point, line.end_point, pen, line.style)
            elif line_type == LineType.SOLID_THIN_BROKEN:
                LineRenderer._draw_broken_line(painter, line.start_point, line.end_point, pen, line.style)
            elif line_type == LineType.DASHED:
                LineRenderer._draw_dashed_line(painter, line.start_point, line.end_point, pen, line.style)
            elif line_type in [LineType.DASH_DOT_THICK, LineType.DASH_DOT_THIN, LineType.DASH_DOT_TWO_DOTS]:
                LineRenderer._draw_dash_dot_line(painter, line.start_point, line.end_point, pen, line.style)
            else:
                # Обычные сплошные линии
                painter.setPen(pen)
                painter.drawLine(line.start_point, line.end_point)
        else:
            # Импорт DXF: толщина и масштаб из lineweight — line.width не ужимаем
            pen = QPen(line.color, line.width)
            if is_selected:
                pen.setWidthF(pen.widthF() * 1.5)
            painter.setBrush(Qt.NoBrush)
            legacy_lt = getattr(line, '_legacy_linetype', 'Continuous') or 'Continuous'
            legacy_lt = str(legacy_lt).strip().upper()
            if legacy_lt == 'DASHED':
                pen.setCapStyle(Qt.FlatCap)
                style = _legacy_pattern_style(pen.widthF(), LineType.DASH_DOT_THIN)
                LineRenderer._draw_dashed_line(painter, line.start_point, line.end_point, pen, style)
            elif legacy_lt in ('DASHDOT', 'DASHDOT2'):
                pen.setCapStyle(Qt.FlatCap)
                lt_enum = LineType.DASH_DOT_TWO_DOTS if legacy_lt == 'DASHDOT2' else LineType.DASH_DOT_THIN
                style = _legacy_pattern_style(pen.widthF(), lt_enum)
                LineRenderer._draw_dash_dot_line(painter, line.start_point, line.end_point, pen, style)
            else:
                pen.setCapStyle(Qt.FlatCap)
                painter.setPen(pen)
                painter.drawLine(line.start_point, line.end_point)
        
        # Кружки на концах отрезка не рисуем (ни при создании, ни после)
        
        # Восстанавливаем brush
        painter.setBrush(old_brush)
    
    @staticmethod
    def _draw_wavy_line(painter: QPainter, start_point: QPointF, end_point: QPointF, pen: QPen, style=None):
        """Отрисовывает волнистую линию (плавная синусоида)"""
        dx = end_point.x() - start_point.x()
        dy = end_point.y() - start_point.y()
        length = math.sqrt(dx*dx + dy*dy)
        angle = math.atan2(dy, dx)
        
        if length < 1:
            return
        
        # Амплитуда волны - используем из стиля, если доступна
        if style and hasattr(style, 'wavy_amplitude_mm'):
            amplitude_mm = style.wavy_amplitude_mm
        else:
            # Автоматический расчет по ГОСТ
            main_thickness_mm = 0.8
            line_thickness_mm = pen.widthF() * 25.4 / 96
            amplitude_mm = (main_thickness_mm / 2.5) * (line_thickness_mm / 0.4)
        
        # Конвертируем миллиметры в пиксели с учетом масштаба
        scale_factor = 1.0  # Масштаб уже учтен в pen
        dpi = 96
        amplitude_px = (amplitude_mm * dpi) / 25.4
        
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
    def _draw_wavy_line_segment(painter: QPainter, start_point: QPointF, end_point: QPointF, 
                                pen: QPen, start_arc_pos: float, actual_wave_length: float, amplitude_px: float):
        """Отрисовывает волнистую линию с учетом накопленной длины дуги для непрерывной волны"""
        dx = end_point.x() - start_point.x()
        dy = end_point.y() - start_point.y()
        length = math.sqrt(dx*dx + dy*dy)
        angle = math.atan2(dy, dx)
        
        if length < 1:
            return
        
        path = QPainterPath()
        cos_angle = math.cos(angle)
        sin_angle = math.sin(angle)
        perp_cos = -sin_angle
        perp_sin = cos_angle
        
        num_points = max(50, int(length / 2))
        
        for i in range(num_points + 1):
            t = i / num_points
            along_line = t * length
            # Используем накопленную длину дуги для непрерывной волны
            total_arc_pos = start_arc_pos + along_line
            wave_phase = (total_arc_pos / actual_wave_length) * 2 * math.pi
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
    def _draw_broken_line(painter: QPainter, start_point: QPointF, end_point: QPointF, pen: QPen, style=None):
        """Отрисовывает сплошную линию с изломами (острые углы, зигзаг)"""
        dx = end_point.x() - start_point.x()
        dy = end_point.y() - start_point.y()
        length = math.sqrt(dx*dx + dy*dy)
        angle = math.atan2(dy, dx)
        
        if length < 1:
            return
        broken_params = _broken_style_params(style)
        zigzag_count = broken_params['zigzag_count']
        zigzag_height = broken_params['zigzag_height']
        zigzag_length_single = broken_params['zigzag_length_single']
        zigzag_step, total_zigzag_length = _fit_broken_pattern(
            length,
            zigzag_count,
            zigzag_length_single,
            broken_params['zigzag_step'],
        )
        
        straight_length = (length - total_zigzag_length) / 2
        
        cos_angle = math.cos(angle)
        sin_angle = math.sin(angle)
        perp_cos = -sin_angle
        perp_sin = cos_angle
        
        path = QPainterPath()
        path.moveTo(start_point)
        
        # Первый прямой участок
        zigzag_start = QPointF(
            start_point.x() + straight_length * cos_angle,
            start_point.y() + straight_length * sin_angle
        )
        path.lineTo(zigzag_start)
        
        # Рисуем все зигзаги с шагом между ними
        current_pos = zigzag_start
        for z in range(zigzag_count):
            segment_length_along = zigzag_length_single / 3
            
            # Первый сегмент: вверх на половину высоты
            point1 = QPointF(
                current_pos.x() + segment_length_along * cos_angle + (zigzag_height / 2) * perp_cos,
                current_pos.y() + segment_length_along * sin_angle + (zigzag_height / 2) * perp_sin
            )
            path.lineTo(point1)
            
            # Второй сегмент: вниз на всю высоту
            point2 = QPointF(
                point1.x() + segment_length_along * cos_angle - zigzag_height * perp_cos,
                point1.y() + segment_length_along * sin_angle - zigzag_height * perp_sin
            )
            path.lineTo(point2)
            
            # Третий сегмент: вверх на половину высоты (возврат к прямой линии)
            zigzag_end = QPointF(
                current_pos.x() + zigzag_length_single * cos_angle,
                current_pos.y() + zigzag_length_single * sin_angle
            )
            path.lineTo(zigzag_end)
            
            # Если это не последний зигзаг, добавляем шаг (прямой участок) до следующего зигзага
            if z < zigzag_count - 1:
                current_pos = QPointF(
                    zigzag_end.x() + zigzag_step * cos_angle,
                    zigzag_end.y() + zigzag_step * sin_angle
                )
                path.lineTo(current_pos)
            else:
                current_pos = zigzag_end
        
        # Второй прямой участок до конца
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
        from PySide6.QtGui import QPainterPath
        from PySide6.QtCore import Qt
        
        # Сохраняем текущее состояние painter
        painter.save()
        
        # Применяем трансформацию: переносим центр в начало координат, поворачиваем, возвращаем
        _apply_rotation_transform(painter, arc.center, arc.rotation_angle)
        
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
                PrimitiveRenderer._draw_wavy_circle(painter, circle, pen, circle.style)
            elif line_type == LineType.SOLID_THIN_BROKEN:
                PrimitiveRenderer._draw_broken_circle(painter, circle, pen, circle.style)
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
            legacy_lt = getattr(circle, '_legacy_linetype', 'Continuous') or 'Continuous'
            legacy_lt = str(legacy_lt).strip().upper()
            if legacy_lt == 'DASHED':
                pen.setCapStyle(Qt.FlatCap)
                style = _legacy_pattern_style(pen.widthF(), LineType.DASHED)
                PrimitiveRenderer._draw_dashed_circle(painter, circle, pen, style)
            elif legacy_lt in ('DASHDOT', 'DASHDOT2'):
                pen.setCapStyle(Qt.FlatCap)
                lt_enum = LineType.DASH_DOT_TWO_DOTS if legacy_lt == 'DASHDOT2' else LineType.DASH_DOT_THIN
                style = _legacy_pattern_style(pen.widthF(), lt_enum)
                PrimitiveRenderer._draw_dash_dot_circle(painter, circle, pen, style)
            else:
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
                PrimitiveRenderer._draw_wavy_arc(painter, arc, pen, arc.style)
            elif line_type == LineType.SOLID_THIN_BROKEN:
                PrimitiveRenderer._draw_broken_arc(painter, arc, pen, arc.style)
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
            legacy_lt = getattr(arc, '_legacy_linetype', 'Continuous') or 'Continuous'
            legacy_lt = str(legacy_lt).strip().upper()
            if legacy_lt == 'DASHED':
                pen.setCapStyle(Qt.FlatCap)
                style = _legacy_pattern_style(pen.widthF(), LineType.DASHED)
                PrimitiveRenderer._draw_dashed_arc(painter, arc, pen, style)
            elif legacy_lt in ('DASHDOT', 'DASHDOT2'):
                pen.setCapStyle(Qt.FlatCap)
                lt_enum = LineType.DASH_DOT_TWO_DOTS if legacy_lt == 'DASHDOT2' else LineType.DASH_DOT_THIN
                style = _legacy_pattern_style(pen.widthF(), lt_enum)
                PrimitiveRenderer._draw_dash_dot_arc(painter, arc, pen, style)
            else:
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
            # Эти методы сами обрабатывают скругленные углы
            if line_type == LineType.SOLID_WAVY:
                PrimitiveRenderer._draw_wavy_rectangle(painter, rectangle, pen, rectangle.style)
            elif line_type == LineType.SOLID_THIN_BROKEN:
                PrimitiveRenderer._draw_broken_rectangle(painter, rectangle, pen, rectangle.style)
            elif line_type == LineType.DASHED:
                PrimitiveRenderer._draw_dashed_rectangle(painter, rectangle, pen, rectangle.style)
            elif line_type in [LineType.DASH_DOT_THICK, LineType.DASH_DOT_THIN, LineType.DASH_DOT_TWO_DOTS]:
                PrimitiveRenderer._draw_dash_dot_rectangle(painter, rectangle, pen, rectangle.style)
            else:
                # Обычные сплошные линии
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                rect = rectangle.get_bounding_box()
                # Проверяем скругление углов для обычных сплошных линий
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
                PrimitiveRenderer._draw_wavy_ellipse(painter, ellipse, pen, ellipse.style)
            elif line_type == LineType.SOLID_THIN_BROKEN:
                PrimitiveRenderer._draw_broken_ellipse(painter, ellipse, pen, ellipse.style)
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
            legacy_lt = getattr(ellipse, '_legacy_linetype', 'Continuous') or 'Continuous'
            legacy_lt = str(legacy_lt).strip().upper()
            if legacy_lt == 'DASHED':
                pen.setCapStyle(Qt.FlatCap)
                style = _legacy_pattern_style(pen.widthF(), LineType.DASHED)
                PrimitiveRenderer._draw_dashed_ellipse(painter, ellipse, pen, style)
            elif legacy_lt in ('DASHDOT', 'DASHDOT2'):
                pen.setCapStyle(Qt.FlatCap)
                lt_enum = LineType.DASH_DOT_TWO_DOTS if legacy_lt == 'DASHDOT2' else LineType.DASH_DOT_THIN
                style = _legacy_pattern_style(pen.widthF(), lt_enum)
                PrimitiveRenderer._draw_dash_dot_ellipse(painter, ellipse, pen, style)
            else:
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
                PrimitiveRenderer._draw_wavy_polygon(painter, polygon, pen, polygon.style)
            elif line_type == LineType.SOLID_THIN_BROKEN:
                PrimitiveRenderer._draw_broken_polygon(painter, polygon, pen, polygon.style)
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
    def _draw_wavy_circle(painter: QPainter, circle, pen: QPen, style=None):
        """Отрисовывает волнистую окружность (как отрезок, скрученный в круг)"""
        import math
        from PySide6.QtGui import QPainterPath
        
        circumference = 2 * math.pi * circle.radius
        if circumference < 1:
            return
        
        # Амплитуда волны - используем из стиля, если доступна
        if style and hasattr(style, 'wavy_amplitude_mm'):
            amplitude_mm = style.wavy_amplitude_mm
        else:
            # Автоматический расчет по ГОСТ
            main_thickness_mm = 0.8
            line_thickness_mm = pen.widthF() * 25.4 / 96
            amplitude_mm = (main_thickness_mm / 2.5) * (line_thickness_mm / 0.4)
        
        dpi = 96
        amplitude_px = (amplitude_mm * dpi) / 25.4
        
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
    def _draw_broken_circle(painter: QPainter, circle, pen: QPen, style=None):
        """Отрисовывает окружность с зигзагами"""
        import math
        from PySide6.QtGui import QPainterPath
        
        circumference = 2 * math.pi * circle.radius
        if circumference < 1:
            return
        
        broken_params = _broken_style_params(style)
        zigzag_count = broken_params['zigzag_count']
        zigzag_height = broken_params['zigzag_height']
        zigzag_length_single = broken_params['zigzag_length_single']
        zigzag_step, total_zigzag_length = _fit_broken_pattern(
            circumference,
            zigzag_count,
            zigzag_length_single,
            broken_params['zigzag_step'],
        )

        # ???????????????????????? ?? ????????
        total_zigzag_angle = (total_zigzag_length / circumference) * 2 * math.pi
        if total_zigzag_angle > math.pi * 0.9:
            total_zigzag_angle = math.pi * 0.9
            zigzag_step, total_zigzag_length = _fit_broken_pattern(
                circumference,
                zigzag_count,
                zigzag_length_single,
                zigzag_step,
            )
            total_zigzag_angle = (total_zigzag_length / circumference) * 2 * math.pi
        
        zigzag_length_single_angle = (zigzag_length_single / circumference) * 2 * math.pi
        zigzag_step_angle = (zigzag_step / circumference) * 2 * math.pi
        
        # Угол начала зигзагов (равномерно распределяем по окружности)
        start_zigzag_angle = math.pi - total_zigzag_angle / 2
        
        path = QPainterPath()
        
        # Рисуем первую часть окружности (до зигзагов)
        num_points_start = max(20, int(start_zigzag_angle / (2 * math.pi) * 100))
        for i in range(num_points_start + 1):
            angle = 2 * math.pi * i / num_points_start * (start_zigzag_angle / (2 * math.pi))
            x = circle.center.x() + circle.radius * math.cos(angle)
            y = circle.center.y() + circle.radius * math.sin(angle)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        
        # Рисуем все зигзаги с шагом между ними
        current_angle = start_zigzag_angle
        for z in range(zigzag_count):
            # Начало зигзага
            zigzag_start_angle = current_angle
            zigzag_mid1_angle = current_angle + zigzag_length_single_angle / 3
            zigzag_mid2_angle = current_angle + 2 * zigzag_length_single_angle / 3
            zigzag_end_angle = current_angle + zigzag_length_single_angle
            
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
            
            # Если это не последний зигзаг, добавляем шаг (прямой участок окружности)
            if z < zigzag_count - 1:
                current_angle = zigzag_end_angle + zigzag_step_angle
                # Рисуем прямой участок окружности между зигзагами
                num_points_step = max(5, int(zigzag_step_angle / (2 * math.pi) * 20))
                for i in range(1, num_points_step + 1):
                    angle = zigzag_end_angle + (zigzag_step_angle * i / num_points_step)
                    x = circle.center.x() + circle.radius * math.cos(angle)
                    y = circle.center.y() + circle.radius * math.sin(angle)
                    path.lineTo(x, y)
            else:
                current_angle = zigzag_end_angle
        
        # Рисуем оставшуюся часть окружности
        end_zigzag_angle = current_angle
        remaining_angle = 2 * math.pi - end_zigzag_angle
        if remaining_angle > 0:
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
            rect = PrimitiveRenderer._circle_rect(circle)
            painter.setPen(pen)
            painter.drawArc(rect, 0, int(360 * 16))
            return
        
        # ???????????????????? ???????????????????????? ???????????? ?? ?????????????? ???? ???????? ????????????????????
        # ??????????????????, ?????? ???????????????????? ????????????????
        num_dashes, adjusted_gap = _distributed_dash_pattern(circumference, dash_length, dash_gap)
        
        
        painter.setPen(pen)
        PrimitiveRenderer._draw_patterned_ellipse_segments(
            painter,
            PrimitiveRenderer._circle_rect(circle),
            [dash_length, adjusted_gap],
            adjusted_gap,
            circumference,
        )
    
    @staticmethod
    def _draw_dash_dot_circle(painter: QPainter, circle, pen: QPen, style):
        """Отрисовывает штрихпунктирную окружность"""
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
        PrimitiveRenderer._draw_patterned_ellipse_segments(
            painter,
            PrimitiveRenderer._circle_rect(circle),
            pattern,
            dash_gap,
            circumference,
        )
    
    # Методы специальной отрисовки для прямоугольников
    @staticmethod
    def _draw_wavy_rectangle(painter: QPainter, rectangle, pen: QPen, style=None):
        """Отрисовывает волнистый прямоугольник с непрерывной волной (как у сплайна)"""
        from PySide6.QtGui import QPainterPath
        
        # Амплитуда волны - используем из стиля, если доступна
        if style and hasattr(style, 'wavy_amplitude_mm'):
            amplitude_mm = style.wavy_amplitude_mm
        else:
            # Автоматический расчет по ГОСТ
            main_thickness_mm = 0.8
            line_thickness_mm = pen.widthF() * 25.4 / 96
            amplitude_mm = (main_thickness_mm / 2.5) * (line_thickness_mm / 0.4)
        
        dpi = 96
        amplitude_px = (amplitude_mm * dpi) / 25.4
        
        points, arc_lengths, total_length = PrimitiveRenderer._rectangle_contour_points(rectangle)
        
        # Контур всегда замкнут, так как мы явно генерируем точки по сегментам
        is_closed = True
        
        if total_length < 1:
            return
        
        # Параметры волны для всего периметра
        wave_length_px = amplitude_px * 5
        num_waves = max(1, int(total_length / wave_length_px))
        actual_wave_length = total_length / num_waves if num_waves > 0 else total_length
        
        # Строим волнистый путь вдоль периметра (как у сплайна)
        path = QPainterPath()
        
        for i in range(len(points)):
            # Вычисляем направление перпендикуляра к контуру
            if i == 0:
                # Для первой точки используем направление к следующей
                if len(points) > 1:
                    dx1 = points[1].x() - points[0].x()
                    dy1 = points[1].y() - points[0].y()
                    len1 = math.sqrt(dx1*dx1 + dy1*dy1)
                    if len1 > 0.001:
                        cos_angle = dx1 / len1
                        sin_angle = dy1 / len1
                        perp_cos = -sin_angle
                        perp_sin = cos_angle
                    else:
                        perp_cos = 0
                        perp_sin = 1
                else:
                    perp_cos = 0
                    perp_sin = 1
            elif i < len(points) - 1:
                # Используем направление между соседними точками
                dx1 = points[i].x() - points[i-1].x()
                dy1 = points[i].y() - points[i-1].y()
                len1 = math.sqrt(dx1*dx1 + dy1*dy1)
                if len1 > 0.001:
                    cos_angle = dx1 / len1
                    sin_angle = dy1 / len1
                    perp_cos = -sin_angle
                    perp_sin = cos_angle
                else:
                    perp_cos = 0
                    perp_sin = 1
            else:
                # Для последней точки используем направление от предыдущей
                dx1 = points[i].x() - points[i-1].x()
                dy1 = points[i].y() - points[i-1].y()
                len1 = math.sqrt(dx1*dx1 + dy1*dy1)
                if len1 > 0.001:
                    cos_angle = dx1 / len1
                    sin_angle = dy1 / len1
                    perp_cos = -sin_angle
                    perp_sin = cos_angle
                else:
                    perp_cos = 0
                    perp_sin = 1
            
            # Вычисляем фазу волны на основе длины дуги
            arc_pos = arc_lengths[i]
            wave_phase = (arc_pos / actual_wave_length) * 2 * math.pi
            wave_offset = amplitude_px * math.sin(wave_phase)
            
            # Применяем смещение перпендикулярно к контуру
            wavy_point = QPointF(
                points[i].x() + wave_offset * perp_cos,
                points[i].y() + wave_offset * perp_sin
            )
            
            if i == 0:
                first_wavy_point = wavy_point
                path.moveTo(wavy_point)
            else:
                path.lineTo(wavy_point)
        
        # Замыкаем контур, если он не замкнут
        if not is_closed:
            path.lineTo(first_wavy_point)
        
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
    
    @staticmethod
    def _append_measured_point(points, arc_lengths, point, accumulated_length):
        points.append(point)
        if len(points) == 1:
            arc_lengths.append(0.0)
            return 0.0

        dx = point.x() - points[-2].x()
        dy = point.y() - points[-2].y()
        accumulated_length += math.hypot(dx, dy)
        arc_lengths.append(accumulated_length)
        return accumulated_length

    @staticmethod
    def _sample_line_segment(start: QPointF, end: QPointF, points_per_unit: float, include_start: bool):
        length = math.hypot(end.x() - start.x(), end.y() - start.y())
        num_steps = max(10, int(length * points_per_unit))
        start_index = 0 if include_start else 1
        samples = []
        for i in range(start_index, num_steps + 1):
            t = i / num_steps if num_steps > 0 else 0.0
            samples.append(
                QPointF(
                    start.x() + (end.x() - start.x()) * t,
                    start.y() + (end.y() - start.y()) * t,
                )
            )
        return samples

    @staticmethod
    def _sample_arc_segment(start: QPointF, end: QPointF, center: QPointF, radius: float, points_per_unit: float):
        if radius <= 0:
            return [QPointF(end)]

        arc_length = radius * math.pi / 2
        num_steps = max(20, int(arc_length * points_per_unit))
        start_angle = math.atan2(start.y() - center.y(), start.x() - center.x())
        end_angle = math.atan2(end.y() - center.y(), end.x() - center.x())
        if end_angle <= start_angle:
            end_angle += 2 * math.pi

        samples = []
        for i in range(1, num_steps + 1):
            t = i / num_steps
            angle = start_angle + t * (end_angle - start_angle)
            samples.append(
                QPointF(
                    center.x() + radius * math.cos(angle),
                    center.y() + radius * math.sin(angle),
                )
            )
        return samples

    @staticmethod
    def _rectangle_contour_points(rectangle, points_per_unit: float = 8.0):
        points = []
        arc_lengths = []
        accumulated_length = 0.0
        line_segments, arc_segments = PrimitiveRenderer._rectangle_contour_segments(rectangle)

        for index, (start, end) in enumerate(line_segments):
            for point in PrimitiveRenderer._sample_line_segment(
                start,
                end,
                points_per_unit,
                include_start=(index == 0),
            ):
                accumulated_length = PrimitiveRenderer._append_measured_point(
                    points, arc_lengths, point, accumulated_length
                )
            if index < len(arc_segments):
                arc_start, arc_end, center, radius = arc_segments[index]
                for point in PrimitiveRenderer._sample_arc_segment(
                    arc_start,
                    arc_end,
                    center,
                    radius,
                    points_per_unit,
                ):
                    accumulated_length = PrimitiveRenderer._append_measured_point(
                        points, arc_lengths, point, accumulated_length
                    )

        return points, arc_lengths, accumulated_length

    @staticmethod
    def _rectangle_contour_segments(rectangle):
        fillet_radius = getattr(rectangle, 'fillet_radius', 0.0)
        rect = rectangle.get_bounding_box()
        w = rect.width()
        h = rect.height()
        r = min(fillet_radius, w / 2, h / 2) if fillet_radius > 0 else 0.0

        if r > 0:
            line_segments = [
                (QPointF(rect.x() + r, rect.y()), QPointF(rect.x() + w - r, rect.y())),
                (QPointF(rect.x() + w, rect.y() + r), QPointF(rect.x() + w, rect.y() + h - r)),
                (QPointF(rect.x() + w - r, rect.y() + h), QPointF(rect.x() + r, rect.y() + h)),
                (QPointF(rect.x(), rect.y() + h - r), QPointF(rect.x(), rect.y() + r)),
            ]
            arc_segments = [
                (
                    QPointF(rect.x() + w - r, rect.y()),
                    QPointF(rect.x() + w, rect.y() + r),
                    QPointF(rect.x() + w - r, rect.y() + r),
                    r,
                ),
                (
                    QPointF(rect.x() + w, rect.y() + h - r),
                    QPointF(rect.x() + w - r, rect.y() + h),
                    QPointF(rect.x() + w - r, rect.y() + h - r),
                    r,
                ),
                (
                    QPointF(rect.x() + r, rect.y() + h),
                    QPointF(rect.x(), rect.y() + h - r),
                    QPointF(rect.x() + r, rect.y() + h - r),
                    r,
                ),
                (
                    QPointF(rect.x(), rect.y() + r),
                    QPointF(rect.x() + r, rect.y()),
                    QPointF(rect.x() + r, rect.y() + r),
                    r,
                ),
            ]
            return line_segments, arc_segments

        corners = [
            QPointF(rect.left(), rect.top()),
            QPointF(rect.right(), rect.top()),
            QPointF(rect.right(), rect.bottom()),
            QPointF(rect.left(), rect.bottom()),
        ]
        line_segments = [
            (corners[i], corners[(i + 1) % 4])
            for i in range(4)
        ]
        return line_segments, []

    @staticmethod
    def _draw_broken_rectangle(painter: QPainter, rectangle, pen: QPen, style=None):
        """Отрисовывает прямоугольник с изломами"""
        line_segments, arc_segments = PrimitiveRenderer._rectangle_contour_segments(rectangle)
        for start, end in line_segments:
            LineRenderer._draw_broken_line(painter, start, end, pen, style)
        for start, end, center, radius in arc_segments:
            PrimitiveRenderer._draw_broken_arc_segment(painter, start, end, center, radius, pen, style)
    
    @staticmethod
    def _draw_dashed_rectangle(painter: QPainter, rectangle, pen: QPen, style):
        """Отрисовывает штриховой прямоугольник"""
        line_segments, arc_segments = PrimitiveRenderer._rectangle_contour_segments(rectangle)
        for start, end in line_segments:
            LineRenderer._draw_dashed_line(painter, start, end, pen, style)
        for start, end, center, radius in arc_segments:
            PrimitiveRenderer._draw_dashed_arc_segment(painter, start, end, center, radius, pen, style)
    
    @staticmethod
    def _draw_dash_dot_rectangle(painter: QPainter, rectangle, pen: QPen, style):
        """Отрисовывает штрихпунктирный прямоугольник"""
        line_segments, arc_segments = PrimitiveRenderer._rectangle_contour_segments(rectangle)
        for start, end in line_segments:
            LineRenderer._draw_dash_dot_line(painter, start, end, pen, style)
        for start, end, center, radius in arc_segments:
            PrimitiveRenderer._draw_dash_dot_arc_segment(painter, start, end, center, radius, pen, style)
    
    @staticmethod
    def _draw_wavy_arc_segment(painter: QPainter, start: QPointF, end: QPointF, center: QPointF, radius: float, pen: QPen):
        """Отрисовывает волнистую линию вдоль дуги скругленного угла"""
        import math
        from PySide6.QtGui import QPainterPath
        
        # Вычисляем углы относительно центра
        start_angle = math.atan2(start.y() - center.y(), start.x() - center.x())
        end_angle = math.atan2(end.y() - center.y(), end.x() - center.x())
        
        # Нормализуем углы
        if end_angle < start_angle:
            end_angle += 2 * math.pi
        
        # Длина дуги
        arc_length = radius * (end_angle - start_angle)
        
        if arc_length < 1:
            return
        
        # Амплитуда волны согласно ГОСТ (та же логика, что и для прямой линии)
        main_thickness_mm = 0.8
        line_thickness_mm = pen.widthF() * 25.4 / 96
        amplitude_mm = (main_thickness_mm / 2.5) * (line_thickness_mm / 0.4)
        amplitude_px = (amplitude_mm * 96) / 25.4
        
        # Для коротких дуг (скругленные углы) гарантируем минимум одну волну
        wave_length_px = amplitude_px * 5
        # Для дуг минимум 2 волны, чтобы волна была видна
        min_waves = max(2, int(arc_length / wave_length_px)) if arc_length >= wave_length_px else 2
        num_waves = max(min_waves, int(arc_length / wave_length_px))
        actual_wave_length = arc_length / num_waves if num_waves > 0 else arc_length
        
        # Для скругленных углов увеличиваем количество точек для более плавной кривой
        # Используем больше точек на единицу длины для коротких дуг
        # Минимум 200 точек на волну для плавности, особенно для скруглений
        points_per_wave = 200
        # Для очень коротких дуг (скругления) используем еще больше точек
        if arc_length < radius * math.pi / 2:  # Если это четверть окружности или меньше
            points_per_wave = 300
        num_points = max(points_per_wave * num_waves, int(arc_length * 8))
        path = QPainterPath()
        
        for i in range(num_points + 1):
            t = i / num_points
            angle = start_angle + t * (end_angle - start_angle)
            
            # Вычисляем расстояние вдоль дуги от начала
            along_arc = t * arc_length
            wave_phase = (along_arc / actual_wave_length) * 2 * math.pi
            wave_offset = amplitude_px * math.sin(wave_phase)
            
            # Позиция на дуге
            base_x = center.x() + radius * math.cos(angle)
            base_y = center.y() + radius * math.sin(angle)
            
            # Перпендикулярное смещение для волны (перпендикуляр к касательной дуги)
            # Правильный перпендикуляр к касательной дуги
            # Касательная направлена по (-sin(angle), cos(angle))
            # Перпендикуляр к касательной: (cos(angle), sin(angle)) или (-cos(angle), -sin(angle))
            # Выбираем направление наружу от центра (от центра к точке на дуге)
            perp_x = math.cos(angle) * wave_offset
            perp_y = math.sin(angle) * wave_offset
            
            x = base_x + perp_x
            y = base_y + perp_y
            
            if i == 0:
                path.moveTo(x, y)
            else:
                # Используем lineTo для всех точек, но с большим количеством точек
                # это создаст более плавную кривую
                path.lineTo(x, y)
        
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
    
    @staticmethod
    def _draw_wavy_arc_segment_continuous(painter: QPainter, start: QPointF, end: QPointF, center: QPointF, 
                                          radius: float, pen: QPen, start_arc_pos: float, actual_wave_length: float, amplitude_px: float):
        """Отрисовывает волнистую линию вдоль дуги с учетом накопленной длины дуги для непрерывной волны"""
        from PySide6.QtGui import QPainterPath
        
        # Вычисляем углы относительно центра
        start_angle = math.atan2(start.y() - center.y(), start.x() - center.x())
        end_angle = math.atan2(end.y() - center.y(), end.x() - center.x())
        
        # Нормализуем углы
        if end_angle < start_angle:
            end_angle += 2 * math.pi
        
        # Длина дуги
        arc_length = radius * (end_angle - start_angle)
        
        if arc_length < 1:
            return
        
        # Для скругленных углов увеличиваем количество точек для более плавной кривой
        # Используем больше точек на единицу длины для коротких дуг
        # Минимум 200 точек на волну для плавности, особенно для скруглений
        points_per_wave = 200
        # Для очень коротких дуг (скругления) используем еще больше точек
        if arc_length < radius * math.pi / 2:  # Если это четверть окружности или меньше
            points_per_wave = 300
        # Оцениваем количество волн на этой дуге для определения количества точек
        estimated_waves = arc_length / actual_wave_length if actual_wave_length > 0 else 1
        num_points = max(int(points_per_wave * estimated_waves), int(arc_length * 8))
        path = QPainterPath()
        
        for i in range(num_points + 1):
            t = i / num_points
            angle = start_angle + t * (end_angle - start_angle)
            
            # Вычисляем расстояние вдоль дуги от начала
            along_arc = t * arc_length
            # Используем накопленную длину дуги для непрерывной волны
            total_arc_pos = start_arc_pos + along_arc
            wave_phase = (total_arc_pos / actual_wave_length) * 2 * math.pi
            wave_offset = amplitude_px * math.sin(wave_phase)
            
            # Позиция на дуге
            base_x = center.x() + radius * math.cos(angle)
            base_y = center.y() + radius * math.sin(angle)
            
            # Перпендикулярное смещение для волны (перпендикуляр к касательной дуги)
            # Правильный перпендикуляр к касательной дуги
            # Касательная направлена по (-sin(angle), cos(angle))
            # Перпендикуляр к касательной: (cos(angle), sin(angle)) или (-cos(angle), -sin(angle))
            # Выбираем направление наружу от центра (от центра к точке на дуге)
            perp_x = math.cos(angle) * wave_offset
            perp_y = math.sin(angle) * wave_offset
            
            x = base_x + perp_x
            y = base_y + perp_y
            
            if i == 0:
                path.moveTo(x, y)
            else:
                # Используем lineTo для всех точек, но с большим количеством точек
                # это создаст более плавную кривую
                path.lineTo(x, y)
        
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
    
    @staticmethod
    def _add_wavy_line_segment_to_path(path: QPainterPath, start_point: QPointF, end_point: QPointF,
                                       start_arc_pos: float, actual_wave_length: float, amplitude_px: float,
                                       first_point_set: bool):
        """Добавляет волнистую линию в существующий путь для непрерывного контура"""
        dx = end_point.x() - start_point.x()
        dy = end_point.y() - start_point.y()
        length = math.sqrt(dx*dx + dy*dy)
        angle = math.atan2(dy, dx)
        
        if length < 1:
            return path, first_point_set
        
        cos_angle = math.cos(angle)
        sin_angle = math.sin(angle)
        perp_cos = -sin_angle
        perp_sin = cos_angle
        
        # Используем одинаковую плотность точек для всех сегментов (как у сплайна)
        # Минимум 8 точек на единицу длины для плавности
        num_points = max(int(length * 8), 50)
        
        # Пропускаем первую точку, если это не первый сегмент (она совпадает с последней точкой предыдущего)
        start_idx = 0 if not first_point_set else 1
        
        for i in range(start_idx, num_points + 1):
            t = i / num_points
            along_line = t * length
            # Используем накопленную длину дуги для непрерывной волны
            total_arc_pos = start_arc_pos + along_line
            wave_phase = (total_arc_pos / actual_wave_length) * 2 * math.pi
            wave_offset = amplitude_px * math.sin(wave_phase)
            
            x = start_point.x() + along_line * cos_angle + wave_offset * perp_cos
            y = start_point.y() + along_line * sin_angle + wave_offset * perp_sin
            
            if not first_point_set:
                path.moveTo(x, y)
                first_point_set = True
            else:
                path.lineTo(x, y)
        
        return path, first_point_set
    
    @staticmethod
    def _add_wavy_arc_segment_to_path(path: QPainterPath, start: QPointF, end: QPointF, center: QPointF,
                                     radius: float, start_arc_pos: float, actual_wave_length: float,
                                     amplitude_px: float, first_point_set: bool):
        """Добавляет волнистую дугу в существующий путь для непрерывного контура"""
        # Вычисляем углы относительно центра
        start_angle = math.atan2(start.y() - center.y(), start.x() - center.x())
        end_angle = math.atan2(end.y() - center.y(), end.x() - center.x())
        
        # Нормализуем углы
        if end_angle < start_angle:
            end_angle += 2 * math.pi
        
        # Длина дуги
        arc_length = radius * (end_angle - start_angle)
        
        if arc_length < 1:
            return path, first_point_set
        
        # Используем одинаковую плотность точек для всех сегментов (как у сплайна)
        # Минимум 8 точек на единицу длины для плавности, как и для прямых линий
        num_points = max(int(arc_length * 8), 50)
        
        # Пропускаем первую точку, если это не первый сегмент (она совпадает с последней точкой предыдущего)
        start_idx = 0 if not first_point_set else 1
        
        for i in range(start_idx, num_points + 1):
            t = i / num_points
            angle = start_angle + t * (end_angle - start_angle)
            
            # Вычисляем расстояние вдоль дуги от начала
            along_arc = t * arc_length
            # Используем накопленную длину дуги для непрерывной волны
            total_arc_pos = start_arc_pos + along_arc
            wave_phase = (total_arc_pos / actual_wave_length) * 2 * math.pi
            wave_offset = amplitude_px * math.sin(wave_phase)
            
            # Позиция на дуге
            base_x = center.x() + radius * math.cos(angle)
            base_y = center.y() + radius * math.sin(angle)
            
            # Перпендикулярное смещение для волны (перпендикуляр к касательной дуги)
            perp_x = math.cos(angle) * wave_offset
            perp_y = math.sin(angle) * wave_offset
            
            x = base_x + perp_x
            y = base_y + perp_y
            
            if not first_point_set:
                path.moveTo(x, y)
                first_point_set = True
            else:
                path.lineTo(x, y)
        
        return path, first_point_set
    
    @staticmethod
    def _draw_broken_arc_segment(painter: QPainter, start: QPointF, end: QPointF, center: QPointF, radius: float, pen: QPen, style=None):
        """Отрисовывает гладкую дугу для ломаного стиля (скругления без заломов)"""
        import math
        from PySide6.QtGui import QPainterPath
        
        # Вычисляем углы относительно центра
        start_angle = math.atan2(start.y() - center.y(), start.x() - center.x())
        end_angle = math.atan2(end.y() - center.y(), end.x() - center.x())
        
        if end_angle < start_angle:
            end_angle += 2 * math.pi
        
        # Длина дуги
        arc_length = radius * (end_angle - start_angle)
        
        if arc_length < 1:
            return
        
        # Для ломаного стиля скругления рисуем гладкой дугой без заломов
        # Используем QPainterPath.arcTo для плавной дуги
        path = QPainterPath()
        path.moveTo(start)
        
        # Вычисляем параметры для arcTo
        # arcTo требует прямоугольник, описывающий дугу
        # Для скругленного угла это квадрат 2r x 2r
        rect_size = 2 * radius
        
        # Определяем, какой это угол (верхний правый, нижний правый, нижний левый, верхний левый)
        # и вычисляем начальный угол и sweep angle для arcTo
        # arcTo использует углы в градусах, где 0° = 3 часа, 90° = 12 часов, и т.д.
        
        # Вычисляем начальный угол в градусах для arcTo
        # arcTo использует систему, где 0° = вправо, 90° = вверх, 180° = влево, 270° = вниз
        start_angle_deg = math.degrees(start_angle)
        sweep_angle_deg = math.degrees(end_angle - start_angle)
        
        # Нормализуем углы для arcTo (arcTo использует другую систему координат)
        # Нужно преобразовать из математической системы (0° = вправо, против часовой)
        # в систему arcTo (0° = 3 часа, по часовой)
        # В Qt arcTo: 0° = вправо, 90° = вверх (против часовой), но sweep может быть отрицательным
        
        # Используем более простой подход - рисуем дугу точками
        num_points = max(50, int(arc_length))
        for i in range(num_points + 1):
            t = i / num_points
            angle = start_angle + t * (end_angle - start_angle)
            x = center.x() + radius * math.cos(angle)
            y = center.y() + radius * math.sin(angle)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
    
    @staticmethod
    def _draw_dashed_arc_segment(painter: QPainter, start: QPointF, end: QPointF, center: QPointF, radius: float, pen: QPen, style):
        """Отрисовывает штриховую линию вдоль дуги скругленного угла"""
        import math
        from PySide6.QtGui import QPainterPath
        
        # Вычисляем углы относительно центра
        start_angle = math.atan2(start.y() - center.y(), start.x() - center.x())
        end_angle = math.atan2(end.y() - center.y(), end.x() - center.x())
        
        if end_angle < start_angle:
            end_angle += 2 * math.pi
        
        # Длина дуги
        arc_length = radius * (end_angle - start_angle)
        
        dash_length = style.dash_length
        dash_gap = style.dash_gap
        
        # Рисуем штрихи вдоль дуги
        current_angle = start_angle
        painter.setPen(pen)
        
        while current_angle < end_angle:
            # Вычисляем длину текущего сегмента дуги
            dash_angle = dash_length / radius if radius > 0 else 0
            gap_angle = dash_gap / radius if radius > 0 else 0
            
            dash_end_angle = min(current_angle + dash_angle, end_angle)
            
            # Рисуем штрих
            num_points = max(10, int((dash_end_angle - current_angle) * radius / 2))
            path = QPainterPath()
            
            for i in range(num_points):
                t = i / (num_points - 1) if num_points > 1 else 0
                angle = current_angle + t * (dash_end_angle - current_angle)
                x = center.x() + radius * math.cos(angle)
                y = center.y() + radius * math.sin(angle)
                
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            
            if num_points > 0:
                painter.drawPath(path)
            
            # Переходим к следующему штриху
            current_angle = dash_end_angle + gap_angle
    
    @staticmethod
    def _draw_dash_dot_arc_segment(painter: QPainter, start: QPointF, end: QPointF, center: QPointF, radius: float, pen: QPen, style):
        """Отрисовывает штрихпунктирную линию вдоль дуги скругленного угла"""
        import math
        from PySide6.QtGui import QPainterPath
        
        # Вычисляем углы относительно центра
        start_angle = math.atan2(start.y() - center.y(), start.x() - center.x())
        end_angle = math.atan2(end.y() - center.y(), end.x() - center.x())
        
        if end_angle < start_angle:
            end_angle += 2 * math.pi
        
        dash_length = style.dash_length
        dash_gap = style.dash_gap
        dot_length = style.thickness_mm * 0.5
        
        if style.line_type == LineType.DASH_DOT_TWO_DOTS:
            pattern = [dash_length, dash_gap, dot_length, dash_gap, dot_length, dash_gap]
        else:
            pattern = [dash_length, dash_gap, dot_length, dash_gap]
        
        # Рисуем паттерн вдоль дуги
        current_angle = start_angle
        pattern_index = 0
        painter.setPen(pen)
        
        while current_angle < end_angle:
            segment_length = pattern[pattern_index % len(pattern)]
            segment_angle = segment_length / radius if radius > 0 else 0
            segment_end_angle = min(current_angle + segment_angle, end_angle)
            
            is_gap = (segment_length == dash_gap)
            if not is_gap:
                # ???????????? ?????????????? (?????????? ?????? ??????????)
                num_points = max(5, int((segment_end_angle - current_angle) * radius / 2))
                path = QPainterPath()
                
                for i in range(num_points):
                    t = i / (num_points - 1) if num_points > 1 else 0
                    angle = current_angle + t * (segment_end_angle - current_angle)
                    x = center.x() + radius * math.cos(angle)
                    y = center.y() + radius * math.sin(angle)
                    
                    if i == 0:
                        path.moveTo(x, y)
                    else:
                        path.lineTo(x, y)
                
                painter.drawPath(path)
            
            current_angle = segment_end_angle
            pattern_index += 1
    
    @staticmethod
    def _draw_ellipse_with_rotation(painter: QPainter, ellipse, pen: QPen):
        """???????????????????????? ???????????? ?? ???????????? ????????????????"""
        from PySide6.QtCore import Qt, QRectF
        
        painter.save()
        
        if hasattr(ellipse, 'rotation_angle') and abs(ellipse.rotation_angle) > 1e-6:
            _apply_rotation_transform(painter, ellipse.center, ellipse.rotation_angle)
            rect = QRectF(-ellipse.radius_x, -ellipse.radius_y, ellipse.radius_x * 2, ellipse.radius_y * 2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(rect)
        else:
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(ellipse.center, ellipse.radius_x, ellipse.radius_y)
        
        painter.restore()
    
    def _draw_wavy_ellipse(painter: QPainter, ellipse, pen: QPen, style=None):
        """Отрисовывает волнистый эллипс (как отрезок, скрученный в эллипс) с учетом поворота"""
        import math
        from PySide6.QtGui import QPainterPath
        from PySide6.QtCore import Qt, QPointF
        
        # Сохраняем состояние painter
        painter.save()
        # ?????????????????? ?????????????????????????? ????????????????
        rotation_angle = getattr(ellipse, 'rotation_angle', 0.0)
        center_x, center_y = _apply_rotation_transform(painter, ellipse.center, rotation_angle)
        center_offset = QPointF(center_x, center_y)
        
        
        # Приблизительная длина окружности эллипса
        a = ellipse.radius_x
        b = ellipse.radius_y
        circumference = _ellipse_circumference(a, b)
        if circumference <= 0:
            painter.restore()
            return
        
        if circumference < 1:
            painter.restore()
            return
        
        amplitude_px = _wavy_amplitude_px(pen, style)
        
        
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
    def _draw_broken_ellipse(painter: QPainter, ellipse, pen: QPen, style=None):
        """Отрисовывает эллипс с зигзагами с учетом поворота"""
        import math
        from PySide6.QtGui import QPainterPath
        from PySide6.QtCore import QPointF
        
        # Сохраняем состояние painter
        painter.save()
        
        # ?????????????????? ?????????????????????????? ????????????????
        rotation_angle = getattr(ellipse, 'rotation_angle', 0.0)
        center_x, center_y = _apply_rotation_transform(painter, ellipse.center, rotation_angle)
        center_offset = QPointF(center_x, center_y)
        
        
        # Приблизительная длина окружности эллипса
        a = ellipse.radius_x
        b = ellipse.radius_y
        circumference = _ellipse_circumference(a, b)
        if circumference <= 0:
            painter.restore()
            return
        
        if circumference < 1:
            painter.restore()
            return
        
        # Количество зигзагов и шаг из стиля
        zigzag_count = style.zigzag_count if style and hasattr(style, 'zigzag_count') else 1
        zigzag_count = max(1, int(zigzag_count))
        zigzag_step_mm = style.zigzag_step_mm if style and hasattr(style, 'zigzag_step_mm') else 4.0
        
        # Параметры зигзага
        zigzag_height_mm = 3.5
        zigzag_width_mm = 4.0
        dpi = 96
        zigzag_height = (zigzag_height_mm * dpi) / 25.4
        zigzag_length_single = (zigzag_width_mm * dpi) / 25.4
        zigzag_step = (zigzag_step_mm * dpi) / 25.4
        
        # Общая длина области зигзагов
        total_zigzag_length = zigzag_length_single * zigzag_count + zigzag_step * (zigzag_count - 1)
        
        # Конвертируем в углы
        total_zigzag_angle = (total_zigzag_length / circumference) * 2 * math.pi
        if total_zigzag_angle > math.pi * 0.9:
            total_zigzag_angle = math.pi * 0.9
            if zigzag_count > 1:
                max_length = circumference * 0.9
                zigzag_step = (max_length - zigzag_length_single * zigzag_count) / (zigzag_count - 1)
                zigzag_step = max(zigzag_step, zigzag_length_single * 0.5)
                total_zigzag_length = zigzag_length_single * zigzag_count + zigzag_step * (zigzag_count - 1)
                total_zigzag_angle = (total_zigzag_length / circumference) * 2 * math.pi
        
        zigzag_length_single_angle = (zigzag_length_single / circumference) * 2 * math.pi
        zigzag_step_angle = (zigzag_step / circumference) * 2 * math.pi
        
        # Угол начала зигзагов (равномерно распределяем по эллипсу)
        start_zigzag_angle = math.pi - total_zigzag_angle / 2
        
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
        
        # Вычисляем нормали для зигзагов
        def get_normal(angle):
            normal_x = b * math.cos(angle)
            normal_y = a * math.sin(angle)
            normal_length = math.sqrt(normal_x * normal_x + normal_y * normal_y)
            if normal_length > 0:
                return normal_x / normal_length, normal_y / normal_length
            return math.cos(angle), math.sin(angle)
        
        # Рисуем все зигзаги с шагом между ними
        current_angle = start_zigzag_angle
        for z in range(zigzag_count):
            # Углы для текущего зигзага
            zigzag_start_angle = current_angle
            zigzag_mid1_angle = current_angle + zigzag_length_single_angle / 3
            zigzag_mid2_angle = current_angle + 2 * zigzag_length_single_angle / 3
            zigzag_end_angle = current_angle + zigzag_length_single_angle
            
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
            
            # Если это не последний зигзаг, добавляем шаг (прямой участок эллипса)
            if z < zigzag_count - 1:
                current_angle = zigzag_end_angle + zigzag_step_angle
                # Рисуем прямой участок эллипса между зигзагами
                num_points_step = max(5, int(zigzag_step_angle / (2 * math.pi) * 20))
                for i in range(1, num_points_step + 1):
                    angle = zigzag_end_angle + (zigzag_step_angle * i / num_points_step)
                    x = center_offset.x() + ellipse.radius_x * math.cos(angle)
                    y = center_offset.y() + ellipse.radius_y * math.sin(angle)
                    path.lineTo(x, y)
            else:
                current_angle = zigzag_end_angle
        
        end_zigzag_angle = current_angle
        
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
        # Сохраняем состояние painter
        painter.save()
        
        # ?????????????????? ?????????????????????????? ????????????????
        rotation_angle = getattr(ellipse, 'rotation_angle', 0.0)
        center_x, center_y = _apply_rotation_transform(painter, ellipse.center, rotation_angle)
        
        
        dash_length = style.dash_length
        dash_gap = style.dash_gap
        
        # Приблизительная длина окружности эллипса
        a = ellipse.radius_x
        b = ellipse.radius_y
        circumference = _ellipse_circumference(a, b)
        if circumference <= 0:
            painter.restore()
            return
        
        if circumference < 0.1:
            painter.restore()
            return
        
        # Вычисляем, сколько полных паттернов (dash + gap) помещается в окружность
        pattern_length = dash_length + dash_gap
        num_patterns = circumference / pattern_length
        
        # Если паттернов меньше 1, рисуем один штрих
        if num_patterns < 1:
            rect = PrimitiveRenderer._ellipse_rect(center_x, center_y, ellipse.radius_x, ellipse.radius_y)
            painter.setPen(pen)
            painter.drawArc(rect, 0, int(360 * 16))
            painter.restore()
            return
        
        # ???????????????????? ???????????????????????? ???????????? ?? ?????????????? ???? ???????? ????????????????????
        num_dashes, adjusted_gap = _distributed_dash_pattern(circumference, dash_length, dash_gap)
        
        
        # Вычисляем углы с учетом равномерного распределения
        total_angle = 2 * math.pi
        dash_angle_rad = (dash_length / circumference) * total_angle
        gap_angle_rad = (adjusted_gap / circumference) * total_angle
        
        painter.setPen(pen)
        rect = PrimitiveRenderer._ellipse_rect(center_x, center_y, ellipse.radius_x, ellipse.radius_y)
        pattern = [dash_length, adjusted_gap]
        PrimitiveRenderer._draw_patterned_ellipse_segments(
            painter,
            rect,
            pattern,
            adjusted_gap,
            circumference,
            total_angle=total_angle,
        )
        
        painter.restore()
    
    @staticmethod
    def _draw_dash_dot_ellipse(painter: QPainter, ellipse, pen: QPen, style):
        """Отрисовывает штрихпунктирный эллипс с учетом поворота"""
        # Сохраняем состояние painter
        painter.save()
        
        # ?????????????????? ?????????????????????????? ????????????????
        rotation_angle = getattr(ellipse, 'rotation_angle', 0.0)
        center_x, center_y = _apply_rotation_transform(painter, ellipse.center, rotation_angle)
        
        
        dash_length = style.dash_length
        dash_gap = style.dash_gap
        dot_length = style.thickness_mm * 0.5
        
        # Приблизительная длина окружности эллипса
        a = ellipse.radius_x
        b = ellipse.radius_y
        circumference = _ellipse_circumference(a, b)
        if circumference <= 0:
            painter.restore()
            return
        
        if circumference < 0.1:
            painter.restore()
            return
        
        if style.line_type == LineType.DASH_DOT_TWO_DOTS:
            pattern = [dash_length, dash_gap, dot_length, dash_gap, dot_length, dash_gap]
        else:
            pattern = [dash_length, dash_gap, dot_length, dash_gap]
        
        painter.setPen(pen)
        PrimitiveRenderer._draw_patterned_ellipse_segments(
            painter,
            PrimitiveRenderer._ellipse_rect(center_x, center_y, ellipse.radius_x, ellipse.radius_y),
            pattern,
            dash_gap,
            circumference,
        )
        
        painter.restore()
    
    # Методы специальной отрисовки для дуг
    @staticmethod
    def _arc_rect(arc):
        return QRectF(
            -arc.radius_x,
            -arc.radius_y,
            arc.radius_x * 2,
            arc.radius_y * 2
        )

    @staticmethod
    def _draw_arc_path_segment(painter: QPainter, rect: QRectF, start_angle: float, end_angle: float):
        path = QPainterPath()
        path.arcMoveTo(rect, start_angle)
        path.arcTo(rect, start_angle, end_angle - start_angle)
        painter.drawPath(path)

    @staticmethod
    def _draw_patterned_arc_segments(
        painter: QPainter,
        arc,
        rect: QRectF,
        pattern,
        gap_length: float,
        arc_length: float,
        angle_span: float,
        span_angle_deg: float,
        max_iterations: int = 1000,
    ):
        if arc_length <= 0 or angle_span <= 0:
            return

        direction = 1 if span_angle_deg >= 0 else -1
        current_angle = arc.start_angle
        pattern_index = 0
        iteration = 0

        while iteration < max_iterations:
            if direction > 0:
                if current_angle >= arc.end_angle:
                    break
            else:
                if current_angle <= arc.end_angle:
                    break

            segment_length = pattern[pattern_index % len(pattern)]
            segment_angle_abs = (segment_length / arc_length) * angle_span
            segment_angle = segment_angle_abs if direction > 0 else -segment_angle_abs

            if segment_length != gap_length:
                start_angle = current_angle
                end_angle = current_angle + segment_angle
                if direction > 0:
                    end_angle = min(end_angle, arc.end_angle)
                else:
                    end_angle = max(end_angle, arc.end_angle)
                PrimitiveRenderer._draw_arc_path_segment(painter, rect, start_angle, end_angle)

            current_angle += segment_angle
            pattern_index += 1
            iteration += 1

    @staticmethod
    def _ellipse_rect(center_x: float, center_y: float, radius_x: float, radius_y: float):
        return QRectF(
            center_x - radius_x,
            center_y - radius_y,
            radius_x * 2,
            radius_y * 2
        )

    @staticmethod
    def _circle_rect(circle):
        return PrimitiveRenderer._ellipse_rect(
            circle.center.x(),
            circle.center.y(),
            circle.radius,
            circle.radius,
        )

    @staticmethod
    def _draw_ellipse_rad_segment(painter: QPainter, rect: QRectF, start_angle_rad: float, end_angle_rad: float):
        start_angle_16 = int(start_angle_rad * 16 * 180 / math.pi)
        span_angle_16 = int((end_angle_rad - start_angle_rad) * 16 * 180 / math.pi)
        painter.drawArc(rect, start_angle_16, span_angle_16)

    @staticmethod
    def _draw_patterned_ellipse_segments(
        painter: QPainter,
        rect: QRectF,
        pattern,
        gap_length: float,
        circumference: float,
        total_angle: float = 2 * math.pi,
    ):
        if circumference <= 0:
            return

        current_angle = 0.0
        pattern_index = 0
        while current_angle < total_angle:
            segment_length = pattern[pattern_index % len(pattern)]
            segment_angle = (segment_length / circumference) * total_angle
            if segment_length != gap_length:
                start_angle = current_angle
                end_angle = min(current_angle + segment_angle, total_angle)
                PrimitiveRenderer._draw_ellipse_rad_segment(painter, rect, start_angle, end_angle)
            current_angle += segment_angle
            pattern_index += 1

    @staticmethod
    def _draw_wavy_arc(painter: QPainter, arc, pen: QPen, style=None):
        """Отрисовывает волнистую дугу эллипса с учетом поворота"""
        import math
        from PySide6.QtGui import QPainterPath
        
        # Сохраняем состояние painter
        painter.save()
        
        # ?????????????????? ?????????????????????????? ????????????????
        _apply_rotation_transform(painter, arc.center, arc.rotation_angle)
        
        
        # Вычисляем span_angle с учетом направления
        span_angle_deg = _normalized_arc_span(arc.start_angle, arc.end_angle)
        
        # ?????????????????? ?????????? ???????? ?????????????? (???????????????????? ???????????????????? ???????????????? ????????)
        angle_span_deg = abs(span_angle_deg)
        arc_length = _arc_length(arc.radius_x, arc.radius_y, span_angle_deg)
        
        if arc_length < 1:
            painter.restore()
            return
        
        # Амплитуда волны - используем из стиля, если доступна
        amplitude_px = _wavy_amplitude_px(pen, style)
        
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
    def _draw_broken_arc(painter: QPainter, arc, pen: QPen, style=None):
        """Отрисовывает дугу эллипса с зигзагами с учетом поворота"""
        import math
        from PySide6.QtGui import QPainterPath
        
        # Сохраняем состояние painter
        painter.save()
        
        # ?????????????????? ?????????????????????????? ????????????????
        _apply_rotation_transform(painter, arc.center, arc.rotation_angle)
        
        
        # Вычисляем span_angle с учетом направления
        span_angle_deg = _normalized_arc_span(arc.start_angle, arc.end_angle)
        
        angle_span = abs(span_angle_deg)
        arc_length = _arc_length(arc.radius_x, arc.radius_y, span_angle_deg)
        
        if arc_length < 1:
            painter.restore()
            return
        
        broken_params = _broken_style_params(style)
        zigzag_count = broken_params['zigzag_count']
        zigzag_height = broken_params['zigzag_height']
        zigzag_length_single = broken_params['zigzag_length_single']
        zigzag_step, total_zigzag_length = _fit_broken_pattern(
            arc_length,
            zigzag_count,
            zigzag_length_single,
            broken_params['zigzag_step'],
        )
        
        
        # Конвертируем длину в параметрический угол
        total_zigzag_angle_abs = (total_zigzag_length / arc_length) * angle_span
        if total_zigzag_angle_abs > angle_span * 0.9:
            total_zigzag_angle_abs = angle_span * 0.9
        
        zigzag_length_single_angle = (zigzag_length_single / arc_length) * angle_span
        zigzag_step_angle = (zigzag_step / arc_length) * angle_span
        
        # Угол начала зигзагов (в середине дуги)
        mid_angle = arc.start_angle + (-span_angle_deg) / 2
        start_zigzag_angle = mid_angle - (total_zigzag_angle_abs / angle_span) * (-span_angle_deg) / 2
        
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
        
        # Вычисляем нормали для зигзагов
        def get_normal(param_angle_rad):
            base_x = arc.radius_x * math.cos(param_angle_rad)
            base_y = arc.radius_y * math.sin(param_angle_rad)
            normal_length = math.sqrt(base_x * base_x + base_y * base_y)
            if normal_length > 0:
                normal_x = base_x / normal_length
                normal_y = base_y / normal_length
                return normal_x, normal_y
            return math.cos(param_angle_rad), math.sin(param_angle_rad)
        
        zigzag_offset_sign = 1
        
        # Рисуем все зигзаги с шагом между ними
        current_angle = start_zigzag_angle
        for z in range(zigzag_count):
            # Углы для текущего зигзага
            zigzag_start_angle = current_angle
            zigzag_mid1_angle = current_angle + (zigzag_length_single_angle / angle_span) * (-span_angle_deg) / 3
            zigzag_mid2_angle = current_angle + 2 * (zigzag_length_single_angle / angle_span) * (-span_angle_deg) / 3
            zigzag_end_angle = current_angle + (zigzag_length_single_angle / angle_span) * (-span_angle_deg)
            
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
            
            # Если это не последний зигзаг, добавляем шаг (прямой участок дуги)
            if z < zigzag_count - 1:
                current_angle = zigzag_end_angle + (zigzag_step_angle / angle_span) * (-span_angle_deg)
                # Рисуем прямой участок дуги между зигзагами
                num_points_step = max(5, int(abs(zigzag_step_angle) / angle_span * 20))
                for i in range(1, num_points_step + 1):
                    param_angle_deg = zigzag_end_angle + (zigzag_step_angle / angle_span) * (-span_angle_deg) * i / num_points_step
                    param_angle_rad = math.radians(param_angle_deg)
                    x = arc.radius_x * math.cos(param_angle_rad)
                    y = arc.radius_y * math.sin(param_angle_rad)
                    path.lineTo(x, y)
            else:
                current_angle = zigzag_end_angle
        
        end_zigzag_angle = current_angle
        
        # Рисуем оставшуюся часть дуги
        # Вычисляем разность углов от конца зигзагов до конца дуги
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
        # Сохраняем состояние painter
        painter.save()
        
        # ?????????????????? ?????????????????????????? ????????????????
        _apply_rotation_transform(painter, arc.center, arc.rotation_angle)
        
        
        dash_length = style.dash_length
        dash_gap = style.dash_gap
        
        # Вычисляем span_angle с учетом направления
        span_angle_deg = _normalized_arc_span(arc.start_angle, arc.end_angle)
        
        angle_span_deg = abs(span_angle_deg)
        arc_length = _arc_length(arc.radius_x, arc.radius_y, span_angle_deg)
        
        if arc_length < 0.1:
            painter.restore()
            return
        
        # Вычисляем, сколько полных паттернов (dash + gap) помещается в дугу
        pattern_length = dash_length + dash_gap
        num_patterns = arc_length / pattern_length
        
        # Если паттернов меньше 1, рисуем один штрих
        if num_patterns < 1:
            rect = PrimitiveRenderer._arc_rect(arc)
            painter.setPen(pen)
            PrimitiveRenderer._draw_arc_path_segment(
                painter,
                rect,
                arc.start_angle,
                arc.start_angle + angle_span_deg,
            )
            painter.restore()
            return
        
        # ???????????????????? ???????????????????????? ???????????? ?? ?????????????? ???? ???????? ????????
        num_dashes, adjusted_gap = _distributed_dash_pattern(arc_length, dash_length, dash_gap)
        
        # ?????????????????? ???????? ?? ???????????? ???????????????????????? ??????????????????????????
        dash_angle_deg = (dash_length / arc_length) * angle_span_deg
        gap_angle_deg = (adjusted_gap / arc_length) * angle_span_deg
        
        painter.setPen(pen)
        current_angle_deg = arc.start_angle
        
        rect = PrimitiveRenderer._arc_rect(arc)
        
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
            PrimitiveRenderer._draw_arc_path_segment(painter, rect, start_angle_deg, end_angle_deg_calc)
            
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
        # Сохраняем состояние painter
        painter.save()
        
        # ?????????????????? ?????????????????????????? ????????????????
        _apply_rotation_transform(painter, arc.center, arc.rotation_angle)
        
        
        dash_length = style.dash_length
        dash_gap = style.dash_gap
        dot_length = style.thickness_mm * 0.5
        # Вычисляем span_angle с учетом направления
        span_angle_deg = _normalized_arc_span(arc.start_angle, arc.end_angle)
        
        angle_span = abs(span_angle_deg)
        arc_length = _arc_length(arc.radius_x, arc.radius_y, span_angle_deg)
        
        if arc_length < 0.1:
            painter.restore()
            return
        
        if style.line_type == LineType.DASH_DOT_TWO_DOTS:
            pattern = [dash_length, dash_gap, dot_length, dash_gap, dot_length, dash_gap]
        else:
            pattern = [dash_length, dash_gap, dot_length, dash_gap]
        
        painter.setPen(pen)
        PrimitiveRenderer._draw_patterned_arc_segments(
            painter,
            arc,
            PrimitiveRenderer._arc_rect(arc),
            pattern,
            dash_gap,
            arc_length,
            angle_span,
            span_angle_deg,
        )
        
        painter.restore()
    
    # Методы специальной отрисовки для многоугольников
    @staticmethod
    def _draw_wavy_polygon(painter: QPainter, polygon, pen: QPen, style=None):
        """Отрисовывает волнистый многоугольник"""
        vertices = polygon.get_vertices()
        if len(vertices) < 3:
            return
        
        # Рисуем каждую сторону как волнистую линию
        for i in range(len(vertices)):
            start = vertices[i]
            end = vertices[(i + 1) % len(vertices)]
            LineRenderer._draw_wavy_line(painter, start, end, pen, style)
    
    @staticmethod
    def _draw_broken_polygon(painter: QPainter, polygon, pen: QPen, style=None):
        """Отрисовывает многоугольник с изломами"""
        vertices = polygon.get_vertices()
        if len(vertices) < 3:
            return
        
        # Рисуем каждую сторону как линию с изломами
        for i in range(len(vertices)):
            start = vertices[i]
            end = vertices[(i + 1) % len(vertices)]
            LineRenderer._draw_broken_line(painter, start, end, pen, style)
    
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
    
    @staticmethod
    def draw_spline(painter: QPainter, spline, scale_factor: float = 1.0, is_selected: bool = False):
        """Отрисовывает сплайн с поддержкой всех типов линий"""
        from PySide6.QtGui import QPainterPath
        
        if len(spline.control_points) < 2:
            return
        
        if spline.style:
            pen = spline.style.get_pen(scale_factor=scale_factor)
            if hasattr(spline, '_legacy_color') and spline._legacy_color != spline.style.color:
                pen.setColor(spline._legacy_color)
            if is_selected:
                pen.setWidthF(pen.widthF() * 1.5)
                color = pen.color()
                color.setAlpha(255)
                pen.setColor(color)
            
            line_type = spline.style.line_type
            
            # Для специальных типов линий используем специальную отрисовку
            if line_type == LineType.SOLID_WAVY:
                PrimitiveRenderer._draw_wavy_spline(painter, spline, pen, scale_factor, spline.style)
            elif line_type == LineType.SOLID_THIN_BROKEN:
                PrimitiveRenderer._draw_broken_spline(painter, spline, pen, spline.style)
            elif line_type == LineType.DASHED:
                PrimitiveRenderer._draw_dashed_spline(painter, spline, pen, spline.style)
            elif line_type in [LineType.DASH_DOT_THICK, LineType.DASH_DOT_THIN, LineType.DASH_DOT_TWO_DOTS]:
                PrimitiveRenderer._draw_dash_dot_spline(painter, spline, pen, spline.style)
            else:
                # Обычные сплошные линии
                path = QPainterPath()
                num_samples = max(100, len(spline.control_points) * 20)
                for i in range(num_samples + 1):
                    t = i / num_samples if num_samples > 0 else 0
                    point = spline._get_point_on_spline(t)
                    if i == 0:
                        path.moveTo(point)
                    else:
                        path.lineTo(point)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(path)
        else:
            pen = QPen(spline.color, spline.width)
            if is_selected:
                pen.setWidthF(pen.widthF() * 1.5)
            legacy_lt = getattr(spline, '_legacy_linetype', 'Continuous') or 'Continuous'
            legacy_lt = str(legacy_lt).strip().upper()
            if legacy_lt == 'DASHED':
                pen.setCapStyle(Qt.FlatCap)
                style = _legacy_pattern_style(pen.widthF(), LineType.DASHED)
                PrimitiveRenderer._draw_dashed_spline(painter, spline, pen, style)
            elif legacy_lt in ('DASHDOT', 'DASHDOT2'):
                pen.setCapStyle(Qt.FlatCap)
                lt_enum = LineType.DASH_DOT_TWO_DOTS if legacy_lt == 'DASHDOT2' else LineType.DASH_DOT_THIN
                style = _legacy_pattern_style(pen.widthF(), lt_enum)
                PrimitiveRenderer._draw_dash_dot_spline(painter, spline, pen, style)
            else:
                path = QPainterPath()
                num_samples = max(100, len(spline.control_points) * 20)
                for i in range(num_samples + 1):
                    t = i / num_samples if num_samples > 0 else 0
                    point = spline._get_point_on_spline(t)
                    if i == 0:
                        path.moveTo(point)
                    else:
                        path.lineTo(point)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(path)
    
    # Методы специальной отрисовки для сплайнов
    @staticmethod
    def _draw_wavy_spline(painter: QPainter, spline, pen: QPen, scale_factor: float = 1.0, style=None):
        """Отрисовывает волнистый сплайн вдоль кривой"""
        from PySide6.QtGui import QPainterPath
        
        if len(spline.control_points) < 2:
            return
        
        amplitude_px = _wavy_amplitude_px(pen, style)

        
        # Используем фиксированную длину волны в пикселях для равномерного распределения
        wave_length_px = amplitude_px * 5
        
        # Конвертируем длину волны в мировые координаты для равномерного распределения
        # При масштабировании длина волны должна оставаться постоянной в пикселях
        wave_length_world = wave_length_px / scale_factor if scale_factor > 0 else wave_length_px
        
        # Сначала вычисляем точки на сплайне и накапливаем длину дуги
        # Используем адаптивное количество точек для более равномерного распределения волн
        # Количество точек должно быть достаточным для плавного отображения волн
        # Минимум 20 точек на волну для плавности
        estimated_waves = 10  # Примерная оценка, будет уточнена после расчета длины
        min_points_per_wave = 20
        num_samples = max(500, len(spline.control_points) * 100, estimated_waves * min_points_per_wave)
        
        points, arc_lengths, total_length = _sample_spline_with_arc_lengths(
            spline,
            min_samples=num_samples,
            factor=100,
        )
        
        if total_length < 1:
            return
        
        # Уточняем количество точек, если нужно, для более равномерного распределения
        num_waves = max(1, int(total_length / wave_length_world))
        # Используем фиксированную длину волны для равномерного распределения
        actual_wave_length = wave_length_world
        
        # Увеличиваем количество точек, если нужно для плавности
        min_total_points = num_waves * min_points_per_wave
        if len(points) < min_total_points:
            # Пересчитываем с большим количеством точек
            num_samples = min_total_points
            points, arc_lengths, total_length = _sample_spline_with_arc_lengths(
                spline,
                min_samples=num_samples,
                factor=100,
            )
        
        # Строим волнистый путь вдоль сплайна
        path = QPainterPath()
        path.moveTo(points[0])
        
        for i in range(1, len(points)):
            perp_cos, perp_sin = _spline_normal_at_index(points, i)
            
            # Вычисляем фазу волны на основе длины дуги
            arc_pos = arc_lengths[i]
            wave_phase = (arc_pos / actual_wave_length) * 2 * math.pi
            wave_offset = amplitude_px * math.sin(wave_phase)
            
            # Применяем смещение перпендикулярно к кривой
            wavy_point = QPointF(
                points[i].x() + wave_offset * perp_cos,
                points[i].y() + wave_offset * perp_sin
            )
            path.lineTo(wavy_point)
        
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
    
    @staticmethod
    def _draw_broken_spline(painter: QPainter, spline, pen: QPen, style=None):
        """Отрисовывает сплайн с изломами вдоль кривой"""
        from PySide6.QtGui import QPainterPath
        
        if len(spline.control_points) < 2:
            return
        
        points, arc_lengths, total_length = _sample_spline_with_arc_lengths(spline)
        
        if total_length < 1:
            return
        
        broken_params = _broken_style_params(style)
        zigzag_count = broken_params['zigzag_count']
        zigzag_height = broken_params['zigzag_height']
        zigzag_length_single = broken_params['zigzag_length_single']
        zigzag_step, total_zigzag_length = _fit_broken_pattern(
            total_length,
            zigzag_count,
            zigzag_length_single,
            broken_params['zigzag_step'],
        )
        
        straight_length = (total_length - total_zigzag_length) / 2
        
        
        # Строим путь с зигзагом
        path = QPainterPath()
        path.moveTo(points[0])
        
        # Находим точки начала и конца зигзага
        zigzag_start_idx = 0
        zigzag_end_idx = len(points) - 1
        
        for i in range(len(arc_lengths)):
            if arc_lengths[i] >= straight_length:
                zigzag_start_idx = i
                break
        
        for i in range(len(arc_lengths) - 1, -1, -1):
            if arc_lengths[i] <= total_length - straight_length:
                zigzag_end_idx = i
                break
        
        # ???????????? ???? ???????????? ??????????????
        for i in range(1, zigzag_start_idx + 1):
            path.lineTo(points[i])
        
        # ???????????? ?????? ?????????????? ?? ?????????? ?????????? ????????
        if zigzag_start_idx < zigzag_end_idx:
            zigzag_segment_length = arc_lengths[zigzag_end_idx] - arc_lengths[zigzag_start_idx]
            if zigzag_segment_length > 0:
                zigzag_length_single_arc = zigzag_length_single
                zigzag_step_arc = zigzag_step

                current_arc_pos = arc_lengths[zigzag_start_idx]

                for z in range(zigzag_count):
                    # ???????????? ??????????????
                    zigzag_start_arc = current_arc_pos
                    zigzag_mid1_arc = current_arc_pos + zigzag_length_single_arc / 3
                    zigzag_mid2_arc = current_arc_pos + 2 * zigzag_length_single_arc / 3
                    zigzag_end_arc = current_arc_pos + zigzag_length_single_arc
                    
                    # Точка начала зигзага
                    p1 = _point_at_arc_length(points, arc_lengths, zigzag_start_arc)
                    path.lineTo(p1)
                    
                    # Первая точка зигзага (вверх)
                    p2_base = _point_at_arc_length(points, arc_lengths, zigzag_mid1_arc)
                    perp_cos, perp_sin = _spline_normal_at_arc_length(points, arc_lengths, zigzag_mid1_arc)
                    p2 = QPointF(
                        p2_base.x() + (zigzag_height / 2) * perp_cos,
                        p2_base.y() + (zigzag_height / 2) * perp_sin
                    )
                    path.lineTo(p2)
                    
                    # Вторая точка зигзага (вниз)
                    p3_base = _point_at_arc_length(points, arc_lengths, zigzag_mid2_arc)
                    perp_cos, perp_sin = _spline_normal_at_arc_length(points, arc_lengths, zigzag_mid2_arc)
                    p3 = QPointF(
                        p3_base.x() - zigzag_height * perp_cos,
                        p3_base.y() - zigzag_height * perp_sin
                    )
                    path.lineTo(p3)
                    
                    # Конец зигзага
                    p4 = _point_at_arc_length(points, arc_lengths, zigzag_end_arc)
                    path.lineTo(p4)
                    
                    # Если это не последний зигзаг, добавляем шаг (прямой участок)
                    if z < zigzag_count - 1:
                        current_arc_pos = zigzag_end_arc + zigzag_step_arc
                        # Рисуем прямой участок между зигзагами
                        num_step_points = max(5, int(zigzag_step_arc / total_length * 20))
                        for i in range(1, num_step_points + 1):
                            step_arc = zigzag_end_arc + (zigzag_step_arc * i / num_step_points)
                            step_point = _point_at_arc_length(points, arc_lengths, step_arc)
                            path.lineTo(step_point)
                    else:
                        current_arc_pos = zigzag_end_arc
        
        # Рисуем от конца зигзага до конца
        for i in range(zigzag_end_idx + 1, len(points)):
            path.lineTo(points[i])
        
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
    
    @staticmethod
    def _draw_dashed_spline(painter: QPainter, spline, pen: QPen, style):
        """Отрисовывает штриховой сплайн вдоль кривой"""
        if len(spline.control_points) < 2:
            return
        
        points, arc_lengths, total_length = _sample_spline_with_arc_lengths(spline)
        
        if total_length < 0.1:
            return
        
        dash_length = style.dash_length
        dash_gap = style.dash_gap
        
        painter.setPen(pen)
        
        # Рисуем штрихи вдоль кривой
        current_arc_pos = 0.0
        drawing_dash = True
        
        while current_arc_pos < total_length:
            if drawing_dash:
                dash_end = min(current_arc_pos + dash_length, total_length)
                # Находим точки на кривой для начала и конца штриха
                start_point = _point_at_arc_length(points, arc_lengths, current_arc_pos)
                end_point = _point_at_arc_length(points, arc_lengths, dash_end)
                painter.drawLine(start_point, end_point)
                current_arc_pos = dash_end
                drawing_dash = False
            else:
                current_arc_pos += dash_gap
                drawing_dash = True
    
    @staticmethod
    def _draw_dash_dot_spline(painter: QPainter, spline, pen: QPen, style):
        """???????????????????????? ?????????????????????????????? ???????????? ?????????? ????????????"""
        if len(spline.control_points) < 2:
            return
        
        points, arc_lengths, total_length = _sample_spline_with_arc_lengths(spline)
        
        if total_length < 0.1:
            return
        
        dash_length = style.dash_length
        dash_gap = style.dash_gap
        dot_length = style.thickness_mm * 0.5
        
        if style.line_type == LineType.DASH_DOT_TWO_DOTS:
            pattern = [dash_length, dash_gap, dot_length, dash_gap, dot_length, dash_gap]
        else:
            pattern = [dash_length, dash_gap, dot_length, dash_gap]
        
        painter.setPen(pen)
        current_arc_pos = 0.0
        pattern_index = 0
        
        while current_arc_pos < total_length:
            segment_length = pattern[pattern_index % len(pattern)]
            segment_end = min(current_arc_pos + segment_length, total_length)
            
            is_gap = (segment_length == dash_gap)
            
            if not is_gap:
                start_point = _point_at_arc_length(points, arc_lengths, current_arc_pos)
                end_point = _point_at_arc_length(points, arc_lengths, segment_end)
                painter.drawLine(start_point, end_point)
            
            current_arc_pos += segment_length
            pattern_index += 1
    @staticmethod
    def _get_point_at_arc_length(points, arc_lengths, target_arc):
        """Находит точку на кривой для заданной длины дуги"""
        return _point_at_arc_length(points, arc_lengths, target_arc)
    

class SceneRenderer:
    """Класс для отрисовки всей сцены"""
    
    def __init__(self, viewport, scene, selection_manager, layer_manager=None):
        self.viewport = viewport
        self.scene = scene
        self.selection_manager = selection_manager
        self.layer_manager = layer_manager
        
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
        
        # Объекты сцены (слой только для видимости, стиль — у каждого объекта свой)
        scale_factor = self.viewport.get_scale()
        for obj in self.scene.get_objects():
            if self.layer_manager:
                obj_layer_name = getattr(obj, '_layer_name', '0')
                if not self.layer_manager.is_layer_visible(obj_layer_name):
                    continue

            is_selected = self.selection_manager.is_selected(obj)
            if isinstance(obj, LineSegment):
                LineRenderer.draw_line(painter, obj, scale_factor, is_selected)
            elif hasattr(obj, 'draw'):
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
