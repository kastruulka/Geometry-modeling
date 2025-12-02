"""
Система привязок для геометрических объектов
"""
from typing import List, Optional, Tuple
from enum import Enum
from PySide6.QtCore import QPointF
import math

from core.geometry import GeometricObject
from widgets.line_segment import LineSegment
from widgets.primitives import Circle, Arc, Rectangle, Ellipse, Polygon, Spline


class SnapType(Enum):
    """Типы точек привязки"""
    END = "end"  # Конец
    MIDDLE = "middle"  # Середина
    CENTER = "center"  # Центр
    VERTEX = "vertex"  # Вершина
    INTERSECTION = "intersection"  # Пересечение
    PERPENDICULAR = "perpendicular"  # Перпендикуляр
    TANGENT = "tangent"  # Касательная


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
        self.snap_to_intersection = True
        self.snap_to_perpendicular = True
        self.snap_to_tangent = True
    
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
            elif isinstance(obj, Polygon):
                snap_points.extend(self._get_polygon_snap_points(obj))
            elif isinstance(obj, Spline):
                snap_points.extend(self._get_spline_snap_points(obj))
        
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
        
        # 4 крайние точки окружности (верхняя, нижняя, левая, правая)
        if self.snap_to_vertex or self.snap_to_end:
            extreme_points = [
                QPointF(circle.center.x(), circle.center.y() - circle.radius),  # Верхняя
                QPointF(circle.center.x(), circle.center.y() + circle.radius),  # Нижняя
                QPointF(circle.center.x() - circle.radius, circle.center.y()),  # Левая
                QPointF(circle.center.x() + circle.radius, circle.center.y())   # Правая
            ]
            
            for point in extreme_points:
                if self.snap_to_vertex:
                    points.append(SnapPoint(point, SnapType.VERTEX, circle))
                elif self.snap_to_end:
                    points.append(SnapPoint(point, SnapType.END, circle))
        
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
    
    def _get_polygon_snap_points(self, polygon: Polygon) -> List[SnapPoint]:
        """Получает точки привязки для многоугольника"""
        points = []
        
        # Центр многоугольника
        if self.snap_to_center:
            points.append(SnapPoint(polygon.center, SnapType.CENTER, polygon))
        
        # Получаем все вершины многоугольника
        vertices = polygon.get_vertices()
        
        # Вершины многоугольника
        if self.snap_to_vertex:
            for vertex in vertices:
                points.append(SnapPoint(vertex, SnapType.VERTEX, polygon))
        
        # Середины граней многоугольника
        if self.snap_to_middle:
            for i in range(len(vertices)):
                p1 = vertices[i]
                p2 = vertices[(i + 1) % len(vertices)]
                mid_x = (p1.x() + p2.x()) / 2.0
                mid_y = (p1.y() + p2.y()) / 2.0
                points.append(SnapPoint(QPointF(mid_x, mid_y), SnapType.MIDDLE, polygon))
        
        return points
    
    def _get_spline_snap_points(self, spline: Spline) -> List[SnapPoint]:
        """Получает точки привязки для сплайна"""
        points = []
        
        # Все контрольные точки сплайна
        if self.snap_to_vertex or self.snap_to_end:
            for control_point in spline.control_points:
                if self.snap_to_vertex:
                    points.append(SnapPoint(control_point, SnapType.VERTEX, spline))
                elif self.snap_to_end:
                    points.append(SnapPoint(control_point, SnapType.END, spline))
        
        return points
    
    def get_dynamic_snap_points(self, point: QPointF, objects: List[GeometricObject],
                                exclude_object: Optional[GeometricObject] = None,
                                start_point: Optional[QPointF] = None) -> List[SnapPoint]:
        """
        Получает динамические точки привязки (пересечение, перпендикуляр, касательная)
        Args:
            point: Текущая позиция курсора
            objects: Список объектов для проверки
            exclude_object: Объект, который нужно исключить
            start_point: Начальная точка текущего рисования (для линии/дуги)
        Returns:
            Список динамических точек привязки
        """
        dynamic_points = []
        
        if not self.enabled:
            return dynamic_points
        
        for obj in objects:
            if exclude_object and obj is exclude_object:
                continue
            
            # Пересечения
            if self.snap_to_intersection and start_point:
                intersections = self._find_intersections(start_point, point, obj)
                for intersection in intersections:
                    # Проверяем, что точка пересечения не слишком близко к началу или концу линии
                    dist_to_start = math.sqrt((intersection.x() - start_point.x())**2 + 
                                             (intersection.y() - start_point.y())**2)
                    dist_to_end = math.sqrt((intersection.x() - point.x())**2 + 
                                           (intersection.y() - point.y())**2)
                    # Игнорируем точки, которые слишком близко к концам (меньше 1 пикселя)
                    if dist_to_start > 1.0 and dist_to_end > 1.0:
                        dynamic_points.append(SnapPoint(intersection, SnapType.INTERSECTION, obj))
            
            # Перпендикуляры
            if self.snap_to_perpendicular and start_point:
                perpendicular = self._find_perpendicular_point(start_point, point, obj)
                if perpendicular:
                    dynamic_points.append(SnapPoint(perpendicular, SnapType.PERPENDICULAR, obj))
            
            # Касательные
            if self.snap_to_tangent:
                tangents = self._find_tangent_points(point, obj)
                for tangent in tangents:
                    dynamic_points.append(SnapPoint(tangent, SnapType.TANGENT, obj))
        
        return dynamic_points
    
    def _find_intersections(self, line_start: QPointF, line_end: QPointF, 
                           obj: GeometricObject) -> List[QPointF]:
        """Находит точки пересечения линии с объектом"""
        intersections = []
        
        if isinstance(obj, LineSegment):
            intersection = self._line_line_intersection(
                line_start, line_end, obj.start_point, obj.end_point
            )
            if intersection:
                # Проверяем, что точка не совпадает с началом или концом линии
                dist_to_start = math.sqrt((intersection.x() - line_start.x())**2 + 
                                         (intersection.y() - line_start.y())**2)
                dist_to_end = math.sqrt((intersection.x() - line_end.x())**2 + 
                                       (intersection.y() - line_end.y())**2)
                if dist_to_start > 1e-6 and dist_to_end > 1e-6:
                    intersections.append(intersection)
        elif isinstance(obj, Circle):
            intersections.extend(self._line_circle_intersection(
                line_start, line_end, obj.center, obj.radius
            ))
        elif isinstance(obj, Arc):
            intersections.extend(self._line_arc_intersection(
                line_start, line_end, obj
            ))
        elif isinstance(obj, Ellipse):
            intersections.extend(self._line_ellipse_intersection(
                line_start, line_end, obj
            ))
        elif isinstance(obj, Rectangle):
            # Пересечение с прямоугольником = пересечение с его сторонами
            bbox = obj.get_bounding_box()
            corners = [
                (QPointF(bbox.left(), bbox.top()), QPointF(bbox.right(), bbox.top())),  # top
                (QPointF(bbox.right(), bbox.top()), QPointF(bbox.right(), bbox.bottom())),  # right
                (QPointF(bbox.right(), bbox.bottom()), QPointF(bbox.left(), bbox.bottom())),  # bottom
                (QPointF(bbox.left(), bbox.bottom()), QPointF(bbox.left(), bbox.top()))  # left
            ]
            for corner_start, corner_end in corners:
                intersection = self._line_line_intersection(
                    line_start, line_end, corner_start, corner_end
                )
                if intersection:
                    intersections.append(intersection)
        
        return intersections
    
    def _find_perpendicular_point(self, line_start: QPointF, line_end: QPointF,
                                 obj: GeometricObject) -> Optional[QPointF]:
        """Находит точку на объекте, которая является основанием перпендикуляра от линии"""
        # Направление линии
        dx = line_end.x() - line_start.x()
        dy = line_end.y() - line_start.y()
        line_length = math.sqrt(dx*dx + dy*dy)
        if line_length < 1e-6:
            return None
        
        # Нормализуем направление
        dx /= line_length
        dy /= line_length
        
        if isinstance(obj, LineSegment):
            return self._perpendicular_to_line(line_start, line_end, obj.start_point, obj.end_point)
        elif isinstance(obj, Circle):
            return self._perpendicular_to_circle(line_start, line_end, obj.center, obj.radius)
        elif isinstance(obj, Arc):
            return self._perpendicular_to_arc(line_start, line_end, obj)
        elif isinstance(obj, Ellipse):
            return self._perpendicular_to_ellipse(line_start, line_end, obj)
        
        return None
    
    def _find_tangent_points(self, point: QPointF, obj: GeometricObject) -> List[QPointF]:
        """Находит точки касания от точки к объекту"""
        tangents = []
        
        if isinstance(obj, Circle):
            tangents.extend(self._tangent_to_circle(point, obj.center, obj.radius))
        elif isinstance(obj, Arc):
            tangents.extend(self._tangent_to_arc(point, obj))
        elif isinstance(obj, Ellipse):
            tangents.extend(self._tangent_to_ellipse(point, obj))
        
        return tangents
    
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
    
    # ========== Геометрические вычисления для динамических привязок ==========
    
    def _line_line_intersection(self, p1: QPointF, p2: QPointF, 
                                p3: QPointF, p4: QPointF) -> Optional[QPointF]:
        """Находит точку пересечения двух отрезков"""
        x1, y1 = p1.x(), p1.y()
        x2, y2 = p2.x(), p2.y()
        x3, y3 = p3.x(), p3.y()
        x4, y4 = p4.x(), p4.y()
        
        # Направляющие векторы
        dx1 = x2 - x1
        dy1 = y2 - y1
        dx2 = x4 - x3
        dy2 = y4 - y3
        
        # Знаменатель для параметрических уравнений
        denom = dx1 * dy2 - dy1 * dx2
        if abs(denom) < 1e-10:
            return None  # Параллельные линии
        
        # Параметры для обоих отрезков
        # t для первого отрезка: P = P1 + t * (P2 - P1)
        # u для второго отрезка: P = P3 + u * (P4 - P3)
        t = ((x3 - x1) * dy2 - (y3 - y1) * dx2) / denom
        u = ((x3 - x1) * dy1 - (y3 - y1) * dx1) / denom
        
        # Проверяем, что точка находится на обоих отрезках
        if 0 <= t <= 1 and 0 <= u <= 1:
            x = x1 + t * dx1
            y = y1 + t * dy1
            return QPointF(x, y)
        
        return None
    
    def _line_circle_intersection(self, line_start: QPointF, line_end: QPointF,
                                   center: QPointF, radius: float) -> List[QPointF]:
        """Находит точки пересечения линии с окружностью"""
        intersections = []
        
        # Переводим в систему координат с центром окружности в начале
        x1 = line_start.x() - center.x()
        y1 = line_start.y() - center.y()
        x2 = line_end.x() - center.x()
        y2 = line_end.y() - center.y()
        
        dx = x2 - x1
        dy = y2 - y1
        dr_sq = dx*dx + dy*dy
        
        if dr_sq < 1e-10:
            return intersections
        
        # Определитель для формулы пересечения линии и окружности
        D = x1 * y2 - x2 * y1
        discriminant = radius*radius * dr_sq - D*D
        
        if discriminant < 0:
            return intersections
        
        sqrt_disc = math.sqrt(discriminant)
        
        # Две точки пересечения (используем правильную формулу)
        for sign in [-1, 1]:
            # Формула для точки пересечения линии и окружности
            x = (D * dy + sign * (1 if dy >= 0 else -1) * dx * sqrt_disc) / dr_sq
            y = (-D * dx + sign * abs(dy) * sqrt_disc) / dr_sq
            
            # Вычисляем параметр t для точки на линии: P = P1 + t * (P2 - P1)
            # Используем более точный метод
            if abs(dr_sq) > 1e-10:
                # Проекция точки на направление линии
                t = ((x - x1) * dx + (y - y1) * dy) / dr_sq
            else:
                t = 0
            
            # Проверяем, что точка на отрезке
            if 0 <= t <= 1:
                world_x = x + center.x()
                world_y = y + center.y()
                intersections.append(QPointF(world_x, world_y))
        
        return intersections
    
    def _line_arc_intersection(self, line_start: QPointF, line_end: QPointF,
                               arc: Arc) -> List[QPointF]:
        """Находит точки пересечения линии с дугой"""
        intersections = []
        
        # Сначала находим пересечения с полным эллипсом
        ellipse_intersections = self._line_ellipse_intersection(
            line_start, line_end, arc
        )
        
        # Фильтруем только те, что попадают в диапазон дуги
        for point in ellipse_intersections:
            if self._point_on_arc(point, arc):
                intersections.append(point)
        
        return intersections
    
    def _line_ellipse_intersection(self, line_start: QPointF, line_end: QPointF,
                                   ellipse) -> List[QPointF]:
        """Находит точки пересечения линии с эллипсом (или дугой)"""
        intersections = []
        
        # Переводим в локальную систему координат эллипса
        # Сначала переносим центр в начало
        x1 = line_start.x() - ellipse.center.x()
        y1 = line_start.y() - ellipse.center.y()
        x2 = line_end.x() - ellipse.center.x()
        y2 = line_end.y() - ellipse.center.y()
        
        # Применяем обратный поворот
        if abs(ellipse.rotation_angle) > 1e-6:
            cos_r = math.cos(-ellipse.rotation_angle)
            sin_r = math.sin(-ellipse.rotation_angle)
            x1_rot = x1 * cos_r - y1 * sin_r
            y1_rot = x1 * sin_r + y1 * cos_r
            x2_rot = x2 * cos_r - y2 * sin_r
            y2_rot = x2 * sin_r + y2 * cos_r
        else:
            x1_rot, y1_rot = x1, y1
            x2_rot, y2_rot = x2, y2
        
        # Нормализуем эллипс к единичной окружности
        if ellipse.radius_x < 1e-6 or ellipse.radius_y < 1e-6:
            return intersections
        
        x1_norm = x1_rot / ellipse.radius_x
        y1_norm = y1_rot / ellipse.radius_y
        x2_norm = x2_rot / ellipse.radius_x
        y2_norm = y2_rot / ellipse.radius_y
        
        # Находим пересечение с единичной окружностью
        dx = x2_norm - x1_norm
        dy = y2_norm - y1_norm
        dr_sq = dx*dx + dy*dy
        
        if dr_sq < 1e-10:
            return intersections
        
        D = x1_norm * y2_norm - x2_norm * y1_norm
        discriminant = dr_sq - D*D
        
        if discriminant < 0:
            return intersections
        
        sqrt_disc = math.sqrt(discriminant)
        
        # Две точки пересечения
        for sign in [-1, 1]:
            x_norm = (D * dy + sign * (dy if dy >= 0 else -dy) * sqrt_disc) / dr_sq
            y_norm = (-D * dx + sign * abs(dy) * sqrt_disc) / dr_sq
            
            # Обратное преобразование к локальным координатам
            x_local = x_norm * ellipse.radius_x
            y_local = y_norm * ellipse.radius_y
            
            # Применяем поворот обратно
            if abs(ellipse.rotation_angle) > 1e-6:
                cos_r = math.cos(ellipse.rotation_angle)
                sin_r = math.sin(ellipse.rotation_angle)
                x_world = x_local * cos_r - y_local * sin_r
                y_world = x_local * sin_r + y_local * cos_r
            else:
                x_world, y_world = x_local, y_local
            
            # Переводим в мировые координаты
            x = x_world + ellipse.center.x()
            y = y_world + ellipse.center.y()
            
            # Проверяем, что точка на отрезке
            t = ((x - line_start.x()) * (line_end.x() - line_start.x()) + 
                 (y - line_start.y()) * (line_end.y() - line_start.y())) / dr_sq if dr_sq > 0 else 0
            if 0 <= t <= 1:
                intersections.append(QPointF(x, y))
        
        return intersections
    
    def _point_on_arc(self, point: QPointF, arc: Arc) -> bool:
        """Проверяет, находится ли точка на дуге (в её угловом диапазоне)"""
        # Переводим точку в локальные координаты
        x = point.x() - arc.center.x()
        y = point.y() - arc.center.y()
        
        # Применяем обратный поворот
        if abs(arc.rotation_angle) > 1e-6:
            cos_r = math.cos(-arc.rotation_angle)
            sin_r = math.sin(-arc.rotation_angle)
            x_rot = x * cos_r - y * sin_r
            y_rot = x * sin_r + y * cos_r
        else:
            x_rot, y_rot = x, y
        
        # Вычисляем параметрический угол
        if abs(x_rot) < 1e-6 and abs(y_rot) < 1e-6:
            return False
        
        # Нормализуем к единичному эллипсу для вычисления угла
        if arc.radius_x < 1e-6 or arc.radius_y < 1e-6:
            return False
        
        x_norm = x_rot / arc.radius_x
        y_norm = y_rot / arc.radius_y
        
        # Вычисляем угол
        angle_rad = math.atan2(y_norm, x_norm)
        angle_deg = math.degrees(angle_rad)
        if angle_deg < 0:
            angle_deg += 360
        
        # Нормализуем углы дуги
        start_angle = arc.start_angle % 360
        end_angle = arc.end_angle % 360
        if end_angle == 0 and arc.end_angle > 0:
            end_angle = 360
        
        # Проверяем, попадает ли угол в диапазон
        if start_angle <= end_angle:
            return start_angle <= angle_deg <= end_angle
        else:
            # Диапазон пересекает 0°
            return angle_deg >= start_angle or angle_deg <= end_angle
    
    def _perpendicular_to_line(self, line_start: QPointF, line_end: QPointF,
                               obj_start: QPointF, obj_end: QPointF) -> Optional[QPointF]:
        """Находит основание перпендикуляра от линии к отрезку"""
        # Направление текущей линии
        line_dx = line_end.x() - line_start.x()
        line_dy = line_end.y() - line_start.y()
        line_len_sq = line_dx*line_dx + line_dy*line_dy
        if line_len_sq < 1e-10:
            return None
        
        # Направление объекта
        obj_dx = obj_end.x() - obj_start.x()
        obj_dy = obj_end.y() - obj_start.y()
        obj_len_sq = obj_dx*obj_dx + obj_dy*obj_dy
        if obj_len_sq < 1e-10:
            return None
        
        # Параметрическое уравнение объекта: obj_start + t * (obj_end - obj_start)
        # Ищем точку на объекте, такую что линия от этой точки перпендикулярна текущей линии
        # Условие перпендикулярности: (point - line_point) · line_dir = 0
        
        # Для каждой точки на объекте находим ближайшую точку на текущей линии
        # и проверяем перпендикулярность
        
        # Пробуем несколько точек на объекте и находим ту, которая дает перпендикуляр
        best_point = None
        best_angle_diff = float('inf')
        
        # Проверяем конечные точки объекта
        for test_point in [obj_start, obj_end]:
            # Вектор от точки объекта к ближайшей точке на линии
            # Ближайшая точка на линии: проекция test_point на линию
            t_line = ((test_point.x() - line_start.x()) * line_dx + 
                     (test_point.y() - line_start.y()) * line_dy) / line_len_sq
            t_line = max(0, min(1, t_line))  # Ограничиваем отрезком
            
            closest_on_line = QPointF(
                line_start.x() + t_line * line_dx,
                line_start.y() + t_line * line_dy
            )
            
            # Вектор от closest_on_line к test_point
            perp_dx = test_point.x() - closest_on_line.x()
            perp_dy = test_point.y() - closest_on_line.y()
            
            # Проверяем перпендикулярность (скалярное произведение должно быть близко к 0)
            dot_product = perp_dx * line_dx + perp_dy * line_dy
            angle_diff = abs(dot_product)
            
            if angle_diff < best_angle_diff:
                best_angle_diff = angle_diff
                best_point = test_point
        
        # Также проверяем точку на объекте, которая точно перпендикулярна
        # Решаем систему: точка на объекте + перпендикулярность
        # (obj_start + t*obj_dir - line_start - s*line_dir) · line_dir = 0
        
        # Упрощенный подход: находим точку на объекте, проекция которой на линию
        # дает минимальное расстояние
        
        # Пробуем точку на объекте, которая ближе всего к перпендикуляру
        # Используем аналитическое решение
        denom = line_dx * obj_dy - line_dy * obj_dx
        if abs(denom) > 1e-10:
            # Находим параметр t для объекта
            t = ((line_start.x() - obj_start.x()) * line_dy - 
                 (line_start.y() - obj_start.y()) * line_dx) / denom
            
            # Ограничиваем t отрезком [0, 1]
            t = max(0, min(1, t))
            
            perp_point = QPointF(
                obj_start.x() + t * obj_dx,
                obj_start.y() + t * obj_dy
            )
            
            # Проверяем, что это действительно перпендикуляр
            # Находим ближайшую точку на линии
            t_line = ((perp_point.x() - line_start.x()) * line_dx + 
                     (perp_point.y() - line_start.y()) * line_dy) / line_len_sq
            t_line = max(0, min(1, t_line))
            
            closest_on_line = QPointF(
                line_start.x() + t_line * line_dx,
                line_start.y() + t_line * line_dy
            )
            
            # Вектор перпендикуляра
            perp_vec_x = perp_point.x() - closest_on_line.x()
            perp_vec_y = perp_point.y() - closest_on_line.y()
            
            # Проверяем перпендикулярность
            dot = perp_vec_x * line_dx + perp_vec_y * line_dy
            if abs(dot) < 0.1:  # Допустимая погрешность
                return perp_point
        
        # Если аналитическое решение не сработало, возвращаем лучшую найденную точку
        if best_point and best_angle_diff < 0.1:
            return best_point
        
        return None
    
    def _perpendicular_to_circle(self, line_start: QPointF, line_end: QPointF,
                                 center: QPointF, radius: float) -> Optional[QPointF]:
        """Находит точку на окружности, которая является основанием перпендикуляра от линии"""
        # Направление линии
        line_dx = line_end.x() - line_start.x()
        line_dy = line_end.y() - line_start.y()
        line_len_sq = line_dx*line_dx + line_dy*line_dy
        
        if line_len_sq < 1e-10:
            return None
        
        # Находим ближайшую точку на линии к центру окружности
        t = ((center.x() - line_start.x()) * line_dx + 
             (center.y() - line_start.y()) * line_dy) / line_len_sq
        t = max(0, min(1, t))  # Ограничиваем отрезком
        
        closest_on_line = QPointF(
            line_start.x() + t * line_dx,
            line_start.y() + t * line_dy
        )
        
        # Вектор от центра к ближайшей точке на линии
        dx = closest_on_line.x() - center.x()
        dy = closest_on_line.y() - center.y()
        dist = math.sqrt(dx*dx + dy*dy)
        
        if dist < 1e-10:
            # Центр на линии - любая точка на окружности перпендикулярна
            # Возвращаем точку в направлении перпендикуляра к линии
            perp_dx = -line_dy
            perp_dy = line_dx
            perp_len = math.sqrt(perp_dx*perp_dx + perp_dy*perp_dy)
            if perp_len > 1e-10:
                perp_point = QPointF(
                    center.x() + radius * perp_dx / perp_len,
                    center.y() + radius * perp_dy / perp_len
                )
                return perp_point
            return None
        
        # Нормализуем и умножаем на радиус
        perp_point = QPointF(
            center.x() + radius * dx / dist,
            center.y() + radius * dy / dist
        )
        
        return perp_point
    
    def _perpendicular_to_arc(self, line_start: QPointF, line_end: QPointF,
                              arc: Arc) -> Optional[QPointF]:
        """Находит точку на дуге, которая является основанием перпендикуляра"""
        # Используем метод для эллипса
        return self._perpendicular_to_ellipse(line_start, line_end, arc)
    
    def _perpendicular_to_ellipse(self, line_start: QPointF, line_end: QPointF,
                                  ellipse) -> Optional[QPointF]:
        """Находит точку на эллипсе, которая является основанием перпендикуляра от линии"""
        # Направление линии
        line_dx = line_end.x() - line_start.x()
        line_dy = line_end.y() - line_start.y()
        line_len_sq = line_dx*line_dx + line_dy*line_dy
        
        if line_len_sq < 1e-10:
            return None
        
        # Находим ближайшую точку на линии к центру эллипса
        t_line = ((ellipse.center.x() - line_start.x()) * line_dx + 
                  (ellipse.center.y() - line_start.y()) * line_dy) / line_len_sq
        t_line = max(0, min(1, t_line))  # Ограничиваем отрезком
        
        closest_on_line = QPointF(
            line_start.x() + t_line * line_dx,
            line_start.y() + t_line * line_dy
        )
        
        # Переводим closest_on_line в локальные координаты эллипса
        x = closest_on_line.x() - ellipse.center.x()
        y = closest_on_line.y() - ellipse.center.y()
        
        # Применяем обратный поворот
        if abs(ellipse.rotation_angle) > 1e-6:
            cos_r = math.cos(-ellipse.rotation_angle)
            sin_r = math.sin(-ellipse.rotation_angle)
            x_rot = x * cos_r - y * sin_r
            y_rot = x * sin_r + y * cos_r
        else:
            x_rot, y_rot = x, y
        
        # Нормализуем к единичному эллипсу
        if ellipse.radius_x < 1e-6 or ellipse.radius_y < 1e-6:
            return None
        
        x_norm = x_rot / ellipse.radius_x
        y_norm = y_rot / ellipse.radius_y
        
        # Находим ближайшую точку на единичной окружности
        dist = math.sqrt(x_norm*x_norm + y_norm*y_norm)
        if dist < 1e-10:
            return None
        
        x_unit = x_norm / dist
        y_unit = y_norm / dist
        
        # Обратное преобразование
        x_local = x_unit * ellipse.radius_x
        y_local = y_unit * ellipse.radius_y
        
        # Применяем поворот
        if abs(ellipse.rotation_angle) > 1e-6:
            cos_r = math.cos(ellipse.rotation_angle)
            sin_r = math.sin(ellipse.rotation_angle)
            x_world = x_local * cos_r - y_local * sin_r
            y_world = x_local * sin_r + y_local * cos_r
        else:
            x_world, y_world = x_local, y_local
        
        perp_point = QPointF(
            ellipse.center.x() + x_world,
            ellipse.center.y() + y_world
        )
        
        # Для дуги проверяем, что точка в диапазоне
        if isinstance(ellipse, Arc):
            if not self._point_on_arc(perp_point, ellipse):
                return None
        
        return perp_point
    
    def _tangent_to_circle(self, point: QPointF, center: QPointF, 
                          radius: float) -> List[QPointF]:
        """Находит точки касания от точки к окружности"""
        tangents = []
        
        # Расстояние от точки до центра
        dx = center.x() - point.x()
        dy = center.y() - point.y()
        dist_sq = dx*dx + dy*dy
        
        if dist_sq < radius*radius - 1e-6:
            return tangents  # Точка внутри окружности
        
        if dist_sq < 1e-10:
            return tangents  # Точка совпадает с центром
        
        # Расстояние от точки до центра
        dist = math.sqrt(dist_sq)
        
        # Угол от точки к центру
        angle_to_center = math.atan2(dy, dx)
        
        # Угол между линией центр-точка и касательной
        if dist < radius + 1e-6:
            # Точка на окружности - одна касательная
            tangents.append(QPointF(point.x(), point.y()))
        else:
            # Две касательные
            sin_alpha = radius / dist
            alpha = math.asin(sin_alpha)
            
            for sign in [-1, 1]:
                angle = angle_to_center + sign * alpha
                tangent_point = QPointF(
                    center.x() + radius * math.cos(angle),
                    center.y() + radius * math.sin(angle)
                )
                tangents.append(tangent_point)
        
        return tangents
    
    def _tangent_to_arc(self, point: QPointF, arc: Arc) -> List[QPointF]:
        """Находит точки касания от точки к дуге"""
        tangents = []
        
        # Используем метод для эллипса, затем фильтруем по диапазону дуги
        ellipse_tangents = self._tangent_to_ellipse(point, arc)
        
        for tangent in ellipse_tangents:
            if self._point_on_arc(tangent, arc):
                tangents.append(tangent)
        
        return tangents
    
    def _tangent_to_ellipse(self, point: QPointF, ellipse) -> List[QPointF]:
        """Находит точки касания от точки к эллипсу"""
        tangents = []
        
        # Переводим точку в локальные координаты
        x = point.x() - ellipse.center.x()
        y = point.y() - ellipse.center.y()
        
        # Применяем обратный поворот
        if abs(ellipse.rotation_angle) > 1e-6:
            cos_r = math.cos(-ellipse.rotation_angle)
            sin_r = math.sin(-ellipse.rotation_angle)
            x_rot = x * cos_r - y * sin_r
            y_rot = x * sin_r + y * cos_r
        else:
            x_rot, y_rot = x, y
        
        # Нормализуем к единичной окружности
        if ellipse.radius_x < 1e-6 or ellipse.radius_y < 1e-6:
            return tangents
        
        x_norm = x_rot / ellipse.radius_x
        y_norm = y_rot / ellipse.radius_y
        
        # Находим касательные к единичной окружности
        dist_sq = x_norm*x_norm + y_norm*y_norm
        
        if dist_sq < 1.0 - 1e-6:
            return tangents  # Точка внутри эллипса
        
        if dist_sq < 1e-10:
            return tangents  # Точка в центре
        
        # Для эллипса используем приближенный метод
        # Находим ближайшую точку на эллипсе
        dist = math.sqrt(dist_sq)
        if dist < 1.0 + 1e-6:
            # Точка на эллипсе - одна касательная
            x_unit = x_norm / dist
            y_unit = y_norm / dist
        else:
            # Две касательные (упрощенный метод)
            # Используем итеративный поиск или аналитическое решение
            # Для простоты используем метод ближайшей точки
            x_unit = x_norm / dist
            y_unit = y_norm / dist
        
        # Обратное преобразование
        x_local = x_unit * ellipse.radius_x
        y_local = y_unit * ellipse.radius_y
        
        # Применяем поворот
        if abs(ellipse.rotation_angle) > 1e-6:
            cos_r = math.cos(ellipse.rotation_angle)
            sin_r = math.sin(ellipse.rotation_angle)
            x_world = x_local * cos_r - y_local * sin_r
            y_world = x_local * sin_r + y_local * cos_r
        else:
            x_world, y_world = x_local, y_local
        
        tangent_point = QPointF(
            ellipse.center.x() + x_world,
            ellipse.center.y() + y_world
        )
        tangents.append(tangent_point)
        
        return tangents

