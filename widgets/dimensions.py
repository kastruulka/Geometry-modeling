import math
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontMetricsF, QPainter, QPainterPath, QPen, QBrush, QPolygonF

from core.geometry import Drawable, GeometricObject


def _point_distance(a: QPointF, b: QPointF) -> float:
    return math.hypot(b.x() - a.x(), b.y() - a.y())


def _normalize(dx: float, dy: float) -> tuple[float, float]:
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return 0.0, 0.0
    return dx / length, dy / length


def _offset_point(point: QPointF, dx: float, dy: float) -> QPointF:
    return QPointF(point.x() + dx, point.y() + dy)


def _line_pen(color: QColor, line_type: str, width_px: float = 1.0) -> QPen:
    style_map = {
        "solid": Qt.SolidLine,
        "dashed": Qt.DashLine,
        "dash_dot": Qt.DashDotLine,
        "dot": Qt.DotLine,
    }
    return QPen(color, width_px, style_map.get(line_type, Qt.SolidLine))


def _format_value(value: float, suffix: str = "") -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{text}{suffix}"


def _resolve_dimension_font_family() -> str:
    candidates = (
        "Gost Type A",
        "GOST Type A",
        "GOST type A",
        "GOST Common",
        "ISOCPEUR",
    )
    font_db = QFontDatabase()
    available = {family.lower(): family for family in font_db.families()}
    for candidate in candidates:
        match = available.get(candidate.lower())
        if match:
            return match
    return candidates[0]


@dataclass
class ExtensionLineParams:
    color: QColor = field(default_factory=lambda: QColor(0, 0, 0))
    line_type: str = "solid"
    width_px: float = 1.0
    gap_from_object: float = 2.0
    overshoot: float = 2.5


@dataclass
class DimensionLineParams:
    color: QColor = field(default_factory=lambda: QColor(0, 0, 0))
    line_type: str = "solid"
    width_px: float = 1.0
    extension: float = 2.0


@dataclass
class ArrowParams:
    arrow_type: str = "closed_filled"
    size: float = 3.5
    filled: bool = True
    color: QColor = field(default_factory=lambda: QColor(0, 0, 0))


@dataclass
class DimensionTextParams:
    font_family: str = field(default_factory=_resolve_dimension_font_family)
    height: float = 4.0
    color: QColor = field(default_factory=lambda: QColor(0, 0, 0))
    position: str = "above"
    gap: float = 4.5


@dataclass
class DimensionStyle:
    extension_lines: ExtensionLineParams = field(default_factory=ExtensionLineParams)
    dimension_line: DimensionLineParams = field(default_factory=DimensionLineParams)
    arrows: ArrowParams = field(default_factory=ArrowParams)
    text: DimensionTextParams = field(default_factory=DimensionTextParams)


class DimensionBase(GeometricObject, Drawable):
    def __init__(self, style: DimensionStyle | None = None):
        super().__init__()
        self.style = style or DimensionStyle()
        self.text_override: str | None = None
        self.text_position_override: QPointF | None = None

    def contains_point(self, point: QPointF, tolerance: float = 5.0) -> bool:
        bbox = self.get_bounding_box()
        expanded = QRectF(
            bbox.x() - tolerance,
            bbox.y() - tolerance,
            bbox.width() + tolerance * 2,
            bbox.height() + tolerance * 2,
        )
        return expanded.contains(point)

    def intersects_rect(self, rect: QRectF) -> bool:
        return rect.intersects(self.get_bounding_box())

    def _draw_arrow(self, painter: QPainter, tip: QPointF, direction: tuple[float, float]):
        ux, uy = _normalize(direction[0], direction[1])
        if abs(ux) < 1e-9 and abs(uy) < 1e-9:
            return
        size = self.style.arrows.size
        back = QPointF(tip.x() + ux * size, tip.y() + uy * size)
        perp_x, perp_y = -uy, ux
        half_width = size * math.tan(math.radians(10.0)) * 1.45
        left = QPointF(back.x() + perp_x * half_width, back.y() + perp_y * half_width)
        right = QPointF(back.x() - perp_x * half_width, back.y() - perp_y * half_width)

        painter.save()
        painter.setPen(QPen(self.style.arrows.color, 1.0))
        if self.style.arrows.arrow_type == "open":
            painter.drawLine(tip, left)
            painter.drawLine(tip, right)
        else:
            polygon = QPolygonF([tip, left, right])
            painter.setBrush(QBrush(self.style.arrows.color if self.style.arrows.filled else Qt.NoBrush))
            painter.drawPolygon(polygon)
        painter.restore()

    def _text_screen_metrics(self, painter: QPainter, text: str, scale_factor: float = 1.0):
        font = QFont(self.style.text.font_family)
        font.setPixelSize(int(round(max(18.0, self.style.text.height * max(scale_factor, 1.0) * 4.4))))
        font.setWeight(QFont.Light)
        font.setStyleStrategy(QFont.PreferOutline)
        metrics = QFontMetricsF(font)
        rect = metrics.boundingRect(text)
        return font, rect

    def _draw_text(
        self,
        painter: QPainter,
        position_world: QPointF,
        text: str,
        scale_factor: float = 1.0,
        angle_degrees: float = 0.0,
    ):
        screen_pos = painter.transform().map(position_world)
        painter.save()
        painter.resetTransform()
        font, rect = self._text_screen_metrics(painter, text, scale_factor)
        painter.setFont(font)
        painter.setPen(QPen(self.style.text.color))
        normalized_angle = ((angle_degrees + 180.0) % 360.0) - 180.0
        if normalized_angle > 90.0:
            normalized_angle -= 180.0
        elif normalized_angle < -90.0:
            normalized_angle += 180.0
        painter.translate(screen_pos)
        painter.rotate(-normalized_angle)
        if self.style.text.position == "above":
            draw_rect = QRectF(-rect.width() / 2, -rect.height(), rect.width(), rect.height())
        else:
            draw_rect = QRectF(-rect.width() / 2, -rect.height() / 2, rect.width(), rect.height())
        painter.drawText(draw_rect, Qt.AlignCenter, text)
        painter.restore()

    def _default_text(self) -> str:
        return ""

    def _resolve_text_position(self, default_position: QPointF) -> QPointF:
        if self.text_position_override is None:
            return QPointF(default_position)
        return QPointF(self.text_position_override)

    def set_text_position(self, position: QPointF | None):
        self.text_position_override = QPointF(position) if position is not None else None

    def get_text_position(self) -> QPointF:
        return QPointF()

    def get_text_angle(self) -> float:
        return 0.0

    @property
    def display_text(self) -> str:
        if self.text_override is not None and self.text_override.strip():
            return self.text_override.strip()
        return self._default_text()


class LinearDimension(DimensionBase):
    def __init__(
        self,
        start: QPointF,
        end: QPointF,
        dimension_type: str = "horizontal",
        offset: float = 10.0,
        style: DimensionStyle | None = None,
    ):
        super().__init__(style=style)
        self.start = QPointF(start)
        self.end = QPointF(end)
        self.dimension_type = dimension_type
        self.offset = offset

    @property
    def value(self) -> float:
        dx = self.end.x() - self.start.x()
        dy = self.end.y() - self.start.y()
        if self.dimension_type == "horizontal":
            return abs(dx)
        if self.dimension_type == "vertical":
            return abs(dy)
        return math.hypot(dx, dy)

    def _geometry(self):
        ext = self.style.extension_lines
        dim = self.style.dimension_line
        text_offset = self.style.text.gap + self.style.text.height * 0.9

        if self.dimension_type == "horizontal":
            reference = max(self.start.y(), self.end.y()) if self.offset >= 0 else min(self.start.y(), self.end.y())
            y_base = reference + self.offset
            outward = 1.0 if self.offset >= 0 else -1.0
            p1 = QPointF(self.start.x(), y_base)
            p2 = QPointF(self.end.x(), y_base)
            ext1_start = QPointF(self.start.x(), self.start.y() + outward * ext.gap_from_object)
            ext2_start = QPointF(self.end.x(), self.end.y() + outward * ext.gap_from_object)
            ext1_end = QPointF(p1.x(), p1.y() + outward * ext.overshoot)
            ext2_end = QPointF(p2.x(), p2.y() + outward * ext.overshoot)
            line_start = QPointF(p1.x() - dim.extension, p1.y())
            line_end = QPointF(p2.x() + dim.extension, p2.y())
            text_pos = QPointF((p1.x() + p2.x()) / 2, y_base + outward * text_offset)
            return ext1_start, ext1_end, ext2_start, ext2_end, line_start, line_end, p1, p2, text_pos, (1.0, 0.0), (0.0, outward)

        if self.dimension_type == "vertical":
            reference = max(self.start.x(), self.end.x()) if self.offset >= 0 else min(self.start.x(), self.end.x())
            x_base = reference + self.offset
            outward = 1.0 if self.offset >= 0 else -1.0
            p1 = QPointF(x_base, self.start.y())
            p2 = QPointF(x_base, self.end.y())
            ext1_start = QPointF(self.start.x() + outward * ext.gap_from_object, self.start.y())
            ext2_start = QPointF(self.end.x() + outward * ext.gap_from_object, self.end.y())
            ext1_end = QPointF(p1.x() + outward * ext.overshoot, p1.y())
            ext2_end = QPointF(p2.x() + outward * ext.overshoot, p2.y())
            line_start = QPointF(p1.x(), p1.y() - dim.extension)
            line_end = QPointF(p2.x(), p2.y() + dim.extension)
            text_pos = QPointF(x_base + outward * text_offset, (p1.y() + p2.y()) / 2)
            return ext1_start, ext1_end, ext2_start, ext2_end, line_start, line_end, p1, p2, text_pos, (0.0, 1.0), (outward, 0.0)

        dx = self.end.x() - self.start.x()
        dy = self.end.y() - self.start.y()
        ux, uy = _normalize(dx, dy)
        nx, ny = -uy, ux
        shift_x = nx * self.offset
        shift_y = ny * self.offset
        normal_sign = 1.0 if self.offset >= 0 else -1.0
        p1 = _offset_point(self.start, shift_x, shift_y)
        p2 = _offset_point(self.end, shift_x, shift_y)
        ext1_start = _offset_point(self.start, nx * self.style.extension_lines.gap_from_object * normal_sign, ny * self.style.extension_lines.gap_from_object * normal_sign)
        ext2_start = _offset_point(self.end, nx * self.style.extension_lines.gap_from_object * normal_sign, ny * self.style.extension_lines.gap_from_object * normal_sign)
        ext1_end = _offset_point(p1, nx * self.style.extension_lines.overshoot * normal_sign, ny * self.style.extension_lines.overshoot * normal_sign)
        ext2_end = _offset_point(p2, nx * self.style.extension_lines.overshoot * normal_sign, ny * self.style.extension_lines.overshoot * normal_sign)
        line_start = _offset_point(p1, -ux * self.style.dimension_line.extension, -uy * self.style.dimension_line.extension)
        line_end = _offset_point(p2, ux * self.style.dimension_line.extension, uy * self.style.dimension_line.extension)
        text_pos = _offset_point(
            QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2),
            nx * text_offset * normal_sign,
            ny * text_offset * normal_sign,
        )
        return ext1_start, ext1_end, ext2_start, ext2_end, line_start, line_end, p1, p2, text_pos, (ux, uy), (nx * normal_sign, ny * normal_sign)

    def get_bounding_box(self) -> QRectF:
        geom = self._geometry()
        points = list(geom[:8]) + [geom[8]]
        min_x = min(p.x() for p in points)
        min_y = min(p.y() for p in points)
        max_x = max(p.x() for p in points)
        max_y = max(p.y() for p in points)
        return QRectF(min_x, min_y, max_x - min_x, max_y - min_y)

    def draw(self, painter, scale_factor: float = 1.0):
        ext1_start, ext1_end, ext2_start, ext2_end, line_start, line_end, arrow1_tip, arrow2_tip, text_pos, tangent, _ = self._geometry()
        ux, uy = tangent
        dim_len_world = _point_distance(arrow1_tip, arrow2_tip)
        arrow_room = self.style.arrows.size * 2.4 + 1.0
        is_small_dimension = dim_len_world < 5.0
        inside_arrows = not is_small_dimension and dim_len_world >= arrow_room
        text_angle = math.degrees(math.atan2(line_end.y() - line_start.y(), line_end.x() - line_start.x()))
        if is_small_dimension:
            side_offset = self.style.text.gap + self.style.arrows.size * 3.5
            text_pos = _offset_point(arrow2_tip, ux * side_offset, uy * side_offset * 0.25)
        text_pos = self._resolve_text_position(text_pos)

        ext_width = self.style.extension_lines.width_px / max(scale_factor, 1e-6)
        dim_width = self.style.dimension_line.width_px / max(scale_factor, 1e-6)
        painter.save()
        painter.setPen(_line_pen(self.style.extension_lines.color, self.style.extension_lines.line_type, ext_width))
        painter.drawLine(ext1_start, ext1_end)
        painter.drawLine(ext2_start, ext2_end)
        painter.setPen(_line_pen(self.style.dimension_line.color, self.style.dimension_line.line_type, dim_width))
        painter.drawLine(line_start, line_end)
        if inside_arrows:
            self._draw_arrow(painter, arrow1_tip, (arrow2_tip.x() - arrow1_tip.x(), arrow2_tip.y() - arrow1_tip.y()))
            self._draw_arrow(painter, arrow2_tip, (arrow1_tip.x() - arrow2_tip.x(), arrow1_tip.y() - arrow2_tip.y()))
        else:
            tail_1 = _offset_point(arrow1_tip, -ux * self.style.arrows.size * 2.8, -uy * self.style.arrows.size * 2.8)
            tail_2 = _offset_point(arrow2_tip, ux * self.style.arrows.size * 2.8, uy * self.style.arrows.size * 2.8)
            painter.drawLine(arrow1_tip, tail_1)
            painter.drawLine(arrow2_tip, tail_2)
            self._draw_arrow(painter, arrow1_tip, (tail_1.x() - arrow1_tip.x(), tail_1.y() - arrow1_tip.y()))
            self._draw_arrow(painter, arrow2_tip, (tail_2.x() - arrow2_tip.x(), tail_2.y() - arrow2_tip.y()))
        painter.restore()
        self._draw_text(painter, text_pos, self.display_text, scale_factor=scale_factor, angle_degrees=text_angle)

    def _default_text(self) -> str:
        return _format_value(self.value)

    def get_text_position(self) -> QPointF:
        _, _, _, _, _, _, arrow1_tip, arrow2_tip, text_pos, tangent, _ = self._geometry()
        ux, uy = tangent
        dim_len_world = _point_distance(arrow1_tip, arrow2_tip)
        if dim_len_world < 5.0:
            side_offset = self.style.text.gap + self.style.arrows.size * 3.5
            text_pos = _offset_point(arrow2_tip, ux * side_offset, uy * side_offset * 0.25)
        return self._resolve_text_position(text_pos)

    def get_text_angle(self) -> float:
        geom = self._geometry()
        line_start = geom[4]
        line_end = geom[5]
        return math.degrees(math.atan2(line_end.y() - line_start.y(), line_end.x() - line_start.x()))


class RadialDimension(DimensionBase):
    def __init__(
        self,
        center: QPointF,
        radius_point: QPointF,
        dimension_type: str = "radius",
        leader_point: QPointF | None = None,
        style: DimensionStyle | None = None,
    ):
        super().__init__(style=style)
        self.center = QPointF(center)
        self.radius_point = QPointF(radius_point)
        self.dimension_type = dimension_type
        self.leader_point = QPointF(leader_point) if leader_point is not None else None

    @property
    def radius(self) -> float:
        return _point_distance(self.center, self.radius_point)

    @property
    def value(self) -> float:
        return self.radius * 2 if self.dimension_type == "diameter" else self.radius

    def get_bounding_box(self) -> QRectF:
        points = [self.center, self.radius_point]
        if self.dimension_type == "diameter":
            dx = self.radius_point.x() - self.center.x()
            dy = self.radius_point.y() - self.center.y()
            points.append(QPointF(self.center.x() - dx, self.center.y() - dy))
        if self.leader_point is not None:
            points.append(self.leader_point)
        min_x = min(p.x() for p in points)
        min_y = min(p.y() for p in points)
        max_x = max(p.x() for p in points)
        max_y = max(p.y() for p in points)
        return QRectF(min_x, min_y, max_x - min_x, max_y - min_y)

    def draw(self, painter, scale_factor: float = 1.0):
        dx = self.radius_point.x() - self.center.x()
        dy = self.radius_point.y() - self.center.y()
        pen = _line_pen(
            self.style.dimension_line.color,
            self.style.dimension_line.line_type,
            self.style.dimension_line.width_px / max(scale_factor, 1e-6),
        )
        painter.save()
        painter.setPen(pen)

        axis_dx = dx
        axis_dy = dy
        if self.leader_point is not None:
            leader_dx = self.leader_point.x() - self.center.x()
            leader_dy = self.leader_point.y() - self.center.y()
            if abs(leader_dx) > 1e-9 or abs(leader_dy) > 1e-9:
                axis_dx, axis_dy = leader_dx, leader_dy
        ux, uy = _normalize(axis_dx, axis_dy)
        radius_tip = QPointF(self.center.x() + ux * self.radius, self.center.y() + uy * self.radius)
        opposite_tip = QPointF(self.center.x() - ux * self.radius, self.center.y() - uy * self.radius)
        text_angle = math.degrees(math.atan2(uy, ux)) if abs(ux) > 1e-9 or abs(uy) > 1e-9 else 0.0

        if self.dimension_type == "diameter":
            if self.leader_point is not None:
                line_end = QPointF(self.leader_point)
            else:
                line_end = _offset_point(radius_tip, ux * self.style.dimension_line.extension, uy * self.style.dimension_line.extension)
            painter.drawLine(opposite_tip, line_end)
            self._draw_arrow(painter, radius_tip, (opposite_tip.x() - radius_tip.x(), opposite_tip.y() - radius_tip.y()))
            self._draw_arrow(painter, opposite_tip, (radius_tip.x() - opposite_tip.x(), radius_tip.y() - opposite_tip.y()))
            if self.leader_point is not None:
                text_pos = _offset_point(line_end, ux * self.style.text.gap, uy * self.style.text.gap)
            else:
                text_pos = _offset_point(
                    QPointF((opposite_tip.x() + radius_tip.x()) / 2, (opposite_tip.y() + radius_tip.y()) / 2),
                    -uy * self.style.text.gap,
                    ux * self.style.text.gap,
                )
        else:
            if self.leader_point is not None:
                line_end = QPointF(self.leader_point)
            else:
                line_end = _offset_point(radius_tip, ux * self.style.dimension_line.extension, uy * self.style.dimension_line.extension)
            painter.drawLine(self.center, line_end)
            self._draw_arrow(painter, radius_tip, (self.center.x() - radius_tip.x(), self.center.y() - radius_tip.y()))
            if self.leader_point is not None:
                text_pos = _offset_point(line_end, ux * self.style.text.gap, uy * self.style.text.gap)
            else:
                text_pos = _offset_point(
                    QPointF((self.center.x() + radius_tip.x()) / 2, (self.center.y() + radius_tip.y()) / 2),
                    -uy * self.style.text.gap,
                    ux * self.style.text.gap,
                )
        text_pos = self._resolve_text_position(text_pos)
        painter.restore()
        self._draw_text(painter, text_pos, self.display_text, scale_factor=scale_factor, angle_degrees=text_angle)

    def _default_text(self) -> str:
        prefix = "⌀" if self.dimension_type == "diameter" else "R"
        return f"{prefix}{_format_value(self.value)}"

    def get_text_position(self) -> QPointF:
        dx = self.radius_point.x() - self.center.x()
        dy = self.radius_point.y() - self.center.y()
        axis_dx = dx
        axis_dy = dy
        if self.leader_point is not None:
            leader_dx = self.leader_point.x() - self.center.x()
            leader_dy = self.leader_point.y() - self.center.y()
            if abs(leader_dx) > 1e-9 or abs(leader_dy) > 1e-9:
                axis_dx, axis_dy = leader_dx, leader_dy
        ux, uy = _normalize(axis_dx, axis_dy)
        radius_tip = QPointF(self.center.x() + ux * self.radius, self.center.y() + uy * self.radius)
        opposite_tip = QPointF(self.center.x() - ux * self.radius, self.center.y() - uy * self.radius)
        if self.dimension_type == "diameter":
            if self.leader_point is not None:
                text_pos = _offset_point(self.leader_point, ux * self.style.text.gap, uy * self.style.text.gap)
            else:
                text_pos = _offset_point(
                    QPointF((opposite_tip.x() + radius_tip.x()) / 2, (opposite_tip.y() + radius_tip.y()) / 2),
                    -uy * self.style.text.gap,
                    ux * self.style.text.gap,
                )
        else:
            if self.leader_point is not None:
                text_pos = _offset_point(self.leader_point, ux * self.style.text.gap, uy * self.style.text.gap)
            else:
                text_pos = _offset_point(
                    QPointF((self.center.x() + radius_tip.x()) / 2, (self.center.y() + radius_tip.y()) / 2),
                    -uy * self.style.text.gap,
                    ux * self.style.text.gap,
                )
        return self._resolve_text_position(text_pos)

    def get_text_angle(self) -> float:
        axis_dx = self.radius_point.x() - self.center.x()
        axis_dy = self.radius_point.y() - self.center.y()
        if self.leader_point is not None:
            leader_dx = self.leader_point.x() - self.center.x()
            leader_dy = self.leader_point.y() - self.center.y()
            if abs(leader_dx) > 1e-9 or abs(leader_dy) > 1e-9:
                axis_dx, axis_dy = leader_dx, leader_dy
        return math.degrees(math.atan2(axis_dy, axis_dx)) if abs(axis_dx) > 1e-9 or abs(axis_dy) > 1e-9 else 0.0


class AngularDimension(DimensionBase):
    def __init__(
        self,
        vertex: QPointF,
        ray_start: QPointF,
        ray_end: QPointF,
        radius: float = 20.0,
        style: DimensionStyle | None = None,
    ):
        super().__init__(style=style)
        self.vertex = QPointF(vertex)
        self.ray_start = QPointF(ray_start)
        self.ray_end = QPointF(ray_end)
        self.radius = radius

    @property
    def value(self) -> float:
        a1, a2, span = self._angles()
        return math.degrees(span)

    def _angles(self) -> tuple[float, float, float]:
        a1 = math.atan2(self.ray_start.y() - self.vertex.y(), self.ray_start.x() - self.vertex.x())
        a2 = math.atan2(self.ray_end.y() - self.vertex.y(), self.ray_end.x() - self.vertex.x())
        span = (a2 - a1) % (2 * math.pi)
        if span > math.pi:
            a1, a2 = a2, a1
            span = (a2 - a1) % (2 * math.pi)
        return a1, a2, span

    def get_bounding_box(self) -> QRectF:
        a1, _, span = self._angles()
        points = [self.vertex, self.ray_start, self.ray_end]
        for i in range(17):
            angle = a1 + span * (i / 16.0)
            points.append(QPointF(self.vertex.x() + self.radius * math.cos(angle), self.vertex.y() + self.radius * math.sin(angle)))
        min_x = min(p.x() for p in points)
        min_y = min(p.y() for p in points)
        max_x = max(p.x() for p in points)
        max_y = max(p.y() for p in points)
        return QRectF(min_x, min_y, max_x - min_x, max_y - min_y)

    def draw(self, painter, scale_factor: float = 1.0):
        a1, a2, span = self._angles()
        pen_ext = _line_pen(self.style.extension_lines.color, self.style.extension_lines.line_type, self.style.extension_lines.width_px / max(scale_factor, 1e-6))
        pen_dim = _line_pen(self.style.dimension_line.color, self.style.dimension_line.line_type, self.style.dimension_line.width_px / max(scale_factor, 1e-6))
        painter.save()
        painter.setPen(pen_ext)
        ext_len = self.radius + self.style.extension_lines.overshoot
        for angle in (a1, a2):
            painter.drawLine(
                self.vertex,
                QPointF(self.vertex.x() + ext_len * math.cos(angle), self.vertex.y() + ext_len * math.sin(angle)),
            )
        painter.setPen(pen_dim)
        path = QPainterPath()
        path.moveTo(QPointF(self.vertex.x() + self.radius * math.cos(a1), self.vertex.y() + self.radius * math.sin(a1)))
        steps = max(24, int(math.degrees(span)))
        for i in range(1, steps + 1):
            angle = a1 + span * (i / steps)
            path.lineTo(QPointF(self.vertex.x() + self.radius * math.cos(angle), self.vertex.y() + self.radius * math.sin(angle)))
        painter.drawPath(path)
        start_tip = QPointF(self.vertex.x() + self.radius * math.cos(a1), self.vertex.y() + self.radius * math.sin(a1))
        end_tip = QPointF(self.vertex.x() + self.radius * math.cos(a2), self.vertex.y() + self.radius * math.sin(a2))
        self._draw_arrow(painter, start_tip, (-math.sin(a1), math.cos(a1)))
        self._draw_arrow(painter, end_tip, (math.sin(a2), -math.cos(a2)))
        painter.restore()
        mid_angle = a1 + span / 2.0
        text_radius = self.radius + self.style.text.gap + self.style.text.height * 1.4
        text_pos = QPointF(
            self.vertex.x() + text_radius * math.cos(mid_angle),
            self.vertex.y() + text_radius * math.sin(mid_angle),
        )
        text_angle = math.degrees(mid_angle) - 90.0
        text_pos = self._resolve_text_position(text_pos)
        self._draw_text(painter, text_pos, self.display_text, scale_factor=scale_factor, angle_degrees=text_angle)

    def _default_text(self) -> str:
        return _format_value(self.value, "°")

    def get_text_position(self) -> QPointF:
        a1, _, span = self._angles()
        mid_angle = a1 + span / 2.0
        text_radius = self.radius + self.style.text.gap + self.style.text.height * 1.4
        default_text = QPointF(
            self.vertex.x() + text_radius * math.cos(mid_angle),
            self.vertex.y() + text_radius * math.sin(mid_angle),
        )
        return self._resolve_text_position(default_text)

    def get_text_angle(self) -> float:
        a1, _, span = self._angles()
        mid_angle = a1 + span / 2.0
        return math.degrees(mid_angle) - 90.0
