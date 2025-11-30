from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor

class LineSegment:
    """Класс для хранения информации об отрезке"""
    def __init__(self, start_point, end_point, style=None, color=None, width=None):
        """
        Инициализация отрезка
        Args:
            start_point: Начальная точка
            end_point: Конечная точка
            style: Стиль линии (LineStyle)
            color: Цвет (для обратной совместимости)
            width: Толщина (для обратной совместимости)
        """
        self.start_point = start_point
        self.end_point = end_point
        self._style = None
        self._style_name = None
        
        # Устанавливаем стиль через setter для правильной регистрации
        if style:
            self.style = style
        
        # Для обратной совместимости
        if color is not None:
            self._legacy_color = color
        else:
            self._legacy_color = QColor(255, 0, 0)
        
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
    def style_name(self):
        return self._style_name
    
    @property
    def color(self):
        """Возвращает цвет из стиля или legacy цвет"""
        if self._style:
            return self._style.color
        return self._legacy_color
    
    @color.setter
    def color(self, value):
        """Устанавливает цвет (обновляет стиль или legacy)"""
        if self._style:
            self._style.color = value
        else:
            self._legacy_color = value
    
    @property
    def width(self):
        """Возвращает ширину из стиля или legacy ширину"""
        if self._style:
            # Конвертируем мм в пиксели для обратной совместимости
            return (self._style.thickness_mm * 96) / 25.4
        return self._legacy_width
    
    @width.setter
    def width(self, value):
        """Устанавливает ширину (обновляет стиль или legacy)"""
        if self._style:
            # Конвертируем пиксели в мм
            thickness_mm = (value * 25.4) / 96
            self._style.thickness_mm = thickness_mm
        else:
            self._legacy_width = value
    
    def on_style_changed(self):
        """Вызывается при изменении стиля"""
        pass  # Может быть использовано для обновления отображения