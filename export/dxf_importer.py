"""
Импорт геометрии из DXF с переносом цветов (ACI и TrueColor) и слоёв.
Для тяжёлых кривых выполняется редукция точек, чтобы не тормозить интерфейс.
"""
import math
import ezdxf
from ezdxf.colors import aci2rgb
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor

from core.geometry import Point
from core.layers import Layer
from widgets.line_segment import LineSegment
from widgets.primitives import Circle, Arc, Ellipse, Spline

# Лимиты точек при импорте (редукция при превышении)
MAX_SPLINE_POINTS = 150
MAX_POLYLINE_POINTS = 250

# Толщина линии при импорте: как у базовой "Сплошная основная" (0.8 мм) в пикселях при 96 DPI
IMPORT_THICKNESS_MM = 0.8
IMPORT_LINE_WIDTH_PX = (IMPORT_THICKNESS_MM * 96) / 25.4


def _decimate_points(points, max_points):
    """Оставляет не более max_points точек, равномерно по индексам (первая и последняя сохраняются)."""
    n = len(points)
    if n <= max_points:
        return points
    step = (n - 1) / (max_points - 1)
    return [points[int(round(i * step))] for i in range(max_points)]


# ---------------------------------------------------------------------------
#  Цвет: ACI (256=BYLAYER), TrueColor, цвет слоя
# ---------------------------------------------------------------------------

def _entity_rgb(doc, entity):
    """
    Возвращает (r, g, b) для сущности: TrueColor, иначе ACI, при 256 (BYLAYER) — цвет слоя (в т.ч. TrueColor слоя).
    """
    from ezdxf import colors as ezdxf_colors

    # 1) TrueColor сущности (group 420) — приоритет
    try:
        tc = getattr(entity.dxf, "true_color", None)
        if tc is not None and int(tc) != 0:
            r, g, b = ezdxf_colors.int2rgb(int(tc))
            return (int(r), int(g), int(b))
    except Exception:
        pass

    # 2) Свойство rgb сущности (то, что пишет наш экспорт)
    try:
        if hasattr(entity, "rgb") and entity.rgb is not None:
            r, g, b = entity.rgb
            return (int(r), int(g), int(b))
    except Exception:
        pass

    # 3) ACI сущности; 256 = BYLAYER → берём цвет слоя
    aci = getattr(entity.dxf, "color", 256)
    if aci == 256:  # BYLAYER
        layer_name = getattr(entity.dxf, "layer", "0") or "0"
        try:
            layer = doc.layers.get(layer_name)
            # Слой может иметь TrueColor
            if hasattr(layer, "rgb") and layer.rgb is not None:
                try:
                    r, g, b = layer.rgb
                    return (int(r), int(g), int(b))
                except Exception:
                    pass
            aci = layer.get_color()
        except Exception:
            aci = 7

    # ACI 0 = BYBLOCK, aci2rgb(0) может вернуть 0 или вызвать ошибку
    if aci is None or aci < 0:
        aci = 7
    if aci > 255:
        aci = 7
    if aci == 0:
        aci = 7

    try:
        rgb = aci2rgb(aci)
    except (IndexError, KeyError, TypeError):
        return (0, 0, 0)

    # aci2rgb может вернуть RGB(r,g,b) или в старых версиях int 0
    if hasattr(rgb, "r") and hasattr(rgb, "g") and hasattr(rgb, "b"):
        return (int(rgb.r), int(rgb.g), int(rgb.b))
    return (0, 0, 0)


def _entity_layer_name(entity):
    return getattr(entity.dxf, 'layer', '0') or '0'


def _entity_linetype(doc, entity):
    """Возвращает имя типа линии сущности (из entity или слоя при BYLAYER)."""
    lt = getattr(entity.dxf, 'linetype', 'Continuous') or 'Continuous'
    if str(lt).upper() in ('BYLAYER', 'BYLAYER ', ''):
        layer_name = _entity_layer_name(entity)
        try:
            layer = doc.layers.get(layer_name)
            lt = getattr(layer.dxf, 'linetype', 'Continuous') or 'Continuous'
        except Exception:
            pass
    return str(lt).strip() if lt else 'Continuous'


def _entity_lineweight_px(doc, entity):
    """
    Толщина линии сущности в тех же единицах, что и IMPORT_LINE_WIDTH_PX.
    DXF lineweight: целое = мм×100 (25=0.25мм, 80=0.8мм); -1=ByLayer, -2=ByBlock, -3=Default(0.25мм).
    """
    lw = getattr(entity.dxf, 'lineweight', -3)
    if lw == -1:  # ByLayer
        layer_name = _entity_layer_name(entity)
        try:
            layer = doc.layers.get(layer_name)
            lw = getattr(layer.dxf, 'lineweight', -3)
        except Exception:
            lw = -3
    if lw < 0:  # ByBlock, Default или неизвестно → 0.25 мм
        lw = 25
    if lw == 0:
        lw = 25  # «волосная» в DXF — рисуем как тонкую 0.25 мм
    mm = lw / 100.0
    return (mm * 96) / 25.4


def _entity_qcolor(doc, entity):
    r, g, b = _entity_rgb(doc, entity)
    return QColor(r, g, b)


# ---------------------------------------------------------------------------
#  Импорт примитивов из modelspace (WCS)
# ---------------------------------------------------------------------------

def _import_line(doc, entity, **kwargs):
    start = entity.dxf.start
    end = entity.dxf.end
    color = _entity_qcolor(doc, entity)
    layer_name = _entity_layer_name(entity)
    linetype = _entity_linetype(doc, entity)
    line = LineSegment(
        QPointF(start.x, start.y),
        QPointF(end.x, end.y),
        style=None,
        color=color,
        width=_entity_lineweight_px(doc, entity),
    )
    line.layer_name = layer_name
    line._from_dxf_import = True
    line._legacy_linetype = linetype
    return line


def _import_circle(doc, entity, **kwargs):
    center = entity.dxf.center
    radius = float(entity.dxf.radius)
    color = _entity_qcolor(doc, entity)
    layer_name = _entity_layer_name(entity)
    circle = Circle(
        QPointF(center.x, center.y),
        radius,
        style=None,
        color=color,
        width=_entity_lineweight_px(doc, entity),
    )
    circle.layer_name = layer_name
    circle._from_dxf_import = True
    circle._legacy_linetype = _entity_linetype(doc, entity)
    return circle


def _import_arc(doc, entity, **kwargs):
    center = entity.dxf.center
    radius = float(entity.dxf.radius)
    
    start_angle_deg = float(entity.dxf.start_angle)
    end_angle_deg   = float(entity.dxf.end_angle)
    
    # Чтобы в вашей программе дуга нарисовалась правильно (размах > 0)
    if end_angle_deg <= start_angle_deg:
        end_angle_deg += 360
        
    color = _entity_qcolor(doc, entity)
    layer_name = _entity_layer_name(entity)
    arc = Arc(
        QPointF(center.x, center.y),
        radius,
        radius,
        start_angle_deg,
        end_angle_deg,
        style=None,
        color=color,
        width=_entity_lineweight_px(doc, entity),
        rotation_angle=0.0,
    )
    arc.layer_name = layer_name
    arc._from_dxf_import = True
    arc._legacy_linetype = _entity_linetype(doc, entity)
    return arc


def _import_ellipse(doc, entity, **kwargs):
    center = entity.dxf.center
    major = entity.dxf.major_axis
    ratio = float(entity.dxf.ratio)
    radius_x = math.hypot(major.x, major.y)
    radius_y = radius_x * ratio
    start_param = getattr(entity.dxf, 'start_param', 0)
    end_param = getattr(entity.dxf, 'end_param', 2 * math.pi)
    
    color = _entity_qcolor(doc, entity)
    layer_name = _entity_layer_name(entity)
    linetype = _entity_linetype(doc, entity)
    width = _entity_lineweight_px(doc, entity)
    
    # Читаем угол КАК ЕСТЬ (без минуса)
    qt_angle_rad = math.atan2(major.y, major.x)

    if abs((end_param - start_param) - 2 * math.pi) < 1e-9:
        # Полный эллипс
        ellipse = Ellipse(
            QPointF(center.x, center.y),
            radius_x,
            radius_y,
            style=None,
            color=color,
            width=width,
            rotation_angle=qt_angle_rad,
        )
        ellipse.layer_name = layer_name
        ellipse._from_dxf_import = True
        ellipse._legacy_linetype = linetype
        return ellipse
    else:
        # Дуга эллипса
        start_angle_deg = math.degrees(start_param)
        end_angle_deg = math.degrees(end_param)
        
        if end_angle_deg <= start_angle_deg:
            end_angle_deg += 360
        
        arc = Arc(
            QPointF(center.x, center.y),
            radius_x,
            radius_y,
            start_angle_deg,
            end_angle_deg,
            style=None,
            color=color,
            width=width,
            rotation_angle=qt_angle_rad,
        )
        arc.layer_name = layer_name
        arc._from_dxf_import = True
        arc._legacy_linetype = linetype
        return arc


# Стили, экспортируемые как LWPOLYLINE с геометрией (зигзаг и т.д.).
# При импорте такие полилинии восстанавливаются как одиночный отрезок,
# чтобы рендерер рисовал спецэффект динамически с правильными пропорциями.
_RECONSTRUCTABLE_LAYER_STYLES = {
    'Сплошная тонкая с изломами',
}


def _import_lwpolyline(doc, entity, **kwargs):
    points = list(entity.get_points('xy'))
    if not points:
        return None
    layer_name = _entity_layer_name(entity)

    # Ломаная линия при экспорте превращается в LWPOLYLINE с точками зигзага.
    # Восстанавливаем её как один отрезок (от первой до последней точки),
    # чтобы стиль «с изломами» нарисовал зигзаг динамически.
    if layer_name in _RECONSTRUCTABLE_LAYER_STYLES and len(points) >= 2 and not entity.closed:
        color = _entity_qcolor(doc, entity)
        width_px = _entity_lineweight_px(doc, entity)
        line = LineSegment(
            QPointF(points[0][0], points[0][1]),
            QPointF(points[-1][0], points[-1][1]),
            style=None,
            color=color,
            width=width_px,
        )
        line.layer_name = layer_name
        line._from_dxf_import = True
        line._legacy_linetype = _entity_linetype(doc, entity)
        return line

    closed = entity.closed
    color = _entity_qcolor(doc, entity)
    qpoints = [QPointF(p[0], p[1]) for p in points]
    qpoints = _decimate_points(qpoints, MAX_POLYLINE_POINTS)
    objs = []
    n = len(qpoints)
    linetype = _entity_linetype(doc, entity)
    width_px = _entity_lineweight_px(doc, entity)
    for i in range(n - 1):
        line = LineSegment(qpoints[i], qpoints[i + 1], style=None, color=color, width=width_px)
        line.layer_name = layer_name
        line._from_dxf_import = True
        line._legacy_linetype = linetype
        objs.append(line)
    if closed and n >= 3:
        line = LineSegment(qpoints[-1], qpoints[0], style=None, color=color, width=width_px)
        line.layer_name = layer_name
        line._from_dxf_import = True
        line._legacy_linetype = linetype
        objs.append(line)
    return objs if objs else None


def _spline_point_to_xy(p):
    """Приводит точку из ezdxf (Vec3, numpy, tuple) к (x, y)."""
    if hasattr(p, 'x') and hasattr(p, 'y'):
        return (float(p.x), -float(p.y))
    return (float(p[0]), float(p[1]))


def _import_spline(doc, entity, **kwargs):
    """Импорт SPLINE: используются fit_points, при отсутствии — control_points."""
    pts = []
    try:
        if getattr(entity, 'fit_point_count', lambda: 0)() > 0:
            pts = list(entity.fit_points)
        if not pts and getattr(entity, 'control_point_count', lambda: 0)() > 0:
            pts = list(entity.control_points)
    except Exception:
        pass
    if not pts:
        return None
    qpoints = [QPointF(*_spline_point_to_xy(p)) for p in pts]
    qpoints = _decimate_points(qpoints, MAX_SPLINE_POINTS)
    if len(qpoints) < 2:
        return None
    color = _entity_qcolor(doc, entity)
    layer_name = _entity_layer_name(entity)
    spline = Spline(qpoints, style=None, color=color, width=_entity_lineweight_px(doc, entity))
    spline.layer_name = layer_name
    spline._from_dxf_import = True
    spline._legacy_linetype = _entity_linetype(doc, entity)
    return spline


def _import_point(doc, entity, **kwargs):
    loc = entity.dxf.location
    layer_name = _entity_layer_name(entity)
    point = Point(loc.x, loc.y)
    point.layer_name = layer_name
    return point


# ---------------------------------------------------------------------------
#  Слои DXF -> LayerManager
# ---------------------------------------------------------------------------

def _ensure_layers_from_dxf(doc, layer_manager):
    """Добавляет в LayerManager слои из DXF с цветом и типом линии. Используется TrueColor слоя, если задан."""
    if layer_manager is None:
        return
    from export.dxf_exporter import _sanitize_layer_name
    for dxf_layer in doc.layers:
        name = _sanitize_layer_name(dxf_layer.dxf.name)
        if not name or name in layer_manager.get_layer_names():
            continue
        color = None
        try:
            if hasattr(dxf_layer, 'rgb') and dxf_layer.rgb is not None:
                rgb_val = dxf_layer.rgb
                if hasattr(rgb_val, 'r'):
                    r, g, b = rgb_val.r, rgb_val.g, rgb_val.b
                else:
                    r, g, b = rgb_val
                if (int(r), int(g), int(b)) != (0, 0, 0):
                    color = QColor(int(r), int(g), int(b))
            if color is None:
                aci = dxf_layer.get_color()
                if aci < 0:
                    aci = 7
                rgb = aci2rgb(aci)
                if hasattr(rgb, 'r'):
                    color = QColor(rgb.r, rgb.g, rgb.b)
                else:
                    color = QColor(0, 0, 0)
        except Exception:
            color = QColor(0, 0, 0)
        if color is None:
            color = QColor(0, 0, 0)
        linetype = getattr(dxf_layer.dxf, 'linetype', 'Continuous') or 'Continuous'
        layer_manager.add_layer(Layer(name=name, color=color, linetype=linetype))
    # Слой "0" всегда есть по умолчанию
    if '0' not in layer_manager.get_layer_names():
        layer_manager.add_layer(Layer(name='0', color=QColor(0, 0, 0), is_default=True))


# ---------------------------------------------------------------------------
#  Сопоставление DXF linetype → ГОСТ-стиль
# ---------------------------------------------------------------------------

_THICK_THRESHOLD_MM = 0.6

# Стили, которые нельзя определить по DXF linetype (они все экспортируются как Continuous),
# но можно определить по имени слоя, совпадающему с именем стиля.
_LAYER_NAME_STYLES = {
    'Сплошная тонкая с изломами',
    'Сплошная волнистая',
}


def _match_gost_style(obj, style_manager):
    """
    Сопоставляет импортированный объект с ГОСТ-стилем из LineStyleManager.
    Приоритет: имя слоя (для спецстилей) → DXF linetype + толщина.
    """
    if style_manager is None:
        return None

    # Спецстили (волнистая, с изломами) экспортируются как Continuous,
    # но имя слоя DXF совпадает с именем стиля — используем его.
    layer_name = getattr(obj, '_layer_name', '0')
    if layer_name in _LAYER_NAME_STYLES:
        layer_style = style_manager.get_style(layer_name)
        if layer_style:
            return layer_style

    lt = getattr(obj, '_legacy_linetype', 'Continuous') or 'Continuous'
    lt = str(lt).strip().upper()

    width_px = getattr(obj, '_legacy_width', 0)
    thickness_mm = (width_px * 25.4) / 96.0

    if lt == 'DASHED':
        return style_manager.get_style('Штриховая')
    elif lt == 'DASHDOT':
        if thickness_mm >= _THICK_THRESHOLD_MM:
            return style_manager.get_style('Штрихпунктирная утолщенная')
        return style_manager.get_style('Штрихпунктирная тонкая')
    elif lt == 'DASHDOT2':
        return style_manager.get_style('Штрихпунктирная с двумя точками')
    else:
        if thickness_mm >= _THICK_THRESHOLD_MM:
            return style_manager.get_style('Сплошная основная')
        return style_manager.get_style('Сплошная тонкая')


def _apply_gost_style(obj, style_manager):
    """Назначает ГОСТ-стиль объекту, сохраняя оригинальный цвет из DXF."""
    if style_manager is None or not hasattr(obj, 'style'):
        return
    gost_style = _match_gost_style(obj, style_manager)
    if gost_style is not None:
        obj.style = gost_style


# ---------------------------------------------------------------------------
#  Главная функция импорта
# ---------------------------------------------------------------------------

def import_dxf_from_file(filepath: str, scene, layer_manager=None,
                         style_manager=None):
    """
    Загружает DXF из файла, создаёт объекты с цветом и слоями, добавляет их на сцену.

    Поддерживаются: LINE, CIRCLE, ARC, ELLIPSE, LWPOLYLINE, SPLINE, POINT.
    Цвет берётся из TrueColor (group 420), иначе из ACI (256 = BYLAYER → цвет слоя).

    Args:
        filepath: путь к .dxf
        scene: Scene для добавления объектов
        layer_manager: опционально — для создания слоёв из DXF
        style_manager: опционально — LineStyleManager для назначения ГОСТ-стилей
    Returns:
        Количество добавленных объектов.
    """
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    _ensure_layers_from_dxf(doc, layer_manager)

    handlers = {
        'LINE': _import_line,
        'CIRCLE': _import_circle,
        'ARC': _import_arc,
        'ELLIPSE': _import_ellipse,
        'LWPOLYLINE': _import_lwpolyline,
        'SPLINE': _import_spline,
        'POINT': _import_point,
    }
    to_add = []
    for entity in msp:
        if entity.dxftype() not in handlers:
            continue
        try:
            obj = handlers[entity.dxftype()](doc, entity)
            if obj is None:
                continue
            if isinstance(obj, list):
                to_add.extend(obj)
            else:
                to_add.append(obj)
        except Exception:
            continue

    for obj in to_add:
        _apply_gost_style(obj, style_manager)

    scene.add_objects(to_add)
    return len(to_add)
