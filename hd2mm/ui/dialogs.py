from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from hd2mm.core.models import ImportOptions


def zh(text: str) -> str:
    return text.encode("utf-8").decode("unicode_escape")


class ImportDialog(QDialog):
    def __init__(self, parent=None, source: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle(zh("\\u5bfc\\u5165 Mod"))
        self.setMinimumWidth(680)
        self.setObjectName("importDialog")
        self.source_edit = QLineEdit(source)
        self.name_edit = QLineEdit()
        self.author_edit = QLineEdit()
        self.link_edit = QLineEdit()
        self.preview_edit = QLineEdit()
        self.order_spin = QSpinBox()
        self.order_spin.setRange(0, 9999)
        self.order_spin.setValue(9999)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        title = QLabel(zh("\\u5bfc\\u5165 Mod"))
        title.setObjectName("dialogTitle")
        subtitle = QLabel(zh("\\u5c06 manifest \\u6216 patch \\u5305\\u5bfc\\u5165\\u5230\\u672c\\u5730\\u7ba1\\u7406\\u5e93"))
        subtitle.setObjectName("muted")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        source_card = self._card(zh("\\u6765\\u6e90"))
        source_form = QFormLayout(source_card)
        source_form.setContentsMargins(14, 36, 14, 14)
        source_form.addRow(zh("Mod \\u8def\\u5f84"), self._path_row(self.source_edit, self._choose_source))
        source_form.addRow(zh("\\u9884\\u89c8\\u56fe"), self._path_row(self.preview_edit, self._choose_preview))
        layout.addWidget(source_card)
        info_card = self._card(zh("\\u57fa\\u672c\\u4fe1\\u606f"))
        form = QFormLayout(info_card)
        form.setContentsMargins(14, 36, 14, 14)
        form.addRow(zh("\\u540d\\u79f0"), self.name_edit)
        form.addRow(zh("\\u4f5c\\u8005"), self.author_edit)
        form.addRow(zh("\\u94fe\\u63a5"), self.link_edit)
        form.addRow(zh("\\u6392\\u5e8f"), self.order_spin)
        layout.addWidget(info_card)
        hint = QLabel(zh("\\u652f\\u6301\\u6587\\u4ef6\\u5939\\u3001.zip\\u3001.7z\\u3001.rar \\u548c HD2 manifest\\u3002\\u65e7\\u683c\\u5f0f\\u8bf7\\u7528\\u4e3b\\u754c\\u9762\\u7684\\u201c\\u5bfc\\u5165\\u65e7 Mod\\u201d\\u3002"))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_button = QPushButton(zh("\\u53d6\\u6d88"))
        save_button = QPushButton(zh("\\u5bfc\\u5165"))
        save_button.setObjectName("primaryButton")
        cancel_button.clicked.connect(self.reject)
        save_button.clicked.connect(self.accept)
        buttons.addWidget(cancel_button)
        buttons.addWidget(save_button)
        layout.addLayout(buttons)

    def _card(self, title_text: str) -> QFrame:
        card = QFrame()
        card.setObjectName("dialogCard")
        title = QLabel(title_text, card)
        title.setObjectName("cardTitle")
        title.setGeometry(14, 8, 360, 24)
        return card

    def _path_row(self, edit: QLineEdit, handler) -> QWidget:
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(edit)
        button = QPushButton(zh("\\u9009\\u62e9"))
        button.clicked.connect(handler)
        layout.addWidget(button)
        return box

    def _choose_source(self) -> None:
        file, _ = QFileDialog.getOpenFileName(self, zh("\\u9009\\u62e9\\u538b\\u7f29\\u5305"), filter="Mod (*.zip *.7z *.rar)")
        if file:
            self.source_edit.setText(file)
            return
        folder = QFileDialog.getExistingDirectory(self, zh("\\u9009\\u62e9 Mod \\u6587\\u4ef6\\u5939"))
        if folder:
            self.source_edit.setText(folder)

    def _choose_preview(self) -> None:
        file, _ = QFileDialog.getOpenFileName(self, zh("\\u9009\\u62e9\\u9884\\u89c8\\u56fe"), filter="Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if file:
            self.preview_edit.setText(file)

    def options(self) -> ImportOptions:
        preview = Path(self.preview_edit.text()) if self.preview_edit.text().strip() else None
        return ImportOptions(
            source=Path(self.source_edit.text().strip()),
            name=self.name_edit.text().strip(),
            author=self.author_edit.text().strip(),
            link=self.link_edit.text().strip(),
            order=self.order_spin.value(),
            preview=preview,
        )


class EditModDialog(QDialog):
    def __init__(self, mod, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(zh("\\u7f16\\u8f91 ") + mod.name)
        self.setMinimumWidth(520)
        self.name_edit = QLineEdit(mod.name)
        self.author_edit = QLineEdit(mod.author)
        self.link_edit = QLineEdit(mod.link)
        self.category_edit = QLineEdit(mod.category)
        self.order_spin = QSpinBox()
        self.order_spin.setRange(0, 9999)
        self.order_spin.setValue(mod.order)
        self.enabled_check = QCheckBox(zh("\\u542f\\u7528"))
        self.enabled_check.setChecked(mod.enabled)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow(zh("\\u540d\\u79f0"), self.name_edit)
        form.addRow(zh("\\u4f5c\\u8005"), self.author_edit)
        form.addRow(zh("\\u94fe\\u63a5"), self.link_edit)
        form.addRow(zh("\\u5206\\u7c7b"), self.category_edit)
        form.addRow(zh("\\u6392\\u5e8f"), self.order_spin)
        form.addRow(zh("\\u72b6\\u6001"), self.enabled_check)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel_button = QPushButton(zh("\\u53d6\\u6d88"))
        save_button = QPushButton(zh("\\u4fdd\\u5b58"))
        save_button.setObjectName("primaryButton")
        cancel_button.clicked.connect(self.reject)
        save_button.clicked.connect(self.accept)
        buttons.addWidget(cancel_button)
        buttons.addWidget(save_button)
        layout.addLayout(buttons)

    def values(self) -> tuple[str, str, str, str, int, bool]:
        return (
            self.name_edit.text().strip(),
            self.author_edit.text().strip(),
            self.link_edit.text().strip(),
            self.category_edit.text().strip(),
            self.order_spin.value(),
            self.enabled_check.isChecked(),
        )


class ImageLabel(QLabel):
    imageDropped = pyqtSignal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.image_path: Path | None = None
        self.hovered = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.paste_shortcut = QShortcut(QKeySequence("Ctrl+V"), self)
        self.paste_shortcut.activated.connect(self.paste_image_from_clipboard)

    def set_image(self, path: Path | str | None, size: int = 96) -> None:
        self.image_path = Path(path) if path else None
        self.setFixedSize(size, size)
        self.setScaledContents(False)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if not path:
            self.setText(zh("\\u65e0\\u9884\\u89c8"))
            return
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.setText(zh("\\u65e0\\u9884\\u89c8"))
            return
        self.setText("")
        self.setPixmap(square_thumbnail(pixmap, size))

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self.hovered or not self.image_path or not self.image_path.exists():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(15, 23, 42, 96))
        center = self.rect().center()
        eye_width = max(34, min(self.width(), self.height()) // 2)
        eye_height = max(18, eye_width // 2)
        eye_rect = self.rect().adjusted(0, 0, 0, 0)
        eye_rect.setWidth(eye_width)
        eye_rect.setHeight(eye_height)
        eye_rect.moveCenter(center)
        painter.setPen(QPen(QColor(255, 255, 255, 220), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(eye_rect)
        pupil_radius = max(4, eye_height // 4)
        painter.setBrush(QColor(255, 255, 255, 230))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, pupil_radius, pupil_radius)

    def enterEvent(self, event) -> None:
        self.hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.image_path and self.image_path.exists():
            dialog = ImagePreviewDialog(self.image_path, self)
            dialog.exec()
            event.accept()
            return
        super().mousePressEvent(event)

    def dragEnterEvent(self, event) -> None:
        mime = event.mimeData()
        if mime.hasImage() or mime.hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event) -> None:
        mime = event.mimeData()
        if mime.hasImage():
            self.imageDropped.emit(mime.imageData())
            event.acceptProposedAction()
            return
        if mime.hasUrls():
            for url in mime.urls():
                file_path = url.toLocalFile()
                if file_path:
                    self.imageDropped.emit(file_path)
                    event.acceptProposedAction()
                    return
        super().dropEvent(event)

    def paste_image_from_clipboard(self) -> None:
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()
        if mime.hasImage():
            self.imageDropped.emit(clipboard.image())
            return
        if mime.hasUrls():
            for url in mime.urls():
                file_path = url.toLocalFile()
                if file_path:
                    self.imageDropped.emit(file_path)
                    return


class ImagePreviewDialog(QDialog):
    def __init__(self, image_path: Path, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(image_path.name)
        self.resize(900, 700)
        self.original_pixmap = QPixmap(str(image_path))
        layout = QVBoxLayout(self)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setWidget(self.image)
        layout.addWidget(self.scroll)
        QTimer.singleShot(0, self.update_scaled_image)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.update_scaled_image()

    def update_scaled_image(self) -> None:
        if self.original_pixmap.isNull():
            self.image.setText(zh("\\u65e0\\u9884\\u89c8"))
            return
        size = self.scroll.viewport().size()
        if size.width() <= 0 or size.height() <= 0:
            return
        scaled = self.original_pixmap.scaled(size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.image.setPixmap(scaled)


def square_thumbnail(pixmap: QPixmap, size: int) -> QPixmap:
    source_size = min(pixmap.width(), pixmap.height())
    x = (pixmap.width() - source_size) // 2
    y = (pixmap.height() - source_size) // 2
    cropped = pixmap.copy(x, y, source_size, source_size)
    return cropped.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
