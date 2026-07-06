from __future__ import annotations

import json
import traceback

from PyQt6.QtCore import QAbstractListModel, QAbstractAnimation, QModelIndex, QPropertyAnimation, QRect, QSize, Qt, QTimer, pyqtSignal, QEasingCurve
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QApplication, QAbstractItemView, QFrame, QListView, QStyle, QStyleOptionViewItem, QStyledItemDelegate

from hd2mm.ui.dialogs import zh


class ModListModel(QAbstractListModel):
    ModRole = Qt.ItemDataRole.UserRole + 1
    ThumbnailRole = Qt.ItemDataRole.UserRole + 2
    BulkCheckedRole = Qt.ItemDataRole.UserRole + 3
    LockedRole = Qt.ItemDataRole.UserRole + 4

    def __init__(self, thumbnail_provider) -> None:
        super().__init__()
        self.mods = []
        self.bulk_selected_ids: set[str] = set()
        self.locked_ids: set[str] = set()
        self.thumbnail_provider = thumbnail_provider
        self.thumbnail_cache: dict[str, QPixmap] = {}

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.mods)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self.mods):
            return None
        mod = self.mods[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return mod.name
        if role == self.ModRole:
            return mod
        if role == self.ThumbnailRole:
            return self.thumbnail_for_mod(mod)
        if role == self.BulkCheckedRole:
            return mod.id in self.bulk_selected_ids
        if role == self.LockedRole:
            return mod.id in self.locked_ids
        return None

    def set_mods(self, mods: list) -> None:
        self.beginResetModel()
        self.mods = list(mods)
        visible_ids = {mod.id for mod in self.mods}
        self.thumbnail_cache = {mod_id: pixmap for mod_id, pixmap in self.thumbnail_cache.items() if mod_id in visible_ids}
        self.endResetModel()

    def thumbnail_for_mod(self, mod) -> QPixmap:
        cached = self.thumbnail_cache.get(mod.id)
        if cached is not None:
            return cached
        pixmap = self.thumbnail_provider(mod.preview_path, 72)
        self.thumbnail_cache[mod.id] = pixmap
        return pixmap

    def set_bulk_selected_ids(self, selected_ids: set[str]) -> None:
        self.bulk_selected_ids = set(selected_ids)
        if self.mods:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.mods) - 1, 0), [self.BulkCheckedRole])

    def set_locked_ids(self, locked_ids: set[str]) -> None:
        self.locked_ids = set(locked_ids)
        if self.mods:
            self.dataChanged.emit(self.index(0, 0), self.index(len(self.mods) - 1, 0), [self.LockedRole])

    def refresh_mod(self, mod_id: str) -> None:
        row = self.row_for_mod(mod_id)
        if row is None:
            return
        self.thumbnail_cache.pop(mod_id, None)
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole, self.ModRole, self.ThumbnailRole, self.BulkCheckedRole, self.LockedRole])

    def update_mod(self, mod) -> None:
        row = self.row_for_mod(mod.id)
        if row is None:
            return
        self.mods[row] = mod
        self.refresh_mod(mod.id)

    def row_for_mod(self, mod_id: str) -> int | None:
        for row, mod in enumerate(self.mods):
            if mod.id == mod_id:
                return row
        return None


class ModListDelegate(QStyledItemDelegate):
    ROW_HEIGHT = 116

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(260, self.ROW_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        mod = index.data(ModListModel.ModRole)
        if not mod:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = option.rect.adjusted(0, 4, -2, -4)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        painter.setPen(QPen(QColor("#bfdbfe" if hover else "#e2e8f0"), 1))
        painter.setBrush(QBrush(QColor("#f8fbff" if hover else "#ffffff")))
        painter.drawRoundedRect(card, 12, 12)
        self._draw_bulk_check(painter, self.bulk_rect(option), bool(index.data(ModListModel.BulkCheckedRole)))
        self._draw_toggle(painter, self.toggle_rect(option), mod.enabled)
        self._draw_thumbnail(painter, self.thumbnail_rect(option), index.data(ModListModel.ThumbnailRole))
        locked = bool(index.data(ModListModel.LockedRole))
        self._draw_text(painter, option, card, self.thumbnail_rect(option), mod, locked)
        if locked:
            self._draw_lock_badge(painter, card)
        painter.restore()

    def bulk_rect(self, option: QStyleOptionViewItem) -> QRect:
        card = option.rect.adjusted(0, 4, -2, -4)
        return QRect(card.left() + 14, card.top() + 49, 20, 20)

    def toggle_rect(self, option: QStyleOptionViewItem) -> QRect:
        card = option.rect.adjusted(0, 4, -2, -4)
        return QRect(card.left() + 46, card.top() + 38, 74, 40)

    def thumbnail_rect(self, option: QStyleOptionViewItem) -> QRect:
        card = option.rect.adjusted(0, 4, -2, -4)
        return QRect(card.left() + 134, card.top() + 22, 72, 72)

    def _draw_lock_badge(self, painter: QPainter, card: QRect) -> None:
        rect = QRect(card.right() - 66, card.top() + 10, 50, 22)
        painter.setPen(QPen(QColor("#1d4ed8"), 1))
        painter.setBrush(QBrush(QColor("#dbeafe")))
        painter.drawRoundedRect(rect, 7, 7)
        badge_font = QFont(painter.font())
        badge_font.setPointSize(max(8, badge_font.pointSize() - 1))
        badge_font.setBold(True)
        painter.setFont(badge_font)
        painter.setPen(QColor("#1d4ed8"))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, zh("\\u540c\\u6b65"))

    def _draw_bulk_check(self, painter: QPainter, rect: QRect, checked: bool) -> None:
        painter.setPen(QPen(QColor("#2563eb" if checked else "#94a3b8"), 2))
        painter.setBrush(QBrush(QColor("#2563eb" if checked else "#ffffff")))
        painter.drawEllipse(rect)
        if checked:
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.drawLine(rect.left() + 5, rect.center().y(), rect.left() + 9, rect.bottom() - 5)
            painter.drawLine(rect.left() + 9, rect.bottom() - 5, rect.right() - 4, rect.top() + 5)

    def _draw_toggle(self, painter: QPainter, rect: QRect, enabled: bool) -> None:
        track = QRect(rect.left() + 10, rect.top() + 8, 54, 24)
        painter.setPen(QPen(QColor("#2563eb" if enabled else "#cbd5e1"), 2))
        painter.setBrush(QBrush(QColor("#2563eb" if enabled else "#ffffff")))
        painter.drawRoundedRect(track, 12, 12)
        painter.setPen(QPen(QColor("#ffffff" if enabled else "#cbd5e1"), 1))
        painter.setBrush(QBrush(QColor("#ffffff" if enabled else "#e5e7eb")))
        painter.drawEllipse(QRect(rect.left() + (40 if enabled else 14), rect.top() + 11, 18, 18))

    def _draw_thumbnail(self, painter: QPainter, rect: QRect, thumbnail) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#eef2f7")))
        painter.drawRoundedRect(rect, 6, 6)
        if isinstance(thumbnail, QPixmap) and not thumbnail.isNull():
            painter.drawPixmap(rect, thumbnail)

    def _draw_text(self, painter: QPainter, option: QStyleOptionViewItem, card: QRect, thumb_rect: QRect, mod, locked: bool) -> None:
        text_left = thumb_rect.right() + 14
        text_right = card.right() - (74 if locked else 14)
        title_rect = QRect(text_left, card.top() + 14, max(0, text_right - text_left), 23)
        desc_rect = QRect(text_left, title_rect.bottom() + 7, max(0, text_right - text_left), 34)
        title_font = QFont(option.font)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor("#101828"))
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._elide(painter, mod.name, title_rect.width()))
        painter.setFont(option.font)
        painter.setPen(QColor("#475569"))
        painter.drawText(desc_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, self._elide(painter, mod.description or "", desc_rect.width()))
        chip_y = card.bottom() - 31
        next_x = self._draw_chip(painter, QRect(text_left, chip_y, 0, 22), mod.category or zh("\\u672a\\u5206\\u7c7b")) + 6
        self._draw_chip(painter, QRect(next_x, chip_y, 0, 22), mod.updated_at.strftime("%y/%m/%d") if mod.updated_at else "--/--/--")

    def _draw_chip(self, painter: QPainter, rect: QRect, text: str) -> int:
        chip_font = QFont(painter.font())
        chip_font.setPointSize(max(8, chip_font.pointSize() - 1))
        chip_font.setBold(True)
        painter.setFont(chip_font)
        width = min(150, painter.fontMetrics().horizontalAdvance(text) + 16)
        chip = QRect(rect.left(), rect.top(), width, rect.height())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#eef2f7")))
        painter.drawRoundedRect(chip, 7, 7)
        painter.setPen(QColor("#475569"))
        painter.drawText(chip.adjusted(7, 0, -7, 0), Qt.AlignmentFlag.AlignCenter, self._elide(painter, text, chip.width() - 14))
        return chip.right()

    def _elide(self, painter: QPainter, text: str, width: int) -> str:
        return painter.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, max(0, width))


class ModListView(QListView):
    blankClicked = pyqtSignal()
    leftClicked = pyqtSignal()
    modIdsDropped = pyqtSignal(list, int)
    enabledChanged = pyqtSignal(str, bool)
    editRequested = pyqtSignal(str)
    checkedForBulk = pyqtSignal(str, bool)
    dragRequested = pyqtSignal(str)
    MIME_TYPE = "application/x-hd2mm-mod-ids"

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.smooth_scroll_target = 0
        self.smooth_scroll_animation = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self.smooth_scroll_animation.setDuration(150)
        self.smooth_scroll_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.drop_indicator = QFrame(self.viewport())
        self.drop_indicator.setObjectName("dropIndicator")
        self.drop_indicator.hide()
        self.press_pos = None
        self.press_mod_id = None
        self.drag_started = False
        self.auto_scroll_delta = 0
        self.auto_scroll_position = None
        self.auto_scroll_timer = QTimer(self)
        self.auto_scroll_timer.setInterval(30)
        self.auto_scroll_timer.timeout.connect(self.perform_drag_auto_scroll)

    def mousePressEvent(self, event) -> None:
        self.smooth_scroll_animation.stop()
        index = self.indexAt(event.position().toPoint())
        if not index.isValid():
            self.leftClicked.emit()
            self.clearSelection()
            self.blankClicked.emit()
            self.press_pos = None
            self.press_mod_id = None
            self.drag_started = False
            super().mousePressEvent(event)
            return
        self.press_pos = event.position().toPoint()
        mod = index.data(ModListModel.ModRole)
        self.press_mod_id = mod.id if mod else None
        self.drag_started = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.press_pos is None or self.drag_started or not self.press_mod_id:
            super().mouseMoveEvent(event)
            return
        distance = (event.position().toPoint() - self.press_pos).manhattanLength()
        if distance >= QApplication.startDragDistance():
            self.drag_started = True
            self.dragRequested.emit(self.press_mod_id)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        try:
            index = self.indexAt(event.position().toPoint())
            was_dragging = self.drag_started
            self.press_pos = None
            self.drag_started = False
            if index.isValid() and not was_dragging:
                mod = index.data(ModListModel.ModRole)
                delegate = self.itemDelegate()
                option = QStyleOptionViewItem()
                option.font = self.font()
                option.rect = self.visualRect(index)
                point = event.position().toPoint()
                if isinstance(delegate, ModListDelegate) and delegate.bulk_rect(option).contains(point):
                    self.checkedForBulk.emit(mod.id, not bool(index.data(ModListModel.BulkCheckedRole)))
                    event.accept()
                    return
                if isinstance(delegate, ModListDelegate) and delegate.toggle_rect(option).contains(point):
                    self.enabledChanged.emit(mod.id, not mod.enabled)
                    event.accept()
                    return
                self.editRequested.emit(mod.id)
                event.accept()
                return
            super().mouseReleaseEvent(event)
        except Exception:
            traceback.print_exc()
            event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        try:
            index = self.indexAt(event.position().toPoint())
            if index.isValid():
                mod = index.data(ModListModel.ModRole)
                if mod:
                    self.editRequested.emit(mod.id)
            super().mouseDoubleClickEvent(event)
        except Exception:
            traceback.print_exc()
            event.accept()

    def wheelEvent(self, event) -> None:
        scrollbar = self.verticalScrollBar()
        delta = event.pixelDelta().y() or event.angleDelta().y() // 2
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
            self.update_drag_auto_scroll(event.position().toPoint())
            self.show_drop_indicator(self._drop_target_index(event.position().toPoint()))
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event) -> None:
        self.stop_drag_auto_scroll()
        self.drop_indicator.hide()
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        self.stop_drag_auto_scroll()
        self.drop_indicator.hide()
        if not event.mimeData().hasFormat(self.MIME_TYPE):
            super().dropEvent(event)
            return
        try:
            mod_ids = json.loads(bytes(event.mimeData().data(self.MIME_TYPE)).decode("utf-8"))
        except (TypeError, ValueError, UnicodeDecodeError):
            event.ignore()
            return
        self.modIdsDropped.emit(mod_ids, self._drop_target_index(event.position().toPoint()))
        event.acceptProposedAction()

    def update_drag_auto_scroll(self, position) -> None:
        margin = 64
        max_step = 22
        viewport_height = self.viewport().height()
        y = position.y()
        if y < margin:
            self.auto_scroll_delta = -max(4, int(max_step * (margin - y) / margin))
        elif y > viewport_height - margin:
            self.auto_scroll_delta = max(4, int(max_step * (y - (viewport_height - margin)) / margin))
        else:
            self.stop_drag_auto_scroll()
            return
        self.auto_scroll_position = position
        if not self.auto_scroll_timer.isActive():
            self.auto_scroll_timer.start()

    def perform_drag_auto_scroll(self) -> None:
        if not self.auto_scroll_delta or self.auto_scroll_position is None:
            self.stop_drag_auto_scroll()
            return
        scrollbar = self.verticalScrollBar()
        value = max(scrollbar.minimum(), min(scrollbar.maximum(), scrollbar.value() + self.auto_scroll_delta))
        if value == scrollbar.value():
            return
        self.smooth_scroll_animation.stop()
        scrollbar.setValue(value)
        self.smooth_scroll_target = value
        self.show_drop_indicator(self._drop_target_index(self.auto_scroll_position))

    def stop_drag_auto_scroll(self) -> None:
        self.auto_scroll_delta = 0
        self.auto_scroll_position = None
        if self.auto_scroll_timer.isActive():
            self.auto_scroll_timer.stop()

    def show_drop_indicator(self, target_index: int) -> None:
        model = self.model()
        if model is None or model.rowCount() == 0:
            y = 0
        elif target_index >= model.rowCount():
            y = self.visualRect(model.index(model.rowCount() - 1, 0)).bottom() + 1
        else:
            y = self.visualRect(model.index(target_index, 0)).top()
        self.drop_indicator.setGeometry(0, max(0, y - 1), self.viewport().width(), 3)
        self.drop_indicator.raise_()
        self.drop_indicator.show()

    def _drop_target_index(self, position) -> int:
        model = self.model()
        if model is None:
            return 0
        index = self.indexAt(position)
        if not index.isValid():
            return model.rowCount()
        rect = self.visualRect(index)
        return index.row() + 1 if position.y() > rect.center().y() else index.row()
