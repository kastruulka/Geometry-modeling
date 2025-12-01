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
        self._current_line: Optional[LineSegment] = None
        self._is_drawing = False
    
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
        self._current_line = None
        self._is_drawing = False
    
    def get_objects(self) -> List[GeometricObject]:
        """Возвращает все объекты на сцене"""
        return self._objects.copy()
    
    def get_lines(self) -> List[LineSegment]:
        """Возвращает все отрезки на сцене"""
        return [obj for obj in self._objects if isinstance(obj, LineSegment)]
    
    def start_drawing(self, start_point: QPointF, style=None, color=None, width=None):
        """Начинает рисование нового отрезка"""
        self._current_line = LineSegment(start_point, start_point, style=style, 
                                        color=color, width=width)
        self._is_drawing = True
    
    def update_current_line(self, end_point: QPointF):
        """Обновляет конечную точку текущего отрезка"""
        if self._current_line:
            self._current_line.end_point = end_point
    
    def finish_drawing(self) -> Optional[LineSegment]:
        """Завершает рисование и возвращает созданный отрезок"""
        if self._current_line:
            line = self._current_line
            self.add_object(line)
            self._current_line = None
            self._is_drawing = False
            return line
        return None
    
    def cancel_drawing(self):
        """Отменяет текущее рисование"""
        self._current_line = None
        self._is_drawing = False
    
    def get_current_line(self) -> Optional[LineSegment]:
        """Возвращает текущий рисуемый отрезок"""
        return self._current_line
    
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
            if isinstance(obj, LineSegment):
                points.append(obj.start_point)
                points.append(obj.end_point)
        if self._current_line:
            points.append(self._current_line.start_point)
            points.append(self._current_line.end_point)
        return points

