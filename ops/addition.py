"""Calcul et affichage de l’addition posée."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ops.exercise import draw_answer_box


Cell = Optional[int]  # None représente une case vide.


@dataclass(frozen=True)
class AdditionLayout:
    a_cells: List[Cell]
    b_cells: List[Cell]
    result_digits: List[int]
    carries: List[Optional[int]]
    a_comma_boundary: Optional[int]
    b_comma_boundary: Optional[int]
    r_comma_boundary: Optional[int]


_DEC_RE = re.compile(r"^\d+(?:[.,]\d+)?$")


def _split_decimal_token(tok: str) -> Tuple[str, str]:
    """Sépare les parties entière et décimale."""
    t = tok.strip()
    if not _DEC_RE.fullmatch(t):
        raise ValueError("Expression invalide. Exemple : 1246 + 325 ou 12,5 + 3,4")

    if "," in t:
        left, right = t.split(",", 1)
        return left, right
    if "." in t:
        left, right = t.split(".", 1)
        return left, right
    return t, ""


def parse_addition(expr: str) -> Tuple[str, str, str, str]:
    s = expr.strip()
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*\+\s*(\d+(?:[.,]\d+)?)", s)
    if not m:
        raise ValueError("Expression invalide. Exemple : 1246 + 325 ou 12,5 + 3,4")

    a_tok = m.group(1)
    b_tok = m.group(2)

    a_int, a_frac = _split_decimal_token(a_tok)
    b_int, b_frac = _split_decimal_token(b_tok)

    return a_int, a_frac, b_int, b_frac


def _build_operand_cells(
    int_part: str,
    frac_part_padded: str,
    width: int,
    int_len: int,
    frac_len: int,
    base: int,
) -> List[Cell]:
    """Aligne les unités et complète la partie décimale par des zéros visibles."""
    cells: List[Cell] = [None] * width

    missing = int_len - len(int_part)
    for j in range(int_len):
        col = base + j
        if j < missing:
            cells[col] = None
        else:
            cells[col] = int(int_part[j - missing])

    for k in range(frac_len):
        col = base + int_len + k
        cells[col] = int(frac_part_padded[k])

    return cells


def compute_french_addition(a_int: str, a_frac: str, b_int: str, b_frac: str) -> AdditionLayout:
    # Compléter les décimales pour aligner les chiffres de même rang.
    max_dec = max(len(a_frac), len(b_frac))
    a_frac_padded = a_frac.ljust(max_dec, "0")
    b_frac_padded = b_frac.ljust(max_dec, "0")

    int_len = max(len(a_int), len(b_int))
    a_int_calc = a_int.rjust(int_len, "0")
    b_int_calc = b_int.rjust(int_len, "0")

    a_calc = a_int_calc + a_frac_padded
    b_calc = b_int_calc + b_frac_padded
    n = int_len + max_dec

    carry = 0
    res_rev: List[int] = []
    carry_out_by_col_rev: List[Optional[int]] = []

    for i in range(n - 1, -1, -1):
        s = int(a_calc[i]) + int(b_calc[i]) + carry
        res_rev.append(s % 10)
        carry = s // 10
        carry_out_by_col_rev.append(carry if carry != 0 else None)

    if carry != 0:
        res_rev.append(carry)

    result_digits = list(reversed(res_rev))
    width = len(result_digits)
    base = width - n  # Une retenue finale décale les opérandes d’une colonne.

    a_cells = _build_operand_cells(a_int, a_frac_padded, width, int_len, max_dec, base)
    b_cells = _build_operand_cells(b_int, b_frac_padded, width, int_len, max_dec, base)

    # Chaque retenue s’affiche au-dessus de la colonne à laquelle elle s’ajoute.
    carries: List[Optional[int]] = [None] * width
    for idx_from_right in range(n):
        carry_val = carry_out_by_col_rev[idx_from_right]
        if carry_val is None:
            continue
        col_in_operands = n - 1 - idx_from_right
        col_in_grid = base + col_in_operands
        target = col_in_grid - 1
        if target >= 0:
            carries[target] = carry_val
        else:
            carries[0] = carry_val

    if max_dec > 0:
        boundary = base + int_len
        a_comma = boundary
        b_comma = boundary
        r_comma = boundary
    else:
        a_comma = b_comma = r_comma = None

    return AdditionLayout(a_cells, b_cells, result_digits, carries, a_comma, b_comma, r_comma)


class AdditionCanvas(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._layout: Optional[AdditionLayout] = None
        self._exercise_mode = False
        self._show_correction = False
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(QSize(520, 260))
        self.font_big = QFont("DejaVu Sans Mono", 28)
        self.font_small = QFont("DejaVu Sans Mono", 16)

    def set_layout(self, layout: Optional[AdditionLayout]) -> None:
        self._layout = layout
        self.update()

    def set_exercise_mode(self, enabled: bool) -> None:
        self._exercise_mode = enabled
        if not enabled:
            self._show_correction = False
        self.update()

    def set_correction_visible(self, visible: bool) -> None:
        self._show_correction = self._exercise_mode and visible
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), self.palette().base())

        if self._layout is None:
            p.setFont(QFont("DejaVu Sans", 13))
            p.setPen(self.palette().text().color())
            p.drawText(
                self.rect(),
                Qt.AlignCenter,
                "Saisir une addition (ex. 1246 + 325 ou 12,5 + 3,4), puis Entrée.",
            )
            return

        lay = self._layout
        width = len(lay.result_digits)

        fm_big = QFontMetrics(self.font_big)
        fm_small = QFontMetrics(self.font_small)

        cell_w = max(fm_big.horizontalAdvance("8"), fm_small.horizontalAdvance("8")) + 12
        cell_h = fm_big.height() + 10

        top_margin = 18
        left_margin = 24

        plus_zone_w = fm_big.horizontalAdvance("+") + 16
        total_w = plus_zone_w + width * cell_w

        x0 = max(left_margin, (self.width() - total_w) // 2)
        x_digits = x0 + plus_zone_w

        y_carry = top_margin + fm_small.ascent()
        y_a = top_margin + fm_small.height() + 14 + fm_big.ascent()
        y_b = y_a + cell_h
        y_line = y_b + 14
        y_res = y_line + 18 + fm_big.ascent()

        p.setPen(self.palette().text().color())

        def draw_cells_row(cells: List[Cell], y_baseline: int, font: QFont) -> None:
            p.setFont(font)
            fm = QFontMetrics(font)
            for col, v in enumerate(cells):
                if v is None:
                    continue
                xc = x_digits + col * cell_w
                rect = (xc, y_baseline - fm.ascent(), cell_w, fm.height())
                p.drawText(*rect, Qt.AlignHCenter | Qt.AlignVCenter, str(v))

        def draw_comma(boundary: Optional[int], y_baseline: int, font: QFont) -> None:
            if boundary is None:
                return
            p.setFont(font)
            fm = QFontMetrics(font)
            x_boundary = x_digits + boundary * cell_w
            comma_w = max(10, cell_w // 2)
            rect = (
                int(x_boundary - comma_w * 0.65),
                int(y_baseline - fm.ascent()),
                int(comma_w),
                int(fm.height()),
            )
            p.drawText(*rect, Qt.AlignHCenter | Qt.AlignVCenter, ",")

        p.setFont(self.font_small)
        for col, v in enumerate(lay.carries):
            if v is None:
                continue
            xc = x_digits + col * cell_w
            rect = (xc, y_carry - fm_small.ascent(), cell_w, fm_small.height())
            if self._exercise_mode:
                draw_answer_box(p, rect, str(v), self._show_correction, self.font_small)
            else:
                p.drawText(*rect, Qt.AlignHCenter | Qt.AlignVCenter, str(v))

        draw_cells_row(lay.a_cells, y_a, self.font_big)
        draw_comma(lay.a_comma_boundary, y_a, self.font_big)

        plus_rect = (x0, y_b - fm_big.ascent(), plus_zone_w, fm_big.height())
        p.setFont(self.font_big)
        p.drawText(*plus_rect, Qt.AlignHCenter | Qt.AlignVCenter, "+")

        draw_cells_row(lay.b_cells, y_b, self.font_big)
        draw_comma(lay.b_comma_boundary, y_b, self.font_big)

        pen = QPen(self.palette().text().color())
        pen.setWidth(2)
        p.setPen(pen)
        p.drawLine(x0, y_line, x_digits + width * cell_w, y_line)

        p.setPen(self.palette().text().color())
        p.setFont(self.font_big)
        for col, v in enumerate(lay.result_digits):
            xc = x_digits + col * cell_w
            rect = (xc, y_res - fm_big.ascent(), cell_w, fm_big.height())
            if self._exercise_mode:
                draw_answer_box(p, rect, str(v), self._show_correction, self.font_big)
            else:
                p.drawText(*rect, Qt.AlignHCenter | Qt.AlignVCenter, str(v))
        draw_comma(lay.r_comma_boundary, y_res, self.font_big)


class AdditionWidget(QWidget):

    def __init__(self) -> None:
        super().__init__()
        self.canvas = AdditionCanvas()
        self.canvas.set_layout(None)

        from PySide6.QtWidgets import QVBoxLayout

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas, 1)

    def set_expression(self, expr: str) -> None:
        if not expr.strip():
            self.canvas.set_layout(None)
            return
        try:
            a_int, a_frac, b_int, b_frac = parse_addition(expr)
            self.canvas.set_layout(compute_french_addition(a_int, a_frac, b_int, b_frac))
        except Exception:
            self.canvas.set_layout(None)
            raise

    def set_exercise_mode(self, enabled: bool) -> None:
        self.canvas.set_exercise_mode(enabled)

    def set_correction_visible(self, visible: bool) -> None:
        self.canvas.set_correction_visible(visible)
