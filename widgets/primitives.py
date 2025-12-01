"""
Базовые геометрические примитивы
"""
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor

from core.geometry import GeometricObject, Drawable
from widgets.line_style import LineStyle


class Circle(GeometricObject, Drawable):
    """Класс для представления окружности"""
    
    def __init__(self, center: QPointF, radius: float, style=None, color=None, width=None):
        super().__init__()
        self.center = QPointF(center) if not isinstance(center, QPointF) else center
        self.radius = radius
        self._style = None
        self._style_name = None
        
        if style:
            self.style = style
        
        if color is not None:
            self._legacy_color = color
        else:
            self._legacy_color = QColor(0, 0, 0)
        
        if width is not None:
            self._legacy_width = width
        else:
            self._legacy_width = 2
    
    @property
    def style(self):
        return self._style
    
    @style.setter
    def style(self, value):
        if self._style:
            self._style.unregister_object(self)
        self._style = value
        self._style_name = value.name if value else None
        if value:
            value.register_object(self)
    
    @property
    def color(self):
        if self._style:
            return self._style.color
        return self._legacy_color
    
    @property
    def width(self):
        if self._style:
            return (self._style.thickness_mm * 96) / 25.4
        return self._legacy_width
    
    def get_bounding_box(self) -> QRectF:
        """Возвращает ограничивающий прямоугольник окружности"""
        return QRectF(
            self.center.x() - self.radius,
            self.center.y() - self.radius,
            self.radius * 2,
            self.radius * 2
        )
    
    def contains_point(self, point: QPointF, tolerance: float = 5.0) -> bool:
        """Проверяет, содержит ли окружность точку"""
        import math
        dx = point.x() - self.center.x()
        dy = point.y() - self.center.y()
        distance = math.sqrt(dx*dx + dy*dy)
        return abs(distance - self.radius) <= tolerance
    
    def intersects_rect(self, rect: QRectF) -> bool:
        """Проверяет, пересекается ли окружность с прямоугольником"""
        # Упрощенная проверка: если центр в прямоугольнике или окружность пересекает границы
        if rect.contains(self.center):
            return True
        
        # Проверяем пересечение с каждой стороной прямоугольника
        # Это упрощенная проверка, для точной нужен более сложный алгоритм
        bbox = self.get_bounding_box()
        return rect.intersects(bbox)
    
    def draw(self, painter, scale_factor: float = 1.0):
        """Отрисовывает окружность"""
        from core.renderer import PrimitiveRenderer
        PrimitiveRenderer.draw_circle(painter, self, scale_factor, self.selected)


class Arc(GeometricObject, Drawable):
    """Класс для представления дуги (часть эллипса)"""
    
    def __init__(self, center: QPointF, radius_x: float, radius_y: float, start_angle: float, end_angle: float,
                 style=None, color=None, width=None, rotation_angle: float = 0.0):
        super().__init__()
        self.center = QPointF(center) if not isinstance(center, QPointF) else center
        self.radius_x = radius_x  # горизонтальный радиус эллипса (вдоль хорды)
        self.radius_y = radius_y  # вертикальный радиус эллипса (перпендикулярно хорде)
        self.start_angle = start_angle  # в градусах
        self.end_angle = end_angle  # в градусах
        self.rotation_angle = rotation_angle  # угол поворота эллипса (в радианах)
        # Для обратной совместимости
        self.radius = max(radius_x, radius_y) if radius_x > 0 and radius_y > 0 else 0
        self._style = None
        self._style_name = None
        
        if style:
            self.style = style
        
        if color is not None:
            self._legacy_color = color
        else:
            self._legacy_color = QColor(0, 0, 0)
        
        if width is not None:
            self._legacy_width = width
        else:
            self._legacy_width = 2
    
    @property
    def style(self):
        return self._style
    
    @style.setter
    def style(self, value):
        if self._style:
            self._style.unregister_object(self)
        self._style = value
        self._style_name = value.name if value else None
        if value:
            value.register_object(self)
    
    @property
    def color(self):
        if self._style:
            return self._style.color
        return self._legacy_color
    
    @property
    def width(self):
        if self._style:
            return (self._style.thickness_mm * 96) / 25.4
        return self._legacy_width
    
    def get_bounding_box(self) -> QRectF:
        """Возвращает ограничивающий прямоугольник дуги"""
        import math
        # Вычисляем точки на дуге для определения границ
        angles = [self.start_angle, self.end_angle]
        # Добавляем промежуточные углы для более точного bounding box
        angle_span = abs(self.end_angle - self.start_angle)
        if angle_span > 90:
            num_points = int(angle_span / 45) + 1
            for i in range(1, num_points):
                angles.append(self.start_angle + (self.end_angle - self.start_angle) * i / num_points)
        
        points = []
        for angle in angles:
            rad = math.radians(angle)
            x = self.center.x() + self.radius_x * math.cos(rad)
            y = self.center.y() + self.radius_y * math.sin(rad)
            points.append(QPointF(x, y))
        
        # Добавляем центр
        points.append(self.center)
        
        min_x = min(p.x() for p in points)
        max_x = max(p.x() for p in points)
        min_y = min(p.y() for p in points)
        max_y = max(p.y() for p in points)
        
        return QRectF(min_x, min_y, max_x - min_x, max_y - min_y)
    
    def contains_point(self, point: QPointF, tolerance: float = 5.0) -> bool:
        """Проверяет, содержит ли дуга точку"""
        import math
        dx = point.x() - self.center.x()
        dy = point.y() - self.center.y()
        distance = math.sqrt(dx*dx + dy*dy)
        
        # Проверяем расстояние до окружности
        if abs(distance - self.radius) > tolerance:
            return False
        
        # Проверяем, находится ли угол точки в диапазоне дуги
        angle = math.degrees(math.atan2(dy, dx))
        # Нормализуем углы
        start = self.start_angle % 360
        end = self.end_angle % 360
        angle_norm = angle % 360
        
        if start <= end:
            return start <= angle_norm <= end
        else:
            # Дуга пересекает 0 градусов
            return angle_norm >= start or angle_norm <= end
    
    def intersects_rect(self, rect: QRectF) -> bool:
        """Проверяет, пересекается ли дуга с прямоугольником"""
        bbox = self.get_bounding_box()
        return rect.intersects(bbox)
    
    def draw(self, painter, scale_factor: float = 1.0):
        """Отрисовывает дугу"""
        from core.renderer import PrimitiveRenderer
        PrimitiveRenderer.draw_arc(painter, self, scale_factor, self.selected)


class Rectangle(GeometricObject, Drawable):
    """Класс для представления прямоугольника"""
    
    def __init__(self, top_left: QPointF, bottom_right: QPointF, style=None, color=None, width=None):
        super().__init__()
        self.top_left = QPointF(top_left) if not isinstance(top_left, QPointF) else top_left
        self.bottom_right = QPointF(bottom_right) if not isinstance(bottom_right, QPointF) else bottom_right
        self._style = None
        self._style_name = None
        
        if style:
            self.style = style
        
        if color is not None:
            self._legacy_color = color
        else:
            self._legacy_color = QColor(0, 0, 0)
        
        if width is not None:
            self._legacy_width = width
        else:
            self._legacy_width = 2
    
    @property
    def style(self):
        return self._style
    
    @style.setter
    def style(self, value):
        if self._style:
            self._style.unregister_object(self)
        self._style = value
        self._style_name = value.name if value else None
        if value:
            value.register_object(self)
    
    @property
    def color(self):
        if self._style:
            return self._style.color
        return self._legacy_color
    
    @property
    def width(self):
        if self._style:
            return (self._style.thickness_mm * 96) / 25.4
        return self._legacy_width
    
    def get_bounding_box(self) -> QRectF:
        """Возвращает ограничивающий прямоугольник"""
        return QRectF(
            min(self.top_left.x(), self.bottom_right.x()),
            min(self.top_left.y(), self.bottom_right.y()),
            abs(self.bottom_right.x() - self.top_left.x()),
            abs(self.bottom_right.y() - self.top_left.y())
        )
    
    def contains_point(self, point: QPointF, tolerance: float = 5.0) -> bool:
        """Проверяет, содержит ли прямоугольник точку"""
        rect = self.get_bounding_box()
        # Расширяем прямоугольник на tolerance
        expanded_rect = QRectF(
            rect.x() - tolerance,
            rect.y() - tolerance,
            rect.width() + 2 * tolerance,
            rect.height() + 2 * tolerance
        )
        return expanded_rect.contains(point)
    
    def intersects_rect(self, rect: QRectF) -> bool:
        """Проверяет, пересекается ли прямоугольник с другим прямоугольником"""
        return rect.intersects(self.get_bounding_box())
    
    def draw(self, painter, scale_factor: float = 1.0):
        """Отрисовывает прямоугольник"""
        from core.renderer import PrimitiveRenderer
        PrimitiveRenderer.draw_rectangle(painter, self, scale_factor, self.selected)


class Ellipse(GeometricObject, Drawable):
    """Класс для представления эллипса"""
    
    def __init__(self, center: QPointF, radius_x: float, radius_y: float, style=None, color=None, width=None, rotation_angle: float = 0.0):
        super().__init__()
        self.center = QPointF(center) if not isinstance(center, QPointF) else center
        self.radius_x = radius_x
        self.radius_y = radius_y
        self.rotation_angle = rotation_angle  # угол поворота эллипса (в радианах)
        self._style = None
        self._style_name = None
        
        if style:
            self.style = style
        
        if color is not None:
            self._legacy_color = color
        else:
            self._legacy_color = QColor(0, 0, 0)
        
        if width is not None:
            self._legacy_width = width
        else:
            self._legacy_width = 2
    
    @property
    def style(self):
        return self._style
    
    @style.setter
    def style(self, value):
        if self._style:
            self._style.unregister_object(self)
        self._style = value
        self._style_name = value.name if value else None
        if value:
            value.register_object(self)
    
    @property
    def color(self):
        if self._style:
            return self._style.color
        return self._legacy_color
    
    @property
    def width(self):
        if self._style:
            return (self._style.thickness_mm * 96) / 25.4
        return self._legacy_width
    
    def get_bounding_box(self) -> QRectF:
        """Возвращает ограничивающий прямоугольник эллипса"""
        return QRectF(
            self.center.x() - self.radius_x,
            self.center.y() - self.radius_y,
            self.radius_x * 2,
            self.radius_y * 2
        )
    
    def contains_point(self, point: QPointF, tolerance: float = 5.0) -> bool:
        """Проверяет, содержит ли эллипс точку"""
        import math
        dx = (point.x() - self.center.x()) / self.radius_x
        dy = (point.y() - self.center.y()) / self.radius_y
        distance = math.sqrt(dx*dx + dy*dy)
        # Проверяем, находится ли точка на эллипсе с учетом tolerance
        return abs(distance - 1.0) * min(self.radius_x, self.radius_y) <= tolerance
    
    def intersects_rect(self, rect: QRectF) -> bool:
        """Проверяет, пересекается ли эллипс с прямоугольником"""
        bbox = self.get_bounding_box()
        return rect.intersects(bbox)
    
    def draw(self, painter, scale_factor: float = 1.0):
        """Отрисовывает эллипс"""
        from core.renderer import PrimitiveRenderer
        PrimitiveRenderer.draw_ellipse(painter, self, scale_factor, self.selected)

