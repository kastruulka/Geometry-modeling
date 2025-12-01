"""
Класс для управления сценой (объектами на сцене)
"""
from typing import List, Optional
from PySide6.QtCore import QPointF

from core.geometry import GeometricObject
from widgets.line_segment import LineSegment


class Scene:
    """Управляет объектами на сцене"""
    
    def __init__(self):
        self._objects: List[GeometricObject] = []
        self._current_object: Optional[GeometricObject] = None
        self._is_drawing = False
        self._drawing_type: Optional[str] = None  # 'line', 'circle', 'arc', 'rectangle', 'ellipse'
        # Для дуги: отслеживание этапов создания
        self._arc_creation_method: Optional[str] = None  # 'three_points', 'center_angles'
        self._arc_start_point: Optional[QPointF] = None
        self._arc_end_point: Optional[QPointF] = None
        self._temp_arc_end_point: Optional[QPointF] = None  # Временная точка для предпросмотра
        self._arc_center: Optional[QPointF] = None  # Для метода центр+углы
        self._arc_radius: float = 0.0  # Для метода центр+углы
        # Для эллипса: отслеживание этапов создания (3 точки)
        self._ellipse_start_point: Optional[QPointF] = None
        self._ellipse_end_point: Optional[QPointF] = None
        self._temp_ellipse_end_point: Optional[QPointF] = None  # Временная точка для предпросмотра
        # Для окружности: отслеживание этапов создания
        self._circle_creation_method: Optional[str] = None  # 'center_radius', 'center_diameter', 'two_points', 'three_points'
        self._circle_point1: Optional[QPointF] = None
        self._circle_point2: Optional[QPointF] = None
        self._circle_point3: Optional[QPointF] = None
        # Для прямоугольника: отслеживание этапов создания
        self._rectangle_creation_method: Optional[str] = None  # 'two_points', 'point_size', 'center_size', 'with_fillets'
        self._rectangle_point1: Optional[QPointF] = None
        self._rectangle_width: float = 0.0
        self._rectangle_height: float = 0.0
        self._rectangle_fillet_radius: float = 0.0  # Радиус скругления/фаски
    
    def add_object(self, obj: GeometricObject):
        """Добавляет объект на сцену"""
        if obj not in self._objects:
            self._objects.append(obj)
    
    def remove_object(self, obj: GeometricObject):
        """Удаляет объект со сцены"""
        if obj in self._objects:
            self._objects.remove(obj)
    
    def clear(self):
        """Очищает сцену"""
        self._objects.clear()
        self._current_object = None
        self._is_drawing = False
        self._drawing_type = None
        self._arc_start_point = None
        self._arc_end_point = None
    
    def set_rectangle_size(self, width: float, height: float):
        """Устанавливает размеры прямоугольника для методов point_size и center_size"""
        if width <= 0 or height <= 0:
            return  # Не устанавливаем нулевые или отрицательные размеры
        
        self._rectangle_width = width
        self._rectangle_height = height
        # Обновляем текущий объект, если он существует
        if self._current_object and self._drawing_type == 'rectangle':
            from widgets.primitives import Rectangle
            if isinstance(self._current_object, Rectangle):
                method = self._rectangle_creation_method or 'two_points'
                if method == 'point_size' and self._rectangle_point1:
                    # Для метода point_size: top_left = начальная точка, bottom_right = точка + размеры
                    end_point = QPointF(
                        self._rectangle_point1.x() + width,
                        self._rectangle_point1.y() + height
                    )
                    self._current_object.top_left = QPointF(self._rectangle_point1)
                    self._current_object.bottom_right = end_point
                elif method == 'center_size' and self._rectangle_point1:
                    # Для метода center_size: вычисляем углы от центра
                    half_width = width / 2.0
                    half_height = height / 2.0
                    top_left = QPointF(
                        self._rectangle_point1.x() - half_width,
                        self._rectangle_point1.y() - half_height
                    )
                    bottom_right = QPointF(
                        self._rectangle_point1.x() + half_width,
                        self._rectangle_point1.y() + half_height
                    )
                    self._current_object.top_left = top_left
                    self._current_object.bottom_right = bottom_right
    
    def set_rectangle_fillet_radius(self, radius: float):
        """Устанавливает радиус скругления для метода with_fillets"""
        self._rectangle_fillet_radius = radius
        # Обновляем текущий объект, если он существует
        if self._current_object and self._drawing_type == 'rectangle':
            from widgets.primitives import Rectangle
            if isinstance(self._current_object, Rectangle):
                if hasattr(self._current_object, 'fillet_radius'):
                    self._current_object.fillet_radius = radius
    
    def get_objects(self) -> List[GeometricObject]:
        """Возвращает все объекты на сцене"""
        return self._objects.copy()
    
    def get_lines(self) -> List[LineSegment]:
        """Возвращает все отрезки на сцене"""
        return [obj for obj in self._objects if isinstance(obj, LineSegment)]
    
    def start_drawing(self, start_point: QPointF, drawing_type: str = 'line', 
                     style=None, color=None, width=None, **kwargs):
        """Начинает рисование нового объекта"""
        self._drawing_type = drawing_type
        
        if drawing_type == 'line':
            from widgets.line_segment import LineSegment
            self._current_object = LineSegment(start_point, start_point, style=style, 
                                              color=color, width=width)
        elif drawing_type == 'circle':
            from widgets.primitives import Circle
            # Получаем метод создания из kwargs или используем по умолчанию
            creation_method = kwargs.get('circle_method', 'center_radius')
            self._circle_creation_method = creation_method
            
            if creation_method == 'center_radius' or creation_method == 'center_diameter':
                # Центр и радиус/диаметр - центр уже задан
                self._current_object = Circle(start_point, 0, style=style, color=color, width=width)
                self._circle_point1 = start_point
            elif creation_method == 'two_points':
                # Две точки - первая точка задана
                self._circle_point1 = start_point
                self._current_object = Circle(start_point, 0, style=style, color=color, width=width)
            elif creation_method == 'three_points':
                # Три точки - первая точка задана
                self._circle_point1 = start_point
                self._circle_point2 = None
                self._circle_point3 = None
                self._current_object = Circle(start_point, 0, style=style, color=color, width=width)
            else:
                # По умолчанию - центр и радиус
                self._current_object = Circle(start_point, 0, style=style, color=color, width=width)
                self._circle_point1 = start_point
        elif drawing_type == 'arc':
            from widgets.primitives import Arc
            # Получаем метод создания из kwargs или используем по умолчанию
            creation_method = kwargs.get('arc_method', 'three_points')
            self._arc_creation_method = creation_method
            
            if creation_method == 'three_points':
                # Три точки - первый клик - начальная точка
                self._arc_start_point = start_point
                self._arc_end_point = None
                # Создаем временный объект для предпросмотра
                self._current_object = Arc(start_point, 0, 0, 0, 0, style=style, color=color, width=width, rotation_angle=0.0)
            elif creation_method == 'center_angles':
                # Центр и углы - первый клик - центр
                self._arc_center = start_point
                self._arc_radius = 0.0
                # Создаем временный объект для предпросмотра
                self._current_object = Arc(start_point, 0, 0, 0, 0, style=style, color=color, width=width, rotation_angle=0.0)
        elif drawing_type == 'rectangle':
            from widgets.primitives import Rectangle
            # Получаем метод создания из kwargs или используем по умолчанию
            creation_method = kwargs.get('rectangle_method', 'two_points')
            self._rectangle_creation_method = creation_method
            
            if creation_method == 'two_points':
                # Две противоположные точки - первая точка задана
                self._rectangle_point1 = start_point
                self._current_object = Rectangle(start_point, start_point, style=style, 
                                               color=color, width=width)
            elif creation_method == 'point_size':
                # Одна точка, ширина и высота - точка задана
                self._rectangle_point1 = start_point
                self._rectangle_width = 0.0
                self._rectangle_height = 0.0
                self._current_object = Rectangle(start_point, start_point, style=style, 
                                               color=color, width=width)
            elif creation_method == 'center_size':
                # Центр, ширина и высота - центр задан
                self._rectangle_point1 = start_point
                self._rectangle_width = 0.0
                self._rectangle_height = 0.0
                self._current_object = Rectangle(start_point, start_point, style=style, 
                                               color=color, width=width)
            elif creation_method == 'with_fillets':
                # С фасками/скруглениями - первая точка задана
                self._rectangle_point1 = start_point
                self._rectangle_fillet_radius = 0.0
                self._current_object = Rectangle(start_point, start_point, style=style, 
                                               color=color, width=width)
        elif drawing_type == 'ellipse':
            # Для эллипса первый клик - начальная точка
            self._ellipse_start_point = start_point
            self._ellipse_end_point = None
            # Создаем временный объект для предпросмотра
            from widgets.primitives import Ellipse
            self._current_object = Ellipse(start_point, 0, 0, style=style, color=color, width=width, rotation_angle=0.0)
        
        self._is_drawing = True
    
    def update_current_object(self, point: QPointF, **kwargs):
        """Обновляет текущий рисуемый объект"""
        if not self._current_object:
            return
        
        if self._drawing_type == 'line':
            if isinstance(self._current_object, LineSegment):
                self._current_object.end_point = point
        elif self._drawing_type == 'circle':
            from widgets.primitives import Circle
            if isinstance(self._current_object, Circle):
                import math
                method = self._circle_creation_method or 'center_radius'
                
                if method == 'center_radius' or method == 'center_diameter':
                    # Центр уже задан, точка определяет радиус
                    dx = point.x() - self._current_object.center.x()
                    dy = point.y() - self._current_object.center.y()
                    radius = math.sqrt(dx*dx + dy*dy)
                    if method == 'center_diameter':
                        radius = radius / 2.0  # Диаметр -> радиус
                    self._current_object.radius = radius
                elif method == 'two_points':
                    # Две точки определяют диаметр
                    if self._circle_point1:
                        dx = point.x() - self._circle_point1.x()
                        dy = point.y() - self._circle_point1.y()
                        radius = math.sqrt(dx*dx + dy*dy) / 2.0
                        center_x = (self._circle_point1.x() + point.x()) / 2.0
                        center_y = (self._circle_point1.y() + point.y()) / 2.0
                        self._current_object.center = QPointF(center_x, center_y)
                        self._current_object.radius = radius
                elif method == 'three_points':
                    # Три точки - показываем предпросмотр по двум точкам
                    if self._circle_point1 and self._circle_point2 is None:
                        # Вторая точка еще не зафиксирована, показываем предпросмотр
                        dx = point.x() - self._circle_point1.x()
                        dy = point.y() - self._circle_point1.y()
                        radius = math.sqrt(dx*dx + dy*dy) / 2.0
                        center_x = (self._circle_point1.x() + point.x()) / 2.0
                        center_y = (self._circle_point1.y() + point.y()) / 2.0
                        self._current_object.center = QPointF(center_x, center_y)
                        self._current_object.radius = radius
                    elif self._circle_point1 and self._circle_point2:
                        # Третья точка - вычисляем окружность по трем точкам
                        center, radius = self._calculate_circle_from_three_points(
                            self._circle_point1, self._circle_point2, point
                        )
                        if center and radius > 0:
                            self._current_object.center = center
                            self._current_object.radius = radius
        elif self._drawing_type == 'arc':
            from widgets.primitives import Arc
            if isinstance(self._current_object, Arc):
                import math
                method = self._arc_creation_method or 'three_points'
                
                if method == 'three_points':
                    if self._arc_end_point is None:
                        # Обновление предпросмотра второй точки (движение мыши)
                        # Показываем прямую линию от начала до текущей позиции
                        # Не фиксируем точку, только предпросмотр
                        self._current_object.center = self._arc_start_point
                        self._current_object.radius_x = 0
                        self._current_object.radius_y = 0
                        self._current_object.radius = 0
                        self._current_object.start_angle = 0
                        self._current_object.end_angle = 0
                    else:
                        # Третий этап - точка высоты (вершина)
                        # Вычисляем параметры дуги эллипса по трем точкам
                        result = self._calculate_ellipse_arc_from_three_points(
                            self._arc_start_point, self._arc_end_point, point
                        )
                        if len(result) == 6 and result[0] is not None:
                            center, radius_x, radius_y, start_angle, end_angle, rotation_angle = result
                            # Проверяем, что радиусы валидны
                            if radius_x > 0 and radius_y > 0:
                                self._current_object.center = center
                                self._current_object.radius_x = radius_x
                                self._current_object.radius_y = radius_y
                                self._current_object.radius = max(radius_x, radius_y)
                                self._current_object.start_angle = start_angle
                                self._current_object.end_angle = end_angle
                                self._current_object.rotation_angle = rotation_angle
                            else:
                                # Если радиусы невалидны, используем минимальные значения
                                self._current_object.center = center
                                self._current_object.radius_x = max(radius_x, 1.0)
                                self._current_object.radius_y = max(radius_y, 1.0)
                                self._current_object.radius = max(self._current_object.radius_x, self._current_object.radius_y)
                                self._current_object.start_angle = start_angle
                                self._current_object.end_angle = end_angle
                                self._current_object.rotation_angle = rotation_angle
                elif method == 'center_angles':
                    # Центр и углы - второй клик определяет радиус
                    if self._arc_radius == 0.0:
                        # Вычисляем радиус от центра до точки
                        dx = point.x() - self._arc_center.x()
                        dy = point.y() - self._arc_center.y()
                        self._arc_radius = math.sqrt(dx*dx + dy*dy)
                    
                    # Обновляем дугу с текущим радиусом и углами (пока предпросмотр)
                    self._current_object.center = self._arc_center
                    self._current_object.radius_x = self._arc_radius
                    self._current_object.radius_y = self._arc_radius
                    self._current_object.radius = self._arc_radius
                    # Углы будут установлены при завершении рисования
                    self._current_object.start_angle = 0
                    self._current_object.end_angle = 90
                    self._current_object.rotation_angle = 0.0
        elif self._drawing_type == 'rectangle':
            from widgets.primitives import Rectangle
            if isinstance(self._current_object, Rectangle):
                method = self._rectangle_creation_method or 'two_points'
                
                if method == 'two_points':
                    # Две противоположные точки - просто обновляем вторую точку
                    self._current_object.bottom_right = point
                elif method == 'point_size':
                    # Одна точка, ширина и высота - координаты устанавливаются через set_rectangle_size
                    # Не обновляем координаты здесь, если размеры уже установлены
                    if self._rectangle_width <= 0 or self._rectangle_height <= 0:
                        # Если размеры еще не установлены, используем текущую точку для предпросмотра
                        if self._rectangle_point1:
                            self._current_object.top_left = QPointF(self._rectangle_point1)
                        self._current_object.bottom_right = QPointF(point)
                    # Если размеры установлены, координаты уже правильные из set_rectangle_size
                elif method == 'center_size':
                    # Центр, ширина и высота - координаты устанавливаются через set_rectangle_size
                    # Не обновляем координаты здесь, если размеры уже установлены
                    if self._rectangle_width <= 0 or self._rectangle_height <= 0:
                        # Если размеры еще не установлены, используем текущую точку для предпросмотра
                        if self._rectangle_point1:
                            self._current_object.top_left = QPointF(self._rectangle_point1)
                        self._current_object.bottom_right = QPointF(point)
                    # Если размеры установлены, координаты уже правильные из set_rectangle_size
                elif method == 'with_fillets':
                    # С фасками/скруглениями - обновляем вторую точку
                    self._current_object.bottom_right = point
                    # Устанавливаем радиус скругления, если он задан
                    if self._rectangle_fillet_radius > 0:
                        self._current_object.fillet_radius = self._rectangle_fillet_radius
        elif self._drawing_type == 'ellipse':
            from widgets.primitives import Ellipse
            if isinstance(self._current_object, Ellipse):
                import math
                if self._ellipse_end_point is None:
                    # Обновление предпросмотра второй точки (движение мыши)
                    # Показываем предпросмотр эллипса с временной третьей точкой
                    # Используем текущую позицию мыши как вторую точку, а для третьей используем перпендикуляр
                    import math
                    # Вычисляем перпендикуляр к линии от первой точки до текущей позиции
                    dx = point.x() - self._ellipse_start_point.x()
                    dy = point.y() - self._ellipse_start_point.y()
                    dist = math.sqrt(dx*dx + dy*dy)
                    if dist > 1e-6:
                        # Перпендикуляр к линии
                        perp_x = -dy / dist
                        perp_y = dx / dist
                        # Третья точка на некотором расстоянии от середины
                        mid_x = (self._ellipse_start_point.x() + point.x()) / 2
                        mid_y = (self._ellipse_start_point.y() + point.y()) / 2
                        temp_third_point = QPointF(mid_x + perp_x * dist * 0.3, mid_y + perp_y * dist * 0.3)
                    else:
                        temp_third_point = point
                    result = self._calculate_ellipse_from_three_points(
                        self._ellipse_start_point, point, temp_third_point
                    )
                    if len(result) == 4 and result[0] is not None:
                        center, radius_x, radius_y, rotation_angle = result
                        if radius_x > 0 and radius_y > 0:
                            self._current_object.center = center
                            self._current_object.radius_x = radius_x
                            self._current_object.radius_y = radius_y
                            self._current_object.rotation_angle = rotation_angle
                        else:
                            self._current_object.center = self._ellipse_start_point
                            self._current_object.radius_x = 0
                            self._current_object.radius_y = 0
                    else:
                        # Если не удалось вычислить, показываем окружность
                        import math
                        dx = point.x() - self._ellipse_start_point.x()
                        dy = point.y() - self._ellipse_start_point.y()
                        radius = math.sqrt(dx*dx + dy*dy)
                        self._current_object.center = self._ellipse_start_point
                        self._current_object.radius_x = radius
                        self._current_object.radius_y = radius
                        self._current_object.rotation_angle = 0.0
                else:
                    # Третий этап - точка высоты (вершина)
                    # Вычисляем параметры эллипса по трем точкам
                    result = self._calculate_ellipse_from_three_points(
                        self._ellipse_start_point, self._ellipse_end_point, point
                    )
                    if len(result) == 4 and result[0] is not None:
                        center, radius_x, radius_y, rotation_angle = result
                        # Проверяем, что радиусы валидны
                        if radius_x > 0 and radius_y > 0:
                            self._current_object.center = center
                            self._current_object.radius_x = radius_x
                            self._current_object.radius_y = radius_y
                            self._current_object.rotation_angle = rotation_angle
                        else:
                            # Если радиусы невалидны, используем минимальные значения
                            self._current_object.center = center
                            self._current_object.radius_x = max(radius_x, 1.0)
                            self._current_object.radius_y = max(radius_y, 1.0)
                            self._current_object.rotation_angle = rotation_angle
    
    def finish_drawing(self) -> Optional[GeometricObject]:
        """Завершает рисование и возвращает созданный объект"""
        if self._drawing_type == 'arc':
            method = self._arc_creation_method or 'three_points'
            if method == 'three_points' and self._arc_end_point is None:
                # Для дуги по трем точкам нужно минимум 2 точки, не завершаем
                return None
            elif method == 'center_angles' and self._arc_radius == 0.0:
                # Для дуги по центру и углам нужен радиус, не завершаем
                return None
        
        if self._drawing_type == 'ellipse' and self._ellipse_end_point is None:
            # Для эллипса нужно минимум 2 точки, не завершаем
            return None
        
        if self._current_object:
            # Для дуги проверяем метод создания
            if self._drawing_type == 'arc':
                from widgets.primitives import Arc
                if isinstance(self._current_object, Arc):
                    method = self._arc_creation_method or 'three_points'
                    if method == 'three_points' and self._arc_end_point is not None:
                        # Проверяем, что радиусы установлены (третья точка была установлена)
                        if self._current_object.radius_x == 0 or self._current_object.radius_y == 0:
                            # Еще не установлена третья точка (высота), не завершаем
                            return None
                        # Проверяем, что углы валидны
                        if self._current_object.start_angle == self._current_object.end_angle:
                            # Углы одинаковые, дуга не может быть построена
                            return None
                    elif method == 'center_angles':
                        # Для метода центр+углы углы должны быть установлены через UI
                        # Здесь мы просто проверяем, что радиус установлен
                        if self._arc_radius == 0.0:
                            return None
            
            # Для эллипса проверяем, что все три точки установлены
            if self._drawing_type == 'ellipse' and self._ellipse_end_point is not None:
                from widgets.primitives import Ellipse
                if isinstance(self._current_object, Ellipse):
                    # Проверяем, что радиусы установлены (третья точка была установлена)
                    if self._current_object.radius_x == 0 or self._current_object.radius_y == 0:
                        # Еще не установлена третья точка (высота), не завершаем
                        return None
            
            # Сохраняем тип рисования перед сбросом для проверок
            drawing_type = self._drawing_type
            
            obj = self._current_object
            self.add_object(obj)
            self._current_object = None
            self._is_drawing = False
            self._drawing_type = None
            self._arc_creation_method = None
            self._arc_start_point = None
            self._arc_end_point = None
            self._arc_center = None
            self._arc_radius = 0.0
            self._ellipse_start_point = None
            self._ellipse_end_point = None
            
            # Для окружности проверяем метод создания (используем сохраненный тип)
            if drawing_type == 'circle':
                method = self._circle_creation_method or 'center_radius'
                if method == 'three_points':
                    # Для трех точек нужно все три точки
                    if self._circle_point2 is None or self._circle_point3 is None:
                        # Восстанавливаем состояние, если проверка не прошла
                        self._current_object = obj
                        self._is_drawing = True
                        self._drawing_type = drawing_type
                        # Удаляем объект из списка, так как мы его вернули
                        if obj in self._objects:
                            self._objects.remove(obj)
                        return None
            
            # Сбрасываем все переменные окружности
            self._circle_creation_method = None
            self._circle_point1 = None
            self._circle_point2 = None
            self._circle_point3 = None
            
            return obj
        
        # Для прямоугольника проверяем метод создания
        if drawing_type == 'rectangle':
            method = self._rectangle_creation_method or 'two_points'
            from widgets.primitives import Rectangle
            if isinstance(obj, Rectangle):
                if method == 'point_size':
                    # Одна точка, ширина и высота - нужно убедиться, что размеры установлены
                    if self._rectangle_width <= 0.0 or self._rectangle_height <= 0.0:
                        # Размеры не установлены, не завершаем
                        return None
                    if not self._rectangle_point1:
                        # Начальная точка не установлена, не завершаем
                        return None
                    # Устанавливаем правильные координаты прямоугольника
                    end_point = QPointF(
                        self._rectangle_point1.x() + self._rectangle_width,
                        self._rectangle_point1.y() + self._rectangle_height
                    )
                    obj.top_left = QPointF(self._rectangle_point1)
                    obj.bottom_right = end_point
                elif method == 'center_size':
                    # Центр, ширина и высота - нужно убедиться, что размеры установлены
                    if self._rectangle_width <= 0.0 or self._rectangle_height <= 0.0:
                        # Размеры не установлены, не завершаем
                        return None
                    if not self._rectangle_point1:
                        # Центр не установлен, не завершаем
                        return None
                    # Устанавливаем правильные координаты прямоугольника
                    half_width = self._rectangle_width / 2.0
                    half_height = self._rectangle_height / 2.0
                    top_left = QPointF(
                        self._rectangle_point1.x() - half_width,
                        self._rectangle_point1.y() - half_height
                    )
                    bottom_right = QPointF(
                        self._rectangle_point1.x() + half_width,
                        self._rectangle_point1.y() + half_height
                    )
                    obj.top_left = top_left
                    obj.bottom_right = bottom_right
                elif method == 'with_fillets':
                    # Для метода с фасками/скруглениями нужно установить радиус скругления
                    # Если радиус не установлен, используем значение по умолчанию
                    if self._rectangle_fillet_radius == 0.0:
                        # Вычисляем радиус скругления как 10% от меньшей стороны
                        bbox = obj.get_bounding_box()
                        min_side = min(bbox.width(), bbox.height())
                        self._rectangle_fillet_radius = min_side * 0.1
                    # Устанавливаем радиус скругления в объект
                    obj.fillet_radius = self._rectangle_fillet_radius
            
            # Сбрасываем все переменные прямоугольника
            self._rectangle_creation_method = None
            self._rectangle_point1 = None
            self._rectangle_width = 0.0
            self._rectangle_height = 0.0
            self._rectangle_fillet_radius = 0.0
            
            return obj
        return None
    
    def cancel_drawing(self):
        """Отменяет текущее рисование"""
        self._current_object = None
        self._is_drawing = False
        self._drawing_type = None
        self._arc_creation_method = None
        self._arc_start_point = None
        self._arc_end_point = None
        self._arc_center = None
        self._arc_radius = 0.0
        self._ellipse_start_point = None
        self._ellipse_end_point = None
        self._circle_creation_method = None
        self._circle_point1 = None
        self._circle_point2 = None
        self._circle_point3 = None
        self._rectangle_creation_method = None
        self._rectangle_point1 = None
        self._rectangle_width = 0.0
        self._rectangle_height = 0.0
        self._rectangle_fillet_radius = 0.0
        self._circle_creation_method = None
        self._circle_point1 = None
        self._circle_point2 = None
        self._circle_point3 = None
        self._rectangle_creation_method = None
        self._rectangle_point1 = None
        self._rectangle_width = 0.0
        self._rectangle_height = 0.0
        self._rectangle_fillet_radius = 0.0
        self._circle_creation_method = None
        self._circle_point1 = None
        self._circle_point2 = None
        self._circle_point3 = None
        self._rectangle_creation_method = None
        self._rectangle_point1 = None
        self._rectangle_width = 0.0
        self._rectangle_height = 0.0
        self._rectangle_fillet_radius = 0.0
    
    def _calculate_ellipse_arc_from_three_points(self, p1: QPointF, p2: QPointF, p3: QPointF):
        """Вычисляет параметры дуги эллипса по трем точкам (начало, конец, вершина)
        Высота определяется перпендикулярно линии между крайними точками"""
        import math
        
        # Проверяем, что точки не совпадают
        if (p1 == p2) or (p1 == p3) or (p2 == p3):
            return None, 0, 0, 0, 0, 0.0
        
        # Середина хорды p1-p2
        chord_mid = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
        chord_length = math.sqrt((p2.x() - p1.x())**2 + (p2.y() - p1.y())**2)
        
        if chord_length < 1e-6:
            return None, 0, 0, 0, 0, 0.0
        
        # Вектор хорды
        chord_vec = QPointF(p2.x() - p1.x(), p2.y() - p1.y())
        chord_angle = math.atan2(chord_vec.y(), chord_vec.x())
        
        # Преобразуем координаты в систему, где хорда горизонтальна
        cos_a = math.cos(-chord_angle)
        sin_a = math.sin(-chord_angle)
        
        # Транслируем так, чтобы середина хорды была в начале координат
        p1_local = QPointF(
            (p1.x() - chord_mid.x()) * cos_a - (p1.y() - chord_mid.y()) * sin_a,
            (p1.x() - chord_mid.x()) * sin_a + (p1.y() - chord_mid.y()) * cos_a
        )
        p2_local = QPointF(
            (p2.x() - chord_mid.x()) * cos_a - (p2.y() - chord_mid.y()) * sin_a,
            (p2.x() - chord_mid.x()) * sin_a + (p2.y() - chord_mid.y()) * cos_a
        )
        p3_local = QPointF(
            (p3.x() - chord_mid.x()) * cos_a - (p3.y() - chord_mid.y()) * sin_a,
            (p3.x() - chord_mid.x()) * sin_a + (p3.y() - chord_mid.y()) * cos_a
        )
        
        # В локальной системе p1 и p2 находятся на оси X
        # p1_local.x() = -chord_length/2, p2_local.x() = chord_length/2
        # p1_local.y() = 0, p2_local.y() = 0
        
        # Проецируем третью точку на перпендикуляр к середине отрезка
        # В локальной системе перпендикуляр - это вертикальная линия через начало координат (x=0)
        # Проекция точки (x3, y3) на эту линию: (0, y3)
        p3_projected = QPointF(0, p3_local.y())
        
        # Высота - это расстояние от спроецированной третьей точки до линии хорды (оси X)
        # В локальной системе это просто y3
        height = p3_projected.y()
        
        # Используем спроецированную точку для дальнейших вычислений
        x3 = p3_projected.x()  # Всегда 0
        y3 = p3_projected.y()
        
        # Если высота слишком мала, используем минимальное значение
        if abs(height) < 1e-6:
            # Используем минимальную высоту вместо возврата None
            height = 1.0 if height >= 0 else -1.0
            # Обновляем y3 с учетом минимальной высоты
            y3 = height
        
        # Находим эллипс в локальной системе координат
        # Эллипс должен проходить через p1, p2 и p3
        # Используем стандартную форму эллипса: (x/a)^2 + ((y-c)/b)^2 = 1
        # где c - смещение центра по Y
        
        a = chord_length / 2  # Полуось по X (половина хорды)
        
        # Точка p3 должна лежать на эллипсе
        # (p3_local.x()/a)^2 + ((p3_local.y() - c)/b)^2 = 1
        # Также эллипс проходит через p1 и p2: (-a, 0) и (a, 0)
        # Это означает, что c = 0 (центр на оси X)
        # Тогда: (p3_projected.x()/a)^2 + (p3_projected.y()/b)^2 = 1
        # Так как p3_projected.x() = 0, получаем: (p3_projected.y()/b)^2 = 1
        # Отсюда: b = |p3_projected.y()|
        
        # Вычисляем b из уравнения эллипса
        # Так как x3 = 0 (точка спроецирована на перпендикуляр), 
        # уравнение упрощается: (y3/b)^2 = 1, откуда b = |y3|
        if abs(y3) < 1e-6:
            # Высота слишком мала, используем минимальное значение
            b = a * 0.1
        else:
            b = abs(y3)  # Полуось по Y равна абсолютному значению высоты
        
        # Убеждаемся, что b не равен 0
        if b < 1e-6:
            b = a * 0.1  # Минимальное значение
        
        # Центр эллипса в локальной системе - начало координат (середина хорды)
        # Преобразуем обратно в мировые координаты
        center = chord_mid
        
        # Вычисляем углы точек на эллипсе
        # Параметрическое уравнение эллипса: x = a*cos(t), y = b*sin(t)
        # Угол для точки p1: t1 = pi (левая точка, x=-a, y=0)
        # Угол для точки p2: t2 = 0 (правая точка, x=a, y=0)
        # Угол для точки p3 (спроецированной): так как x3 = 0, то cos(t3) = 0
        # Это означает t3 = pi/2 (если y3 > 0) или t3 = -pi/2 (если y3 < 0)
        
        t1 = math.pi
        t2 = 0.0
        if abs(y3) < 1e-6:
            # Если высота близка к нулю, используем угол близкий к pi/2
            t3 = math.pi / 2 if y3 >= 0 else -math.pi / 2
        else:
            # Третья точка спроецирована на перпендикуляр (x=0)
            # Для эллипса: x = a*cos(t) = 0, значит cos(t) = 0, t = ±pi/2
            t3 = math.pi / 2 if y3 > 0 else -math.pi / 2
        
        # Определяем направление дуги через третью точку
        # Если y3 > 0 (третья точка выше хорды), дуга идет вверх (против часовой стрелки)
        # Если y3 < 0 (третья точка ниже хорды), дуга идет вниз (по часовой стрелке)
        
        # Преобразуем параметрические углы в градусы
        start_angle = math.degrees(t1)  # 180 градусов
        end_angle = math.degrees(t2)    # 0 градусов
        
        if y3 > 0:
            # Третья точка выше хорды - дуга идет вверх (против часовой стрелки)
            # От p1 (180°) до p2 (0°) через верхнюю часть эллипса
            # Это означает, что дуга идет от 180° до 360° (или 0°), против часовой стрелки
            # Устанавливаем end_angle = 360, чтобы span был положительным (180°)
            start_angle = 180
            end_angle = 360
        else:
            # Третья точка ниже хорды - дуга идет вниз (по часовой стрелке)
            # От p1 (180°) до p2 (0°) через нижнюю часть эллипса
            # Это означает, что дуга идет от 180° до 0° по часовой стрелке
            # Оставляем start_angle = 180, end_angle = 0
            # В renderer span будет отрицательным (0 - 180 = -180), что означает по часовой стрелке
            start_angle = 180
            end_angle = 0
        
        # Радиусы эллипса
        # a - горизонтальный радиус (вдоль хорды)
        # b - вертикальный радиус (перпендикулярно хорде)
        # Но нужно учесть поворот эллипса
        
        # В локальной системе: a - по X, b - по Y
        # После поворота на угол chord_angle:
        # radius_x = max(a, b) если эллипс не повернут
        # Но так как мы используем локальную систему, где хорда горизонтальна,
        # нам нужно правильно определить радиусы в мировых координатах
        
        # Для простоты: если a > b, то radius_x = a, radius_y = b
        # Иначе radius_x = b, radius_y = a
        # Но нужно учесть, что эллипс повернут на угол chord_angle
        
        # Более правильный подход: радиусы в локальной системе
        # После поворота они остаются теми же, но оси меняются
        # Используем a и b как есть, но нужно правильно определить их ориентацию
        
        radius_x = max(a, b)
        radius_y = min(a, b)
        
        # Но это не совсем правильно, так как эллипс может быть повернут
        # Для корректной работы нужно использовать a и b напрямую
        # и учитывать поворот при отрисовке
        
        # Угол поворота эллипса - это угол хорды
        rotation_angle = chord_angle
        
        return center, a, b, start_angle, end_angle, rotation_angle
    
    def _calculate_ellipse_from_three_points(self, p1: QPointF, p2: QPointF, p3: QPointF):
        """Вычисляет параметры эллипса по трем точкам
        Эллипс проходит через все три точки и симметричен относительно перпендикуляра к хорде p1-p2
        Возвращает центр, радиусы и угол поворота эллипса"""
        import math
        
        # Проверяем, что точки не совпадают
        if (p1 == p2) or (p1 == p3) or (p2 == p3):
            return None, 0, 0, 0.0
        
        # Середина хорды p1-p2
        chord_mid = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
        chord_length = math.sqrt((p2.x() - p1.x())**2 + (p2.y() - p1.y())**2)
        
        if chord_length < 1e-6:
            return None, 0, 0, 0.0
        
        # Вектор хорды
        chord_vec = QPointF(p2.x() - p1.x(), p2.y() - p1.y())
        chord_angle = math.atan2(chord_vec.y(), chord_vec.x())
        
        # Преобразуем координаты в систему, где хорда горизонтальна
        cos_a = math.cos(-chord_angle)
        sin_a = math.sin(-chord_angle)
        
        # Транслируем так, чтобы середина хорды была в начале координат
        p1_local = QPointF(
            (p1.x() - chord_mid.x()) * cos_a - (p1.y() - chord_mid.y()) * sin_a,
            (p1.x() - chord_mid.x()) * sin_a + (p1.y() - chord_mid.y()) * cos_a
        )
        p2_local = QPointF(
            (p2.x() - chord_mid.x()) * cos_a - (p2.y() - chord_mid.y()) * sin_a,
            (p2.x() - chord_mid.x()) * sin_a + (p2.y() - chord_mid.y()) * cos_a
        )
        p3_local = QPointF(
            (p3.x() - chord_mid.x()) * cos_a - (p3.y() - chord_mid.y()) * sin_a,
            (p3.x() - chord_mid.x()) * sin_a + (p3.y() - chord_mid.y()) * cos_a
        )
        
        # В локальной системе p1 и p2 находятся на оси X
        # p1_local.x() = -chord_length/2, p2_local.x() = chord_length/2
        # p1_local.y() = 0, p2_local.y() = 0
        
        # Для эллипса, проходящего через p1, p2 и p3, используем стандартную форму:
        # (x/a)^2 + (y/b)^2 = 1
        # где центр в начале координат
        
        # Точки p1 и p2 лежат на эллипсе: (-a, 0) и (a, 0)
        # где a = chord_length / 2
        a = chord_length / 2
        
        # Точка p3 должна лежать на эллипсе: (x3/a)^2 + (y3/b)^2 = 1
        # Отсюда: (y3/b)^2 = 1 - (x3/a)^2
        # b^2 = y3^2 / (1 - (x3/a)^2)
        x3 = p3_local.x()
        y3 = p3_local.y()
        
        # Вычисляем b
        x3_over_a_sq = (x3 / a) ** 2
        if abs(x3_over_a_sq - 1.0) < 1e-6:
            # Третья точка слишком близка к концам хорды, используем минимальное значение
            b = abs(y3) if abs(y3) > 1e-6 else a * 0.1
        else:
            if 1.0 - x3_over_a_sq < 0:
                # Третья точка находится вне эллипса, используем минимальное значение
                b = abs(y3) if abs(y3) > 1e-6 else a * 0.1
            else:
                b_sq = (y3 ** 2) / (1.0 - x3_over_a_sq)
                b = math.sqrt(b_sq) if b_sq > 0 else a * 0.1
        
        # Убеждаемся, что b не равен 0
        if b < 1e-6:
            b = a * 0.1  # Минимальное значение
        
        # Центр эллипса - середина хорды
        center = chord_mid
        
        # Радиусы эллипса в локальной системе: a и b
        # Используем a и b напрямую, так как теперь поддерживаем поворот
        radius_x = a
        radius_y = b
        
        # Угол поворота эллипса - это угол хорды
        rotation_angle = chord_angle
        
        return center, radius_x, radius_y, rotation_angle
    
    def _calculate_circle_from_three_points(self, p1: QPointF, p2: QPointF, p3: QPointF):
        """Вычисляет центр и радиус окружности по трем точкам"""
        import math
        
        # Проверяем, что точки не совпадают
        if (p1 == p2) or (p1 == p3) or (p2 == p3):
            return None, 0
        
        # Вычисляем перпендикуляры к серединам отрезков p1-p2 и p2-p3
        # Уравнение окружности через три точки: (x-a)² + (y-b)² = r²
        # Раскрывая скобки: x² - 2ax + a² + y² - 2by + b² = r²
        # x² + y² - 2ax - 2by + (a² + b² - r²) = 0
        
        # Используем метод решения системы уравнений
        x1, y1 = p1.x(), p1.y()
        x2, y2 = p2.x(), p2.y()
        x3, y3 = p3.x(), p3.y()
        
        # Вычисляем определители для решения системы
        A = x1 * (y2 - y3) - y1 * (x2 - x3) + (x2 * y3 - x3 * y2)
        
        if abs(A) < 1e-10:
            # Точки коллинеарны, окружность не может быть построена
            return None, 0
        
        B = (x1*x1 + y1*y1) * (y3 - y2) + (x2*x2 + y2*y2) * (y1 - y3) + (x3*x3 + y3*y3) * (y2 - y1)
        C = (x1*x1 + y1*y1) * (x2 - x3) + (x2*x2 + y2*y2) * (x3 - x1) + (x3*x3 + y3*y3) * (x1 - x2)
        
        # Центр окружности
        center_x = -B / (2 * A)
        center_y = -C / (2 * A)
        center = QPointF(center_x, center_y)
        
        # Радиус
        dx = x1 - center_x
        dy = y1 - center_y
        radius = math.sqrt(dx*dx + dy*dy)
        
        return center, radius
    
    def get_current_object(self) -> Optional[GeometricObject]:
        """Возвращает текущий рисуемый объект"""
        return self._current_object
    
    def get_current_line(self) -> Optional[LineSegment]:
        """Возвращает текущий рисуемый отрезок (для обратной совместимости)"""
        if isinstance(self._current_object, LineSegment):
            return self._current_object
        return None
    
    def is_drawing(self) -> bool:
        """Возвращает True, если идет процесс рисования"""
        return self._is_drawing
    
    def delete_last_object(self):
        """Удаляет последний объект"""
        if self._objects:
            self._objects.pop()
    
    def get_all_points(self) -> List[QPointF]:
        """Возвращает все точки объектов (для вычисления границ)"""
        points = []
        for obj in self._objects:
            bbox = obj.get_bounding_box()
            # Используем все 4 угла bounding box для более точного вычисления
            points.append(QPointF(bbox.left(), bbox.top()))
            points.append(QPointF(bbox.right(), bbox.top()))
            points.append(QPointF(bbox.right(), bbox.bottom()))
            points.append(QPointF(bbox.left(), bbox.bottom()))
        if self._current_object:
            bbox = self._current_object.get_bounding_box()
            # Используем все 4 угла bounding box
            points.append(QPointF(bbox.left(), bbox.top()))
            points.append(QPointF(bbox.right(), bbox.top()))
            points.append(QPointF(bbox.right(), bbox.bottom()))
            points.append(QPointF(bbox.left(), bbox.bottom()))
        return points

