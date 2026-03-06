"""
Панель управления слоями чертежа.
"""
from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout, QPushButton,
                               QListWidget, QListWidgetItem, QDialog, QFormLayout,
                               QDialogButtonBox, QLineEdit, QDoubleSpinBox,
                               QComboBox, QCheckBox, QMessageBox, QWidget,
                               QColorDialog)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPixmap, QIcon

from core.layers import Layer, LayerManager


class LayerEditDialog(QDialog):
    """Диалог редактирования свойств слоя."""

    def __init__(self, layer: Layer = None, parent=None, is_new=False):
        super().__init__(parent)
        self.setWindowTitle("Новый слой" if is_new else "Редактирование слоя")
        self.setMinimumWidth(320)
        self._color = QColor(layer.color) if layer else QColor(0, 0, 0)

        layout = QFormLayout()

        # Имя
        self.name_edit = QLineEdit()
        if layer:
            self.name_edit.setText(layer.name)
        if layer and layer.is_default:
            self.name_edit.setEnabled(False)
        layout.addRow("Имя слоя:", self.name_edit)

        # Цвет
        color_layout = QHBoxLayout()
        self.color_btn = QPushButton()
        self.color_btn.setFixedSize(60, 24)
        self._update_color_button()
        self.color_btn.clicked.connect(self._pick_color)
        color_layout.addWidget(self.color_btn)
        color_layout.addStretch()
        layout.addRow("Цвет:", color_layout)

        # Тип линии
        self.linetype_combo = QComboBox()
        self.linetype_combo.addItems(["Continuous", "DASHED", "DASHDOT", "DASHDOT2"])
        if layer:
            idx = self.linetype_combo.findText(layer.linetype)
            if idx >= 0:
                self.linetype_combo.setCurrentIndex(idx)
        layout.addRow("Тип линии:", self.linetype_combo)

        # Толщина
        self.lineweight_spin = QDoubleSpinBox()
        self.lineweight_spin.setRange(0.05, 2.0)
        self.lineweight_spin.setSingleStep(0.1)
        self.lineweight_spin.setSuffix(" мм")
        self.lineweight_spin.setValue(layer.lineweight if layer else 0.8)
        layout.addRow("Толщина:", self.lineweight_spin)

        # Видимость
        self.visible_check = QCheckBox("Видимый")
        self.visible_check.setChecked(layer.visible if layer else True)
        layout.addRow("", self.visible_check)

        # Блокировка
        self.locked_check = QCheckBox("Заблокирован")
        self.locked_check.setChecked(layer.locked if layer else False)
        layout.addRow("", self.locked_check)

        # Кнопки OK / Cancel
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self.setLayout(layout)

    def _update_color_button(self):
        pixmap = QPixmap(60, 24)
        pixmap.fill(self._color)
        self.color_btn.setIcon(QIcon(pixmap))
        self.color_btn.setIconSize(pixmap.size())

    def _pick_color(self):
        color = QColorDialog.getColor(self._color, self, "Цвет слоя")
        if color.isValid():
            self._color = color
            self._update_color_button()

    def get_values(self):
        return {
            'name': self.name_edit.text().strip(),
            'color': QColor(self._color),
            'linetype': self.linetype_combo.currentText(),
            'lineweight': self.lineweight_spin.value(),
            'visible': self.visible_check.isChecked(),
            'locked': self.locked_check.isChecked(),
        }


class LayerPanel(QGroupBox):
    """Панель управления слоями в боковой панели."""

    current_layer_changed = Signal(str)
    layers_changed = Signal()  # для обновления canvas

    def __init__(self, layer_manager: LayerManager, parent=None, scene=None):
        super().__init__("Слои", parent)
        self.layer_manager = layer_manager
        self.scene = scene
        self._init_ui()

        layer_manager.layer_added.connect(lambda _: self.refresh_list())
        layer_manager.layer_removed.connect(lambda _: self.refresh_list())
        layer_manager.layer_changed.connect(lambda _: self.refresh_list())
        layer_manager.current_layer_changed.connect(self._on_current_changed)

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(4)

        self.layer_list = QListWidget()
        self.layer_list.setMaximumHeight(150)
        self.layer_list.itemClicked.connect(self._on_item_clicked)
        self.layer_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.layer_list)

        # Кнопки
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        self.add_btn = QPushButton("Создать")
        self.add_btn.clicked.connect(self.create_layer)
        btn_row.addWidget(self.add_btn)

        self.edit_btn = QPushButton("Редактировать")
        self.edit_btn.clicked.connect(self.edit_selected_layer)
        btn_row.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("Удалить")
        self.delete_btn.clicked.connect(self.delete_selected_layer)
        self.delete_btn.setEnabled(False)
        btn_row.addWidget(self.delete_btn)

        layout.addLayout(btn_row)

        self.setLayout(layout)
        self.refresh_list()

    def refresh_list(self):
        self.layer_list.clear()
        if not self.layer_manager:
            return

        # Подсчитываем объекты на каждом слое
        obj_counts = {}
        if self.scene:
            for obj in self.scene.get_objects():
                ln = getattr(obj, '_layer_name', '0')
                obj_counts[ln] = obj_counts.get(ln, 0) + 1

        current_name = self.layer_manager.get_current_layer_name()
        for layer in self.layer_manager.get_all_layers():
            vis = "\u25C9" if layer.visible else "\u25CB"  # ◉ / ○
            lock = "\U0001F512" if layer.locked else ""  # 🔒
            marker = "\u25B6 " if layer.name == current_name else "   "
            count = obj_counts.get(layer.name, 0)
            text = f"{marker}{vis} {lock} {layer.name} ({count})"

            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, layer.name)

            # Иконка цвета
            pixmap = QPixmap(16, 16)
            pixmap.fill(layer.color)
            item.setIcon(QIcon(pixmap))

            if not layer.visible:
                item.setForeground(QColor(180, 180, 180))

            self.layer_list.addItem(item)

        self.delete_btn.setEnabled(False)

    def _on_item_clicked(self, item):
        name = item.data(Qt.UserRole)
        layer = self.layer_manager.get_layer(name)
        # Одинарный клик — делаем текущим
        self.layer_manager.set_current_layer(name)
        # Обновляем кнопку удаления (после смены текущего слоя)
        self.delete_btn.setEnabled(layer is not None and not layer.is_default)

    def _on_item_double_clicked(self, item):
        name = item.data(Qt.UserRole)
        self._edit_layer(name)

    def _on_current_changed(self, name):
        self.current_layer_changed.emit(name)
        self.refresh_list()

    def create_layer(self):
        dlg = LayerEditDialog(parent=self, is_new=True)
        if dlg.exec() == QDialog.Accepted:
            vals = dlg.get_values()
            if not vals['name']:
                QMessageBox.warning(self, "Ошибка", "Имя слоя не может быть пустым.")
                return
            try:
                layer = Layer(vals['name'], vals['color'], vals['linetype'],
                              vals['lineweight'], vals['visible'], vals['locked'])
                self.layer_manager.add_layer(layer)
                self.layer_manager.set_current_layer(layer.name)
                self.layers_changed.emit()
            except ValueError as e:
                QMessageBox.warning(self, "Ошибка", str(e))

    def edit_selected_layer(self):
        item = self.layer_list.currentItem()
        if not item:
            return
        name = item.data(Qt.UserRole)
        self._edit_layer(name)

    def _edit_layer(self, name: str):
        layer = self.layer_manager.get_layer(name)
        if not layer:
            return
        dlg = LayerEditDialog(layer, parent=self)
        if dlg.exec() == QDialog.Accepted:
            vals = dlg.get_values()
            new_name = vals['name']
            # Переименование
            if new_name != layer.name and not layer.is_default:
                try:
                    self.layer_manager.rename_layer(layer.name, new_name)
                except ValueError as e:
                    QMessageBox.warning(self, "Ошибка", str(e))
                    return
            # Обновляем свойства
            layer.color = vals['color']
            layer.linetype = vals['linetype']
            layer.lineweight = vals['lineweight']
            layer.visible = vals['visible']
            layer.locked = vals['locked']
            self.layer_manager.notify_layer_changed(layer)
            self.layers_changed.emit()

    def delete_selected_layer(self):
        item = self.layer_list.currentItem()
        if not item:
            return
        name = item.data(Qt.UserRole)
        layer = self.layer_manager.get_layer(name)
        if not layer or layer.is_default:
            return
        reply = QMessageBox.question(
            self, "Удаление слоя",
            f"Удалить слой \"{name}\"?\nОбъекты будут перемещены на слой \"0\".",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                self.layer_manager.remove_layer(name)
                self.layers_changed.emit()
            except ValueError as e:
                QMessageBox.warning(self, "Ошибка", str(e))
