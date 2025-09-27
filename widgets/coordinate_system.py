import math
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QFont

from .line_segment import LineSegment

class CoordinateSystemWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.grid_step = 20
        self.background_color = QColor(255, 255, 255)
        self.grid_color = QColor(200, 200, 200)
        self.axis_color = QColor(0, 0, 0)
        self.line_color = QColor(255, 0, 0)
        self.line_width = 2
        
        # Хранилище всех отрезков
        self.lines = []
        
        # Текущий рисуемый отрезок
        self.current_line = None
        self.is_drawing = False
        self.current_point = None
        
        self.setMinimumSize(600, 400)
        self.setMouseTracking(True)
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Рисуем фон
        painter.fillRect(self.rect(), self.background_color)
        
        # Рисуем сетку
        self.draw_grid(painter)
        
        # Рисуем оси координат
        self.draw_axes(painter)
        
        # Рисуем все сохраненные отрезки
        for line in self.lines:
            self.draw_saved_line(painter, line)
        
        # Рисуем текущий отрезок (если он есть)
        if self.current_line:
            self.draw_saved_line(painter, self.current_line)
        
        # Рисуем текущую точку при рисовании
        if self.is_drawing and self.current_point:
            self.draw_current_point(painter)
    
    def draw_grid(self, painter):
        painter.setPen(QPen(self.grid_color, 1, Qt.DotLine))
        
        width = self.width()
        height = self.height()
        center_x = width // 2
        center_y = height // 2
        
        # Вертикальные линии
        for x in range(center_x % self.grid_step, width, self.grid_step):
            painter.drawLine(x, 0, x, height)
        
        # Горизонтальные линии
        for y in range(center_y % self.grid_step, height, self.grid_step):
            painter.drawLine(0, y, width, y)
    
    def draw_axes(self, painter):
        painter.setPen(QPen(self.axis_color, 2))
        
        width = self.width()
        height = self.height()
        center_x = width // 2
        center_y = height // 2
        
        # Ось X
        painter.drawLine(0, center_y, width, center_y)
        # Ось Y
        painter.drawLine(center_x, 0, center_x, height)
        
        # Подписи осей
        painter.setFont(QFont("Arial", 10))
        painter.drawText(width - 20, center_y - 5, "X")
        painter.drawText(center_x + 5, 20, "Y")
        painter.drawText(center_x + 5, center_y + 15, "0")
    
    def draw_saved_line(self, painter, line):
        """Рисует сохраненный отрезок"""
        painter.setPen(QPen(line.color, line.width))
        
        center_x = self.width() // 2
        center_y = self.height() // 2
        
        # Преобразуем математические координаты в экранные
        screen_start = QPointF(
            center_x + line.start_point.x(),
            center_y - line.start_point.y()
        )
        screen_end = QPointF(
            center_x + line.end_point.x(),
            center_y - line.end_point.y()
        )
        
        painter.drawLine(screen_start, screen_end)
        
        # Рисуем точки начала и конца
        painter.setBrush(line.color)
        painter.drawEllipse(screen_start, 4, 4)
        painter.drawEllipse(screen_end, 4, 4)
    
    def draw_current_point(self, painter):
        painter.setPen(QPen(Qt.blue, 2))
        painter.setBrush(Qt.blue)
        
        center_x = self.width() // 2
        center_y = self.height() // 2
        
        screen_point = QPointF(
            center_x + self.current_point.x(),
            center_y - self.current_point.y()
        )
        
        painter.drawEllipse(screen_point, 3, 3)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            center_x = self.width() // 2
            center_y = self.height() // 2
            
            # Преобразуем экранные координаты в математические
            math_x = event.position().x() - center_x
            math_y = center_y - event.position().y()
            
            if not self.is_drawing:
                # Начинаем новый отрезок
                self.current_line = LineSegment(
                    QPointF(math_x, math_y),
                    QPointF(math_x, math_y),
                    self.line_color,
                    self.line_width
                )
                self.is_drawing = True
            else:
                # Заканчиваем рисование текущего отрезка
                if self.current_line:
                    self.current_line.end_point = QPointF(math_x, math_y)
                    self.lines.append(self.current_line)
                    self.current_line = None
                self.is_drawing = False
                self.current_point = None
            self.update()
    
    def mouseMoveEvent(self, event):
        if self.is_drawing and self.current_line:
            center_x = self.width() // 2
            center_y = self.height() // 2
            
            math_x = event.position().x() - center_x
            math_y = center_y - event.position().y()
            
            self.current_point = QPointF(math_x, math_y)
            self.current_line.end_point = QPointF(math_x, math_y)
            self.update()
    
    def start_new_line(self):
        """Начинает новый отрезок"""
        if self.is_drawing and self.current_line:
            # Сохраняем текущий отрезок если он есть
            self.lines.append(self.current_line)
        
        self.is_drawing = True
        self.current_point = None
        self.current_line = None
    
    def delete_last_line(self):
        """Удаляет последний добавленный отрезок"""
        if self.lines:
            self.lines.pop()
            self.update()
    
    def delete_all_lines(self):
        """Удаляет все отрезки"""
        self.lines.clear()
        self.current_line = None
        self.is_drawing = False
        self.current_point = None
        self.update()
    
    def set_grid_step(self, step):
        self.grid_step = step
        self.update()
    
    def set_line_color(self, color):
        self.line_color = color
        if self.current_line:
            self.current_line.color = color
    
    def set_background_color(self, color):
        self.background_color = color
        self.update()
    
    def set_grid_color(self, color):
        self.grid_color = color
        self.update()
    
    def set_line_width(self, width):
        self.line_width = width
        if self.current_line:
            self.current_line.width = width
    
    def get_current_points(self):
        """Возвращает текущие точки (для информационной панели)"""
        if self.current_line:
            return self.current_line.start_point, self.current_line.end_point
        elif self.lines:
            last_line = self.lines[-1]
            return last_line.start_point, last_line.end_point
        else:
            return QPointF(0, 0), QPointF(0, 0)
    
    def set_points_from_input(self, start_point, end_point):
        """Установка точек из числового ввода"""
        if self.is_drawing:
            # Если мы в режиме рисования, обновляем текущий отрезок
            if not self.current_line:
                self.current_line = LineSegment(start_point, end_point, self.line_color, self.line_width)
            else:
                self.current_line.start_point = start_point
                self.current_line.end_point = end_point
        else:
            # Создаем новый отрезок
            new_line = LineSegment(start_point, end_point, self.line_color, self.line_width)
            self.lines.append(new_line)
        
        self.update()