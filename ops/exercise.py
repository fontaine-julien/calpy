"""Petits outils de rendu communs au mode Entraînement."""

from __future__ import annotations

from typing import Optional, Sequence

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen


EXERCISE_BLUE = QColor(38, 101, 158)


def draw_answer_box(
    painter: QPainter,
    rect: QRectF | Sequence[float],
    value: Optional[str],
    reveal: bool,
    font: QFont,
) -> None:
    """Dessine une case de réponse et, si demandé, sa correction."""
    box = QRectF(rect) if isinstance(rect, QRectF) else QRectF(*rect)
    box = box.adjusted(2.0, 1.5, -2.0, -1.5)

    painter.save()
    pen = QPen(EXERCISE_BLUE)
    pen.setWidthF(1.6)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(box, 3.0, 3.0)

    if reveal and value is not None:
        painter.setFont(font)
        painter.setPen(EXERCISE_BLUE)
        painter.drawText(box, Qt.AlignHCenter | Qt.AlignVCenter, value)
    painter.restore()
