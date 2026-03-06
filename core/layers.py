"""
Система слоёв для организации геометрических объектов.
"""
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor


class Layer:
    """Слой чертежа с визуальными свойствами и состоянием."""

    def __init__(self, name: str, color: QColor = None, linetype: str = "Continuous",
                 lineweight: float = 0.8, visible: bool = True, locked: bool = False,
                 is_default: bool = False):
        self._name = name
        self._color = color if color else QColor(0, 0, 0)
        self._linetype = linetype
        self._lineweight = lineweight
        self._visible = visible
        self._locked = locked
        self._is_default = is_default

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value: str):
        if self._is_default:
            raise ValueError("Нельзя переименовать слой по умолчанию")
        self._name = value

    @property
    def color(self):
        return self._color

    @color.setter
    def color(self, value: QColor):
        self._color = value

    @property
    def linetype(self):
        return self._linetype

    @linetype.setter
    def linetype(self, value: str):
        self._linetype = value

    @property
    def lineweight(self):
        return self._lineweight

    @lineweight.setter
    def lineweight(self, value: float):
        self._lineweight = value

    @property
    def visible(self):
        return self._visible

    @visible.setter
    def visible(self, value: bool):
        self._visible = value

    @property
    def locked(self):
        return self._locked

    @locked.setter
    def locked(self, value: bool):
        self._locked = value

    @property
    def is_default(self):
        return self._is_default


class LayerManager(QObject):
    """Менеджер слоёв. Управляет списком слоёв и текущим активным слоем."""

    layer_added = Signal(object)
    layer_removed = Signal(str)
    layer_changed = Signal(object)
    current_layer_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layers = {}
        self._current_layer_name = None
        self._initialize_default_layers()

    def _initialize_default_layers(self):
        default = Layer("0", QColor(0, 0, 0), "Continuous", 0.8,
                        visible=True, locked=False, is_default=True)
        self._layers["0"] = default
        self._current_layer_name = "0"

    def get_layer(self, name: str):
        return self._layers.get(name)

    def get_all_layers(self):
        return list(self._layers.values())

    def get_layer_names(self):
        return list(self._layers.keys())

    def get_current_layer(self):
        return self._layers.get(self._current_layer_name)

    def get_current_layer_name(self):
        return self._current_layer_name

    def set_current_layer(self, layer_name: str):
        if layer_name in self._layers:
            self._current_layer_name = layer_name
            self.current_layer_changed.emit(layer_name)

    def add_layer(self, layer: Layer):
        if layer.name in self._layers:
            raise ValueError(f"Слой '{layer.name}' уже существует")
        self._layers[layer.name] = layer
        self.layer_added.emit(layer)

    def remove_layer(self, name: str):
        if name not in self._layers:
            return False
        layer = self._layers[name]
        if layer.is_default:
            raise ValueError("Нельзя удалить слой по умолчанию")
        del self._layers[name]
        if self._current_layer_name == name:
            self._current_layer_name = "0"
            self.current_layer_changed.emit("0")
        self.layer_removed.emit(name)
        return True

    def rename_layer(self, old_name: str, new_name: str):
        if old_name not in self._layers:
            raise ValueError(f"Слой '{old_name}' не найден")
        layer = self._layers[old_name]
        if layer.is_default:
            raise ValueError("Нельзя переименовать слой по умолчанию")
        if new_name in self._layers:
            raise ValueError(f"Слой '{new_name}' уже существует")
        layer._name = new_name
        self._layers[new_name] = self._layers.pop(old_name)
        if self._current_layer_name == old_name:
            self._current_layer_name = new_name
        self.layer_changed.emit(layer)

    def is_layer_visible(self, layer_name: str) -> bool:
        layer = self._layers.get(layer_name)
        return layer.visible if layer else True

    def is_layer_locked(self, layer_name: str) -> bool:
        layer = self._layers.get(layer_name)
        return layer.locked if layer else False

    def notify_layer_changed(self, layer):
        """Уведомляет о изменении свойств слоя."""
        self.layer_changed.emit(layer)
