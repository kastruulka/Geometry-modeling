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
from widgets.primitives import Circle, Arc, Ellipse, Spline, Rectangle, Polygon

# Лимиты точек при импорте (редукция при превышении)
MAX_SPLINE_POINTS = 150
MAX_POLYLINE_POINTS = 250

# Толщина линии при импорте: как у базовой "Сплошная основная" (0.8 мм) в пикселях при 96 DPI
# Толщина линии при импорте: как у базовой "Сплошная основная" (0.8 мм) в пикселях при 96 DPI
IMPORT_THICKNESS_MM = 0.8
IMPORT_LINE_WIDTH_PX = (IMPORT_THICKNESS_MM * 96) / 25.4

# Стили слоёв, которые при экспорте превращаются в сложные полилинии (изломы, волны),
# но при отсутствии XData (например, файл пересохранен в другом CAD) 
# должны восстанавливаться как простой прямой отрезок по первой и последней точке.
_RECONSTRUCTABLE_LAYER_STYLES = {
    'Сплошная тонкая с изломами',
    'Сплошная волнистая',
}


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
    if r == 255 and g == 255 and b == 255:
        r, g, b = 0, 0, 0
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

    dxf_start = float(entity.dxf.start_angle)
    dxf_end = float(entity.dxf.end_angle)
    
    start_angle_deg = (-dxf_end) % 360
    end_angle_deg = (-dxf_start) % 360
    
    color = _entity_qcolor(doc, entity)
    layer_name = _entity_layer_name(entity)
    arc = Arc(
        QPointF(center.x, center.y),
        radius, radius,
        start_angle_deg, end_angle_deg,
        style=None, color=color,
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

    if abs((end_param - start_param) - 2 * math.pi) < 1e-9:
        angle_rad = math.atan2(major.y, major.x)
        ellipse = Ellipse(
            QPointF(center.x, center.y),
            radius_x, radius_y,
            style=None, color=color,
            width=_entity_lineweight_px(doc, entity),
            rotation_angle=angle_rad,
        )
        ellipse.layer_name = layer_name
        ellipse._from_dxf_import = True
        ellipse._legacy_linetype = _entity_linetype(doc, entity)
        return ellipse
    else:
        # ИСПОЛЬЗУЕМ ЧИСТЫЕ УГЛЫ!
        start_angle_deg = math.degrees(start_param)
        end_angle_deg = math.degrees(end_param)
        
        arc = Arc(
            QPointF(center.x, center.y),
            radius_x, radius_y,
            start_angle_deg, end_angle_deg,
            style=None, color=color,
            width=_entity_lineweight_px(doc, entity),
            rotation_angle=math.atan2(major.y, major.x),
        )
        arc.layer_name = layer_name
        arc._from_dxf_import = True
        arc._legacy_linetype = _entity_linetype(doc, entity)
        return arc

def _restore_from_xdata(doc, entity):
    """Универсальный восстановитель любой геометрии из XData (наших скрытых метаданных)."""
    if not entity.has_xdata("GEO_MODELER"):
        return None
    try:
        xdata = entity.get_xdata("GEO_MODELER")
        obj_type = None
        floats = []
        for code, value in xdata:
            if code == 1000: obj_type = value
            elif code == 1040: floats.append(value)

        color = _entity_qcolor(doc, entity)
        width_px = _entity_lineweight_px(doc, entity)
        layer_name = _entity_layer_name(entity)
        linetype = _entity_linetype(doc, entity)

        obj = None
        if obj_type == "Circle" and len(floats) >= 3:
            obj = Circle(QPointF(floats[0], floats[1]), floats[2], style=None, color=color, width=width_px)
        elif obj_type == "Arc" and len(floats) >= 7:
            obj = Arc(QPointF(floats[0], floats[1]), floats[2], floats[3], floats[4], floats[5], style=None, color=color, width=width_px, rotation_angle=floats[6])
        elif obj_type == "Ellipse" and len(floats) >= 5:
            obj = Ellipse(QPointF(floats[0], floats[1]), floats[2], floats[3], style=None, color=color, width=width_px, rotation_angle=floats[4])
        elif obj_type == "Rectangle" and len(floats) >= 5:
            obj = Rectangle(QPointF(floats[0], floats[1]), QPointF(floats[2], floats[3]), style=None, color=color, width=width_px)
            obj.fillet_radius = floats[4]
        elif obj_type == "Polygon" and len(floats) >= 4:
            import math
            cx, cy = floats[0], floats[1]
            radius = floats[2]
            num_vertices = int(floats[3])
            start_angle = floats[4] if len(floats) >= 5 else -math.pi / 2
            obj = Polygon(QPointF(cx, cy), radius, num_vertices, style=None, color=color, width=width_px, start_angle=start_angle)
        elif obj_type == "Spline" and len(floats) >= 4:
            qpts = [QPointF(floats[i], floats[i+1]) for i in range(0, len(floats)-1, 2)]
            obj = Spline(qpts, style=None, color=color, width=width_px)
        elif obj_type == "Line" and len(floats) >= 4:
            obj = LineSegment(QPointF(floats[0], floats[1]), QPointF(floats[2], floats[3]), style=None, color=color, width=width_px)

        if obj is not None:
            obj.layer_name = layer_name
            obj._layer_name = layer_name  
            obj._from_dxf_import = True
            obj._legacy_linetype = linetype
            return obj
    except Exception as e:
        print(f"Ошибка при чтении XData: {e}")
    return None

def _import_lwpolyline(doc, entity, **kwargs):
    layer_name = _entity_layer_name(entity)
    color = _entity_qcolor(doc, entity)
    width_px = _entity_lineweight_px(doc, entity)
    linetype = _entity_linetype(doc, entity)

    # --- 1. Пытаемся восстановить оригинальную фигуру из XData ---
    if entity.has_xdata("GEO_MODELER"):
        try:
            xdata = entity.get_xdata("GEO_MODELER")
            obj_type = None
            floats = []
            for code, value in xdata:
                if code == 1000:
                    obj_type = value
                elif code == 1040:
                    floats.append(value)

            obj = None
            if obj_type == "Circle" and len(floats) >= 3:
                obj = Circle(QPointF(floats[0], floats[1]), floats[2], style=None, color=color, width=width_px)
            
            elif obj_type == "Arc" and len(floats) >= 7:
                obj = Arc(QPointF(floats[0], floats[1]), floats[2], floats[3], floats[4], floats[5], style=None, color=color, width=width_px, rotation_angle=floats[6])
            
            elif obj_type == "Ellipse" and len(floats) >= 5:
                obj = Ellipse(QPointF(floats[0], floats[1]), floats[2], floats[3], style=None, color=color, width=width_px, rotation_angle=floats[4])
            
            elif obj_type == "Rectangle" and len(floats) >= 5:
                obj = Rectangle(QPointF(floats[0], floats[1]), QPointF(floats[2], floats[3]), style=None, color=color, width=width_px)
                obj.fillet_radius = floats[4]
            
            elif obj_type == "Spline" and len(floats) >= 4:
                qpts = [QPointF(floats[i], floats[i+1]) for i in range(0, len(floats)-1, 2)]
                obj = Spline(qpts, style=None, color=color, width=width_px)
            
            elif obj_type == "Line" and len(floats) >= 4:
                obj = LineSegment(QPointF(floats[0], floats[1]), QPointF(floats[2], floats[3]), style=None, color=color, width=width_px)
                
            elif obj_type == "Polygon" and len(floats) >= 4:
                import math
                cx, cy = floats[0], floats[1]
                radius = floats[2]
                num_vertices = int(floats[3])
                # Читаем сохраненный угол (если файла старый, ставим дефолтный -pi/2)
                start_angle = floats[4] if len(floats) >= 5 else -math.pi / 2
                
                # Создаем Polygon с передачей start_angle!
                obj = Polygon(
                    QPointF(cx, cy), 
                    radius, 
                    num_vertices, 
                    style=None, 
                    color=color, 
                    width=width_px, 
                    start_angle=start_angle
                )

            if obj is not None:
                obj.layer_name = layer_name
                obj._layer_name = layer_name  
                obj._from_dxf_import = True
                obj._legacy_linetype = linetype
                return obj
        except Exception as e:
            print(f"Ошибка при чтении XData: {e}")

    # --- 2. Стандартный импорт полилинии (запасной план) ---
    points = list(entity.get_points('xy'))
    if not points:
        return None

    if layer_name in _RECONSTRUCTABLE_LAYER_STYLES and len(points) >= 2 and not entity.closed:
        line = LineSegment(QPointF(points[0][0], points[0][1]), QPointF(points[-1][0], points[-1][1]), style=None, color=color, width=width_px)
        line.layer_name = layer_name
        line._layer_name = layer_name 
        line._from_dxf_import = True
        line._legacy_linetype = linetype
        return line

    closed = entity.closed
    qpoints = [QPointF(p[0], p[1]) for p in points]
    qpoints = _decimate_points(qpoints, MAX_POLYLINE_POINTS)
    objs = []
    n = len(qpoints)
    for i in range(n - 1):
        line = LineSegment(qpoints[i], qpoints[i + 1], style=None, color=color, width=width_px)
        line.layer_name = layer_name
        line._layer_name = layer_name
        line._from_dxf_import = True
        line._legacy_linetype = linetype
        objs.append(line)
    if closed and n >= 3:
        line = LineSegment(qpoints[-1], qpoints[0], style=None, color=color, width=width_px)
        line.layer_name = layer_name
        line._layer_name = layer_name
        line._from_dxf_import = True
        line._legacy_linetype = linetype
        objs.append(line)
    return objs if objs else None


def _spline_point_to_xy(p):
    """Приводит точку из ezdxf (Vec3, numpy, tuple) к (x, y)."""
    if hasattr(p, 'x') and hasattr(p, 'y'):
        return (float(p.x), float(p.y))
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

    # Надежно достаем имя слоя (проверяем и скрытый, и публичный атрибут)
    layer_name = getattr(obj, '_layer_name', getattr(obj, 'layer_name', '0'))
    
    # Спецстили (волнистая, с изломами) экспортируются как Continuous,
    # но имя слоя DXF совпадает с именем стиля — используем его.
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

def import_dxf_from_file(filepath: str, scene, layer_manager=None, style_manager=None):
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

    def process_entity(entity):
        if entity.dxftype() == 'INSERT':
            try:
                block = doc.blocks.get(entity.dxf.name)
                b_entities = list(block)
                if len(b_entities) == 4 and all(e.dxftype() == 'LINE' for e in b_entities):
                    xs, ys = [], []
                    for e in b_entities:
                        xs.extend([e.dxf.start.x, e.dxf.end.x])
                        ys.extend([e.dxf.start.y, e.dxf.end.y])
                    ins = entity.dxf.insert
                    sx, sy = entity.dxf.xscale, entity.dxf.yscale
                    real_min_x = ins.x + min(xs) * sx
                    real_max_x = ins.x + max(xs) * sx
                    real_min_y = ins.y + min(ys) * sy
                    real_max_y = ins.y + max(ys) * sy
                    color = _entity_qcolor(doc, b_entities[0])
                    layer = _entity_layer_name(b_entities[0])
                    if layer == '0': layer = _entity_layer_name(entity)
                    rect = Rectangle(
                        QPointF(real_min_x, real_min_y), QPointF(real_max_x, real_max_y),
                        style=None, color=color, width=_entity_lineweight_px(doc, b_entities[0])
                    )
                    rect.layer_name = layer
                    rect._from_dxf_import = True
                    return [rect]
                
                objs = []
                for sub_entity in entity.virtual_entities():
                    res = process_entity(sub_entity)
                    if res:
                        if isinstance(res, list): objs.extend(res)
                        else: objs.append(res)
                return objs
            except Exception as e:
                print(f"Ошибка чтения блока: {e}")
                return None
        
        # --- УНИВЕРСАЛЬНАЯ ЗАЩИТА (МАГИЯ XDATA) ---
        # Ловит твои идеальные фигуры до того, как они попадут в кривые обработчики DXF
        xdata_obj = _restore_from_xdata(doc, entity)
        if xdata_obj is not None:
            return xdata_obj
            
        # --- ОБЫЧНЫЙ ИМПОРТ ---
        # Для чужих файлов (T-FLEX, AutoCAD и т.д.)
        if entity.dxftype() in handlers:
            return handlers[entity.dxftype()](doc, entity)
        return None

    for entity in msp:
        try:
            obj = process_entity(entity)
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