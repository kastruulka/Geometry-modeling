"""
Система привязок для геометрических объектов
"""
from typing import List, Optional, Tuple
from enum import Enum
from PySide6.QtCore import QPointF
import math

from core.geometry import GeometricObject
from widgets.line_segment import LineSegment
from widgets.primitives import Circle, Arc, Rectangle, Ellipse


class SnapType(Enum):
    """Типы точек привязки"""
    END = "end"  # Конец
    MIDDLE = "middle"  # Середина
    CENTER = "center"  # Центр
    VERTEX = "vertex"  # Вершина


class SnapPoint:
    """Точка привязки"""
    
    def __init__(self, point: QPointF, snap_type: SnapType, object: GeometricObject):
        self.point = point
        self.snap_type = snap_type
        self.object = object
    
    def distance_to(self, other_point: QPointF) -> float:
        """Вычисляет расстояние до другой точки"""
        dx = self.point.x() - other_point.x()
        dy = self.point.y() - other_point.y()
        return math.sqrt(dx*dx + dy*dy)


class SnapManager:
    """Менеджер системы привязок"""
    
    def __init__(self, tolerance: float = 10.0):
        """
        Инициализация менеджера привязок
        Args:
            tolerance: Радиус привязки в пикселях
        """
        self.tolerance = tolerance
        self.enabled = True
        self.snap_to_end = True
        self.snap_to_middle = True
        self.snap_to_center = True
        self.snap_to_vertex = True
    
    def set_tolerance(self, tolerance: float):
        """Устанавливает радиус привязки"""
        self.tolerance = tolerance
    
    def get_snap_points(self, objects: List[GeometricObject], 
                       exclude_object: Optional[GeometricObject] = None) -> List[SnapPoint]:
        """
        Получает все точки привязки из объектов
        Args:
            objects: Список объектов для извлечения точек привязки
            exclude_object: Объект, который нужно исключить (например, текущий рисуемый)
        Returns:
            Список точек привязки
        """
        snap_points = []
        
        for obj in objects:
            if exclude_object and obj is exclude_object:
                continue
            
            if isinstance(obj, LineSegment):
                snap_points.extend(self._get_line_snap_points(obj))
            elif isinstance(obj, Circle):
                snap_points.extend(self._get_circle_snap_points(obj))
            elif isinstance(obj, Arc):
                snap_points.extend(self._get_arc_snap_points(obj))
            elif isinstance(obj, Rectangle):
                snap_points.extend(self._get_rectangle_snap_points(obj))
            elif isinstance(obj, Ellipse):
                snap_points.extend(self._get_ellipse_snap_points(obj))
        
        return snap_points
    
    def _get_line_snap_points(self, line: LineSegment) -> List[SnapPoint]:
        """Получает точки привязки для отрезка"""
        points = []
        
        if self.snap_to_end:
            points.append(SnapPoint(line.start_point, SnapType.END, line))
            points.append(SnapPoint(line.end_point, SnapType.END, line))
        
        if self.snap_to_middle:
            mid_x = (line.start_point.x() + line.end_point.x()) / 2.0
            mid_y = (line.start_point.y() + line.end_point.y()) / 2.0
            points.append(SnapPoint(QPointF(mid_x, mid_y), SnapType.MIDDLE, line))
        
        return points
    
    def _get_circle_snap_points(self, circle: Circle) -> List[SnapPoint]:
        """Получает точки привязки для окружности"""
        points = []
        
        if self.snap_to_center:
            points.append(SnapPoint(circle.center, SnapType.CENTER, circle))
        
        # Для окружности можно добавить точки на концах диаметров
        # Но по требованиям нужны только Конец, Середина, Центр
        # Для окружности "конец" не применим, "середина" тоже
        
        return points
    
    def _get_arc_snap_points(self, arc: Arc) -> List[SnapPoint]:
        """Получает точки привязки для дуги - центр + 4 крайние точки (верх, низ, лево, право) + третья заданная точка"""
        points = []
        
        if self.snap_to_center:
            points.append(SnapPoint(arc.center, SnapType.CENTER, arc))
        
        # Get 4 extreme points of the ellipse (top, bottom, left, right)
        # These are calculated even if they don't fall within the arc range
        # Extreme points in local coordinates (before rotation)
        extreme_points_local = [
            (0, "right", arc.radius_x, 0),      # Right: parametric angle 0°
            (90, "bottom", 0, arc.radius_y),    # Bottom: parametric angle 90°
            (180, "left", -arc.radius_x, 0),    # Left: parametric angle 180°
            (270, "top", 0, -arc.radius_y)     # Top: parametric angle 270°
        ]
        
        # Function to check if point is duplicate
        def is_duplicate_point(new_point: QPointF, existing_points: List[SnapPoint]) -> bool:
            for existing in existing_points:
                dx = new_point.x() - existing.point.x()
                dy = new_point.y() - existing.point.y()
                distance = math.sqrt(dx*dx + dy*dy)
                if distance < 0.1:
                    return True
            return False
        
        # Apply rotation and add all 4 extreme points (even if not in arc range)
        if abs(arc.rotation_angle) > 1e-6:
            cos_r = math.cos(arc.rotation_angle)
            sin_r = math.sin(arc.rotation_angle)
            for param_angle, name, local_x, local_y in extreme_points_local:
                rotated_x = local_x * cos_r - local_y * sin_r
                rotated_y = local_x * sin_r + local_y * cos_r
                world_point = QPointF(
                    arc.center.x() + rotated_x,
                    arc.center.y() + rotated_y
                )
                if not is_duplicate_point(world_point, points):
                    if self.snap_to_vertex:
                        points.append(SnapPoint(world_point, SnapType.VERTEX, arc))
                    elif self.snap_to_end:
                        points.append(SnapPoint(world_point, SnapType.END, arc))
        else:
            # No rotation
            for param_angle, name, local_x, local_y in extreme_points_local:
                world_point = QPointF(
                    arc.center.x() + local_x,
                    arc.center.y() + local_y
                )
                if not is_duplicate_point(world_point, points):
                    if self.snap_to_vertex:
                        points.append(SnapPoint(world_point, SnapType.VERTEX, arc))
                    elif self.snap_to_end:
                        points.append(SnapPoint(world_point, SnapType.END, arc))
        
        return points
    
    def _get_arc_point_at_angle(self, arc: Arc, angle_deg: float) -> QPointF:
        """Вычисляет точку на дуге для заданного угла в градусах"""
        import math
        rad = math.radians(angle_deg)
        local_x = arc.radius_x * math.cos(rad)
        local_y = arc.radius_y * math.sin(rad)
        
        # Apply rotation if present
        if abs(arc.rotation_angle) > 1e-6:
            cos_r = math.cos(arc.rotation_angle)
            sin_r = math.sin(arc.rotation_angle)
            rotated_x = local_x * cos_r - local_y * sin_r
            rotated_y = local_x * sin_r + local_y * cos_r
        else:
            rotated_x = local_x
            rotated_y = local_y
        
        # Convert to world coordinates
        x = arc.center.x() + rotated_x
        y = arc.center.y() + rotated_y
        return QPointF(x, y)
    
    def _get_rectangle_snap_points(self, rect: Rectangle) -> List[SnapPoint]:
        """Получает точки привязки для прямоугольника"""
        points = []
        
        bbox = rect.get_bounding_box()
        top_left = QPointF(bbox.left(), bbox.top())
        top_right = QPointF(bbox.right(), bbox.top())
        bottom_left = QPointF(bbox.left(), bbox.bottom())
        bottom_right = QPointF(bbox.right(), bbox.bottom())
        center = QPointF(bbox.center().x(), bbox.center().y())
        
        if self.snap_to_end:
            # Углы прямоугольника - это "концы"
            points.append(SnapPoint(top_left, SnapType.END, rect))
            points.append(SnapPoint(top_right, SnapType.END, rect))
            points.append(SnapPoint(bottom_left, SnapType.END, rect))
            points.append(SnapPoint(bottom_right, SnapType.END, rect))
        
        if self.snap_to_center:
            points.append(SnapPoint(center, SnapType.CENTER, rect))
        
        if self.snap_to_middle:
            # Середины сторон прямоугольника
            mid_top = QPointF(bbox.center().x(), bbox.top())
            mid_bottom = QPointF(bbox.center().x(), bbox.bottom())
            mid_left = QPointF(bbox.left(), bbox.center().y())
            mid_right = QPointF(bbox.right(), bbox.center().y())
            points.append(SnapPoint(mid_top, SnapType.MIDDLE, rect))
            points.append(SnapPoint(mid_bottom, SnapType.MIDDLE, rect))
            points.append(SnapPoint(mid_left, SnapType.MIDDLE, rect))
            points.append(SnapPoint(mid_right, SnapType.MIDDLE, rect))
        
        return points
    
    def _get_ellipse_snap_points(self, ellipse: Ellipse) -> List[SnapPoint]:
        """Получает точки привязки для эллипса"""
        points = []
        
        if self.snap_to_center:
            points.append(SnapPoint(ellipse.center, SnapType.CENTER, ellipse))
        
        # 4 крайние точки эллипса (верх, низ, лево, право)
        if self.snap_to_vertex or self.snap_to_end:
            # Вычисляем крайние точки в локальной системе координат
            # Верх: (0, -radius_y)
            # Низ: (0, radius_y)
            # Лево: (-radius_x, 0)
            # Право: (radius_x, 0)
            extreme_points_local = [
                QPointF(0, -ellipse.radius_y),  # Верх
                QPointF(0, ellipse.radius_y),   # Низ
                QPointF(-ellipse.radius_x, 0),  # Лево
                QPointF(ellipse.radius_x, 0)    # Право
            ]
            
            # Применяем поворот, если он есть
            if abs(ellipse.rotation_angle) > 1e-6:
                cos_r = math.cos(ellipse.rotation_angle)
                sin_r = math.sin(ellipse.rotation_angle)
                for local_point in extreme_points_local:
                    rotated_x = local_point.x() * cos_r - local_point.y() * sin_r
                    rotated_y = local_point.x() * sin_r + local_point.y() * cos_r
                    world_point = QPointF(
                        ellipse.center.x() + rotated_x,
                        ellipse.center.y() + rotated_y
                    )
                    if self.snap_to_vertex:
                        points.append(SnapPoint(world_point, SnapType.VERTEX, ellipse))
                    elif self.snap_to_end:
                        points.append(SnapPoint(world_point, SnapType.END, ellipse))
            else:
                # Без поворота
                for local_point in extreme_points_local:
                    world_point = QPointF(
                        ellipse.center.x() + local_point.x(),
                        ellipse.center.y() + local_point.y()
                    )
                    if self.snap_to_vertex:
                        points.append(SnapPoint(world_point, SnapType.VERTEX, ellipse))
                    elif self.snap_to_end:
                        points.append(SnapPoint(world_point, SnapType.END, ellipse))
        
        return points
    
    def find_nearest_snap(self, point: QPointF, snap_points: List[SnapPoint], 
                          scale_factor: float = 1.0) -> Optional[Tuple[QPointF, SnapPoint]]:
        """
        Находит ближайшую точку привязки
        Args:
            point: Точка для поиска привязки
            snap_points: Список точек привязки
            scale_factor: Масштаб для учета в tolerance
        Returns:
            Кортеж (привязанная точка, SnapPoint) или None, если привязка не найдена
        """
        if not self.enabled or not snap_points:
            return None
        
        # Учитываем масштаб при вычислении tolerance
        scaled_tolerance = self.tolerance / scale_factor if scale_factor > 0 else self.tolerance
        
        nearest_snap = None
        min_distance = float('inf')
        
        for snap_point in snap_points:
            distance = snap_point.distance_to(point)
            if distance < scaled_tolerance and distance < min_distance:
                min_distance = distance
                nearest_snap = snap_point
        
        if nearest_snap:
            return (nearest_snap.point, nearest_snap)
        
        return None

