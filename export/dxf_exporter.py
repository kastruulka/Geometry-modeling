"""
Экспорт геометрических примитивов в формат DXF (Autodesk Drawing Exchange Format).
Поддерживает открытие в AutoCAD, nanoCAD, Компас и других CAD-системах.
"""
import math
import ezdxf
from ezdxf.colors import aci2rgb
from PySide6.QtCore import QRectF
from PySide6.QtGui import QPainterPath, QTransform

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

        # Если слой уже существует (например, был создан из layer_manager), 
        # мы просто привязываемся к нему, а не создаем дубликаты вида _1, _2
        if layer_name not in layers:
            # Цвет слоя (ACI)
            color = style.color
            aci = _nearest_aci_color(color.red(), color.green(), color.blue())

            # Тип линии слоя
            lt_name = _get_linetype_name(style.line_type)

            # Толщина линии слоя
            lw = _lineweight_from_mm(style.thickness_mm)

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

def _embed_original_geometry(entity, obj_type: str, floats: list):
    """
    Прячет исходные параметры математической фигуры (радиусы, координаты) 
    внутрь сгенерированной волнистой полилинии через DXF XData.
    """
    xdata = [(1000, obj_type)]  # 1000 - текстовый код (тип фигуры)
    for f in floats:
        xdata.append((1040, float(f)))  # 1040 - код для float значений
    entity.set_xdata("GEO_MODELER", xdata)

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


def _get_wavy_segment_points(sx: float, sy: float, ex: float, ey: float, style):
    """Генерирует точки волны между двумя координатами (универсальная функция)."""
    dx = ex - sx
    dy = ey - sy
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return [(sx, sy), (ex, ey)]

    angle = math.atan2(dy, dx)
    cos_angle = math.cos(angle)
    sin_angle = math.sin(angle)
    perp_cos = -sin_angle
    perp_sin = cos_angle

    dpi = 96
    if style is not None and hasattr(style, 'wavy_amplitude_mm') and style.wavy_amplitude_mm is not None:
        amplitude_mm = float(style.wavy_amplitude_mm)
    else:
        thickness_mm = float(getattr(style, 'thickness_mm', 0.8) or 0.8)
        amplitude_mm = (0.8 / 2.5) * (thickness_mm / 0.4)

    amplitude_px = (amplitude_mm * dpi) / 25.4
    wave_length_px = max(1.0, amplitude_px * 5.0)

    num_waves = max(1, int(length / wave_length_px))
    actual_wave_length = length / num_waves if num_waves > 0 else length

    num_points = max(20, int(length / 2))
    points = []
    for i in range(num_points + 1):
        t = i / num_points
        along_line = t * length
        wave_phase = (along_line / actual_wave_length) * 2.0 * math.pi
        wave_offset = amplitude_px * math.sin(wave_phase)
        x = sx + along_line * cos_angle + wave_offset * perp_cos
        y = sy + along_line * sin_angle + wave_offset * perp_sin
        points.append((x, y))
    return points

def _get_wavy_segment_points(sx: float, sy: float, ex: float, ey: float, style):
    """Генерирует идеально гладкую прямую волну."""
    dx = ex - sx
    dy = ey - sy
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return [(sx, sy), (ex, ey)]

    angle = math.atan2(dy, dx)
    cos_angle = math.cos(angle)
    sin_angle = math.sin(angle)
    perp_cos = -sin_angle
    perp_sin = cos_angle

    dpi = 96
    if style is not None and hasattr(style, 'wavy_amplitude_mm') and style.wavy_amplitude_mm is not None:
        amplitude_mm = float(style.wavy_amplitude_mm)
    else:
        thickness_mm = float(getattr(style, 'thickness_mm', 0.8) or 0.8)
        amplitude_mm = (0.8 / 2.5) * (thickness_mm / 0.4)

    amplitude_px = (amplitude_mm * dpi) / 25.4
    wave_length_px = max(1.0, amplitude_px * 5.0)

    num_waves = max(1, int(length / wave_length_px))
    actual_wave_length = length / num_waves if num_waves > 0 else length

    # 30 точек на одну волну делают её идеально гладкой
    points_per_wave = 30
    num_points = max(50, num_waves * points_per_wave)

    points = []
    for i in range(num_points + 1):
        t = i / num_points
        along_line = t * length
        wave_phase = (along_line / actual_wave_length) * 2.0 * math.pi
        wave_offset = amplitude_px * math.sin(wave_phase)
        x = sx + along_line * cos_angle + wave_offset * perp_cos
        y = sy + along_line * sin_angle + wave_offset * perp_sin
        points.append((x, y))
    return points

def _wavy_line_polyline_points(line: LineSegment, style):
    return _get_wavy_segment_points(
        line.start_point.x(), line.start_point.y(),
        line.end_point.x(), line.end_point.y(),
        style
    )

def _wavy_points_along_polyline(base_points, style):
    """Накладывает гладкую волну на уже построенную полилинию."""
    if not base_points or len(base_points) < 2:
        return base_points or []

    dpi = 96
    if style is not None and hasattr(style, 'wavy_amplitude_mm') and style.wavy_amplitude_mm is not None:
        amplitude_mm = float(style.wavy_amplitude_mm)
    else:
        thickness_mm = float(getattr(style, 'thickness_mm', 0.8) or 0.8)
        amplitude_mm = (0.8 / 2.5) * (thickness_mm / 0.4)

    amplitude_px = (amplitude_mm * dpi) / 25.4
    wave_length_px = max(1.0, amplitude_px * 5.0)

    arc_lengths = [0.0]
    total_length = 0.0
    for i in range(1, len(base_points)):
        x1, y1 = base_points[i - 1]
        x2, y2 = base_points[i]
        total_length += math.hypot(x2 - x1, y2 - y1)
        arc_lengths.append(total_length)

    if total_length < 1e-6:
        return base_points

    num_waves = max(1, int(total_length / wave_length_px))
    actual_wave_length = total_length / num_waves if num_waves > 0 else total_length
    points_per_wave = 30
    num_points = max(100, num_waves * points_per_wave)

    def sample_point(distance):
        if distance <= 0.0:
            return base_points[0]
        if distance >= total_length:
            return base_points[-1]

        for i in range(1, len(arc_lengths)):
            if arc_lengths[i] >= distance:
                prev_len = arc_lengths[i - 1]
                seg_len = arc_lengths[i] - prev_len
                x1, y1 = base_points[i - 1]
                x2, y2 = base_points[i]
                t = (distance - prev_len) / seg_len if seg_len > 1e-9 else 0.0
                return (x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)
        return base_points[-1]

    points = []
    sample_step = total_length / num_points
    for i in range(num_points + 1):
        dist = min(total_length, i * sample_step)
        px, py = sample_point(dist)

        prev_dist = max(0.0, dist - sample_step)
        next_dist = min(total_length, dist + sample_step)
        prev_pt = sample_point(prev_dist)
        next_pt = sample_point(next_dist)
        tx = next_pt[0] - prev_pt[0]
        ty = next_pt[1] - prev_pt[1]
        mag = math.hypot(tx, ty)
        if mag < 1e-9:
            nx, ny = 0.0, 0.0
        else:
            nx, ny = -ty / mag, tx / mag

        wave_phase = (dist / actual_wave_length) * 2.0 * math.pi
        wave_offset = amplitude_px * math.sin(wave_phase)
        points.append((px + nx * wave_offset, py + ny * wave_offset))

    return points

def _wavy_parametric_curve_points(cx, cy, rx, ry, rotation_angle_rad, start_param, end_param, style):
    """Генерирует идеально гладкую волну вокруг окружностей, дуг и эллипсов."""
    dpi = 96
    if style is not None and hasattr(style, 'wavy_amplitude_mm') and style.wavy_amplitude_mm is not None:
        amplitude_mm = float(style.wavy_amplitude_mm)
    else:
        thickness_mm = float(getattr(style, 'thickness_mm', 0.8) or 0.8)
        amplitude_mm = (0.8 / 2.5) * (thickness_mm / 0.4)

    amplitude_px = (amplitude_mm * dpi) / 25.4
    wave_length_px = max(1.0, amplitude_px * 5.0)

    cos_rot = math.cos(rotation_angle_rad)
    sin_rot = math.sin(rotation_angle_rad)

    def get_pt(t):
        x0 = rx * math.cos(t)
        y0 = ry * math.sin(t)
        return cx + x0 * cos_rot - y0 * sin_rot, cy + x0 * sin_rot + y0 * cos_rot
        
    def get_normal(t):
        dx0 = -rx * math.sin(t)
        dy0 = ry * math.cos(t)
        dx = dx0 * cos_rot - dy0 * sin_rot
        dy = dx0 * sin_rot + dy0 * cos_rot
        mag = math.hypot(dx, dy)
        if mag < 1e-9: return 0, 0
        return -dy/mag, dx/mag # Нормаль к касательной

    # Измеряем длину дуги/эллипса
    num_len_samples = 100
    length = 0.0
    prev_x, prev_y = None, None
    dt = (end_param - start_param) / num_len_samples
    for i in range(num_len_samples + 1):
        px, py = get_pt(start_param + i * dt)
        if prev_x is not None:
            length += math.hypot(px - prev_x, py - prev_y)
        prev_x, prev_y = px, py

    if length < 1e-6: return []

    num_waves = max(1, int(length / wave_length_px))
    actual_wave_length = length / num_waves if num_waves > 0 else length
    
    points_per_wave = 30
    num_points = max(100, num_waves * points_per_wave)

    points = []
    current_len = 0.0
    prev_x, prev_y = get_pt(start_param)
    dt = (end_param - start_param) / num_points
    
    for i in range(num_points + 1):
        t = start_param + i * dt
        px, py = get_pt(t)
        
        if i > 0:
            current_len += math.hypot(px - prev_x, py - prev_y)
        prev_x, prev_y = px, py
        
        wave_phase = (current_len / actual_wave_length) * 2.0 * math.pi
        wave_offset = amplitude_px * math.sin(wave_phase)
        
        nx, ny = get_normal(t)
        points.append((px + nx * wave_offset, py + ny * wave_offset))
        
    return points

def _wavy_spline_polyline_points(spline: Spline, style):
    """Генерирует волнистую полилинию по сплайну, вычисляя нормали через смещение."""
    dpi = 96
    if style is not None and hasattr(style, 'wavy_amplitude_mm') and style.wavy_amplitude_mm is not None:
        amplitude_mm = float(style.wavy_amplitude_mm)
    else:
        thickness_mm = float(getattr(style, 'thickness_mm', 0.8) or 0.8)
        amplitude_mm = (0.8 / 2.5) * (thickness_mm / 0.4)

    amplitude_px = (amplitude_mm * dpi) / 25.4
    wave_length_px = max(1.0, amplitude_px * 5.0)

    # Шаг 1: Измеряем примерную длину сплайна
    num_len_samples = max(100, len(spline.control_points) * 20)
    length = 0.0
    prev_pt = spline._get_point_on_spline(0.0)
    for i in range(1, num_len_samples + 1):
        t = i / num_len_samples
        pt = spline._get_point_on_spline(t)
        length += math.hypot(pt.x() - prev_pt.x(), pt.y() - prev_pt.y())
        prev_pt = pt

    if length < 1e-6:
        return []

    num_waves = max(1, int(length / wave_length_px))
    actual_wave_length = length / num_waves if num_waves > 0 else length
    
    points_per_wave = 30
    num_points = max(100, num_waves * points_per_wave)

    points = []
    current_len = 0.0
    eps = 1e-5 # Малое смещение для поиска нормали
    
    prev_x = spline._get_point_on_spline(0.0).x()
    prev_y = spline._get_point_on_spline(0.0).y()
    
    # Шаг 2: Генерируем точки с учетом нормали
    for i in range(num_points + 1):
        t = i / num_points
        pt = spline._get_point_on_spline(t)
        px, py = pt.x(), pt.y()
        
        if i > 0:
            current_len += math.hypot(px - prev_x, py - prev_y)
        
        # Ищем вектор касательной для расчета нормали
        t_next = min(1.0, t + eps)
        if t >= 1.0 - eps:
            t_prev = max(0.0, t - eps)
            pt_prev = spline._get_point_on_spline(t_prev)
            dx = px - pt_prev.x()
            dy = py - pt_prev.y()
        else:
            pt_next = spline._get_point_on_spline(t_next)
            dx = pt_next.x() - px
            dy = pt_next.y() - py
            
        mag = math.hypot(dx, dy)
        if mag < 1e-9:
            nx, ny = 0, 0
        else:
            nx, ny = -dy / mag, dx / mag # Вектор нормали
            
        wave_phase = (current_len / actual_wave_length) * 2.0 * math.pi
        wave_offset = amplitude_px * math.sin(wave_phase)
        
        points.append((px + nx * wave_offset, py + ny * wave_offset))
        prev_x, prev_y = px, py
        
    return points

def _wavy_arc_polyline_points(cx: float, cy: float, radius: float, start_angle_deg: float, end_angle_deg: float, style):
    """Генерирует точки волны по дуге/окружности."""
    dpi = 96
    if style is not None and hasattr(style, 'wavy_amplitude_mm') and style.wavy_amplitude_mm is not None:
        amplitude_mm = float(style.wavy_amplitude_mm)
    else:
        thickness_mm = float(getattr(style, 'thickness_mm', 0.8) or 0.8)
        amplitude_mm = (0.8 / 2.5) * (thickness_mm / 0.4)

    amplitude_px = (amplitude_mm * dpi) / 25.4
    wave_length_px = max(1.0, amplitude_px * 5.0)

    start_rad = math.radians(start_angle_deg)
    end_rad = math.radians(end_angle_deg)
    if end_rad <= start_rad:
        end_rad += 2 * math.pi

    arc_length = radius * (end_rad - start_rad)
    if arc_length < 1e-6:
        return []

    num_waves = max(1, int(arc_length / wave_length_px))
    actual_wave_length = arc_length / num_waves if num_waves > 0 else arc_length
    num_points = max(50, int(arc_length / 2))
    
    points = []
    for i in range(num_points + 1):
        t = i / num_points
        current_angle = start_rad + t * (end_rad - start_rad)
        along_line = t * arc_length
        wave_phase = (along_line / actual_wave_length) * 2.0 * math.pi
        wave_offset = amplitude_px * math.sin(wave_phase)
        
        r = radius + wave_offset
        points.append((cx + r * math.cos(current_angle), cy + r * math.sin(current_angle)))
    return points


def _export_line(msp, line: LineSegment, style_to_layer, layer_manager=None):
    """Экспортирует отрезок: обычная линия — LINE, излом/волна — LWPOLYLINE (как геометрию)."""
    style = getattr(line, '_style', None)
    is_broken = (
        style is not None
        and getattr(style, 'line_type', None) == LineType.SOLID_THIN_BROKEN
    )
    is_wavy = (
        style is not None
        and getattr(style, 'line_type', None) == LineType.SOLID_WAVY
    )
    if is_broken:
        pts = _broken_line_polyline_points(line)
        entity = msp.add_lwpolyline(pts, close=False)
        _embed_original_geometry(entity, "Line", [line.start_point.x(), line.start_point.y(), line.end_point.x(), line.end_point.y()])
    elif is_wavy:
        pts = _wavy_line_polyline_points(line, style)
        entity = msp.add_lwpolyline(pts, close=False)
        _embed_original_geometry(entity, "Line", [line.start_point.x(), line.start_point.y(), line.end_point.x(), line.end_point.y()])
    else:
        entity = msp.add_line(
            start=(line.start_point.x(), line.start_point.y(), 0),
            end=(line.end_point.x(), line.end_point.y(), 0),
        )
    _apply_entity_style(entity, line, style_to_layer, layer_manager)


def _export_circle(msp, circle: Circle, style_to_layer, layer_manager=None):
    style = getattr(circle, '_style', None)
    is_wavy = (style is not None and getattr(style, 'line_type', None) == LineType.SOLID_WAVY)

    if is_wavy:
        pts = _wavy_parametric_curve_points(
            circle.center.x(), circle.center.y(), 
            circle.radius, circle.radius, 0.0, 
            0, math.tau, style
        )
        entity = msp.add_lwpolyline(pts, close=True)
        _embed_original_geometry(entity, "Circle", [circle.center.x(), circle.center.y(), circle.radius])
    else:
        entity = msp.add_circle(
            center=(circle.center.x(), circle.center.y(), 0),
            radius=circle.radius,
        )
    _apply_entity_style(entity, circle, style_to_layer, layer_manager)


def _arc_to_dxf_ccw_angles(start_angle: float, end_angle: float) -> tuple[float, float]:
    """
    Переводит внутренние углы дуги в CCW-углы DXF так, чтобы сохранить саму
    геометрию дуги, даже если внутри приложения она задана по часовой стрелке.
    """
    start = float(start_angle) % 360.0
    end = float(end_angle) % 360.0

    span = end - start
    if span < -180.0:
        span += 360.0
    elif span > 180.0:
        span -= 360.0

    if span >= 0.0:
        dxf_start = start
        dxf_end = start + span
    elif math.isclose(abs(span), 180.0, abs_tol=1e-9):
        dxf_start = start
        dxf_end = start + 180.0
    else:
        dxf_start = end
        dxf_end = start

    return dxf_start % 360.0, dxf_end % 360.0


def _point_to_dxf_angle(center: Point | object, point) -> float:
    dx = float(point.x()) - float(center.x())
    # Во внутренней геометрии приложения ось Y направлена вниз.
    # Для DXF/CAD угол должен вычисляться в системе, где Y направлена вверх.
    dy = float(center.y()) - float(point.y())
    return math.degrees(math.atan2(dy, dx)) % 360.0


def _angle_is_on_ccw_arc(start_angle: float, end_angle: float, test_angle: float) -> bool:
    start = start_angle % 360.0
    end = end_angle % 360.0
    test = test_angle % 360.0

    if end < start:
        end += 360.0
    if test < start:
        test += 360.0

    return start <= test <= end


def _circular_arc_to_dxf_angles(arc: Arc) -> tuple[float, float]:
    start_point = arc.get_point_at_angle(float(arc.start_angle))
    end_point = arc.get_point_at_angle(float(arc.end_angle))
    through_point = getattr(arc, "_original_vertex_point", None) or arc.get_vertex_point()

    start_angle = _point_to_dxf_angle(arc.center, start_point)
    end_angle = _point_to_dxf_angle(arc.center, end_point)
    through_angle = _point_to_dxf_angle(arc.center, through_point)

    if _angle_is_on_ccw_arc(start_angle, end_angle, through_angle):
        return start_angle, end_angle
    return end_angle, start_angle


def _arc_polyline_points(arc: Arc, min_samples: int = 48) -> list[tuple[float, float]]:
    start_angle_deg = float(arc.start_angle)
    end_angle_deg = float(arc.end_angle)
    span_angle_deg = end_angle_deg - start_angle_deg

    if span_angle_deg < -180.0:
        span_angle_deg += 360.0

    if abs(span_angle_deg) < 0.1:
        return []

    rect = QRectF(
        -arc.radius_x,
        -arc.radius_y,
        arc.radius_x * 2,
        arc.radius_y * 2,
    )

    path = QPainterPath()
    path.arcMoveTo(rect, start_angle_deg)
    path.arcTo(rect, start_angle_deg, span_angle_deg)

    transform = QTransform()
    transform.translate(arc.center.x(), arc.center.y())
    transform.rotate(math.degrees(arc.rotation_angle))
    path = transform.map(path)

    sample_count = max(min_samples, int(abs(span_angle_deg) / 4.0) + 1)
    points = []
    for i in range(sample_count + 1):
        point = path.pointAtPercent(i / sample_count if sample_count > 0 else 0.0)
        points.append((point.x(), point.y()))
    return points


def _export_arc(msp, arc: Arc, style_to_layer, layer_manager=None):
    qt_start = float(arc.start_angle)
    qt_end = float(arc.end_angle)

    dxf_start, dxf_end = _arc_to_dxf_ccw_angles(qt_start, qt_end)
    dxf_rot = float(arc.rotation_angle)

    style = getattr(arc, '_style', None)
    is_wavy = (style is not None and getattr(style, 'line_type', None) == LineType.SOLID_WAVY)
    is_circular = abs(arc.radius_x - arc.radius_y) < 1e-6

    if is_wavy:
        pts = _wavy_points_along_polyline(_arc_polyline_points(arc), style)
        entity = msp.add_lwpolyline(pts, close=False)
        _embed_original_geometry(entity, "Arc", [arc.center.x(), arc.center.y(), arc.radius_x, arc.radius_y, float(arc.start_angle), float(arc.end_angle), float(arc.rotation_angle)])
        _apply_entity_style(entity, arc, style_to_layer, layer_manager)
        return

    pts = _arc_polyline_points(arc)
    entity = msp.add_lwpolyline(pts, close=False)
    _embed_original_geometry(entity, "Arc", [arc.center.x(), arc.center.y(), arc.radius_x, arc.radius_y, float(arc.start_angle), float(arc.end_angle), float(arc.rotation_angle)])
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
    pts = _rectangle_fillet_polyline_points(rect)
    if len(pts) < 2:
        return
        
    style = getattr(rect, '_style', None)
    is_wavy = (style is not None and getattr(style, 'line_type', None) == LineType.SOLID_WAVY)

    if is_wavy:
        all_wavy_points = []
        n = len(pts)
        for i in range(n):
            start = pts[i]
            end = pts[(i + 1) % n]
            wavy_segment = _get_wavy_segment_points(start[0], start[1], end[0], end[1], style)
            if i > 0:
                wavy_segment = wavy_segment[1:] # Убираем дублирование точек на углах
            all_wavy_points.extend(wavy_segment)
            
        entity = msp.add_lwpolyline(all_wavy_points, close=True)
        fillet = getattr(rect, 'fillet_radius', 0.0)
        _embed_original_geometry(entity, "Rectangle", [rect.top_left.x(), rect.top_left.y(), rect.bottom_right.x(), rect.bottom_right.y(), fillet])
        _apply_entity_style(entity, rect, style_to_layer, layer_manager)
    else:
        n = len(pts)
        for i in range(n):
            start = pts[i]
            end = pts[(i + 1) % n]
            entity = msp.add_line(
                start=(start[0], start[1], 0), end=(end[0], end[1], 0),
            )
            _apply_entity_style(entity, rect, style_to_layer, layer_manager)


def _export_ellipse(msp, ellipse: Ellipse, style_to_layer, layer_manager=None):
    style = getattr(ellipse, '_style', None)
    is_wavy = (style is not None and getattr(style, 'line_type', None) == LineType.SOLID_WAVY)

    if is_wavy:
        pts = _wavy_parametric_curve_points(
            ellipse.center.x(), ellipse.center.y(),
            ellipse.radius_x, ellipse.radius_y,
            ellipse.rotation_angle,
            0, math.tau, style
        )
        entity = msp.add_lwpolyline(pts, close=True)
        _embed_original_geometry(entity, "Ellipse", [ellipse.center.x(), ellipse.center.y(), ellipse.radius_x, ellipse.radius_y, ellipse.rotation_angle])
        _apply_entity_style(entity, ellipse, style_to_layer, layer_manager)
        return

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
        major_axis=major_axis, ratio=ratio,
        start_param=0, end_param=math.tau,
    )
    _apply_entity_style(entity, ellipse, style_to_layer, layer_manager)


def _export_polygon(msp, polygon: Polygon, style_to_layer, layer_manager=None):
    vertices = polygon.get_vertices()
    if len(vertices) < 2:
        return
        
    style = getattr(polygon, '_style', None)
    is_wavy = (style is not None and getattr(style, 'line_type', None) == LineType.SOLID_WAVY)

    n = len(vertices)
    if is_wavy:
        all_wavy_points = []
        for i in range(n):
            start = vertices[i]
            end = vertices[(i + 1) % n]
            wavy_segment = _get_wavy_segment_points(start.x(), start.y(), end.x(), end.y(), style)
            if i > 0:
                wavy_segment = wavy_segment[1:]
            all_wavy_points.extend(wavy_segment)
            
        entity = msp.add_lwpolyline(all_wavy_points, close=True)
        
        # --- Прячем правильные параметры многоугольника ---
        cx = polygon.center.x()
        cy = polygon.center.y()
        radius = polygon.radius
        num_vertices = polygon.num_vertices
        
        # Берем именно start_angle, который использует твой класс!
        start_angle = getattr(polygon, 'start_angle', -math.pi / 2)
            
        _embed_original_geometry(entity, "Polygon", [cx, cy, radius, num_vertices, start_angle])
        # ----------------------------------------------------
        
        _apply_entity_style(entity, polygon, style_to_layer, layer_manager)
    else:
        for i in range(n):
            start = vertices[i]
            end = vertices[(i + 1) % n]
            entity = msp.add_line(
                start=(start.x(), start.y(), 0), end=(end.x(), end.y(), 0),
            )
            _apply_entity_style(entity, polygon, style_to_layer, layer_manager)


def _export_spline(msp, spline: Spline, style_to_layer, layer_manager=None):
    """Экспортирует сплайн как SPLINE (аппроксимация по fit-точкам) или LWPOLYLINE (волнистый)."""
    if len(spline.control_points) < 2:
        return

    style = getattr(spline, '_style', None)
    is_wavy = (style is not None and getattr(style, 'line_type', None) == LineType.SOLID_WAVY)

    # Если сплайн выродился в прямую линию
    if len(spline.control_points) == 2:
        p1 = spline.control_points[0]
        p2 = spline.control_points[1]
        if is_wavy:
            pts = _get_wavy_segment_points(p1.x(), p1.y(), p2.x(), p2.y(), style)
            entity = msp.add_lwpolyline(pts, close=False)
        else:
            entity = msp.add_line(
                start=(p1.x(), p1.y(), 0),
                end=(p2.x(), p2.y(), 0),
            )
        _apply_entity_style(entity, spline, style_to_layer, layer_manager)
        return

    # Экспорт волнистого сплайна
    if is_wavy:
        pts = _wavy_spline_polyline_points(spline, style)
        if pts:
            entity = msp.add_lwpolyline(pts, close=False)
            coords = []
            for p in spline.control_points:
                coords.extend([p.x(), p.y()])
            _embed_original_geometry(entity, "Spline", coords)
            _apply_entity_style(entity, spline, style_to_layer, layer_manager)
        return

    # Экспорт обычного сплайна
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

    # --- Регистрация приложения для XData ---
    if "GEO_MODELER" not in doc.appids:
        doc.appids.add("GEO_MODELER")

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
