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
                 style=None, color=None, width=None, rotation_angle: float = 0.0,
                 start_point: QPointF = None, end_point: QPointF = None, vertex_point: QPointF = None):
        super().__init__()
        self.center = QPointF(center) if not isinstance(center, QPointF) else center
        self.radius_x = radius_x  # горизонтальный радиус эллипса (вдоль хорды)
        self.radius_y = radius_y  # вертикальный радиус эллипса (перпендикулярно хорде)
        self.start_angle = start_angle  # в градусах
        self.end_angle = end_angle  # в градусах
        self.rotation_angle = rotation_angle  # угол поворота эллипса (в радианах)
        # Для обратной совместимости
        self.radius = max(radius_x, radius_y) if radius_x > 0 and radius_y > 0 else 0
        # Исходные точки для привязки (если дуга создана тремя точками)
        self._start_point = QPointF(start_point) if start_point is not None else None
        self._end_point = QPointF(end_point) if end_point is not None else None
        self._vertex_point = QPointF(vertex_point) if vertex_point is not None else None
        # Исходная третья точка (используется для определения правильной стороны дуги)
        self._original_vertex_point = None
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
        
        # Нормализуем углы в диапазон [0, 360)
        start_angle = self.start_angle % 360
        end_angle = self.end_angle % 360
        
        # Вычисляем реальный угол дуги
        if start_angle <= end_angle:
            angle_span = end_angle - start_angle
        else:
            # Дуга пересекает 0°
            angle_span = (360 - start_angle) + end_angle
        
        # Используем больше точек для точного вычисления bounding box
        # Минимум 128 точек на полный круг (360°), пропорционально для дуги
        # Это гарантирует, что мы не пропустим точки экстремумов даже для малых дуг
        # Для малых дуг используем минимум 32 точки независимо от угла
        if angle_span < 10:
            num_points = 32
        else:
            num_points = max(128, int(angle_span * 128 / 360) + 1)
        
        def get_point_at_angle(angle_deg):
            """Вычисляет точку на дуге для заданного угла в градусах"""
            rad = math.radians(angle_deg)
            local_x = self.radius_x * math.cos(rad)
            local_y = self.radius_y * math.sin(rad)
            
            # Применяем поворот, если он есть
            if abs(self.rotation_angle) > 1e-6:
                cos_r = math.cos(self.rotation_angle)
                sin_r = math.sin(self.rotation_angle)
                rotated_x = local_x * cos_r - local_y * sin_r
                rotated_y = local_x * sin_r + local_y * cos_r
            else:
                rotated_x = local_x
                rotated_y = local_y
            
            # Переводим в мировые координаты
            x = self.center.x() + rotated_x
            y = self.center.y() + rotated_y
            return QPointF(x, y)
        
        points = []
        
        # Добавляем начальную и конечную точки
        points.append(get_point_at_angle(start_angle))
        points.append(get_point_at_angle(end_angle))
        
        # Добавляем равномерно распределенные точки по дуге
        for i in range(1, num_points):
            # Вычисляем угол для текущей точки
            if start_angle <= end_angle:
                # Обычная дуга (не пересекает 0°)
                angle = start_angle + angle_span * i / num_points
            else:
                # Дуга пересекает 0° (например, от 350° до 10°)
                # Первая часть: от start_angle до 360°
                first_part_span = 360 - start_angle
                # Вторая часть: от 0° до end_angle
                second_part_span = end_angle
                
                # Определяем, в какой части дуги мы находимся
                progress = i / num_points
                if progress * angle_span <= first_part_span:
                    # Первая часть: от start_angle до 360°
                    local_progress = (progress * angle_span) / first_part_span
                    angle = start_angle + first_part_span * local_progress
                else:
                    # Вторая часть: от 0° до end_angle
                    remaining_span = progress * angle_span - first_part_span
                    local_progress = remaining_span / second_part_span
                    angle = local_progress * end_angle
            
            points.append(get_point_at_angle(angle))
        
        # Добавляем критические углы (0°, 90°, 180°, 270°), если они попадают в диапазон дуги
        # Эти углы соответствуют точкам экстремумов для эллипса без поворота
        # и важны для точного вычисления bounding box
        critical_angles = [0, 90, 180, 270]
        for crit_angle in critical_angles:
            # Проверяем, попадает ли критический угол в диапазон дуги
            in_range = False
            if start_angle <= end_angle:
                in_range = start_angle <= crit_angle <= end_angle
            else:
                in_range = crit_angle >= start_angle or crit_angle <= end_angle
            
            if in_range:
                points.append(get_point_at_angle(crit_angle))
        
        # Добавляем центр (может быть внутри или снаружи дуги)
        points.append(self.center)
        
        if not points:
            return QRectF()
        
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
    
    def get_point_at_angle(self, angle_deg: float) -> QPointF:
        """Вычисляет точку на дуге для заданного угла в градусах (параметрический угол)"""
        import math
        rad = math.radians(angle_deg)
        local_x = self.radius_x * math.cos(rad)
        local_y = self.radius_y * math.sin(rad)
        
        # Применяем поворот, если он есть
        if abs(self.rotation_angle) > 1e-6:
            cos_r = math.cos(self.rotation_angle)
            sin_r = math.sin(self.rotation_angle)
            rotated_x = local_x * cos_r - local_y * sin_r
            rotated_y = local_x * sin_r + local_y * cos_r
        else:
            rotated_x = local_x
            rotated_y = local_y
        
        # Переводим в мировые координаты
        x = self.center.x() + rotated_x
        y = self.center.y() + rotated_y
        return QPointF(x, y)
    
    def get_vertex_point(self) -> QPointF:
        """Вычисляет вершину дуги - точку на дуге, максимально удаленную от хорды
        Учитывает сторону дуги относительно хорды (определяется по исходной третьей точке)"""
        import math
        
        # Получаем начальную и конечную точки дуги
        start_point = self.get_point_at_angle(self.start_angle)
        end_point = self.get_point_at_angle(self.end_angle)
        
        # Находим вектор хорды для вычисления расстояния до прямой
        chord_vec = QPointF(end_point.x() - start_point.x(), end_point.y() - start_point.y())
        chord_length = math.sqrt(chord_vec.x()**2 + chord_vec.y()**2)
        
        if chord_length < 1e-6:
            # Хорда вырождена, возвращаем середину дуги
            start_angle = self.start_angle % 360
            end_angle = self.end_angle % 360
            if start_angle <= end_angle:
                mid_angle = (start_angle + end_angle) / 2.0
            else:
                span = (360 - start_angle) + end_angle
                mid_angle = (start_angle + span / 2.0) % 360
            return self.get_point_at_angle(mid_angle)
        
        # Вычисляем нормаль к хорде для определения стороны
        normal = QPointF(-chord_vec.y(), chord_vec.x())
        reference_side = None
        signed_dist_ref = None
        
        # Используем исходную третью точку, если она доступна
        reference_point = None
        if hasattr(self, '_original_vertex_point') and self._original_vertex_point is not None:
            reference_point = self._original_vertex_point
        
        if reference_point is not None:
            # Вектор от начала хорды до референсной точки
            to_ref = QPointF(
                reference_point.x() - start_point.x(),
                reference_point.y() - start_point.y()
            )
            # Скалярное произведение с нормалью дает знаковое расстояние
            signed_dist_ref = normal.x() * to_ref.x() + normal.y() * to_ref.y()
            # Для дуги "вверх" третья точка должна быть выше хорды
            # Используем знак signed_dist_ref для определения правильной стороны
            # Если signed_dist_ref > 0, точка выше хорды - используем эту сторону
            reference_side = 1 if signed_dist_ref > 0 else -1
        else:
            # Fallback: определяем сторону по углам дуги
            # Для дуги, созданной через три точки, используем логику определения направления
            # Находим точку в середине дуги для определения стороны
            start_angle_norm = self.start_angle % 360
            end_angle_norm = self.end_angle % 360
            
            # Вычисляем span угла
            if start_angle_norm <= end_angle_norm:
                span = end_angle_norm - start_angle_norm
                mid_angle = (start_angle_norm + end_angle_norm) / 2.0
            else:
                span = (360 - start_angle_norm) + end_angle_norm
                mid_angle = (start_angle_norm + span / 2.0) % 360
            
            # Используем середину дуги для определения стороны
            mid_point = self.get_point_at_angle(mid_angle)
            to_mid = QPointF(
                mid_point.x() - start_point.x(),
                mid_point.y() - start_point.y()
            )
            signed_dist_mid = normal.x() * to_mid.x() + normal.y() * to_mid.y()
            
            # Проверяем, проходит ли дуга через верхнюю часть (270° в параметрических координатах)
            # В параметрических координатах эллипса: 0° = право, 90° = низ, 180° = лево, 270° = верх
            # Если дуга проходит через 270° (верх), то вершина должна быть выше хорды
            passes_through_top = False
            if start_angle_norm <= end_angle_norm:
                # Обычная дуга
                passes_through_top = start_angle_norm <= 270 <= end_angle_norm
            else:
                # Дуга пересекает 0°
                passes_through_top = start_angle_norm <= 270 or end_angle_norm >= 270
            
            # Определяем сторону: используем сторону середины дуги
            # Это гарантирует, что вершина будет на той же стороне, что и середина дуги
            reference_side = 1 if signed_dist_mid > 0 else -1
        
        # Нормализуем углы
        start_angle = self.start_angle % 360
        end_angle = self.end_angle % 360
        
        # Сначала ищем точку с максимальным расстоянием БЕЗ фильтрации по стороне
        max_dist_no_filter = -1
        vertex_angle_no_filter = start_angle
        
        for angle in range(0, 360, 2):  # Используем шаг 2 градуса для большей точности
            # Проверяем, попадает ли угол в диапазон дуги
            if start_angle <= end_angle:
                in_range = start_angle <= angle <= end_angle
            else:
                in_range = angle >= start_angle or angle <= end_angle
            
            if in_range:
                test_point = self.get_point_at_angle(angle)
                to_point = QPointF(
                    test_point.x() - start_point.x(),
                    test_point.y() - start_point.y()
                )
                # Проекция на хорду
                dot = to_point.x() * chord_vec.x() + to_point.y() * chord_vec.y()
                t = dot / (chord_length * chord_length)
                t = max(0, min(1, t))
                # Точка на хорде, ближайшая к test_point
                closest_on_chord = QPointF(
                    start_point.x() + t * chord_vec.x(),
                    start_point.y() + t * chord_vec.y()
                )
                # Вектор от ближайшей точки на хорде до test_point
                to_test = QPointF(
                    test_point.x() - closest_on_chord.x(),
                    test_point.y() - closest_on_chord.y()
                )
                # Расстояние от test_point до хорды
                dist = math.sqrt(to_test.x()**2 + to_test.y()**2)
                
                if dist > max_dist_no_filter:
                    max_dist_no_filter = dist
                    vertex_angle_no_filter = angle
        
        # Если есть референсная точка или определена сторона, ищем точку с максимальным расстоянием на правильной стороне
        if reference_point is not None or reference_side is not None:
            max_dist_correct_side = -1
            vertex_angle_correct_side = start_angle
            
            # Ищем точку с максимальным расстоянием на правильной стороне
            for angle in range(0, 360, 2):
                if start_angle <= end_angle:
                    in_range = start_angle <= angle <= end_angle
                else:
                    in_range = angle >= start_angle or angle <= end_angle
                
                if in_range:
                    test_point = self.get_point_at_angle(angle)
                    to_point = QPointF(
                        test_point.x() - start_point.x(),
                        test_point.y() - start_point.y()
                    )
                    signed_dist = normal.x() * to_point.x() + normal.y() * to_point.y()
                    side = 1 if signed_dist > 0 else -1
                    
                    # Проверяем, что точка на правильной стороне
                    if reference_side is not None and reference_side * side > 0:
                        dot = to_point.x() * chord_vec.x() + to_point.y() * chord_vec.y()
                        t = dot / (chord_length * chord_length)
                        t = max(0, min(1, t))
                        closest_on_chord = QPointF(
                            start_point.x() + t * chord_vec.x(),
                            start_point.y() + t * chord_vec.y()
                        )
                        to_test = QPointF(
                            test_point.x() - closest_on_chord.x(),
                            test_point.y() - closest_on_chord.y()
                        )
                        dist = math.sqrt(to_test.x()**2 + to_test.y()**2)
                        
                        if dist > max_dist_correct_side:
                            max_dist_correct_side = dist
                            vertex_angle_correct_side = angle
            
            # Если нашли точку на правильной стороне, используем её
            if max_dist_correct_side > 0:
                vertex_angle = vertex_angle_correct_side
            else:
                # Если не нашли точку на правильной стороне, это означает, что все точки на дуге
                # находятся на неправильной стороне относительно reference_point
                # Для дуги "вверх" (reference_point выше хорды) нужно найти вершину выше хорды
                # Расширяем поиск на весь эллипс, чтобы найти точку на правильной стороне
                max_dist_extended = -1
                vertex_angle_extended = start_angle
                
                # Ищем точку на правильной стороне на всем эллипсе (не только в диапазоне дуги)
                for angle in range(0, 360, 2):
                    test_point = self.get_point_at_angle(angle)
                    to_point = QPointF(
                        test_point.x() - start_point.x(),
                        test_point.y() - start_point.y()
                    )
                    signed_dist = normal.x() * to_point.x() + normal.y() * to_point.y()
                    side = 1 if signed_dist > 0 else -1
                    
                    # Ищем точку на правильной стороне (той же, что и reference_point)
                    if reference_side is not None and reference_side * side > 0:
                        dot = to_point.x() * chord_vec.x() + to_point.y() * chord_vec.y()
                        t = dot / (chord_length * chord_length)
                        t = max(0, min(1, t))
                        closest_on_chord = QPointF(
                            start_point.x() + t * chord_vec.x(),
                            start_point.y() + t * chord_vec.y()
                        )
                        to_test = QPointF(
                            test_point.x() - closest_on_chord.x(),
                            test_point.y() - closest_on_chord.y()
                        )
                        dist = math.sqrt(to_test.x()**2 + to_test.y()**2)
                        
                        if dist > max_dist_extended:
                            max_dist_extended = dist
                            vertex_angle_extended = angle
                
                # Используем найденную точку на правильной стороне
                if max_dist_extended > 0:
                    vertex_angle = vertex_angle_extended
                else:
                    # Если не нашли точку на правильной стороне, используем точку с максимальным расстоянием
                    vertex_angle = vertex_angle_no_filter
        elif reference_side is not None:
            # Есть определенная сторона, но нет референсной точки - ищем точку на правильной стороне
            max_dist_correct_side = -1
            vertex_angle_correct_side = start_angle
            
            # Ищем точку с максимальным расстоянием на правильной стороне
            for angle in range(0, 360, 2):
                if start_angle <= end_angle:
                    in_range = start_angle <= angle <= end_angle
                else:
                    in_range = angle >= start_angle or angle <= end_angle
                
                if in_range:
                    test_point = self.get_point_at_angle(angle)
                    to_point = QPointF(
                        test_point.x() - start_point.x(),
                        test_point.y() - start_point.y()
                    )
                    signed_dist = normal.x() * to_point.x() + normal.y() * to_point.y()
                    side = 1 if signed_dist > 0 else -1
                    
                    # Проверяем, что точка на правильной стороне
                    if reference_side * side > 0:
                        dot = to_point.x() * chord_vec.x() + to_point.y() * chord_vec.y()
                        t = dot / (chord_length * chord_length)
                        t = max(0, min(1, t))
                        closest_on_chord = QPointF(
                            start_point.x() + t * chord_vec.x(),
                            start_point.y() + t * chord_vec.y()
                        )
                        to_test = QPointF(
                            test_point.x() - closest_on_chord.x(),
                            test_point.y() - closest_on_chord.y()
                        )
                        dist = math.sqrt(to_test.x()**2 + to_test.y()**2)
                        
                        if dist > max_dist_correct_side:
                            max_dist_correct_side = dist
                            vertex_angle_correct_side = angle
            
            # Если нашли точку на правильной стороне, используем её
            if max_dist_correct_side > 0:
                vertex_angle = vertex_angle_correct_side
            else:
                # Если не нашли точку на правильной стороне, используем точку с максимальным расстоянием
                vertex_angle = vertex_angle_no_filter
        else:
            # Нет референсной точки и не определена сторона - используем точку с максимальным расстоянием
            vertex_angle = vertex_angle_no_filter
        
        # Уточняем поиск вокруг найденной вершины с шагом 0.5 градуса
        if max_dist_no_filter > 0:
            best_angle = vertex_angle
            # Вычисляем расстояние для начальной вершины
            test_point_init = self.get_point_at_angle(vertex_angle)
            to_point_init = QPointF(
                test_point_init.x() - start_point.x(),
                test_point_init.y() - start_point.y()
            )
            dot_init = to_point_init.x() * chord_vec.x() + to_point_init.y() * chord_vec.y()
            t_init = dot_init / (chord_length * chord_length)
            t_init = max(0, min(1, t_init))
            closest_on_chord_init = QPointF(
                start_point.x() + t_init * chord_vec.x(),
                start_point.y() + t_init * chord_vec.y()
            )
            to_test_init = QPointF(
                test_point_init.x() - closest_on_chord_init.x(),
                test_point_init.y() - closest_on_chord_init.y()
            )
            best_dist = math.sqrt(to_test_init.x()**2 + to_test_init.y()**2)
            
            for offset in range(-4, 5, 1):
                angle = (vertex_angle + offset * 0.5) % 360
                # Проверяем, попадает ли угол в диапазон дуги
                if start_angle <= end_angle:
                    in_range = start_angle <= angle <= end_angle
                else:
                    in_range = angle >= start_angle or angle <= end_angle
                
                if in_range:
                    test_point = self.get_point_at_angle(angle)
                    to_point = QPointF(
                        test_point.x() - start_point.x(),
                        test_point.y() - start_point.y()
                    )
                    
                            # Если есть референсная точка или определена сторона, проверяем сторону ПЕРЕД вычислением расстояния
                    if reference_side is not None:
                        signed_dist = normal.x() * to_point.x() + normal.y() * to_point.y()
                        side = 1 if signed_dist > 0 else -1
                        # Пропускаем точки на неправильной стороне
                        if reference_side * side <= 0:
                            continue
                    
                    dot = to_point.x() * chord_vec.x() + to_point.y() * chord_vec.y()
                    t = dot / (chord_length * chord_length)
                    t = max(0, min(1, t))
                    closest_on_chord = QPointF(
                        start_point.x() + t * chord_vec.x(),
                        start_point.y() + t * chord_vec.y()
                    )
                    to_test = QPointF(
                        test_point.x() - closest_on_chord.x(),
                        test_point.y() - closest_on_chord.y()
                    )
                    dist = math.sqrt(to_test.x()**2 + to_test.y()**2)
                    
                    if dist > best_dist:
                        best_dist = dist
                        best_angle = angle
            
            vertex_angle = best_angle
        
        # Если вершина все еще не найдена, используем середину углового диапазона
        if max_dist_no_filter <= 0:
            if start_angle <= end_angle:
                vertex_angle = (start_angle + end_angle) / 2.0
            else:
                span = (360 - start_angle) + end_angle
                vertex_angle = (start_angle + span / 2.0) % 360
        
        return self.get_point_at_angle(vertex_angle)
    
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
    
    def __init__(self, top_left: QPointF, bottom_right: QPointF, style=None, color=None, width=None, 
                 fillet_radius: float = 0.0):
        super().__init__()
        self.top_left = QPointF(top_left) if not isinstance(top_left, QPointF) else top_left
        self.bottom_right = QPointF(bottom_right) if not isinstance(bottom_right, QPointF) else bottom_right
        self.fillet_radius = fillet_radius  # Радиус скругления углов (0 = без скругления)
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


class Polygon(GeometricObject, Drawable):
    """Класс для представления многоугольника"""
    
    def __init__(self, center: QPointF, radius: float, num_vertices: int, style=None, color=None, width=None):
        super().__init__()
        self.center = QPointF(center) if not isinstance(center, QPointF) else center
        self.radius = radius
        self.num_vertices = num_vertices
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
    
    def get_vertices(self):
        """Возвращает список вершин многоугольника"""
        import math
        vertices = []
        angle_step = 2 * math.pi / self.num_vertices
        for i in range(self.num_vertices):
            angle = i * angle_step - math.pi / 2  # Начинаем с верхней точки
            x = self.center.x() + self.radius * math.cos(angle)
            y = self.center.y() + self.radius * math.sin(angle)
            vertices.append(QPointF(x, y))
        return vertices
    
    def get_bounding_box(self) -> QRectF:
        """Возвращает ограничивающий прямоугольник многоугольника"""
        vertices = self.get_vertices()
        if not vertices:
            return QRectF()
        min_x = min(v.x() for v in vertices)
        max_x = max(v.x() for v in vertices)
        min_y = min(v.y() for v in vertices)
        max_y = max(v.y() for v in vertices)
        return QRectF(min_x, min_y, max_x - min_x, max_y - min_y)
    
    def contains_point(self, point: QPointF, tolerance: float = 5.0) -> bool:
        """Проверяет, содержит ли многоугольник точку (проверка на границе)"""
        import math
        vertices = self.get_vertices()
        if len(vertices) < 3:
            return False
        
        # Проверяем расстояние до каждой стороны многоугольника
        for i in range(len(vertices)):
            p1 = vertices[i]
            p2 = vertices[(i + 1) % len(vertices)]
            
            # Вектор стороны
            dx = p2.x() - p1.x()
            dy = p2.y() - p1.y()
            length = math.sqrt(dx*dx + dy*dy)
            
            if length < 1e-6:
                continue
            
            # Вектор от p1 до точки
            to_point_x = point.x() - p1.x()
            to_point_y = point.y() - p1.y()
            
            # Проекция на сторону
            t = (to_point_x * dx + to_point_y * dy) / (length * length)
            t = max(0, min(1, t))
            
            # Ближайшая точка на стороне
            closest_x = p1.x() + t * dx
            closest_y = p1.y() + t * dy
            
            # Расстояние до стороны
            dist = math.sqrt((point.x() - closest_x)**2 + (point.y() - closest_y)**2)
            
            if dist <= tolerance:
                return True
        
        return False
    
    def intersects_rect(self, rect: QRectF) -> bool:
        """Проверяет, пересекается ли многоугольник с прямоугольником"""
        bbox = self.get_bounding_box()
        return rect.intersects(bbox)
    
    def draw(self, painter, scale_factor: float = 1.0):
        """Отрисовывает многоугольник"""
        from core.renderer import PrimitiveRenderer
        PrimitiveRenderer.draw_polygon(painter, self, scale_factor, self.selected)

