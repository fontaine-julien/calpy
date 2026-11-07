"""Soustraction posée avec les marques d’emprunt de la méthode française."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget, QVBoxLayout

from ops.exercise import draw_answer_box


Cell = Optional[int]  # None représente une case vide.


_DEC_RE = re.compile(r"^\d+(?:[.,]\d+)?$")


def _split_decimal_token(tok: str) -> Tuple[str, str]:
    """Sépare les parties entière et décimale."""
    t = tok.strip()
    if not _DEC_RE.fullmatch(t):
        raise ValueError("Expression invalide. Exemple : 2048 - 16 ou 12,5 - 3,4")

    if "," in t:
        left, right = t.split(",", 1)
        return left, right
    if "." in t:
        left, right = t.split(".", 1)
        return left, right
    return t, ""


def _scaled_value(int_part: str, frac_part: str, max_dec: int) -> int:
    frac = frac_part.ljust(max_dec, "0")
    return int(int_part) * (10**max_dec) + int((frac or "0"))


def parse_subtraction(expr: str) -> Tuple[str, str, str, str, bool]:
    s = expr.strip()
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*([-−–])\s*(\d+(?:[.,]\d+)?)", s)
    if not m:
        raise ValueError("Expression invalide. Exemple : 2048 - 16 ou 12,5 - 3,4")

    a_tok = m.group(1)
    b_tok = m.group(3)

    a_int, a_frac = _split_decimal_token(a_tok)
    b_int, b_frac = _split_decimal_token(b_tok)

    max_dec = max(len(a_frac), len(b_frac))
    a_scaled = _scaled_value(a_int, a_frac, max_dec)
    b_scaled = _scaled_value(b_int, b_frac, max_dec)

    negative = False
    if b_scaled > a_scaled:
        # Calculer la différence positive et afficher le signe moins au résultat.
        negative = True
        a_int, a_frac, b_int, b_frac = b_int, b_frac, a_int, a_frac

    return a_int, a_frac, b_int, b_frac, negative


def int_of_cell(c: Cell) -> int:
    return 0 if c is None else c


def _build_operand_cells(
    int_part: str,
    frac_part_padded: str,
    width: int,
    int_len: int,
    frac_len: int,
) -> List[Cell]:
    """Aligne les unités et complète la partie décimale par des zéros visibles."""
    cells: List[Cell] = [None] * width

    missing = int_len - len(int_part)
    for j in range(int_len):
        if j < missing:
            cells[j] = None
        else:
            cells[j] = int(int_part[j - missing])

    for k in range(frac_len):
        cells[int_len + k] = int(frac_part_padded[k])

    return cells


@dataclass(frozen=True)
class BorrowMarkers:
    add1_left_cols: List[bool]
    sub1_below_cols: List[bool]


def compute_borrow_markers(a_calc_digits: List[int], b_calc_digits: List[int]) -> BorrowMarkers:
    """Repère les colonnes qui prêtent et celles qui reçoivent une dizaine."""
    n = len(a_calc_digits)
    work = a_calc_digits[:]
    add1 = [False] * n
    sub1 = [False] * n

    for i in range(n - 1, -1, -1):
        if work[i] < b_calc_digits[i]:
            # Chercher la première colonne à gauche qui peut prêter.
            j = i - 1
            while j >= 0 and work[j] == 0:
                j -= 1
            if j < 0:
                break

            work[j] -= 1
            sub1[j] = True

            # L’emprunt transforme les zéros intermédiaires en 9.
            for k in range(j + 1, i):
                work[k] = 9
            work[i] += 10
            add1[i] = True

    return BorrowMarkers(add1_left_cols=add1, sub1_below_cols=sub1)


@dataclass(frozen=True)
class SubtractionLayout:
    width: int
    a_cells: List[Cell]
    b_cells: List[Cell]
    result_cells: List[Cell]
    borrow: BorrowMarkers
    a_comma_boundary: Optional[int]
    b_comma_boundary: Optional[int]
    r_comma_boundary: Optional[int]
    result_negative: bool


def compute_french_subtraction(a_int: str, a_frac: str, b_int: str, b_frac: str, negative: bool) -> SubtractionLayout:
    frac_len = max(len(a_frac), len(b_frac))
    a_frac_padded = a_frac.ljust(frac_len, "0")
    b_frac_padded = b_frac.ljust(frac_len, "0")

    int_len = max(len(a_int), len(b_int))
    a_int_calc = a_int.rjust(int_len, "0")
    b_int_calc = b_int.rjust(int_len, "0")

    a_calc = a_int_calc + a_frac_padded
    b_calc = b_int_calc + b_frac_padded
    width = int_len + frac_len

    a_cells = _build_operand_cells(a_int, a_frac_padded, width, int_len, frac_len)
    b_cells = _build_operand_cells(b_int, b_frac_padded, width, int_len, frac_len)

    a_digits = [int(ch) for ch in a_calc]
    b_digits = [int(ch) for ch in b_calc]

    borrow = compute_borrow_markers(a_digits, b_digits)

    res_digits = [0] * width
    carry = 0
    for i in range(width - 1, -1, -1):
        ai = a_digits[i] - carry
        bi = b_digits[i]
        if ai < bi:
            ai += 10
            carry = 1
        else:
            carry = 0
        res_digits[i] = ai - bi

    result_cells: List[Cell] = [int(d) for d in res_digits]

    comma_boundary = int_len if frac_len > 0 else None

    return SubtractionLayout(
        width=width,
        a_cells=a_cells,
        b_cells=b_cells,
        result_cells=result_cells,
        borrow=borrow,
        a_comma_boundary=comma_boundary,
        b_comma_boundary=comma_boundary,
        r_comma_boundary=comma_boundary,
        result_negative=negative,
    )


class SubtractionRenderer(QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.font_big = QFont("DejaVu Sans Mono", 28)
        self.font_big.setStyleHint(QFont.Monospace)

        self.font_small = QFont("DejaVu Sans Mono", 16)
        self.font_small.setStyleHint(QFont.Monospace)

        self._layout: Optional[SubtractionLayout] = None
        self._exercise_mode = False
        self._show_correction = False

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_layout(self, layout: Optional[SubtractionLayout]) -> None:
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

    def sizeHint(self) -> QSize:
        return QSize(900, 420)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), self.palette().base())

        if self._layout is None:
            p.setFont(QFont("DejaVu Sans", 13))
            p.setPen(self.palette().text().color())
            p.drawText(self.rect(), Qt.AlignCenter, "Saisir une soustraction (ex. 2048 - 16 ou 12,5 - 3,4), puis Entrée.")
            return

        lay = self._layout
        width = lay.width

        fm_big = QFontMetrics(self.font_big)
        fm_small = QFontMetrics(self.font_small)

        cell_w = max(fm_big.horizontalAdvance("8"), fm_small.horizontalAdvance("8")) + 12
        cell_h = fm_big.height() + 10

        top_margin = 18
        left_margin = 24

        sign_zone_w = fm_big.horizontalAdvance("-") + 16
        total_w = sign_zone_w + width * cell_w

        x0 = max(left_margin, (self.width() - total_w) // 2)
        x_digits = x0 + sign_zone_w

        pen_line = QPen(self.palette().text().color())
        pen_line.setWidth(2)

        p.setPen(self.palette().text().color())

        def draw_cells_row(
            cells: List[Cell],
            y_baseline: int,
            font: QFont,
            expected: bool = False,
        ) -> None:
            p.setFont(font)
            fm = QFontMetrics(font)
            for col, v in enumerate(cells):
                if v is None:
                    continue
                xc = x_digits + col * cell_w
                rect = (xc, y_baseline - fm.ascent(), cell_w, fm.height())
                if expected and self._exercise_mode:
                    draw_answer_box(p, rect, str(v), self._show_correction, font)
                else:
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

        def draw_minus_sign(y_baseline: int, expected: bool = False) -> None:
            p.setFont(self.font_big)
            rect = (x0, y_baseline - fm_big.ascent(), sign_zone_w, fm_big.height())
            if expected and self._exercise_mode:
                draw_answer_box(p, rect, "-", self._show_correction, self.font_big)
            else:
                p.drawText(*rect, Qt.AlignHCenter | Qt.AlignVCenter, "-")

        def draw_borrow_add1_left(markers: List[bool], y_baseline: int) -> None:
            p.setFont(self.font_small)
            for col, on in enumerate(markers):
                if not on:
                    continue
                xc = x_digits + col * cell_w
                rect = (xc - (cell_w // 4), y_baseline - fm_big.ascent(), cell_w // 2, fm_big.height())
                if self._exercise_mode:
                    draw_answer_box(p, rect, "1", self._show_correction, self.font_small)
                else:
                    p.drawText(*rect, Qt.AlignCenter, "1")

        def draw_borrow_sub1_below(markers: List[bool], y_baseline: int) -> None:
            p.setFont(self.font_small)
            y_under = y_baseline + (fm_small.ascent() + 4)
            for col, on in enumerate(markers):
                if not on:
                    continue
                xc = x_digits + col * cell_w
                rect = (xc, y_under - fm_small.ascent(), cell_w, fm_small.height())
                if self._exercise_mode:
                    draw_answer_box(p, rect, "1", self._show_correction, self.font_small)
                else:
                    p.drawText(*rect, Qt.AlignHCenter | Qt.AlignVCenter, "1")

        y = top_margin

        y_a = y + fm_big.ascent()
        draw_cells_row(lay.a_cells, y_a, self.font_big)
        draw_comma(lay.a_comma_boundary, y_a, self.font_big)

        draw_borrow_add1_left(lay.borrow.add1_left_cols, y_a)

        y += cell_h

        y_b = y + fm_big.ascent()
        draw_minus_sign(y_b)
        draw_cells_row(lay.b_cells, y_b, self.font_big)
        draw_comma(lay.b_comma_boundary, y_b, self.font_big)

        draw_borrow_sub1_below(lay.borrow.sub1_below_cols, y_b)

        y += cell_h

        y_line = y + 8
        p.setPen(pen_line)
        p.drawLine(x0, y_line, x_digits + width * cell_w, y_line)
        p.setPen(self.palette().text().color())
        y = y_line + 10

        y_r = y + fm_big.ascent()
        if lay.result_negative:
            draw_minus_sign(y_r, expected=True)
        draw_cells_row(lay.result_cells, y_r, self.font_big, expected=True)
        draw_comma(lay.r_comma_boundary, y_r, self.font_big)


class SubtractionWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._renderer = SubtractionRenderer()

        lay = QVBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._renderer)
        self.setLayout(lay)

    def set_expression(self, expr: str) -> None:
        expr = (expr or "").strip()
        if not expr:
            self._renderer.set_layout(None)
            return

        try:
            a_int, a_frac, b_int, b_frac, negative = parse_subtraction(expr)
            layout = compute_french_subtraction(a_int, a_frac, b_int, b_frac, negative)
            self._renderer.set_layout(layout)
        except Exception:
            self._renderer.set_layout(None)
            raise

    def set_exercise_mode(self, enabled: bool) -> None:
        self._renderer.set_exercise_mode(enabled)

    def set_correction_visible(self, visible: bool) -> None:
        self._renderer.set_correction_visible(visible)
