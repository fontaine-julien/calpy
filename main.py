"""Interface de CalPy, projection des calculs et export des fiches PDF."""


from __future__ import annotations
import sys
import tempfile
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QBuffer, QByteArray, QObject, Signal, QSize, QRect, QPoint, QPointF, QRectF, QTimer, QEvent
from PySide6.QtGui import QPixmap, QPainter, QFont, QColor, QImage, QIcon
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from ops.addition import AdditionWidget
from ops.subtraction import SubtractionWidget
from ops.multiplication import MultiplicationWidget
from ops.division import DivisionWidget

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas as rl_canvas


_PT_PER_CM = 28.346456692913385
MARGIN_CM = 1.0
TOP_MARGIN_CM = 0.2

SLOT_W_CM = 6.925
SLOT_H_CM = 4.5

MAX_EXPORT_OPS = 4


_OPERATION_PATTERNS = (
    ("Addition", re.compile(r"\+")),
    ("Soustraction", re.compile(r"[-−–]")),
    ("Multiplication", re.compile(r"[xX*×]")),
    ("Division", re.compile(r"(?:÷|/|:|\bdiv\b)", re.IGNORECASE)),
)


def detect_operation(expr: str) -> str:
    """Déduit l'opération de l'unique opérateur présent dans l'expression."""
    text = (expr or "").strip()
    detected = [name for name, pattern in _OPERATION_PATTERNS if pattern.search(text)]
    if not detected:
        raise ValueError("Opérateur introuvable : utilisez +, -, ×, * ou /.")
    if len(detected) > 1:
        raise ValueError("Saisissez une seule opération à la fois.")
    return detected[0]


def _pixmap_to_png_bytes(px: QPixmap) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.WriteOnly)
    px.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def _content_rect(px: QPixmap, bg_threshold: int = 240, pad: int = 12) -> QRect:
    """Repère la zone non blanche d'une image, avec une petite marge."""
    if px.isNull():
        return QRect()

    img = px.toImage().convertToFormat(QImage.Format_ARGB32)
    w, h = img.width(), img.height()

    # Une vignette suffit pour repérer les marges des captures haute définition.
    max_scan_side = 700
    if max(w, h) > max_scan_side:
        scan = img.scaled(
            max_scan_side,
            max_scan_side,
            Qt.KeepAspectRatio,
            Qt.FastTransformation,
        )
    else:
        scan = img
    sw, sh = scan.width(), scan.height()

    left, right = sw, -1
    top, bottom = sh, -1

    for y in range(sh):
        for x in range(sw):
            c = QColor(scan.pixel(x, y))
            if c.alpha() < 10:
                continue
            if (
                c.red() >= bg_threshold
                and c.green() >= bg_threshold
                and c.blue() >= bg_threshold
            ):
                continue

            left = min(left, x)
            right = max(right, x)
            top = min(top, y)
            bottom = max(bottom, y)

    if right < left or bottom < top:
        return px.rect()

    scale_x = w / sw
    scale_y = h / sh
    left = max(0, int(left * scale_x) - pad)
    top = max(0, int(top * scale_y) - pad)
    right = min(w - 1, int((right + 1) * scale_x) + pad)
    bottom = min(h - 1, int((bottom + 1) * scale_y) + pad)

    return QRect(left, top, right - left + 1, bottom - top + 1)


def _autocrop_pixmap(px: QPixmap, bg_threshold: int = 240, pad: int = 12) -> QPixmap:
    """Supprime automatiquement les bordures quasi blanches autour du calcul."""
    if px.isNull():
        return px
    return px.copy(_content_rect(px, bg_threshold=bg_threshold, pad=pad))


def _widget_logical_size(widget: QWidget) -> QSize:
    size = widget.size()
    if size.width() <= 0 or size.height() <= 0:
        size = widget.sizeHint().expandedTo(QSize(900, 500))
    return size


def _render_widget_raw(widget: QWidget, scale: float = 1.0) -> QPixmap:
    logical_size = _widget_logical_size(widget)
    px = QPixmap(
        max(1, round(logical_size.width() * scale)),
        max(1, round(logical_size.height() * scale)),
    )
    px.fill(Qt.white)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    painter.scale(scale, scale)
    widget.render(painter, QPoint())
    painter.end()
    return px


def _render_widget_pixmap(widget: QWidget, scale: float = 1.0) -> QPixmap:
    px = _render_widget_raw(widget, scale)
    return _autocrop_pixmap(px, pad=max(12, round(12 * scale)))


def _render_high_resolution_pixmap(
    widget: QWidget,
    *,
    target_w: float,
    target_h: float,
    max_w: float,
    max_h: float,
    max_scale: float,
) -> QPixmap:
    """Rend uniquement la zone du calcul à la définition demandée."""
    probe = _render_widget_raw(widget, scale=1.0)
    region = _content_rect(probe, pad=16)
    if region.isEmpty():
        return probe

    scale = max(
        2.0,
        target_w / max(1, region.width()),
        target_h / max(1, region.height()),
    )
    scale = min(
        max_scale,
        scale,
        max_w / max(1, region.width()),
        max_h / max(1, region.height()),
    )
    scale = max(1.0, scale)

    px = QPixmap(
        max(1, round(region.width() * scale)),
        max(1, round(region.height() * scale)),
    )
    px.fill(Qt.white)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    painter.scale(scale, scale)
    painter.translate(-region.x(), -region.y())
    widget.render(painter, QPoint())
    painter.end()
    return px


def _render_projector_pixmap(widget: QWidget) -> QPixmap:
    """Adapte la définition du calcul à la projection plein écran."""
    return _render_high_resolution_pixmap(
        widget,
        target_w=2400.0,
        target_h=1600.0,
        max_w=4096.0,
        max_h=3072.0,
        max_scale=12.0,
    )


def _try_grab_widget_png(widget: QWidget) -> Optional[bytes]:
    try:
        px = _render_high_resolution_pixmap(
            widget,
            target_w=1200.0,
            target_h=800.0,
            max_w=2048.0,
            max_h=1536.0,
            max_scale=8.0,
        )
        if px.isNull():
            return None
        return _pixmap_to_png_bytes(px)
    except Exception:
        return None


def _fallback_text_png(title: str, expr: str) -> bytes:
    px = QPixmap(QSize(900, 300))
    px.fill(Qt.white)

    p = QPainter(px)
    f = QFont("Consolas", 28)
    f.setStyleHint(QFont.Monospace)
    p.setFont(f)
    p.setPen(Qt.black)

    p.drawText(20, 60, title)
    p.drawText(20, 120, expr if expr else "(capture indisponible)")
    p.end()

    return _pixmap_to_png_bytes(px)


def _fit_rect_keep_aspect(iw, ih, bw, bh):
    scale = min(bw / iw, bh / ih)
    return iw * scale, ih * scale


def _compose_training_pixmaps(pixmaps: List[QPixmap]) -> QPixmap:
    """Répartit les calculs en colonnes égales sans rogner le plus haut."""
    if not pixmaps:
        return QPixmap()
    padding, gap = 32, 48
    column_width = max(px.width() for px in pixmaps)
    height = max(px.height() for px in pixmaps)
    result = QPixmap(
        2 * padding + len(pixmaps) * column_width + (len(pixmaps) - 1) * gap,
        2 * padding + height,
    )
    result.fill(Qt.white)
    painter = QPainter(result)
    for index, px in enumerate(pixmaps):
        left = padding + index * (column_width + gap)
        painter.drawPixmap(left + (column_width - px.width()) // 2, padding, px)
        if index:
            painter.setPen(QColor(210, 220, 230))
            painter.drawLine(left - gap // 2, padding, left - gap // 2, padding + height)
    painter.end()
    return result


def _draw_small_caps_centered(c, text: str, cx: float, cy: float, font_name: str = "Helvetica", size: float = 12.0):
    small = size * 0.75
    parts: List[Tuple[str, float]] = []
    for ch in (text or ""):
        if ch.isalpha():
            if ch.islower():
                parts.append((ch.upper(), small))
            else:
                parts.append((ch.upper(), size))
        else:
            parts.append((ch, size))

    total_w = 0.0
    for ch, fs in parts:
        total_w += pdfmetrics.stringWidth(ch, font_name, fs)

    x = cx - (total_w / 2.0)
    for ch, fs in parts:
        c.setFont(font_name, fs)
        w = pdfmetrics.stringWidth(ch, font_name, fs)
        c.drawString(x, cy - (fs * 0.35), ch)
        x += w


class ProjectorCanvas(QWidget):
    """Surface de projection avec zoom et déplacement à la souris."""

    revealRequested = Signal()
    hideRequested = Signal()

    def __init__(self, pixmap: QPixmap, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._pixmap = pixmap
        self._zoom = 1.0
        self._offset = QPointF(0.0, 0.0)
        self._drag_origin: Optional[QPointF] = None
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.OpenHandCursor)
        self.setMouseTracking(True)

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self._pixmap = pixmap
        self.update()

    def _fit_scale(self) -> float:
        if self._pixmap.isNull():
            return 1.0
        usable_w = max(1.0, self.width() - 64.0)
        usable_h = max(1.0, self.height() - 64.0)
        return min(usable_w / self._pixmap.width(), usable_h / self._pixmap.height())

    def _scale(self) -> float:
        return self._fit_scale() * self._zoom

    def _top_left(self, scale: float) -> QPointF:
        centered = QPointF(
            (self.width() - self._pixmap.width() * scale) / 2.0,
            (self.height() - self._pixmap.height() * scale) / 2.0,
        )
        return centered + self._offset

    def reset_view(self) -> None:
        self._zoom = 1.0
        self._offset = QPointF(0.0, 0.0)
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.white)
        if self._pixmap.isNull():
            return
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        scale = self._scale()
        top_left = self._top_left(scale)
        target = QRectF(
            top_left.x(),
            top_left.y(),
            self._pixmap.width() * scale,
            self._pixmap.height() * scale,
        )
        painter.drawPixmap(target, self._pixmap, QRectF(self._pixmap.rect()))

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            delta = event.pixelDelta().y()
        if delta == 0 or self._pixmap.isNull():
            event.ignore()
            return

        old_scale = self._scale()
        old_top_left = self._top_left(old_scale)
        cursor = event.position()
        image_point = QPointF(
            (cursor.x() - old_top_left.x()) / old_scale,
            (cursor.y() - old_top_left.y()) / old_scale,
        )

        factor = 1.15 if delta > 0 else (1.0 / 1.15)
        self._zoom = max(0.2, min(8.0, self._zoom * factor))
        new_scale = self._scale()
        centered = QPointF(
            (self.width() - self._pixmap.width() * new_scale) / 2.0,
            (self.height() - self._pixmap.height() * new_scale) / 2.0,
        )
        self._offset = cursor - centered - QPointF(
            image_point.x() * new_scale,
            image_point.y() * new_scale,
        )
        self.update()
        event.accept()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_origin = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_origin is not None:
            current = event.position()
            self._offset += current - self._drag_origin
            self._drag_origin = current
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._drag_origin is not None:
            self._drag_origin = None
            self.setCursor(Qt.OpenHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.reset_view()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            if isinstance(self.window(), ProjectorWindow):
                self.window().close()
            return
        if event.key() == Qt.Key_R:
            self.revealRequested.emit()
            return
        if event.key() == Qt.Key_C:
            self.hideRequested.emit()
            return
        super().keyPressEvent(event)


class ProjectorWindow(QMainWindow):
    def __init__(self, pixmap: QPixmap, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("CalPy - Mode vidéoprojecteur")
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.canvas = ProjectorCanvas(pixmap, self)
        self.setCentralWidget(self.canvas)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.canvas.setFocus(Qt.OtherFocusReason)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)


class PdfPreviewDialog(QDialog):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Aperçu du PDF")
        self.resize(1000, 720)

        self.document = QPdfDocument(self)
        self._pdf_buffer: Optional[QBuffer] = None
        self.view = QPdfView(self)
        self.view.setDocument(self.document)
        self.view.setPageMode(QPdfView.PageMode.MultiPage)
        self.view.setZoomMode(QPdfView.ZoomMode.FitInView)

        self.info = QLabel("L'aperçu correspond exactement au document exporté.")
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.close)

        layout = QVBoxLayout(self)
        layout.addWidget(self.info)
        layout.addWidget(self.view, 1)
        layout.addWidget(buttons)

    def load_pdf(self, path: str, item_count: int) -> None:
        self.document.close()
        if self._pdf_buffer is not None:
            self._pdf_buffer.close()
            self._pdf_buffer.deleteLater()

        # La lecture en mémoire évite de verrouiller le PDF sous Windows.
        self._pdf_buffer = QBuffer(self)
        self._pdf_buffer.setData(QByteArray(Path(path).read_bytes()))
        self._pdf_buffer.open(QBuffer.ReadOnly)
        error = self.document.load(self._pdf_buffer)
        # Avec un QBuffer, Qt charge le PDF de façon asynchrone.
        if error is not None and error != QPdfDocument.Error.None_:
            raise RuntimeError(f"Impossible de charger l'aperçu PDF ({error}).")
        self.info.setText(
            f"Aperçu réel du PDF - {item_count} opération"
            f"{'s' if item_count > 1 else ''} ajoutée{'s' if item_count > 1 else ''}."
        )
        self.view.setZoomMode(QPdfView.ZoomMode.FitInView)
        self.show()
        self.raise_()
        self.activateWindow()


@dataclass
class ExportItem:
    op_key: str
    expr: str
    png_bytes: bytes


class ExportManager(QObject):
    changed = Signal()

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._items: List[ExportItem] = []
        self._temp_dir = tempfile.TemporaryDirectory(prefix="calpy-preview-")
        self._preview_path = str(Path(self._temp_dir.name) / "apercu.pdf")
        self._preview_dialog = PdfPreviewDialog(parent)

    def items(self):
        return list(self._items)

    def can_add_more(self):
        return len(self._items) < MAX_EXPORT_OPS

    def try_add(self, op_key, expr, widget):
        if not self.can_add_more():
            return False

        png = _try_grab_widget_png(widget)
        if png is None:
            png = _fallback_text_png(op_key, expr)

        self._items.append(ExportItem(op_key, expr, png))
        self.changed.emit()
        return True

    def preview_pdf(self, title: str = "") -> None:
        if not self._items:
            return
        self._write_pdf(self._preview_path, title)
        self._preview_dialog.load_pdf(self._preview_path, len(self._items))

    def is_preview_visible(self) -> bool:
        return self._preview_dialog.isVisible()

    def close_preview(self) -> None:
        self._preview_dialog.close()

    def export_pdf(self, parent: QWidget, title: str = "") -> Optional[str]:
        if not self._items:
            return None

        path, _ = QFileDialog.getSaveFileName(parent, "Exporter le PDF", "export.pdf", "PDF (*.pdf)")
        if not path:
            return None
        if not path.lower().endswith(".pdf"):
            path += ".pdf"

        self._write_pdf(path, title)
        return path

    def _write_pdf(self, path, title: str):
        page_w, page_h = landscape(A4)
        c = rl_canvas.Canvas(path, pagesize=(page_w, page_h))

        margin_lr = MARGIN_CM * _PT_PER_CM
        bottom_margin = MARGIN_CM * _PT_PER_CM
        top_margin = TOP_MARGIN_CM * _PT_PER_CM
        center_gap = 0.0 * _PT_PER_CM

        mid = page_w / 2
        left_x0 = margin_lr
        left_x1 = mid - center_gap
        right_x0 = mid + center_gap
        right_x1 = page_w - margin_lr

        slot_w = SLOT_W_CM * _PT_PER_CM
        slot_h = SLOT_H_CM * _PT_PER_CM

        title_box_w = 13.5 * _PT_PER_CM
        title_box_h = 0.7 * _PT_PER_CM
        title_gap = 0.2 * _PT_PER_CM

        def draw_title_box(x0, x1):
            col_w = x1 - x0
            x = x0 + (col_w - title_box_w) / 2
            y = page_h - top_margin - title_box_h
            c.setStrokeColorRGB(0, 0, 0)
            c.setLineWidth(1)
            c.setFillColorRGB(0.9, 0.9, 0.9)
            c.rect(x, y, title_box_w, title_box_h, stroke=1, fill=1)
            c.setFillColorRGB(0, 0, 0)

            _draw_small_caps_centered(
                c,
                title or "",
                cx=x + (title_box_w / 2),
                cy=y + (title_box_h / 2),
                font_name="Helvetica",
                size=12.0,
            )

        def slot_positions(x0, x1):
            col_w = x1 - x0
            y_start = page_h - top_margin - title_box_h - title_gap
            col_h = y_start - bottom_margin

            desired_side_x = 0.2 * _PT_PER_CM
            min_inner_gap_x = 0.2 * _PT_PER_CM

            inner_gap_x = col_w - (2 * slot_w) - (2 * desired_side_x)
            if inner_gap_x < min_inner_gap_x:
                inner_gap_x = min_inner_gap_x
                side_x = max(0.0, (col_w - (2 * slot_w) - inner_gap_x) / 2)
            else:
                side_x = desired_side_x

            desired_top_gap = 0.2 * _PT_PER_CM
            desired_bottom_gap = 0.2 * _PT_PER_CM
            min_inner_gap_y = 0.2 * _PT_PER_CM

            inner_gap_y = col_h - desired_top_gap - desired_bottom_gap - (2 * slot_h)
            if inner_gap_y < min_inner_gap_y:
                inner_gap_y = min_inner_gap_y
                top_gap = max(0.0, col_h - desired_bottom_gap - (2 * slot_h) - inner_gap_y)
            else:
                top_gap = desired_top_gap
            bottom_gap = desired_bottom_gap

            x_left = x0 + side_x
            x_right = x_left + slot_w + inner_gap_x

            y_bottom = bottom_margin + bottom_gap
            y_top = y_bottom + slot_h + inner_gap_y

            if (y_top + slot_h) > (y_start - top_gap):
                y_top = max(y_bottom, y_start - top_gap - slot_h)
                y_bottom = max(bottom_margin, y_top - inner_gap_y - slot_h)

            return [
                (x_left, y_top),
                (x_right, y_top),
                (x_left, y_bottom),
                (x_right, y_bottom),
            ]

        draw_title_box(left_x0, left_x1)
        draw_title_box(right_x0, right_x1)

        left_slots = slot_positions(left_x0, left_x1)
        right_slots = slot_positions(right_x0, right_x1)

        def draw(items, slots):
            for i, item in enumerate(items[:4]):
                x, y = slots[i]
                img = ImageReader(BytesIO(item.png_bytes))
                iw, ih = img.getSize()
                dw, dh = _fit_rect_keep_aspect(iw, ih, slot_w, slot_h)
                c.drawImage(img, x + (slot_w - dw) / 2, y + (slot_h - dh) / 2, dw, dh)

        # La feuille contient deux exemplaires identiques à découper.
        draw(self._items, left_slots)
        draw(self._items, right_slots)

        c.showPage()
        c.save()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CalPy")
        icon_path = Path(__file__).resolve().parent / "icone.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.export_manager = ExportManager(self)
        self._projector: Optional[ProjectorWindow] = None
        self._correction_visible = False
        self._current_operation: Optional[str] = None
        self._training_widgets: List[QWidget] = []
        self._training_expressions: List[str] = []
        self._preview_refresh_timer = QTimer(self)
        self._preview_refresh_timer.setSingleShot(True)
        self._preview_refresh_timer.setInterval(300)
        self._preview_refresh_timer.timeout.connect(self._refresh_open_preview)

        self.mode_tabs = QTabBar()
        self.mode_tabs.addTab("Calcul")
        self.mode_tabs.addTab("Entraînement")
        self.mode_tabs.setExpanding(False)

        self.expr_edit = QLineEdit()
        self.expr_edit.setClearButtonEnabled(True)
        self.expr_edit.setPlaceholderText(
            "Ex. 1246 + 325, 493 × 37 ou 12,43 ÷ 4,56"
        )
        self.detected_operation_label = QLabel("Opération : en attente")
        self.detected_operation_label.setMinimumWidth(190)

        self.show_btn = QPushButton("Afficher")
        self.correction_btn = QPushButton("Révéler la correction (R)")
        self.correction_btn.setVisible(False)
        self.projector_btn = QPushButton("Vidéoprojecteur")
        self.projector_btn.setToolTip(
            "Plein écran : molette ou pavé tactile pour zoomer, clic gauche pour déplacer, Échap pour quitter."
        )

        self.plus_btn = QPushButton("+")
        self.plus_btn.setFixedWidth(38)
        self.plus_btn.setToolTip("Ajouter le calcul au PDF et ouvrir son aperçu")

        self.pdf_title_edit = QLineEdit()
        self.pdf_title_edit.setPlaceholderText("Titre du PDF (facultatif)")
        self.pdf_title_edit.setClearButtonEnabled(True)

        self.item_count_label = QLabel(f"0/{MAX_EXPORT_OPS}")
        self.preview_btn = QPushButton("Aperçu PDF")
        self.preview_btn.setEnabled(False)

        self.export_btn = QPushButton("Exporter le PDF")
        self.export_btn.setEnabled(False)

        self.stack = QStackedWidget()
        self.widgets: Dict[str, QWidget] = {
            "Addition": AdditionWidget(),
            "Soustraction": SubtractionWidget(),
            "Multiplication": MultiplicationWidget(),
            "Division": DivisionWidget(),
        }
        self.pages: Dict[str, QScrollArea] = {}

        for name, widget in self.widgets.items():
            page = QScrollArea()
            page.setFrameShape(QFrame.NoFrame)
            page.setWidgetResizable(True)
            page.setAlignment(Qt.AlignCenter)
            page.setWidget(widget)
            self.pages[name] = page
            self.stack.addWidget(page)

        self.training_preview = ProjectorCanvas(QPixmap())
        self.stack.addWidget(self.training_preview)
        self.training_preview.revealRequested.connect(lambda: self._set_correction_visible(True))
        self.training_preview.hideRequested.connect(lambda: self._set_correction_visible(False))
        self.training_count = QComboBox()
        self.training_count.addItems(["1 calcul", "2 calculs côte à côte", "3 calculs côte à côte"])
        self.training_bar = QWidget()
        training_row = QHBoxLayout(self.training_bar)
        training_row.setContentsMargins(0, 0, 0, 0)
        training_row.addWidget(QLabel("Disposition"))
        training_row.addWidget(self.training_count)
        self.training_inputs = [self.expr_edit]
        self._extra_training_fields = []
        for index in (2, 3):
            field = QWidget()
            row = QHBoxLayout(field)
            row.setContentsMargins(0, 0, 0, 0)
            edit = QLineEdit()
            edit.setPlaceholderText("Ex. 493 × 37 ou 1248 ÷ 6")
            edit.setClearButtonEnabled(True)
            edit.returnPressed.connect(self._show)
            row.addWidget(QLabel(f"Calcul {index}"))
            row.addWidget(edit, 1)
            training_row.addWidget(field, 1)
            self.training_inputs.append(edit)
            self._extra_training_fields.append(field)
        self.training_count.currentIndexChanged.connect(self._change_training_count)

        operation_row = QHBoxLayout()
        operation_row.addWidget(QLabel("Expression"))
        operation_row.addWidget(self.expr_edit, 1)
        operation_row.addWidget(self.detected_operation_label)
        operation_row.addWidget(self.show_btn)
        operation_row.addWidget(self.correction_btn)
        operation_row.addWidget(self.projector_btn)

        document_row = QHBoxLayout()
        document_row.addWidget(QLabel("Document"))
        document_row.addWidget(self.pdf_title_edit, 1)
        document_row.addWidget(self.plus_btn)
        document_row.addWidget(self.item_count_label)
        document_row.addWidget(self.preview_btn)
        document_row.addWidget(self.export_btn)

        self.document_bar = QWidget()
        self.document_bar.setLayout(document_row)
        document_row.setContentsMargins(0, 0, 0, 0)

        root = QVBoxLayout()
        root.setContentsMargins(12, 12, 12, 10)
        root.setSpacing(8)
        root.addWidget(self.mode_tabs)
        root.addLayout(operation_row)
        root.addWidget(self.training_bar)
        root.addWidget(self.document_bar)
        root.addWidget(self.stack, 1)

        container = QWidget()
        container.setLayout(root)
        self.setCentralWidget(container)

        self.mode_tabs.currentChanged.connect(self._change_mode)
        self.show_btn.clicked.connect(self._show)
        self.expr_edit.textChanged.connect(self._detect_from_input)
        self.expr_edit.returnPressed.connect(self._show)
        self.correction_btn.clicked.connect(self._toggle_correction)
        self.projector_btn.clicked.connect(self._show_projector)
        self.plus_btn.clicked.connect(self._add_export)
        self.preview_btn.clicked.connect(self._show_pdf_preview)
        self.export_btn.clicked.connect(self._export_pdf)
        self.pdf_title_edit.textChanged.connect(lambda *_: self._preview_refresh_timer.start())
        self.export_manager.changed.connect(self._sync_buttons)

        self._change_mode(self.mode_tabs.currentIndex())
        self.statusBar().showMessage("Prêt")
        QApplication.instance().installEventFilter(self)

    def _is_training_mode(self) -> bool:
        return self.mode_tabs.currentIndex() == 1

    def _multiple_training(self) -> bool:
        return self._is_training_mode() and self.training_count.currentIndex() > 0

    def _change_training_count(self, *_args) -> None:
        count = self.training_count.currentIndex() + 1
        for index, field in enumerate(self._extra_training_fields, start=2):
            field.setVisible(index <= count)
        for widget in self._training_widgets:
            widget.deleteLater()
        self._training_widgets = []
        self._training_expressions = []
        self.training_preview.set_pixmap(QPixmap())
        self.training_preview.reset_view()
        if self._multiple_training():
            self.stack.setCurrentWidget(self.training_preview)
            if self._projector is not None:
                self._projector.canvas.set_pixmap(QPixmap())
        elif self._current_operation:
            self.stack.setCurrentWidget(self.pages[self._current_operation])
        self._set_correction_visible(False)

    def _training_pixmap(self) -> QPixmap:
        images = []
        for widget in self._training_widgets:
            widget.ensurePolished()
            widget.resize(widget.sizeHint().expandedTo(widget.minimumSizeHint()).expandedTo(QSize(900, 500)))
            widget.layout().activate()
            images.append(_render_widget_pixmap(widget, scale=2.0))
        return _compose_training_pixmaps(images)

    def _show_training(self) -> bool:
        expressions = [edit.text().strip() for edit in self.training_inputs[:self.training_count.currentIndex() + 1]]
        if expressions == self._training_expressions:
            return True
        # Valider tous les calculs avant de remplacer ceux déjà affichés.
        pending = []
        try:
            for index, expression in enumerate(expressions, start=1):
                if not expression:
                    raise ValueError(f"Calcul {index} : saisissez une opération.")
                operation = detect_operation(expression)
                widget = type(self.widgets[operation])()
                widget.setParent(self)
                widget.hide()
                pending.append(widget)
                widget.set_exercise_mode(True)
                try:
                    widget.set_expression(expression)
                except ValueError as exc:
                    raise ValueError(f"Calcul {index} : {exc}") from exc
        except Exception as exc:
            for widget in pending:
                widget.deleteLater()
            QMessageBox.warning(self, "Expression invalide", str(exc))
            return False
        for widget in self._training_widgets:
            widget.deleteLater()
        self._training_widgets = pending
        self._training_expressions = expressions
        self.stack.setCurrentWidget(self.training_preview)
        self.training_preview.reset_view()
        self._set_correction_visible(False)
        self.statusBar().showMessage("Calculs affichés côte à côte.", 3000)
        return True

    def eventFilter(self, watched, event) -> bool:
        if (
            self._is_training_mode()
            and event.type() == QEvent.KeyPress
            and event.modifiers() == Qt.NoModifier
        ):
            if event.key() == Qt.Key_R:
                self._set_correction_visible(True)
                return True
            if event.key() == Qt.Key_C:
                self._set_correction_visible(False)
                return True
        return super().eventFilter(watched, event)

    def closeEvent(self, event) -> None:
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        super().closeEvent(event)

    def _change_mode(self, index: int) -> None:
        training = index == 1
        self.training_bar.setVisible(training)
        self.document_bar.setVisible(not training)
        self.correction_btn.setVisible(training)
        self.show_btn.setText("Afficher l'exercice" if training else "Afficher")

        for widget in self.widgets.values():
            if hasattr(widget, "set_exercise_mode"):
                widget.set_exercise_mode(training)

        self._correction_visible = False
        for widget in self.widgets.values():
            if hasattr(widget, "set_correction_visible"):
                widget.set_correction_visible(False)
        self.correction_btn.setText("Révéler la correction (R)")
        self._change_training_count()

        if training:
            self.export_manager.close_preview()
            self.statusBar().showMessage(
                "Mode Entraînement : R révèle la correction, C la cache.",
                5000,
            )
        else:
            self.statusBar().showMessage("Mode Calcul.", 3000)
        self._refresh_projector_pixmap()

    def _toggle_correction(self) -> None:
        self._set_correction_visible(not self._correction_visible)

    def _set_correction_visible(self, visible: bool) -> None:
        if not self._is_training_mode():
            return
        self._correction_visible = visible
        for widget in self.widgets.values():
            if hasattr(widget, "set_correction_visible"):
                widget.set_correction_visible(visible)

        for widget in self._training_widgets:
            widget.set_correction_visible(visible)
        if self._multiple_training():
            self.training_preview.set_pixmap(self._training_pixmap())

        self.correction_btn.setText(
            "Cacher la correction (C)" if visible else "Révéler la correction (R)"
        )
        self.statusBar().showMessage(
            "Correction révélée." if visible else "Correction cachée.",
            3000,
        )
        self._refresh_projector_pixmap()

    def _set_operation(self, operation: str) -> None:
        self._current_operation = operation
        if not self._multiple_training():
            self.stack.setCurrentWidget(self.pages[operation])
        self.detected_operation_label.setText(f"Opération : {operation}")

    def _detect_from_input(self, expression: str) -> None:
        if not expression.strip():
            self._current_operation = None
            self.detected_operation_label.setText("Opération : en attente")
            return
        try:
            self._set_operation(detect_operation(expression))
        except ValueError:
            self._current_operation = None
            self.detected_operation_label.setText("Opération : saisie ambiguë")

    def _show(self) -> bool:
        if self._multiple_training():
            return self._show_training()
        expression = self.expr_edit.text().strip()
        if not expression:
            QMessageBox.information(self, "Expression manquante", "Saisissez d'abord une opération.")
            return False

        try:
            operation = detect_operation(expression)
            self._set_operation(operation)
            w = self.widgets[operation]
            if hasattr(w, "set_expression"):
                w.set_expression(expression)
            self.statusBar().showMessage("Calcul affiché.", 3000)
            self._refresh_projector_pixmap()
            return True
        except ValueError as exc:
            self.statusBar().showMessage(str(exc), 5000)
            QMessageBox.warning(self, "Expression invalide", str(exc))
        except Exception as exc:
            self.statusBar().showMessage("Le calcul n'a pas pu être affiché.", 5000)
            QMessageBox.critical(self, "Erreur de calcul", str(exc))
        return False

    def _add_export(self):
        if not self._show():
            return
        operation = self._current_operation
        if operation is None:
            return
        w = self.widgets[operation]
        added = self.export_manager.try_add(
            operation,
            self.expr_edit.text().strip(),
            w,
        )
        if not added:
            QMessageBox.information(
                self,
                "Document complet",
                f"Le PDF accepte au maximum {MAX_EXPORT_OPS} opérations.",
            )
            return
        self.statusBar().showMessage("Opération ajoutée au document.", 3000)
        self._show_pdf_preview()

    def _show_projector(self):
        if not self._show():
            return
        try:
            pixmap = self._training_pixmap() if self._multiple_training() else _render_projector_pixmap(self.widgets[self._current_operation])
            if pixmap.isNull():
                raise RuntimeError("La capture du calcul est vide.")
            if self._projector is not None:
                self._projector.close()
            self._projector = ProjectorWindow(pixmap, self)
            self._projector.setAttribute(Qt.WA_DeleteOnClose, True)
            self._projector.canvas.revealRequested.connect(
                lambda: self._set_correction_visible(True)
            )
            self._projector.canvas.hideRequested.connect(
                lambda: self._set_correction_visible(False)
            )
            self._projector.destroyed.connect(lambda *_: setattr(self, "_projector", None))
            self._projector.showFullScreen()
        except Exception as exc:
            QMessageBox.critical(self, "Mode vidéoprojecteur", str(exc))

    def _refresh_projector_pixmap(self) -> None:
        if self._projector is None or not self._projector.isVisible():
            return
        if self._multiple_training():
            self._projector.canvas.set_pixmap(self.training_preview._pixmap)
            self._projector.canvas.reset_view()
            return
        if self._current_operation is None:
            return
        operation_widget = self.widgets[self._current_operation]
        operation_widget.update()
        QApplication.processEvents()
        pixmap = _render_projector_pixmap(operation_widget)
        if not pixmap.isNull():
            self._projector.canvas.set_pixmap(pixmap)

    def _show_pdf_preview(self):
        try:
            self.export_manager.preview_pdf(self.pdf_title_edit.text().strip())
        except Exception as exc:
            QMessageBox.critical(self, "Aperçu PDF", str(exc))

    def _refresh_open_preview(self):
        if self.export_manager.items() and self.export_manager.is_preview_visible():
            self._show_pdf_preview()

    def _export_pdf(self):
        try:
            path = self.export_manager.export_pdf(self, self.pdf_title_edit.text().strip())
            if path:
                self.statusBar().showMessage(f"PDF exporté : {path}", 6000)
        except Exception as exc:
            QMessageBox.critical(self, "Export PDF", str(exc))

    def _sync_buttons(self):
        item_count = len(self.export_manager.items())
        self.plus_btn.setEnabled(self.export_manager.can_add_more())
        self.preview_btn.setEnabled(item_count > 0)
        self.export_btn.setEnabled(item_count > 0)
        self.item_count_label.setText(f"{item_count}/{MAX_EXPORT_OPS}")


def main():
    app = QApplication(sys.argv)
    icon_path = Path(__file__).resolve().parent / "icone.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    w = MainWindow()
    w.resize(1280, 760)
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
