"""
Экспорт геометрических примитивов в формат DXF (Autodesk Drawing Exchange Format).
Поддерживает открытие в AutoCAD, nanoCAD, Компас и других CAD-системах.
"""
import math
import ezdxf
from ezdxf.colors import aci2rgb

from core.geometry import GeometricObject, Point
from widgets.line_segment import LineSegment
from widgets.primitives import Circle, Arc, Rectangle, Ellipse, Polygon, Spline
from widgets.line_style import LineType


# ---------------------------------------------------------------------------
#  ACI-палитра (1–255): поиск ближайшего цвета
# ---------------------------------------------------------------------------

def _build_aci_table():
    """Строит таблицу RGB для всех 255 цветов ACI (индексы 1–255)."""
    table = {}
    for idx in range(1, 256):
        rgb = aci2rgb(idx)
        table[idx] = (rgb.r, rgb.g, rgb.b)
    return table


_ACI_TABLE = _build_aci_table()


def _nearest_aci_color(r: int, g: int, b: int) -> int:
    """Находит ближайший цвет ACI (1–255) для заданного RGB."""
    best_idx = 7
    best_dist = float('inf')
    for idx, (cr, cg, cb) in _ACI_TABLE.items():
        dist = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
        if dist < best_dist:
            best_dist = dist
            best_idx = idx
            if dist == 0:
                break
    return best_idx


# ---------------------------------------------------------------------------
#  Толщина линии → DXF lineweight
# ---------------------------------------------------------------------------

_STANDARD_WEIGHTS = [
    0, 5, 9, 13, 15, 18, 20, 25, 30, 35, 40,
    50, 53, 60, 70, 80, 90, 100, 106, 120, 140, 158, 200, 211
]


def _lineweight_from_mm(thickness_mm: float) -> int:
    """Конвертирует толщину линии (мм) в DXF lineweight (сотые мм)."""
    lw = int(round(thickness_mm * 100))
    return min(_STANDARD_WEIGHTS, key=lambda w: abs(w - lw))


# ---------------------------------------------------------------------------
#  Тип линии ГОСТ → имя DXF linetype
# ---------------------------------------------------------------------------

_LINETYPE_MAP = {
    LineType.SOLID_MAIN: "Continuous",
    LineType.SOLID_THIN: "Continuous",
    LineType.SOLID_WAVY: "Continuous",
    LineType.DASHED: "DASHED",
    LineType.DASH_DOT_THICK: "DASHDOT",
    LineType.DASH_DOT_THIN: "DASHDOT",
    LineType.DASH_DOT_TWO_DOTS: "DASHDOT2",
    LineType.SOLID_THIN_BROKEN: "Continuous",
}


def _get_linetype_name(line_type: LineType) -> str:
    """Возвращает имя DXF-линотипа для типа линии ГОСТ."""
    return _LINETYPE_MAP.get(line_type, "Continuous")


def _setup_linetypes(doc):
    """Регистрирует линотипы в таблице документа DXF."""
    linetypes = doc.linetypes

    if "DASHED" not in linetypes:
        doc.linetypes.add(
            "DASHED",
            pattern=[10.0, 5.0, -2.5],
            description="Штриховая __ __ __ __"
        )

    if "DASHDOT" not in linetypes:
        doc.linetypes.add(
            "DASHDOT",
            pattern=[12.0, 5.0, -2.5, 0.0, -2.5],
            description="Штрихпунктирная __.__.__.__"
        )

    if "DASHDOT2" not in linetypes:
        doc.linetypes.add(
            "DASHDOT2",
            pattern=[14.0, 5.0, -2.5, 0.0, -2.5, 0.0, -2.5],
            description="Штрихпунктирная с двумя точками __..__..__.."
        )


# ---------------------------------------------------------------------------
#  Слои: создание DXF-слоев из стилей линий
# ---------------------------------------------------------------------------

def _sanitize_layer_name(name: str) -> str:
    """Очищает имя слоя от символов, запрещённых в DXF."""
    # DXF запрещает: < > / \ " : ; ? * | = ` и непечатные символы
    forbidden = '<>/\\":;?*|=`'
    result = name
    for ch in forbidden:
        result = result.replace(ch, '_')
    return result.strip() or "0"


def _setup_layers(doc, objects):
    """
    Создаёт DXF-слои на основе стилей (LineStyle) используемых объектов.
    Возвращает словарь {style_name: dxf_layer_name} для назначения объектов слоям.
    """
    layers = doc.layers
    style_to_layer = {}

    for obj in objects:
        style = getattr(obj, '_style', None)
        if style is None:
            continue
        if style.name in style_to_layer:
            continue

        layer_name = _sanitize_layer_name(style.name)

        # Уникальность имени
        base_name = layer_name
        counter = 1
        while layer_name in layers and layer_name not in style_to_layer.values():
            layer_name = f"{base_name}_{counter}"
            counter += 1

        # Цвет слоя (ACI)
        color = style.color
        aci = _nearest_aci_color(color.red(), color.green(), color.blue())

        # Тип линии слоя
        lt_name = _get_linetype_name(style.line_type)

        # Толщина линии слоя
        lw = _lineweight_from_mm(style.thickness_mm)

        if layer_name not in layers:
            layers.add(
                name=layer_name,
                color=aci,
                linetype=lt_name,
                lineweight=lw,
            )
            # TrueColor для слоя
            layer = layers.get(layer_name)
            layer.rgb = (color.red(), color.green(), color.blue())

        style_to_layer[style.name] = layer_name

    return style_to_layer


# ---------------------------------------------------------------------------
#  Применение стиля к DXF-сущности
# ---------------------------------------------------------------------------

def _get_entity_color(obj, layer_manager=None):
    """Возвращает (r, g, b) для объекта: из стиля, color или _legacy_color. Если цвет чёрный — пробуем цвет слоя."""
    style = getattr(obj, '_style', None)
    if style is not None:
        c = style.color
        r, g, b = (c.red(), c.green(), c.blue())
        if (r, g, b) != (0, 0, 0):
            return (r, g, b)
    color = getattr(obj, 'color', None)
    if color is not None and hasattr(color, 'red'):
        r, g, b = (color.red(), color.green(), color.blue())
        if (r, g, b) != (0, 0, 0):
            return (r, g, b)
    legacy = getattr(obj, '_legacy_color', None)
    if legacy is not None and hasattr(legacy, 'red'):
        r, g, b = (legacy.red(), legacy.green(), legacy.blue())
        if (r, g, b) != (0, 0, 0):
            return (r, g, b)
    # Чёрный по умолчанию — подставляем цвет слоя, если объект на слое и есть layer_manager
    if layer_manager:
        layer_name = getattr(obj, '_layer_name', None)
        if layer_name and layer_name != "0":
            layer = layer_manager.get_layer(layer_name)
            if layer and layer.color:
                return (layer.color.red(), layer.color.green(), layer.color.blue())
    return (0, 0, 0)


def _apply_entity_style(entity, obj, style_to_layer, layer_manager=None):
    """Применяет слой, цвет, толщину и тип линии к DXF-сущности. Цвет задаётся всегда явно."""
    style = getattr(obj, '_style', None)

    obj_layer = getattr(obj, '_layer_name', '0')
    if obj_layer and obj_layer != "0":
        entity.dxf.layer = _sanitize_layer_name(obj_layer)
    elif style and style.name in style_to_layer:
        entity.dxf.layer = style_to_layer[style.name]
    else:
        entity.dxf.layer = "0"

    r, g, b = _get_entity_color(obj, layer_manager)
    entity.dxf.color = _nearest_aci_color(r, g, b)
    entity.rgb = (r, g, b)

    if style is not None:
        entity.dxf.lineweight = _lineweight_from_mm(style.thickness_mm)
        entity.dxf.linetype = _get_linetype_name(style.line_type)
    else:
        if hasattr(obj, '_legacy_width'):
            thickness_mm = (obj._legacy_width * 25.4) / 96.0
            entity.dxf.lineweight = _lineweight_from_mm(thickness_mm)
        else:
            entity.dxf.lineweight = _lineweight_from_mm(0.8)
        entity.dxf.linetype = "Continuous"


# ---------------------------------------------------------------------------
#  Экспорт каждого типа примитива
# ---------------------------------------------------------------------------

def _export_point(msp, point: Point, style_to_layer, layer_manager=None):
    """Экспортирует точку как POINT."""
    entity = msp.add_point((point.x, point.y, 0))
    _apply_entity_style(entity, point, style_to_layer, layer_manager)


def _broken_line_polyline_points(line: LineSegment, num_samples_per_zigzag: int = 4):
    """
    Возвращает список точек линии с изломом (SOLID_THIN_BROKEN) в мировых координатах,
    чтобы экспортировать как LWPOLYLINE. Геометрия как в рендерере (зигзаг).
    """
    sx = line.start_point.x()
    sy = line.start_point.y()
    ex = line.end_point.x()
    ey = line.end_point.y()
    dx = ex - sx
    dy = ey - sy
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return [(sx, sy), (ex, ey)]
    ux = dx / length
    uy = dy / length
    px = -uy
    py = ux

    style = getattr(line, '_style', None)
    zigzag_count = 1
    zigzag_step_mm = 4.0
    if style and hasattr(style, 'zigzag_count'):
        zigzag_count = max(1, int(style.zigzag_count))
    if style and hasattr(style, 'zigzag_step_mm'):
        zigzag_step_mm = style.zigzag_step_mm

    zigzag_height_mm = 3.5
    zigzag_width_mm = 4.0
    zigzag_length_single = zigzag_width_mm
    zigzag_step = zigzag_step_mm
    total_zigzag_length = zigzag_length_single * zigzag_count + zigzag_step * (zigzag_count - 1)
    if total_zigzag_length > length * 0.9:
        total_zigzag_length = length * 0.9
        if zigzag_count > 1:
            zigzag_step = (total_zigzag_length - zigzag_length_single * zigzag_count) / (zigzag_count - 1)
    straight_length = (length - total_zigzag_length) / 2

    points = []
    points.append((sx, sy))
    z_start_x = sx + straight_length * ux
    z_start_y = sy + straight_length * uy
    points.append((z_start_x, z_start_y))

    seg_len = zigzag_length_single / 3
    curr_x, curr_y = z_start_x, z_start_y
    for z in range(zigzag_count):
        p1_x = curr_x + seg_len * ux + (zigzag_height_mm / 2) * px
        p1_y = curr_y + seg_len * uy + (zigzag_height_mm / 2) * py
        points.append((p1_x, p1_y))
        p2_x = p1_x + seg_len * ux - zigzag_height_mm * px
        p2_y = p1_y + seg_len * uy - zigzag_height_mm * py
        points.append((p2_x, p2_y))
        end_x = curr_x + zigzag_length_single * ux
        end_y = curr_y + zigzag_length_single * uy
        points.append((end_x, end_y))
        if z < zigzag_count - 1:
            curr_x = end_x + zigzag_step * ux
            curr_y = end_y + zigzag_step * uy
            points.append((curr_x, curr_y))
        else:
            curr_x, curr_y = end_x, end_y
    points.append((ex, ey))
    return points


def _export_line(msp, line: LineSegment, style_to_layer, layer_manager=None):
    """Экспортирует отрезок: обычная линия — LINE, линия с изломом — LWPOLYLINE."""
    style = getattr(line, '_style', None)
    is_broken = (
        style is not None
        and getattr(style, 'line_type', None) == LineType.SOLID_THIN_BROKEN
    )
    if is_broken:
        pts = _broken_line_polyline_points(line)
        entity = msp.add_lwpolyline(pts, close=False)
    else:
        entity = msp.add_line(
            start=(line.start_point.x(), line.start_point.y(), 0),
            end=(line.end_point.x(), line.end_point.y(), 0),
        )
    _apply_entity_style(entity, line, style_to_layer, layer_manager)


def _export_circle(msp, circle: Circle, style_to_layer, layer_manager=None):
    """Экспортирует окружность как CIRCLE."""
    entity = msp.add_circle(
        center=(circle.center.x(), circle.center.y(), 0),
        radius=circle.radius,
    )
    _apply_entity_style(entity, circle, style_to_layer, layer_manager)


def _export_arc(msp, arc: Arc, style_to_layer, layer_manager=None):
    """Экспортирует дугу. Круговые дуги → ARC, эллиптические → ELLIPSE."""
    is_circular = abs(arc.radius_x - arc.radius_y) < 1e-6 and abs(arc.rotation_angle) < 1e-6

    if is_circular:
        entity = msp.add_arc(
            center=(arc.center.x(), arc.center.y(), 0),
            radius=arc.radius_x,
            start_angle=arc.start_angle,
            end_angle=arc.end_angle,
        )
    else:
        cos_rot = math.cos(arc.rotation_angle)
        sin_rot = math.sin(arc.rotation_angle)

        if arc.radius_x >= arc.radius_y:
            major_axis = (arc.radius_x * cos_rot, arc.radius_x * sin_rot, 0)
            ratio = arc.radius_y / arc.radius_x if arc.radius_x > 0 else 1.0
            start_param = math.radians(arc.start_angle)
            end_param = math.radians(arc.end_angle)
        else:
            major_axis = (-arc.radius_y * sin_rot, arc.radius_y * cos_rot, 0)
            ratio = arc.radius_x / arc.radius_y if arc.radius_y > 0 else 1.0
            start_param = math.radians(arc.start_angle) - math.pi / 2
            end_param = math.radians(arc.end_angle) - math.pi / 2

        entity = msp.add_ellipse(
            center=(arc.center.x(), arc.center.y(), 0),
            major_axis=major_axis,
            ratio=ratio,
            start_param=start_param,
            end_param=end_param,
        )

    _apply_entity_style(entity, arc, style_to_layer, layer_manager)


def _rectangle_fillet_polyline_points(rect: Rectangle, num_arc_samples: int = 12):
    """
    Возвращает список точек контура прямоугольника со скруглениями.
    Обход по часовой стрелке, как при отрисовке в программе (верх → право → низ → лево),
    чтобы в CAD скругления отображались наружу, а не внутрь.
    В мировой системе и DXF: Y вверх, top = min(y), bottom = max(y) для rect.
    """
    x1, y1 = rect.top_left.x(), rect.top_left.y()
    x2, y2 = rect.bottom_right.x(), rect.bottom_right.y()
    left = min(x1, x2)
    right = max(x1, x2)
    top = min(y1, y2)
    bottom = max(y1, y2)
    w = right - left
    h = bottom - top
    r = 0.0
    if getattr(rect, 'fillet_radius', 0.0) > 0:
        r = min(rect.fillet_radius, w / 2, h / 2)

    if r <= 0:
        return [
            (left, top),
            (right, top),
            (right, bottom),
            (left, bottom),
        ]

    points = []
    n = max(2, num_arc_samples)

    def add_arc(cx, cy, start_deg, span_deg):
        """Добавляет точки дуги (центр, начальный угол, протяжённость в градусах)."""
        for i in range(1, n):
            t = i / n
            deg = start_deg + t * span_deg
            rad = math.radians(deg)
            points.append((cx + r * math.cos(rad), cy + r * math.sin(rad)))

    # По часовой стрелке, как в рендерере: верх → право → низ → лево. Центры дуг совпадают с arcTo.
    points.append((left + r, top))
    points.append((right - r, top))
    add_arc(right - r, top + r, 270, 90)
    points.append((right, top + r))
    points.append((right, bottom - r))
    add_arc(right - r, bottom - r, 0, 90)
    points.append((right - r, bottom))
    points.append((left + r, bottom))
    add_arc(left + r, bottom - r, 90, 90)
    points.append((left, bottom - r))
    points.append((left, top + r))
    add_arc(left + r, top + r, 180, 90)
    return points


def _export_rectangle(msp, rect: Rectangle, style_to_layer, layer_manager=None):
    """Экспортирует прямоугольник как цепочку LINE (каждая сторона/сегмент — отдельный отрезок).
    Так в сторонних программах можно измерять углы между сторонами."""
    pts = _rectangle_fillet_polyline_points(rect)
    if len(pts) < 2:
        return
    n = len(pts)
    for i in range(n):
        start = pts[i]
        end = pts[(i + 1) % n]
        entity = msp.add_line(
            start=(start[0], start[1], 0),
            end=(end[0], end[1], 0),
        )
        _apply_entity_style(entity, rect, style_to_layer, layer_manager)


def _export_ellipse(msp, ellipse: Ellipse, style_to_layer, layer_manager=None):
    """Экспортирует эллипс как ELLIPSE (полный, 0–2π)."""
    cos_rot = math.cos(ellipse.rotation_angle)
    sin_rot = math.sin(ellipse.rotation_angle)

    if ellipse.radius_x >= ellipse.radius_y:
        major_axis = (ellipse.radius_x * cos_rot, ellipse.radius_x * sin_rot, 0)
        ratio = ellipse.radius_y / ellipse.radius_x if ellipse.radius_x > 0 else 1.0
    else:
        major_axis = (-ellipse.radius_y * sin_rot, ellipse.radius_y * cos_rot, 0)
        ratio = ellipse.radius_x / ellipse.radius_y if ellipse.radius_y > 0 else 1.0

    entity = msp.add_ellipse(
        center=(ellipse.center.x(), ellipse.center.y(), 0),
        major_axis=major_axis,
        ratio=ratio,
        start_param=0,
        end_param=math.tau,
    )
    _apply_entity_style(entity, ellipse, style_to_layer, layer_manager)


def _export_polygon(msp, polygon: Polygon, style_to_layer, layer_manager=None):
    """Экспортирует многоугольник как цепочку LINE (каждая сторона — отдельный отрезок).
    Так в сторонних программах можно измерять углы между сторонами."""
    vertices = polygon.get_vertices()
    if len(vertices) < 2:
        return
    n = len(vertices)
    for i in range(n):
        start = vertices[i]
        end = vertices[(i + 1) % n]
        entity = msp.add_line(
            start=(start.x(), start.y(), 0),
            end=(end.x(), end.y(), 0),
        )
        _apply_entity_style(entity, polygon, style_to_layer, layer_manager)


def _export_spline(msp, spline: Spline, style_to_layer, layer_manager=None):
    """Экспортирует сплайн как SPLINE (аппроксимация по fit-точкам)."""
    if len(spline.control_points) < 2:
        return

    if len(spline.control_points) == 2:
        p1 = spline.control_points[0]
        p2 = spline.control_points[1]
        entity = msp.add_line(
            start=(p1.x(), p1.y(), 0),
            end=(p2.x(), p2.y(), 0),
        )
        _apply_entity_style(entity, spline, style_to_layer, layer_manager)
        return

    num_samples = max(50, len(spline.control_points) * 20)
    fit_points = []
    for i in range(num_samples + 1):
        t = i / num_samples
        pt = spline._get_point_on_spline(t)
        fit_points.append((pt.x(), pt.y(), 0))

    entity = msp.add_spline(fit_points, degree=3)
    _apply_entity_style(entity, spline, style_to_layer, layer_manager)


# ---------------------------------------------------------------------------
#  Главная функция экспорта
# ---------------------------------------------------------------------------

def export_scene_to_dxf(objects, filepath: str, dxf_version: str = "R2010",
                        layer_manager=None):
    """
    Экспортирует список геометрических объектов сцены в файл DXF.

    Args:
        objects: список GeometricObject из Scene
        filepath: путь к выходному файлу .dxf
        dxf_version: версия DXF ("R12", "R2000", "R2004", "R2007", "R2010", "R2013", "R2018")
        layer_manager: опциональный LayerManager для создания DXF-слоёв
    """
    doc = ezdxf.new(dxf_version)
    msp = doc.modelspace()

    # --- 1. Единицы измерения (миллиметры) ---
    doc.header['$INSUNITS'] = 4       # 4 = миллиметры
    doc.header['$MEASUREMENT'] = 1    # 1 = метрическая система
    doc.header['$LUNITS'] = 2         # 2 = десятичные единицы
    doc.header['$LUPREC'] = 4         # точность — 4 знака после запятой

    # --- 2. Регистрация линотипов ---
    _setup_linetypes(doc)

    # --- 3. Создание DXF-слоёв из LayerManager ---
    if layer_manager:
        dxf_layers = doc.layers
        for layer in layer_manager.get_all_layers():
            lname = _sanitize_layer_name(layer.name)
            if lname not in dxf_layers:
                c = layer.color
                aci = _nearest_aci_color(c.red(), c.green(), c.blue())
                dxf_layers.add(
                    name=lname,
                    color=aci,
                    linetype=layer.linetype,
                    lineweight=_lineweight_from_mm(layer.lineweight),
                )
                dxf_layer = dxf_layers.get(lname)
                dxf_layer.rgb = (c.red(), c.green(), c.blue())

    # --- 4. Создание слоёв из стилей (для объектов со стилем, но без явного слоя) ---
    style_to_layer = _setup_layers(doc, objects)

    # --- 4. Включаем отображение lineweight ---
    doc.header['$LWDISPLAY'] = 1

    # --- 5. Экспорт примитивов в WCS ---
    _EXPORTERS = {
        LineSegment: _export_line,
        Circle: _export_circle,
        Arc: _export_arc,
        Rectangle: _export_rectangle,
        Ellipse: _export_ellipse,
        Polygon: _export_polygon,
        Spline: _export_spline,
        Point: _export_point,
    }

    exported_count = 0
    for obj in objects:
        for cls, exporter in _EXPORTERS.items():
            if isinstance(obj, cls):
                exporter(msp, obj, style_to_layer, layer_manager)
                exported_count += 1
                break

    doc.saveas(filepath)
    return exported_count