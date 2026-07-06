from __future__ import annotations

import os
import json
import sys
import webbrowser
from pathlib import Path

from PyQt6.QtCore import QAbstractAnimation, QAbstractListModel, QDir, QEasingCurve, QEventLoop, QMimeData, QModelIndex, QObject, QPropertyAnimation, QRect, QThread, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QDrag, QFont, QIcon, QImage, QPainter, QPen, QPixmap, QPixmapCache
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QTreeView,
    QMainWindow,
    QPushButton,
    QRadioButton,
    QProgressBar,
    QScrollArea,
    QSplitter,
    QAbstractItemView,
    QVBoxLayout,
    QWidget,
)

from hd2mm.core.config import ConfigService
from hd2mm.core.arsenal_importer import ArsenalImportService
from hd2mm.core.importer import ModImporter
from hd2mm.core.installer import InstallService
from hd2mm.core.legacy import LegacyMigrationService
from hd2mm.core.locks import ModLockService
from hd2mm.core.models import ImportOptions
from hd2mm.core.options import OptionService
from hd2mm.core.paths import ICON_FILE, ensure_workspace_dirs
from hd2mm.core.repository import ModRepository
from hd2mm.core.war_api import fetch_current_war_status, load_war_status_cache
from hd2mm.ui.dialogs import ImageLabel, square_thumbnail, zh
from hd2mm.ui.mod_list_view import ModListDelegate, ModListModel, ModListView


class OrderSaveWorker(QObject):
    finished = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, repository: ModRepository, orders: list[tuple[str, int]]) -> None:
        super().__init__()
        self.repository = repository
        self.orders = orders

    def run(self) -> None:
        try:
            for mod_id, order in self.orders:
                self.repository.save_order(mod_id, order)
            self.finished.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class WarStatusWorker(QObject):
    loaded = pyqtSignal(str)
    failed = pyqtSignal(str)

    def run(self) -> None:
        try:
            self.loaded.emit(fetch_current_war_status().display_text())
        except Exception as exc:
            self.failed.emit(str(exc))


class ModLoadWorker(QObject):
    progressChanged = pyqtSignal(int, str)
    loaded = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, repository: ModRepository, legacy_migrator: LegacyMigrationService) -> None:
        super().__init__()
        self.repository = repository
        self.legacy_migrator = legacy_migrator

    def run(self) -> None:
        try:
            self.legacy_migrator.migrate_runtime_mods()
            mods = self.repository.list_mods_with_progress(
                lambda current, total, name: self.progressChanged.emit(
                    int((current / total) * 100) if total else 100,
                    f"{current}/{total}  {name}",
                )
            )
            self.loaded.emit(mods)
        except Exception as exc:
            self.failed.emit(str(exc))


class ClickOverlay(QFrame):
    clicked = pyqtSignal()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.hide()
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class SmoothScrollArea(QScrollArea):
    def __init__(self) -> None:
        super().__init__()
        self.smooth_scroll_target = 0
        self.smooth_scroll_animation = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self.smooth_scroll_animation.setDuration(150)
        self.smooth_scroll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def wheelEvent(self, event) -> None:
        scrollbar = self.verticalScrollBar()
        delta = event.pixelDelta().y()
        if not delta:
            delta = event.angleDelta().y() // 2
        if not delta:
            super().wheelEvent(event)
            return
        if self.smooth_scroll_animation.state() != QAbstractAnimation.State.Running:
            self.smooth_scroll_target = scrollbar.value()
        self.smooth_scroll_target = max(scrollbar.minimum(), min(scrollbar.maximum(), self.smooth_scroll_target - delta))
        self.smooth_scroll_animation.stop()
        self.smooth_scroll_animation.setStartValue(scrollbar.value())
        self.smooth_scroll_animation.setEndValue(self.smooth_scroll_target)
        self.smooth_scroll_animation.start()
        event.accept()


class ModListWidget(QListWidget):
    blankClicked = pyqtSignal()
    leftClicked = pyqtSignal()
    modIdsDropped = pyqtSignal(list, int)
    MIME_TYPE = "application/x-hd2mm-mod-ids"

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.smooth_scroll_target = 0
        self.smooth_scroll_animation = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self.smooth_scroll_animation.setDuration(150)
        self.smooth_scroll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.drop_indicator = QFrame(self.viewport())
        self.drop_indicator.setObjectName("dropIndicator")
        self.drop_indicator.hide()

    def mousePressEvent(self, event) -> None:
        self.smooth_scroll_animation.stop()
        self.leftClicked.emit()
        if self.itemAt(event.position().toPoint()) is None:
            self.clearSelection()
            self.blankClicked.emit()
        super().mousePressEvent(event)

    def wheelEvent(self, event) -> None:
        scrollbar = self.verticalScrollBar()
        delta = event.pixelDelta().y()
        if not delta:
            delta = event.angleDelta().y() // 2
        if not delta:
            super().wheelEvent(event)
            return
        if self.smooth_scroll_animation.state() != QAbstractAnimation.State.Running:
            self.smooth_scroll_target = scrollbar.value()
        self.smooth_scroll_target = max(scrollbar.minimum(), min(scrollbar.maximum(), self.smooth_scroll_target - delta))
        self.smooth_scroll_animation.stop()
        self.smooth_scroll_animation.setStartValue(scrollbar.value())
        self.smooth_scroll_animation.setEndValue(self.smooth_scroll_target)
        self.smooth_scroll_animation.start()
        event.accept()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(self.MIME_TYPE):
            self.show_drop_indicator(self._drop_target_index(event.position().toPoint()))
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat(self.MIME_TYPE):
            self.show_drop_indicator(self._drop_target_index(event.position().toPoint()))
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event) -> None:
        self.drop_indicator.hide()
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        self.drop_indicator.hide()
        if not event.mimeData().hasFormat(self.MIME_TYPE):
            super().dropEvent(event)
            return
        try:
            mod_ids = json.loads(bytes(event.mimeData().data(self.MIME_TYPE)).decode("utf-8"))
        except (TypeError, ValueError, UnicodeDecodeError):
            event.ignore()
            return
        target_index = self._drop_target_index(event.position().toPoint())
        self.modIdsDropped.emit(mod_ids, target_index)
        event.acceptProposedAction()

    def show_drop_indicator(self, target_index: int) -> None:
        if self.count() == 0:
            y = 0
        elif target_index >= self.count():
            y = self.visualItemRect(self.item(self.count() - 1)).bottom() + 1
        else:
            y = self.visualItemRect(self.item(target_index)).top()
        self.drop_indicator.setGeometry(0, max(0, y - 1), self.viewport().width(), 3)
        self.drop_indicator.raise_()
        self.drop_indicator.show()

    def _drop_target_index(self, position) -> int:
        item = self.itemAt(position)
        if item is None:
            return self.count()
        row = self.row(item)
        rect = self.visualItemRect(item)
        return row + 1 if position.y() > rect.center().y() else row




class ToggleSwitch(QCheckBox):
    
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(74, 40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setText("")
        self.setStyleSheet("QCheckBox::indicator { width: 0px; height: 0px; }")

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#2563eb"), 2))
        painter.setBrush(QBrush(QColor("#111827")))
        painter.drawRoundedRect(10, 8, 54, 24, 12, 12)
        knob_x = 40 if self.isChecked() else 14
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#2563eb") if self.isChecked() else QColor("#94a3b8")))
        painter.drawEllipse(knob_x, 11, 18, 18)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle()
            event.accept()
            return
        super().mousePressEvent(event)


    def hitButton(self, position) -> bool:
        return self.rect().contains(position)

class ModListRow(QWidget):
    enabledChanged = pyqtSignal(str, bool)
    editRequested = pyqtSignal(str)
    selectRequested = pyqtSignal(str, object)
    checkedForBulk = pyqtSignal(str, bool)
    dragRequested = pyqtSignal(str)

    def __init__(self, mod, thumbnail: QPixmap) -> None:
        super().__init__()
        self.setObjectName("modRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mod_id = mod.id
        self.press_pos = None
        self.drag_started = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(14)
        self.bulk_check = QCheckBox()
        self.bulk_check.setObjectName("bulkRowCheck")
        self.bulk_check.toggled.connect(lambda checked: self.checkedForBulk.emit(self.mod_id, checked))
        layout.addWidget(self.bulk_check)
        self.enabled_check = ToggleSwitch()
        self.enabled_check.setChecked(mod.enabled)
        self.enabled_check.toggled.connect(lambda checked: self.enabledChanged.emit(self.mod_id, checked))
        layout.addWidget(self.enabled_check)
        self.icon_label = QLabel()
        self.icon_label.setObjectName("modThumb")
        self.icon_label.setFixedSize(72, 72)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setPixmap(thumbnail)
        layout.addWidget(self.icon_label)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(6)
        self.name_label = QLabel(mod.name)
        self.name_label.setObjectName("modRowTitle")
        self.name_label.setWordWrap(True)
        text_layout.addWidget(self.name_label)
        self.description_label = QLabel(mod.description or "")
        self.description_label.setObjectName("modDescription")
        self.description_label.setWordWrap(True)
        text_layout.addWidget(self.description_label)
        chips = QHBoxLayout()
        chips.setSpacing(6)
        self.category_chip = self._chip(mod.category or zh("\\u672a\\u5206\\u7c7b"))
        self.date_chip = self._chip(self._date_text(mod.updated_at))
        chips.addWidget(self.category_chip)
        chips.addWidget(self.date_chip)
        chips.addStretch()
        text_layout.addLayout(chips)
        layout.addLayout(text_layout, 1)

    def mousePressEvent(self, event) -> None:
        point = event.position().toPoint()
        if self.bulk_check.isVisible() and self.bulk_check.geometry().contains(point):
            super().mousePressEvent(event)
            return
        self.press_pos = event.position().toPoint()
        self.drag_started = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.press_pos is None or self.drag_started:
            super().mouseMoveEvent(event)
            return
        distance = (event.position().toPoint() - self.press_pos).manhattanLength()
        if distance >= QApplication.startDragDistance():
            self.drag_started = True
            self.dragRequested.emit(self.mod_id)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        point = event.position().toPoint()
        should_open = self.press_pos is not None and not self.drag_started and not self.enabled_check.geometry().contains(point)
        self.press_pos = None
        was_dragging = self.drag_started
        self.drag_started = False
        if should_open and not was_dragging:
            self.editRequested.emit(self.mod_id)
        super().mouseReleaseEvent(event)

    def update_mod(self, mod, thumbnail: QPixmap) -> None:
        self.mod_id = mod.id
        self.name_label.setText(mod.name)
        self.description_label.setText(mod.description or "")
        self.category_chip.setText(mod.category or zh("\\u672a\\u5206\\u7c7b"))
        self.date_chip.setText(self._date_text(mod.updated_at))
        self.icon_label.setPixmap(thumbnail)
        self.enabled_check.blockSignals(True)
        self.enabled_check.setChecked(mod.enabled)
        self.enabled_check.blockSignals(False)
        self.enabled_check.update()

    def set_bulk_mode(self, enabled: bool) -> None:
        self.bulk_check.setVisible(True)

    def set_bulk_checked(self, checked: bool) -> None:
        self.bulk_check.blockSignals(True)
        self.bulk_check.setChecked(checked)
        self.bulk_check.blockSignals(False)

    def mouseDoubleClickEvent(self, event) -> None:
        if not self.enabled_check.geometry().contains(event.position().toPoint()):
            self.editRequested.emit(self.mod_id)
        super().mouseDoubleClickEvent(event)

    def _chip(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("chip")
        return label

    def _date_text(self, updated_at) -> str:
        return updated_at.strftime("%y/%m/%d") if updated_at else "--/--/--"


class MainWindow(QMainWindow):
    
    def __init__(self, startup_imports: list[Path] | None = None) -> None:
        super().__init__()
        ensure_workspace_dirs()
        self.config = ConfigService()
        self.repository = ModRepository()
        self.options = OptionService()
        self.locks = ModLockService()
        self.legacy_migrator = LegacyMigrationService(self.repository, self.options)
        self.install_dir = self.config.load_install_dir()
        self.importer = ModImporter(self.repository, self.options)
        self.arsenal_importer = ArsenalImportService(self.repository, self.options)
        self.installer = InstallService(self.repository, self.options, self.install_dir)
        self.mods = []
        self.visible_mods = []
        self.mod_list_model: ModListModel | None = None
        self.bulk_selected_ids: set[str] = set()
        self.locked_mod_ids: set[str] = set()
        self.suppress_next_drawer_open = False
        self.loading_thread: QThread | None = None
        self.loading_worker: ModLoadWorker | None = None
        self.order_save_thread: QThread | None = None
        self.order_save_worker: OrderSaveWorker | None = None
        self.war_status_thread: QThread | None = None
        self.war_status_worker: WarStatusWorker | None = None
        self.pending_order_save: list[tuple[str, int]] | None = None
        self.order_save_error: str | None = None
        self.selected_mod_id: str | None = None
        self.drawer_animation: QPropertyAnimation | None = None
        self.startup_import_message: tuple[str, str, bool] | None = None
        self.setWindowTitle("Helldivers 2 Mod Manager")
        self.resize(1180, 760)
        self.setAcceptDrops(True)
        if ICON_FILE.exists():
            self.setWindowIcon(QIcon(str(ICON_FILE)))
        self._build()
        self.start_war_status_load()
        self.import_startup_mods(startup_imports or [])
        self.show_loading_overlay(0, zh("\\u6b63\\u5728\\u626b\\u63cf Mod..."))
        self.start_async_mod_load()

    def _build(self) -> None:
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_sidebar())
        splitter.addWidget(self._build_content())
        splitter.setSizes([290, 860])
        layout.addWidget(splitter)
        self.setCentralWidget(root)
        self.loading_overlay = QFrame(root)
        self.loading_overlay.setObjectName("loadingOverlay")
        self.loading_overlay.setGeometry(root.rect())
        overlay_layout = QVBoxLayout(self.loading_overlay)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        overlay_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_box = QFrame()
        loading_box.setObjectName("loadingBox")
        loading_box.setFixedWidth(460)
        box_layout = QVBoxLayout(loading_box)
        box_layout.setContentsMargins(22, 18, 22, 18)
        box_layout.setSpacing(12)
        self.loading_label = QLabel(zh("\\u6b63\\u5728\\u52a0\\u8f7d..."))
        self.loading_label.setObjectName("loadingLabel")
        self.loading_progress = QProgressBar()
        box_layout.addWidget(self.loading_label)
        box_layout.addWidget(self.loading_progress)
        overlay_layout.addWidget(loading_box, 0, Qt.AlignmentFlag.AlignCenter)
        self.loading_overlay.hide()

    def _build_sidebar(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("sidePanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 18, 16, 16)
        layout.setSpacing(10)
        title = QLabel(zh("\\u8d85\\u7ea7\\u5730\\u7403\\u6218\\u51b5"))
        title.setObjectName("appTitle")
        layout.addWidget(title)
        self.war_status_label = QLabel(load_war_status_cache() or zh("\\u6b63\\u5728\\u540c\\u6b65 MO \\u548c\\u661f\\u7403\\u89e3\\u653e\\u8fdb\\u5ea6..."))
        self.war_status_label.setWordWrap(True)
        self.war_status_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.war_status_label.setObjectName("warStatusText")
        self.war_status_label.setMinimumWidth(220)
        self.war_status_scroll = SmoothScrollArea()
        self.war_status_scroll.setObjectName("warStatus")
        self.war_status_scroll.setWidgetResizable(True)
        self.war_status_scroll.setMinimumHeight(150)
        self.war_status_scroll.setMaximumHeight(240)
        self.war_status_scroll.setWidget(self.war_status_label)
        layout.addWidget(self.war_status_scroll)
        layout.addWidget(self._section_label(zh("\\u6d4f\\u89c8")))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(zh("\\u641c\\u7d22 Mod"))
        self.search_edit.textChanged.connect(self.apply_filters)
        layout.addWidget(self.search_edit)
        self.category_combo = QComboBox()
        self.category_combo.currentTextChanged.connect(self.apply_filters)
        layout.addWidget(self.category_combo)
        layout.addWidget(self._section_label(zh("\\u64cd\\u4f5c")))
        actions = [
            (zh("\\u5bfc\\u5165 Mod"), self.import_mod),
            (zh("\\u5e94\\u7528\\u5230\\u6e38\\u620f"), self.install_mods),
            (zh("\\u6e05\\u9664\\u6e38\\u620f Mod"), self.remove_game_mods),
            (zh("\\u9009\\u62e9\\u6e38\\u620f\\u76ee\\u5f55"), self.choose_game_dir),
            (zh("\\u542f\\u52a8\\u6e38\\u620f"), self.start_game),
        ]
        for index, (text, handler) in enumerate(actions):
            button = QPushButton(text)
            if index == 1:
                button.setObjectName("primaryButton")
            button.clicked.connect(handler)
            layout.addWidget(button)
        layout.addStretch()
        return panel

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    def _inline_edit(self, text: str, object_name: str) -> QLineEdit:
        edit = QLineEdit(text)
        edit.setObjectName(object_name)
        edit.setFrame(False)
        return edit

    def _build_content(self) -> QWidget:
        content = QWidget()
        layout = QHBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        list_panel = QFrame()
        self.list_panel = list_panel
        list_panel.setObjectName("listPanel")
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(14, 14, 14, 14)
        list_layout.setSpacing(10)
        list_header = QHBoxLayout()
        self.select_all_check = QCheckBox(zh("\\u5168\\u9009"))
        self.select_all_check.setObjectName("selectVisibleCheck")
        self.select_all_check.toggled.connect(self.toggle_select_all_visible)
        self.header_selected_count = QLabel("0")
        self.header_selected_count.setObjectName("headerSelectedCount")
        self.count_label = QLabel()
        self.count_label.setObjectName("muted")
        list_header.addWidget(self.select_all_check)
        list_header.addWidget(self.header_selected_count)
        list_header.addStretch()
        list_header.addWidget(self.count_label)
        list_layout.addLayout(list_header)
        self.mod_list = ModListView()
        self.mod_list_model = ModListModel(self._thumbnail)
        self.mod_list.setModel(self.mod_list_model)
        self.mod_list.setItemDelegate(ModListDelegate(self.mod_list))
        self.mod_list.modIdsDropped.connect(self.move_mods_to_index)
        self.mod_list.enabledChanged.connect(self.set_mod_enabled)
        self.mod_list.editRequested.connect(self.open_mod_drawer)
        self.mod_list.checkedForBulk.connect(self.set_mod_bulk_checked)
        self.mod_list.dragRequested.connect(self.start_mod_drag)
        list_layout.addWidget(self.mod_list)
        self.bulk_bar = self._build_bulk_bar()
        self.bulk_bar.hide()
        list_layout.addWidget(self.bulk_bar)
        self.left_overlay = ClickOverlay(list_panel)
        self.left_overlay.setObjectName("leftOverlay")
        self.left_overlay.clicked.connect(self.close_drawer)
        self.left_overlay.hide()
        layout.addWidget(list_panel, 2)
        self.detail_area = QScrollArea()
        self.detail_area.setWidgetResizable(True)
        self.detail_area.setObjectName("drawerPanel")
        self.detail_area.setMaximumWidth(0)
        self.detail_area.setMinimumWidth(0)
        self.detail_area.setFixedWidth(0)
        self.detail_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.detail_panel = QWidget()
        self.detail_panel.setMinimumWidth(0)
        self.detail_layout = QVBoxLayout(self.detail_panel)
        self.detail_layout.setContentsMargins(18, 18, 18, 18)
        self.detail_layout.setSpacing(14)
        self.detail_area.setWidget(self.detail_panel)
        layout.addWidget(self.detail_area)
        return content

    def _build_bulk_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("bulkBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        self.selected_count_label = QLabel(zh("\\u5df2\\u9009 0"))
        self.selected_count_label.setObjectName("bulkCount")
        enable_button = QPushButton(zh("\\u542f\\u7528"))
        disable_button = QPushButton(zh("\\u7981\\u7528"))
        lock_button = QPushButton(zh("\\u540c\\u6b65"))
        unlock_button = QPushButton(zh("\\u53d6\\u6d88\\u540c\\u6b65"))
        enable_button.clicked.connect(lambda: self.set_selected_mods_enabled(True))
        disable_button.clicked.connect(lambda: self.set_selected_mods_enabled(False))
        lock_button.clicked.connect(self.lock_selected_mods)
        unlock_button.clicked.connect(self.unlock_selected_mods)
        self.bulk_category_edit = QLineEdit()
        self.bulk_category_edit.setPlaceholderText(zh("\\u5206\\u7c7b"))
        apply_category = QPushButton(zh("\\u4fee\\u6539\\u5206\\u7c7b"))
        apply_category.clicked.connect(self.apply_category_to_selected)
        layout.addWidget(self.selected_count_label)
        layout.addWidget(enable_button)
        layout.addWidget(disable_button)
        layout.addWidget(lock_button)
        layout.addWidget(unlock_button)
        layout.addWidget(self.bulk_category_edit, 1)
        layout.addWidget(apply_category)
        return bar

    def refresh_mods(self) -> None:
        self.legacy_migrator.migrate_runtime_mods()
        self.mods = self.repository.list_mods()
        self.sync_lock_state()
        self._sync_categories()
        self.apply_filters()

    def start_async_mod_load(self) -> None:
        self.loading_thread = QThread(self)
        self.loading_worker = ModLoadWorker(self.repository, self.legacy_migrator)
        self.loading_worker.moveToThread(self.loading_thread)
        self.loading_thread.started.connect(self.loading_worker.run)
        self.loading_worker.progressChanged.connect(self.show_loading_overlay)
        self.loading_worker.loaded.connect(self.finish_async_mod_load)
        self.loading_worker.failed.connect(self.fail_async_mod_load)
        self.loading_worker.loaded.connect(self.loading_thread.quit)
        self.loading_worker.failed.connect(self.loading_thread.quit)
        self.loading_thread.finished.connect(self.loading_worker.deleteLater)
        self.loading_thread.finished.connect(self.loading_thread.deleteLater)
        self.loading_thread.start()

    def start_war_status_load(self) -> None:
        self.war_status_thread = QThread(self)
        self.war_status_worker = WarStatusWorker()
        self.war_status_worker.moveToThread(self.war_status_thread)
        self.war_status_thread.started.connect(self.war_status_worker.run)
        self.war_status_worker.loaded.connect(self.finish_war_status_load)
        self.war_status_worker.failed.connect(self.fail_war_status_load)
        self.war_status_worker.loaded.connect(self.war_status_thread.quit)
        self.war_status_worker.failed.connect(self.war_status_thread.quit)
        self.war_status_thread.finished.connect(self.war_status_worker.deleteLater)
        self.war_status_thread.finished.connect(self.war_status_thread.deleteLater)
        self.war_status_thread.start()

    def finish_war_status_load(self, text: str) -> None:
        self.war_status_label.setText(text)
        self.war_status_thread = None
        self.war_status_worker = None

    def fail_war_status_load(self, message: str) -> None:
        self.war_status_label.setText(zh("\\u6218\\u51b5\\u540c\\u6b65\\u5931\\u8d25\\uff0c\\u7a0d\\u540e\\u91cd\\u542f\\u7ba1\\u7406\\u5668\\u53ef\\u91cd\\u8bd5\\u3002") + f"\n{message}")
        self.war_status_thread = None
        self.war_status_worker = None

    def show_loading_overlay(self, value: int, text: str) -> None:
        if not hasattr(self, "loading_overlay"):
            return
        self.loading_label.setText(text)
        self.loading_progress.setValue(value)
        self.loading_overlay.show()
        self.loading_overlay.raise_()

    def finish_async_mod_load(self, mods: list) -> None:
        self.mods = mods
        self.sync_lock_state()
        self._sync_categories()
        self.loading_overlay.hide()
        self.apply_filters(show_render_overlay=False)
        if self.startup_import_message:
            title, message, is_error = self.startup_import_message
            self.startup_import_message = None
            QTimer.singleShot(0, lambda: self.show_error(title, message) if is_error else self.show_info(title, message))
        self.loading_thread = None
        self.loading_worker = None

    def fail_async_mod_load(self, message: str) -> None:
        self.loading_overlay.hide()
        self.show_error(zh("\\u52a0\\u8f7d\\u5931\\u8d25"), message)

    def import_startup_mods(self, sources: list[Path]) -> None:
        if not sources:
            return
        imported, errors = self.import_sources(sources)
        if errors:
            message = "\n".join(errors)
            if imported:
                message = zh("\\u5df2\\u5bfc\\u5165: ") + ", ".join(imported) + "\n" + message
            self.startup_import_message = (zh("\\u5bfc\\u5165\\u5931\\u8d25"), message, True)
            return
        self.startup_import_message = (zh("\\u5bfc\\u5165\\u5b8c\\u6210"), zh("\\u5df2\\u5bfc\\u5165: ") + ", ".join(imported), False)

    def import_sources(self, sources: list[Path]) -> tuple[list[str], list[str]]:
        imported: list[str] = []
        errors: list[str] = []
        for source in sources:
            try:
                if ArsenalImportService.is_arsenal_library(source):
                    count = self.arsenal_importer.import_library(source)
                    imported.append(str(count) + " HD2 Arsenal Mods")
                else:
                    mod_id = self.importer.import_mod(ImportOptions(source=source))
                    imported.append(self.repository.get(mod_id).name)
            except Exception as exc:
                errors.append(f"{source}: {exc}")
        return imported, errors

    def show_info(self, title: str, message: str) -> None:
        self._show_overlay_message("info", title, message, [(zh("\\u786e\\u5b9a"), True)])

    def show_error(self, title: str, message: str) -> None:
        self._show_overlay_message("error", title, message, [(zh("\\u786e\\u5b9a"), True)])

    def confirm(self, title: str, message: str) -> bool:
        return self._show_overlay_message("question", title, message, [(zh("\\u662f"), True), (zh("\\u5426"), False)])

    def _show_overlay_message(self, kind: str, title: str, message: str, actions: list[tuple[str, bool]]) -> bool:
        overlay = QFrame(self.centralWidget())
        overlay.setObjectName("messageOverlay")
        overlay.setGeometry(self.centralWidget().rect())
        overlay.raise_()
        overlay_layout = QVBoxLayout(overlay)
        overlay_layout.setContentsMargins(24, 24, 24, 24)
        overlay_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card = QFrame()
        card.setObjectName("messageCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 18)
        card_layout.setSpacing(14)
        header = QHBoxLayout()
        icon = QLabel(self._message_icon_text(kind))
        icon.setObjectName(f"messageIcon_{kind}")
        icon.setFixedSize(34, 34)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label = QLabel(title)
        title_label.setObjectName("messageTitle")
        header.addWidget(icon)
        header.addWidget(title_label, 1)
        card_layout.addLayout(header)
        body = QLabel(message)
        body.setObjectName("messageBody")
        body.setWordWrap(True)
        card_layout.addWidget(body)
        buttons = QHBoxLayout()
        buttons.addStretch()
        result = {"value": False}
        loop = QEventLoop(self)
        for index, (text, value) in enumerate(actions):
            button = QPushButton(text)
            button.setObjectName("messagePrimaryButton" if index == 0 else "messageSecondaryButton")
            button.clicked.connect(lambda _checked=False, selected=value: self._finish_overlay_message(overlay, loop, result, selected))
            buttons.addWidget(button)
        card_layout.addLayout(buttons)
        overlay_layout.addWidget(card, 0, Qt.AlignmentFlag.AlignCenter)
        overlay.show()
        loop.exec()
        return result["value"]

    def _finish_overlay_message(self, overlay: QFrame, loop: QEventLoop, result: dict, value: bool) -> None:
        result["value"] = value
        overlay.deleteLater()
        loop.quit()

    def _message_icon_text(self, kind: str) -> str:
        return {"info": "i", "error": "!", "question": "?"}.get(kind, "i")

    def dragEnterEvent(self, event) -> None:
        if self._event_import_sources(event):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event) -> None:
        sources = self._event_import_sources(event)
        if not sources:
            super().dropEvent(event)
            return
        imported, errors = self.import_sources(sources)
        self.refresh_mods()
        if errors:
            self.show_error(zh("\\u5bfc\\u5165\\u5931\\u8d25"), "\n".join(errors))
        elif imported:
            self.show_info(zh("\\u5bfc\\u5165\\u5b8c\\u6210"), zh("\\u5df2\\u5bfc\\u5165: ") + ", ".join(imported))
        event.acceptProposedAction()

    def _event_import_sources(self, event) -> list[Path]:
        mime = event.mimeData()
        if not mime.hasUrls():
            return []
        sources: list[Path] = []
        for url in mime.urls():
            path_text = url.toLocalFile()
            if not path_text:
                continue
            source = Path(path_text)
            if source.is_dir() or source.suffix.lower() in {".zip", ".rar", ".7z"}:
                sources.append(source)
        return sources

    def apply_filters(self, *args, show_render_overlay: bool = False) -> None:
        search_text = self.search_edit.text().strip().lower() if hasattr(self, "search_edit") else ""
        category = self.category_combo.currentData() if hasattr(self, "category_combo") else None
        self.visible_mods = []
        for mod in self.mods:
            haystack = " ".join([mod.name, mod.author, mod.description, mod.category]).lower()
            if search_text and search_text not in haystack:
                continue
            if category is not None and (mod.category or zh("\\u672a\\u5206\\u7c7b")) != category:
                continue
            self.visible_mods.append(mod)
        self.start_visible_render(show_render_overlay)
        if hasattr(self, "count_label"):
            self.count_label.setText(f"{len(self.visible_mods)} / {len(self.mods)}")
        self.sync_selection_tools()
        if not self.mods:
            self._clear_detail(zh("\\u8fd8\\u6ca1\\u6709 Mod\\uff0c\\u5148\\u5bfc\\u5165\\u4e00\\u4e2a\\u5427\\u3002"))
            self._animate_drawer(False)
        elif not self.visible_mods:
            self._clear_detail(zh("\\u6ca1\\u6709\\u5339\\u914d\\u7684 Mod"))
            self._animate_drawer(False)
        elif self.selected_mod_id:
            self.show_mod_options(self.selected_mod_id)

    def start_visible_render(self, show_overlay: bool = False) -> None:
        if show_overlay and hasattr(self, "loading_overlay"):
            self.loading_overlay.hide()
        if self.mod_list_model:
            self.mod_list_model.set_mods(self.visible_mods)


    def toggle_select_all_visible(self, checked: bool) -> None:
        visible_ids = {mod.id for mod in self.visible_mods}
        if checked:
            self.bulk_selected_ids.update(visible_ids)
        else:
            self.bulk_selected_ids.difference_update(visible_ids)
        self.sync_selection_tools()

    def _sync_categories(self) -> None:
        if not hasattr(self, "category_combo"):
            return
        current = self.category_combo.currentData()
        categories = sorted({mod.category or zh("\\u672a\\u5206\\u7c7b") for mod in self.mods})
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItem(zh("\\u5168\\u90e8\\u5206\\u7c7b"), None)
        for category in categories:
            self.category_combo.addItem(category, category)
        index = self.category_combo.findData(current)
        self.category_combo.setCurrentIndex(index if index >= 0 else 0)
        self.category_combo.blockSignals(False)

    def sync_lock_state(self) -> None:
        valid_ids = {mod.id for mod in self.mods}
        self.locks.prune(valid_ids)
        self.locked_mod_ids = set(self.locks.lock_map())
        if self.mod_list_model:
            self.mod_list_model.set_locked_ids(self.locked_mod_ids)

    def sync_selection_tools(self) -> None:
        visible_ids = {mod.id for mod in self.visible_mods}
        valid_ids = {mod.id for mod in self.mods}
        self.bulk_selected_ids.intersection_update(valid_ids)
        self.bulk_selected_ids = self.locks.expand_ids(self.bulk_selected_ids).intersection(valid_ids)
        selected_count = len(self.bulk_selected_ids)
        if hasattr(self, "selected_count_label"):
            self.selected_count_label.setText(zh("\\u5df2\\u9009 ") + str(selected_count))
        if hasattr(self, "header_selected_count"):
            self.header_selected_count.setText(str(selected_count))
        if self.mod_list_model:
            self.mod_list_model.set_bulk_selected_ids(self.bulk_selected_ids)
            self.mod_list_model.set_locked_ids(self.locked_mod_ids)
        if hasattr(self, "select_all_check"):
            self.select_all_check.blockSignals(True)
            if not self.visible_mods:
                self.select_all_check.setChecked(False)
                self.select_all_check.setEnabled(False)
            else:
                self.select_all_check.setEnabled(True)
                self.select_all_check.setChecked(visible_ids.issubset(self.bulk_selected_ids))
            self.select_all_check.blockSignals(False)
        if hasattr(self, "bulk_bar"):
            self.bulk_bar.setVisible(selected_count > 0)

    def selected_mod_ids(self) -> list[str]:
        return list(self.locks.expand_ids(self.bulk_selected_ids))

    def set_mod_bulk_checked(self, mod_id: str, checked: bool) -> None:
        mod_ids = self.locks.linked_ids(mod_id)
        if checked:
            self.bulk_selected_ids.update(mod_ids)
        else:
            self.bulk_selected_ids.difference_update(mod_ids)
        self.sync_selection_tools()

    def select_mod_row(self, mod_id: str, modifiers) -> None:
        self.set_mod_bulk_checked(mod_id, True)

    def lock_selected_mods(self) -> None:
        selected_ids = set(self.selected_mod_ids())
        if len(selected_ids) < 2:
            return
        self.locks.lock(selected_ids)
        self.sync_lock_state()
        self.sync_selection_tools()

    def unlock_selected_mods(self) -> None:
        selected_ids = set(self.selected_mod_ids())
        if not selected_ids:
            return
        self.locks.unlock(selected_ids)
        self.sync_lock_state()
        self.sync_selection_tools()

    def apply_category_to_selected(self) -> None:
        category = self.bulk_category_edit.text().strip()
        selected_ids = self.selected_mod_ids()
        if not selected_ids:
            return
        selected_id_set = set(selected_ids)
        for mod_id in selected_ids:
            mod = self.repository.get(mod_id)
            self.repository.save_meta(mod.id, mod.name, mod.author, mod.link, mod.order, mod.enabled, mod.description, category)
        for mod in self.mods:
            if mod.id in selected_id_set:
                mod.category = category
        self._sync_categories()
        self.apply_filters()

    def set_selected_mods_enabled(self, enabled: bool) -> None:
        selected_ids = self.locks.expand_ids(set(self.selected_mod_ids()))
        for mod_id in selected_ids:
            self.repository.set_enabled(mod_id, enabled)
            try:
                self._replace_local_mod(self.repository.get(mod_id))
            except FileNotFoundError:
                continue

    def start_mod_drag(self, source_mod_id: str) -> None:
        visible_ids = [mod.id for mod in self.visible_mods]
        if source_mod_id in self.bulk_selected_ids:
            requested_ids = self.locks.expand_ids(self.bulk_selected_ids)
        else:
            requested_ids = self.locks.linked_ids(source_mod_id)
        dragged_ids = [mod_id for mod_id in visible_ids if mod_id in requested_ids]
        if not dragged_ids:
            return
        drag = QDrag(self.mod_list)
        mime_data = QMimeData()
        mime_data.setData(ModListView.MIME_TYPE, json.dumps(dragged_ids).encode("utf-8"))
        drag.setMimeData(mime_data)
        label = zh("\\u62d6\\u52a8 ") + str(len(dragged_ids)) + " Mod"
        pixmap = QPixmap(180, 34)
        pixmap.fill(QColor("#111827"))
        painter = QPainter(pixmap)
        painter.setPen(QColor("#f8fafc"))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, label)
        painter.end()
        drag.setPixmap(pixmap)
        drag.exec(Qt.DropAction.MoveAction)

    def move_mods_to_index(self, mod_ids: list[str], target_index: int) -> None:
        visible_ids = [mod.id for mod in self.visible_mods]
        requested_ids = self.locks.expand_ids(set(mod_ids))
        dragged_ids = [mod_id for mod_id in visible_ids if mod_id in requested_ids]
        if not dragged_ids:
            return
        dragged_set = set(dragged_ids)
        removed_before_target = sum(1 for index, mod_id in enumerate(visible_ids) if index < target_index and mod_id in dragged_set)
        remaining_visible_ids = [mod_id for mod_id in visible_ids if mod_id not in dragged_set]
        insert_index = max(0, min(target_index - removed_before_target, len(remaining_visible_ids)))
        ordered_visible_ids = remaining_visible_ids[:insert_index] + dragged_ids + remaining_visible_ids[insert_index:]
        self.save_visible_order(ordered_visible_ids)

    def apply_visible_order_to_list(self, ordered_visible_ids: list[str]) -> None:
        visible_by_id = {mod.id: mod for mod in self.visible_mods}
        ordered_visible = [visible_by_id[mod_id] for mod_id in ordered_visible_ids if mod_id in visible_by_id]
        self.visible_mods = ordered_visible
        if self.mod_list_model:
            self.mod_list_model.set_mods(ordered_visible)

    def save_visible_order(self, ordered_visible_ids: list[str] | None = None) -> None:
        if ordered_visible_ids is None:
            ordered_visible_ids = [mod.id for mod in self.visible_mods]
        if not ordered_visible_ids:
            return
        visible_by_id = {mod.id: mod for mod in self.visible_mods}
        ordered_visible = [visible_by_id[mod_id] for mod_id in ordered_visible_ids if mod_id in visible_by_id]
        hidden = [mod for mod in self.mods if mod.id not in visible_by_id]
        combined = ordered_visible + hidden
        self.visible_mods = ordered_visible
        self.mods = combined
        if self.mod_list_model:
            self.mod_list_model.set_mods(self.visible_mods)
        changed_orders: list[tuple[str, int]] = []
        for index, mod in enumerate(combined, start=1):
            if mod.order != index:
                changed_orders.append((mod.id, index))
            mod.order = index
        self.save_orders_async(changed_orders)
        self.sync_selection_tools()

    def save_orders_async(self, orders: list[tuple[str, int]]) -> None:
        if not orders:
            return
        if self.order_save_thread is not None:
            self.pending_order_save = orders
            return
        self.order_save_thread = QThread(self)
        self.order_save_worker = OrderSaveWorker(self.repository, orders)
        self.order_save_worker.moveToThread(self.order_save_thread)
        self.order_save_thread.started.connect(self.order_save_worker.run)
        self.order_save_worker.failed.connect(self.remember_order_save_error)
        self.order_save_worker.finished.connect(self.order_save_thread.quit)
        self.order_save_worker.failed.connect(self.order_save_thread.quit)
        self.order_save_thread.finished.connect(self.order_save_worker.deleteLater)
        self.order_save_thread.finished.connect(self.order_save_thread.deleteLater)
        self.order_save_thread.finished.connect(self.finish_order_save)
        self.order_save_thread.start()

    def remember_order_save_error(self, message: str) -> None:
        self.order_save_error = message

    def finish_order_save(self) -> None:
        self.order_save_thread = None
        self.order_save_worker = None
        error = self.order_save_error
        self.order_save_error = None
        pending = self.pending_order_save
        self.pending_order_save = None
        if error:
            self.show_error(zh("\\u4fdd\\u5b58\\u5931\\u8d25"), error)
        if pending:
            self.save_orders_async(pending)

    def on_left_panel_clicked(self) -> None:
        if self.selected_mod_id:
            self.suppress_next_drawer_open = True
            self.close_drawer()

    def open_mod_drawer(self, mod_id: str) -> None:
        if self.suppress_next_drawer_open:
            self.suppress_next_drawer_open = False
            return
        if self.selected_mod_id == mod_id and self.detail_area.width() > 0:
            return
        if self.selected_mod_id and self.selected_mod_id != mod_id:
            return
        self.selected_mod_id = mod_id
        QTimer.singleShot(0, lambda mid=mod_id: self._open_mod_drawer_deferred(mid))

    def _open_mod_drawer_deferred(self, mod_id: str) -> None:
        if self.selected_mod_id != mod_id:
            return
        self.show_mod_options(mod_id)
        self._animate_drawer(True)

    def show_mod_options(self, mod_id: str) -> None:
        try:
            mod = self.repository.get(mod_id)
        except FileNotFoundError:
            self.close_drawer()
            return
        self._clear_detail()
        header = QHBoxLayout()
        header.setSpacing(14)
        image = ImageLabel()
        image.set_image(mod.preview_path, 128)
        image.setToolTip(zh("\\u5355\\u51fb\\u9884\\u89c8\\uff0c\\u62d6\\u5165\\u6216 Ctrl+V \\u66ff\\u6362\\u56fe\\u7247"))
        image.imageDropped.connect(lambda data, mid=mod.id: self.replace_mod_preview(mid, data))
        header.addWidget(image)
        meta = QVBoxLayout()
        meta.setSpacing(8)
        name_edit = self._inline_edit(mod.name, "detailTitle")
        author_edit = self._inline_edit(mod.author, "inlineEdit")
        link_edit = self._inline_edit(mod.link, "inlineEdit")
        category_edit = self._inline_edit(mod.category, "inlineEdit")
        description_edit = self._inline_edit(mod.description, "inlineEdit")
        author_edit.setPlaceholderText(zh("\\u4f5c\\u8005"))
        link_edit.setPlaceholderText(zh("\\u94fe\\u63a5"))
        category_edit.setPlaceholderText(zh("\\u5206\\u7c7b"))
        description_edit.setPlaceholderText(zh("\\u63cf\\u8ff0"))
        save_fields = lambda: self.save_inline_mod_field(mod.id, name_edit.text(), author_edit.text(), link_edit.text(), category_edit.text(), description_edit.text())
        name_edit.editingFinished.connect(save_fields)
        author_edit.editingFinished.connect(save_fields)
        link_edit.editingFinished.connect(save_fields)
        category_edit.editingFinished.connect(save_fields)
        description_edit.editingFinished.connect(save_fields)
        meta.addWidget(name_edit)
        meta.addWidget(author_edit)
        meta.addWidget(link_edit)
        meta.addWidget(category_edit)
        meta.addWidget(description_edit)
        buttons = QGridLayout()
        buttons.setHorizontalSpacing(8)
        buttons.setVerticalSpacing(8)
        open_dir = QPushButton(zh("\\u6253\\u5f00\\u76ee\\u5f55"))
        open_dir.clicked.connect(lambda: os.startfile(Path("mods") / mod.id))
        delete = QPushButton(zh("\\u5220\\u9664"))
        delete.setObjectName("dangerButton")
        delete.clicked.connect(lambda: self.delete_mod(mod.id))
        for index, button in enumerate((open_dir, delete)):
            button.setMinimumHeight(34)
            buttons.addWidget(button, index // 2, index % 2)
        meta.addLayout(buttons)
        header.addLayout(meta, 1)
        self.detail_layout.addLayout(header)
        for group in self.options.load_groups(mod.id):
            self._add_option_group(mod.id, group)
        self.detail_layout.addStretch()

    def refresh_mod_options_preserving_scroll(self, mod_id: str) -> None:
        scroll_bar = self.detail_area.verticalScrollBar()
        position = scroll_bar.value()
        self.show_mod_options(mod_id)
        QTimer.singleShot(30, lambda pos=position: self._restore_detail_scroll(pos))

    def _restore_detail_scroll(self, position: int) -> None:
        QApplication.processEvents()
        scroll_bar = self.detail_area.verticalScrollBar()
        scroll_bar.setValue(max(scroll_bar.minimum(), min(position, scroll_bar.maximum())))

    def _add_option_group(self, mod_id: str, group) -> None:
        box = QFrame()
        box.setObjectName("optionGroup")
        layout = QVBoxLayout(box)
        choices = group.choices or []
        flat_choice = choices[0] if len(choices) == 1 and not choices[0].children else None
        if flat_choice:
            self._add_choice_row(
                layout,
                mod_id,
                group.id,
                flat_choice,
                True,
                None,
                0,
                True,
                display_name=group.name,
                display_description=flat_choice.description or group.description,
            )
        else:
            title = QCheckBox(group.name)
            title.setObjectName("groupTitle")
            title.setChecked(any(choice.selected for choice in choices))
            title.toggled.connect(lambda checked, gid=group.id: self._set_option_group_enabled(mod_id, gid, checked))
            title.setToolTip(group.name)
            title.setTristate(False)
            layout.addWidget(title)
        show_group_description = bool(group.description) and not (
            flat_choice and flat_choice.description and group.description.strip() == flat_choice.description.strip()
        )
        if show_group_description and not flat_choice:
            desc = QLabel(group.description)
            desc.setWordWrap(True)
            desc.setObjectName("muted")
            layout.addWidget(desc)
        button_group = QButtonGroup(box)
        button_group.setExclusive(not group.multiple)
        if not flat_choice:
            group_enabled = any(choice.selected for choice in choices)
            for choice in choices:
                self._add_choice_row(layout, mod_id, group.id, choice, group.multiple, button_group, 0, group_enabled)
        self.detail_layout.addWidget(box)

    def _add_choice_row(
        self,
        layout: QVBoxLayout,
        mod_id: str,
        group_id: str,
        choice,
        multiple: bool,
        button_group: QButtonGroup | None,
        depth: int,
        group_enabled: bool = True,
        display_name: str | None = None,
        display_description: str | None = None,
    ) -> None:
        row_box = QFrame()
        row_box.setObjectName("optionChoiceRow")
        row = QHBoxLayout(row_box)
        row.setContentsMargins(8 + depth * 22, 6, 8, 6)
        row.setSpacing(10)
        control = QCheckBox() if multiple or depth > 0 else QRadioButton()
        control.setToolTip(display_name or choice.name)
        control.setEnabled(group_enabled)
        control.setChecked(choice.selected)
        row.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        if choice.image:
            icon = ImageLabel()
            icon.set_image(choice.image, 48)
            row.addWidget(icon)
        else:
            placeholder = QLabel()
            placeholder.setObjectName("optionImagePlaceholder")
            placeholder.setFixedSize(48, 48)
            row.addWidget(placeholder)
        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(2)
        if depth == 0:
            control.toggled.connect(lambda checked, gid=group_id, cid=choice.id, is_multiple=multiple: self._select_choice(mod_id, gid, cid, checked, is_multiple))
            if button_group is not None:
                button_group.addButton(control)
        else:
            control.toggled.connect(lambda checked, cid=choice.id: self._select_nested_choice(mod_id, cid, checked))
        title = QLabel(display_name or choice.name)
        title.setObjectName("optionChoiceTitle")
        text.addWidget(title)
        description = display_description if display_description is not None else choice.description
        if description:
            desc = QLabel(description)
            desc.setWordWrap(True)
            desc.setObjectName("muted")
            text.addWidget(desc)
        row.addLayout(text, 1)
        layout.addWidget(row_box)
        for child in choice.children or []:
            self._add_choice_row(layout, mod_id, group_id, child, True, None, depth + 1, group_enabled)

    def _select_choice(self, mod_id: str, group_id: str, choice_id: str, checked: bool, multiple: bool = True) -> None:
        if not multiple and not checked:
            return
        self.options.set_choice_selected(mod_id, group_id, choice_id, checked)
        self.refresh_mod_options_preserving_scroll(mod_id)

    def _set_option_group_enabled(self, mod_id: str, group_id: str, enabled: bool) -> None:
        groups = self.options.load_groups(mod_id)
        for group in groups:
            if group.id == group_id:
                choices = group.choices or []
                if enabled and not any(choice.selected for choice in choices):
                    if choices:
                        choices[0].selected = True
                elif not enabled:
                    for choice in choices:
                        choice.selected = False
                        self._clear_choice_children(choice)
        self.options.save_groups(mod_id, groups)
        self.refresh_mod_options_preserving_scroll(mod_id)

    def _clear_choice_children(self, choice) -> None:
        for child in choice.children or []:
            child.selected = False
            self._clear_choice_children(child)

    def _select_nested_choice(self, mod_id: str, choice_id: str, checked: bool) -> None:
        self.options.set_nested_choice_selected(mod_id, choice_id, checked)

    def replace_mod_preview(self, mod_id: str, image_data) -> None:
        try:
            if isinstance(image_data, QPixmap):
                source_image = image_data.toImage()
            else:
                source_image = QImage(str(image_data)) if isinstance(image_data, (str, Path)) else image_data
            if source_image is None or source_image.isNull():
                raise ValueError(zh("\\u65e0\\u6cd5\\u8bfb\\u53d6\\u56fe\\u7247"))
            mod = self.repository.get(mod_id)
            target = Path("mods") / mod_id / "images" / "preview.png"
            target.parent.mkdir(parents=True, exist_ok=True)
            if not source_image.save(str(target), "PNG"):
                raise ValueError(zh("\\u4fdd\\u5b58\\u56fe\\u7247\\u5931\\u8d25"))
            self.repository.save_meta(mod.id, mod.name, mod.author, mod.link, mod.order, mod.enabled, mod.description, mod.category, "images/preview.png")
            QPixmapCache.clear()
            self._replace_local_mod(self.repository.get(mod_id))
            self.show_mod_options(mod_id)
        except Exception as exc:
            self.show_error(zh("\\u56fe\\u7247\\u5904\\u7406\\u5931\\u8d25"), str(exc))

    def import_mod(self) -> None:
        source = self.choose_import_source()
        if not source:
            return
        imported, errors = self.import_sources([source])
        self.refresh_mods()
        if errors:
            self.show_error(zh("\\u5bfc\\u5165\\u5931\\u8d25"), "\n".join(errors))
        elif imported:
            self.show_info(zh("\\u5bfc\\u5165\\u5b8c\\u6210"), zh("\\u5df2\\u5bfc\\u5165: ") + ", ".join(imported))

    def choose_import_source(self) -> Path | None:
        dialog = QFileDialog(self, zh("\\u9009\\u62e9 Mod \\u538b\\u7f29\\u5305\\u6216\\u6587\\u4ef6\\u5939"))
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setFilter(QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot)
        dialog.setNameFilters(["Mod Archives or Folders (*.zip *.rar *.7z)", "All Files and Folders (*)"])
        for view in dialog.findChildren((QListView, QTreeView)):
            view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        if dialog.exec() != QFileDialog.DialogCode.Accepted:
            return None
        selected = dialog.selectedFiles()
        if not selected:
            return None
        source = Path(selected[0])
        if source.is_dir() or source.suffix.lower() in {".zip", ".rar", ".7z"}:
            return source
        self.show_error(zh("\\u5bfc\\u5165\\u5931\\u8d25"), zh("\\u8bf7\\u9009\\u62e9 .zip/.rar/.7z \\u538b\\u7f29\\u5305\\u6216 Mod \\u6587\\u4ef6\\u5939"))
        return None

    def install_mods(self) -> None:
        try:
            copied = self.installer.install_enabled_mods()
            self.show_info(zh("\\u5b8c\\u6210"), zh("\\u5df2\\u590d\\u5236 ") + str(copied) + zh(" \\u4e2a patch \\u6587\\u4ef6"))
        except Exception as exc:
            self.show_error(zh("\\u5b89\\u88c5\\u5931\\u8d25"), str(exc))

    def remove_game_mods(self) -> None:
        if not self.confirm(zh("\\u786e\\u8ba4"), zh("\\u5220\\u9664\\u6e38\\u620f data \\u76ee\\u5f55\\u4e2d\\u7684 patch_ \\u6587\\u4ef6\\uff1f")):
            return
        try:
            removed = self.installer.remove_all_patch_files()
            self.show_info(zh("\\u5b8c\\u6210"), zh("\\u5df2\\u5220\\u9664 ") + str(removed) + zh(" \\u4e2a\\u6587\\u4ef6"))
        except Exception as exc:
            self.show_error(zh("\\u5220\\u9664\\u5931\\u8d25"), str(exc))

    def choose_game_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, zh("\\u9009\\u62e9 Helldivers 2 data \\u76ee\\u5f55"))
        if folder:
            self.install_dir = self.config.save_install_dir(folder)
            self.installer.set_install_dir(self.install_dir)

    def start_game(self) -> None:
        os.system("start steam://rungameid/553850")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "loading_overlay"):
            self.loading_overlay.setGeometry(self.centralWidget().rect())
        self._sync_left_overlay_geometry()
        if self.selected_mod_id and self.detail_area.width() > 0:
            width = self._drawer_width()
            self.detail_area.setFixedWidth(width)
            self.detail_panel.setMinimumWidth(max(0, width - 42))

    def _drawer_width(self) -> int:
        available = max(420, self.width() - 430)
        return max(420, min(640, available))

    def _sync_left_overlay_geometry(self) -> None:
        if not hasattr(self, "left_overlay") or not hasattr(self, "list_panel"):
            return
        self.left_overlay.setGeometry(self.list_panel.rect())
        self.left_overlay.raise_()

    def toggle_mod(self, mod_id: str, enabled: bool) -> None:
        self.set_mod_enabled(mod_id, enabled)

    def set_mod_enabled(self, mod_id: str, enabled: bool) -> None:
        for linked_id in self.locks.linked_ids(mod_id):
            self.repository.set_enabled(linked_id, enabled)
            updated_mod = self.repository.get(linked_id)
            self._replace_local_mod(updated_mod)
        if self.selected_mod_id in self.locks.linked_ids(mod_id):
            self.show_mod_options(self.selected_mod_id)

    def _replace_local_mod(self, updated_mod) -> bool:
        for index, mod in enumerate(self.mods):
            if mod.id == updated_mod.id:
                self.mods[index] = updated_mod
                break
        visible = False
        for index, mod in enumerate(self.visible_mods):
            if mod.id == updated_mod.id:
                self.visible_mods[index] = updated_mod
                visible = True
                break
        if visible and self.mod_list_model:
            self.mod_list_model.update_mod(updated_mod)
        return visible

    def save_inline_mod_field(self, mod_id: str, name: str, author: str, link: str, category: str, description: str) -> None:
        mod = self.repository.get(mod_id)
        new_name = name.strip() or mod.name
        new_author = author.strip()
        new_link = link.strip()
        new_category = category.strip()
        new_description = description.strip()
        self.repository.save_meta(mod.id, new_name, new_author, new_link, mod.order, mod.enabled, new_description, new_category)
        updated_mod = self.repository.get(mod_id)
        visible = self._replace_local_mod(updated_mod)
        self._sync_categories()
        current_category = self.category_combo.currentData() if hasattr(self, "category_combo") else None
        if current_category is not None and updated_mod and (updated_mod.category or zh("\\u672a\\u5206\\u7c7b")) != current_category:
            self.apply_filters()
            return
        if not visible:
            self.apply_filters()

    def delete_mod(self, mod_id: str) -> None:
        if self.confirm(zh("\\u786e\\u8ba4\\u5220\\u9664"), zh("\\u786e\\u5b9a\\u5220\\u9664\\u8fd9\\u4e2a Mod\\uff1f")):
            self.repository.delete(mod_id)
            self.mods = [mod for mod in self.mods if mod.id != mod_id]
            self.visible_mods = [mod for mod in self.visible_mods if mod.id != mod_id]
            self.bulk_selected_ids.discard(mod_id)
            self.locks.unlock({mod_id})
            self.sync_lock_state()
            if self.selected_mod_id == mod_id:
                self.selected_mod_id = None
                self.close_drawer()
            self._sync_categories()
            self.apply_filters()

    def _mod_text(self, mod) -> str:
        return f"{mod.name}\n{mod.author or '-'}  |  {mod.option_count} options"

    def close_drawer(self) -> None:
        closing_mod_id = self.selected_mod_id
        self.selected_mod_id = None
        self._clear_detail()
        self._animate_drawer(False)
        if closing_mod_id:
            self.refresh_single_mod(closing_mod_id)

    def refresh_single_mod(self, mod_id: str) -> None:
        try:
            self.repository.refresh_payload_mtime(mod_id)
            refreshed = self.repository.get(mod_id)
        except FileNotFoundError:
            return
        self._replace_local_mod(refreshed)

    def _animate_drawer(self, open_drawer: bool) -> None:
        start = self.detail_area.width()
        end = self._drawer_width() if open_drawer else 0
        if open_drawer:
            self._set_left_overlay_visible(True)
        self.detail_area.setMinimumWidth(0)
        self.detail_area.setMaximumWidth(16777215)
        self.drawer_animation = QPropertyAnimation(self.detail_area, b"maximumWidth", self)
        self.drawer_animation.setStartValue(start)
        self.drawer_animation.setEndValue(end)
        self.drawer_animation.setDuration(220)
        self.drawer_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.drawer_animation.valueChanged.connect(self._set_drawer_width)
        self.drawer_animation.finished.connect(lambda: self._finalize_drawer_width(end))
        self.drawer_animation.start()

    def _set_drawer_width(self, value) -> None:
        width = int(value)
        self.detail_area.setFixedWidth(width)
        self.detail_panel.setMinimumWidth(max(0, width - 42))

    def _finalize_drawer_width(self, width: int) -> None:
        self.detail_area.setFixedWidth(width)
        self.detail_panel.setMinimumWidth(max(0, width - 42))
        self._set_left_overlay_visible(width > 0)

    def _set_left_overlay_visible(self, visible: bool) -> None:
        if not hasattr(self, "left_overlay"):
            return
        self._sync_left_overlay_geometry()
        self.left_overlay.setVisible(visible)
        if visible:
            self.left_overlay.raise_()

    def _link_html(self, link: str) -> str:
        if not link:
            return zh("\\u94fe\\u63a5: \\u672a\\u8bbe\\u7f6e")
        return f'<a href="{link}">{link}</a>'

    def _thumbnail(self, path: Path | None, size: int) -> QPixmap:
        try:
            mtime = path.stat().st_mtime if path and path.exists() else 0
        except OSError:
            mtime = 0
        cache_key = f"{path}:{size}:{mtime}"
        cached = QPixmapCache.find(cache_key)
        if cached:
            return cached
        pixmap = QPixmap(str(path)) if path else QPixmap()
        if pixmap.isNull():
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
        thumb = square_thumbnail(pixmap, size)
        QPixmapCache.insert(cache_key, thumb)
        return thumb

    def _clear_detail(self, text: str | None = None) -> None:
        while self.detail_layout.count():
            item = self.detail_layout.takeAt(0)
            self._delete_layout_item(item)
        if text:
            self.detail_layout.addWidget(QLabel(text))

    def _delete_layout_item(self, item) -> None:
        widget = item.widget()
        if widget:
            widget.setParent(None)
            widget.deleteLater()
            return
        child_layout = item.layout()
        if child_layout:
            while child_layout.count():
                self._delete_layout_item(child_layout.takeAt(0))
            child_layout.deleteLater()


def startup_import_paths(argv: list[str]) -> list[Path]:
    paths: list[Path] = []
    index = 1
    while index < len(argv):
        arg = argv[index]
        if arg in ("--import", "-i") and index + 1 < len(argv):
            paths.append(Path(argv[index + 1]))
            index += 2
            continue
        if arg.startswith("--import="):
            paths.append(Path(arg.split("=", 1)[1]))
            index += 1
            continue
        if not arg.startswith("-") and Path(arg).exists():
            paths.append(Path(arg))
        index += 1
    return paths


def run_app(argv: list[str] | None = None) -> int:
    raw_args = list(sys.argv if argv is None else argv)
    app = QApplication(raw_args[:1])
    app.setStyleSheet(STYLE)
    window = MainWindow(startup_import_paths(raw_args))
    window.show()
    return app.exec()


STYLE = """
QWidget { font-family: Segoe UI, Microsoft YaHei; font-size: 14px; color: #172033; }
QMainWindow { background: #eef2f7; }
#sidePanel, #listPanel, #drawerPanel { background: #ffffff; border: 1px solid #d8e0ea; border-radius: 10px; }
#loadingOverlay { background: rgba(238, 242, 247, 218); }
#leftOverlay { background: rgba(15, 23, 42, 90); border-radius: 10px; }
#loadingBox { background: #ffffff; border: 1px solid #d8e0ea; border-radius: 12px; }
#loadingLabel { font-size: 16px; font-weight: 700; color: #101828; }
#dropIndicator { background: #111827; border-radius: 1px; }
#appTitle { font-size: 24px; font-weight: 800; color: #101828; }
#warStatus { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; }
#warStatusText { color: #334155; background: transparent; padding: 10px; line-height: 1.35; }
#panelTitle { font-size: 18px; font-weight: 750; color: #101828; }
#sectionLabel { margin-top: 12px; color: #667085; font-size: 12px; font-weight: 700; letter-spacing: 0px; }
#selectVisibleCheck { margin-left: 14px; color: #334155; font-weight: 600; }
#headerSelectedCount { color: #334155; font-weight: 800; margin-left: 12px; }
#bulkRowCheck { margin-right: 2px; }
#bulkRowCheck::indicator { width: 18px; height: 18px; border-radius: 9px; border: 2px solid #94a3b8; background: #ffffff; }
#bulkRowCheck::indicator:checked { background: #2563eb; border-color: #2563eb; }
#bulkBar { background: #111827; border: 1px solid #334155; border-radius: 12px; }
#bulkCount { color: #f8fafc; font-weight: 700; }
#bulkBar QPushButton { background: #1f2937; color: #f8fafc; border-color: #475569; }
#bulkBar QPushButton:hover { background: #334155; }
#bulkBar QLineEdit { background: #0f172a; color: #f8fafc; border-color: #475569; }
#inlineEdit { color: #334155; background: transparent; border: 0; padding: 2px 0; }
#inlineEdit:focus { background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px; padding: 2px 6px; }
#detailTitle { font-size: 24px; font-weight: 800; color: #101828; }
#groupTitle { font-size: 16px; font-weight: 750; color: #101828; }
#muted { color: #667085; }
#linkLabel { color: #2563eb; }
#modRow { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; }
#modRow:hover { background: #f8fbff; border-color: #bfdbfe; }
#modRowTitle { font-weight: 700; color: #101828; }
#modDescription { color: #475569; }
#chip { color: #475569; background: #eef2f7; border-radius: 7px; padding: 2px 7px; font-size: 12px; font-weight: 600; }
#modThumb { border-radius: 6px; background: #eef2f7; }
QLineEdit, QComboBox, QSpinBox { min-height: 34px; padding: 6px 10px; border: 1px solid #ccd6e2; border-radius: 7px; background: #ffffff; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #2563eb; }
QComboBox { selection-background-color: #e8f1ff; selection-color: #172033; }
QComboBox::drop-down { width: 28px; border: 0; }
QComboBox QAbstractItemView { background: #ffffff; color: #172033; border: 1px solid #ccd6e2; border-radius: 7px; padding: 4px; outline: 0; selection-background-color: #e8f1ff; selection-color: #172033; }
QComboBox QAbstractItemView::item { min-height: 28px; padding: 6px 10px; border-radius: 5px; color: #172033; }
QComboBox QAbstractItemView::item:hover, QComboBox QAbstractItemView::item:selected { background: #e8f1ff; color: #172033; }
QPushButton { min-height: 34px; padding: 8px 12px; border: 1px solid #cbd5e1; border-radius: 7px; background: #ffffff; color: #172033; }
QPushButton:hover { background: #f2f6fb; border-color: #9db5d5; }
#smallButton { min-height: 30px; padding: 5px 10px; }
#primaryButton { color: #ffffff; background: #2563eb; border-color: #2563eb; font-weight: 700; }
#primaryButton:hover { background: #1d4ed8; }
#dangerButton { color: #ffffff; background: #dc2626; border-color: #dc2626; font-weight: 700; }
#dangerButton:hover { background: #b91c1c; }
#optionGroup { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 9px; padding: 10px; margin-top: 8px; }
#optionChoiceRow { background: transparent; border: 0; }
#optionChoiceTitle { color: #101828; font-weight: 750; }
#optionImagePlaceholder { border: 1px dashed #cbd5e1; border-radius: 6px; background: #f8fafc; }
QListView { background: #ffffff; border: 0; outline: none; }
QListView::item { margin: 4px 0; border-radius: 8px; }
QListView::item:selected { background: transparent; }
QScrollBar:vertical { width: 10px; background: transparent; }
QScrollBar::handle:vertical { background: #cbd5e1; border-radius: 5px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
#importDialog { background: #f8fafc; }
#dialogTitle { font-size: 22px; font-weight: 800; color: #101828; }
#dialogCard { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; }
#cardTitle { font-size: 13px; font-weight: 800; color: #334155; }
#hint { color: #667085; background: #eef6ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 10px; }
#messageOverlay { background: rgba(15, 23, 42, 105); }
#messageCard { background: #ffffff; border: 1px solid #d8e0ea; border-radius: 10px; min-width: 420px; max-width: 560px; }
#messageTitle { font-size: 17px; font-weight: 800; color: #101828; }
#messageBody { color: #172033; min-width: 360px; }
#messageIcon_info, #messageIcon_question { color: #ffffff; background: #2563eb; border-radius: 17px; font-weight: 800; }
#messageIcon_error { color: #ffffff; background: #dc2626; border-radius: 17px; font-weight: 800; }
#messagePrimaryButton { color: #ffffff; background: #2563eb; border-color: #2563eb; font-weight: 800; min-width: 104px; max-width: 140px; }
#messagePrimaryButton:hover { background: #1d4ed8; }
#messageSecondaryButton { min-width: 104px; max-width: 140px; }
"""
