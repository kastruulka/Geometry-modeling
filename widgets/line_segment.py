from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor

class LineSegment:
    """Класс для хранения информации об отрезке"""
    def __init__(self, start_point, end_point, color=QColor(255, 0, 0), width=2):
        self.start_point = start_point
        self.end_point = end_point
        self.color = color
        self.width = width