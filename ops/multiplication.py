"""Multiplication posée avec retenues, produits partiels et placement de la virgule."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, QSize, QPointF
from PySide6.QtGui import QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget, QVBoxLayout

from ops.exercise import draw_answer_box


Cell = Optional[int]  # None représente une case vide.


def shift_dot_columns(width: int, shift: int) -> List[int]:
    """Colonnes remplacées par des points pour un produit partiel décalé."""
    start = max(0, width - max(0, shift))
    return list(range(start, width))


@dataclass(frozen=True)
class MultiplicationLayout:
    width: int
    a_cells: List[Cell]
    b_cells: List[Cell]
    partials: List[List[Cell]]  # Des unités vers les rangs supérieurs.
    partial_carries: List[List[Cell]]
    sum_carries: List[Cell]
    result_cells: List[Cell]
    a_comma_boundary: Optional[int]
    b_comma_boundary: Optional[int]
    r_comma_boundary: Optional[int]


_DEC_RE = re.compile(r"^\d+(?:[.,]\d+)?$")


def _normalize_decimal_token(tok: str) -> Tuple[str, int]:
    """Conserve les chiffres et compte les décimales. 12,50 donne 1250 et 2."""
    t = tok.strip()
    if not _DEC_RE.fullmatch(t):
        raise ValueError("Expression invalide. Exemple : 12,5 x 3,4")

    if "," in t:
        left, right = t.split(",", 1)
        dec = len(right)
        digits = left + right
        return digits, dec

    if "." in t:
        left, right = t.split(".", 1)
        dec = len(right)
        digits = left + right
        return digits, dec

    return t, 0


def parse_multiplication(expr: str) -> Tuple[str, int, str, int]:
    s = expr.strip()
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*([xX\*×])\s*(\d+(?:[.,]\d+)?)", s)
    if not m:
        raise ValueError("Expression invalide. Exemple : 493 x 37 ou 12,5 x 3,4")

    a_tok = m.group(1)
    b_tok = m.group(3)

    a_digits, a_dec = _normalize_decimal_token(a_tok)
    b_digits, b_dec = _normalize_decimal_token(b_tok)
    return a_digits, a_dec, b_digits, b_dec


def to_cells_from_digits(digits: str, width: int) -> List[Cell]:
    s = digits
    pad = width - len(s)
    out: List[Cell] = [None] * max(0, pad)
    out.extend(int(ch) for ch in s[-width:])
    return out


def int_of_cell(c: Cell) -> int:
    return 0 if c is None else c


def _comma_boundary(width: int, digits_len: int, decimals: int) -> Optional[int]:
    """Donne la position de la virgule dans la grille, blancs compris."""
    if decimals <= 0:
        return None
    start = width - digits_len
    boundary = start + (digits_len - decimals)
    if boundary < 0:
        boundary = 0
    if boundary > width:
        boundary = width
    return boundary


def compute_partial(a_digits: List[int], d: int, shift: int, width: int) -> Tuple[List[Cell], List[Cell]]:
    """Calcule un produit partiel décalé avec ses retenues."""
    partial: List[Cell] = [None] * width
    carries: List[Cell] = [None] * width

    col = width - 1 - shift
    carry = 0

    for digit in reversed(a_digits):
        s = digit * d + carry
        partial_digit = s % 10
        carry = s // 10

        if col < 0:
            break

        partial[col] = partial_digit

        if carry != 0 and (col - 1) >= 0:
            carries[col - 1] = carry

        col -= 1

    if carry != 0 and col >= 0:
        partial[col] = carry

    return partial, carries


def add_rows_with_carries(rows: List[List[Cell]], width: int) -> Tuple[List[Cell], List[Cell]]:
    result: List[Cell] = [None] * width
    sum_carries: List[Cell] = [None] * width

    carry = 0
    for col in range(width - 1, -1, -1):
        column_sum = carry
        for r in rows:
            column_sum += int_of_cell(r[col])

        digit = column_sum % 10
        carry = column_sum // 10

        result[col] = digit

        if carry != 0 and (col - 1) >= 0:
            sum_carries[col - 1] = carry

    if carry != 0:
        result[0] = carry

    return sum_carries, result


def _pad_result_digits_for_decimals(result_digits: str, decimals: int) -> str:
    """Ajoute des zéros à gauche pour garder un chiffre avant la virgule."""
    if decimals <= 0:
        return result_digits
    min_len = decimals + 1
    if len(result_digits) < min_len:
        return ("0" * (min_len - len(result_digits))) + result_digits
    return result_digits


def compute_french_multiplication(a_digits: str, a_dec: int, b_digits: str, b_dec: int) -> MultiplicationLayout:
    # Poser les produits sans les virgules des facteurs, puis placer celle du résultat.
    a_str = a_digits
    b_str = b_digits

    a_list = [int(ch) for ch in a_str]
    b_list = [int(ch) for ch in b_str]

    a_int = int(a_str) if a_str else 0
    b_int = int(b_str) if b_str else 0

    product_int = a_int * b_int
    product_str_raw = str(product_int)

    total_dec = a_dec + b_dec
    product_str = _pad_result_digits_for_decimals(product_str_raw, total_dec)
    product_len_display = len(product_str)

    width = max(
        product_len_display,
        len(a_str),
        len(b_str) + 1,
        (len(a_str) + len(b_str) - 1) if (len(a_str) and len(b_str)) else 1,
    )

    a_cells = to_cells_from_digits(a_str, width)
    b_cells = to_cells_from_digits(b_str, width)
    result_cells = to_cells_from_digits(product_str, width)

    partials: List[List[Cell]] = []
    partial_carries: List[List[Cell]] = []

    for shift, d in enumerate(reversed(b_list)):
        part, carr = compute_partial(a_digits=a_list, d=d, shift=shift, width=width)
        partials.append(part)
        partial_carries.append(carr)

    if len(partials) >= 2:
        sum_carries, _ = add_rows_with_carries(partials, width)
    else:
        sum_carries = [None] * width

    return MultiplicationLayout(
        width=width,
        a_cells=a_cells,
        b_cells=b_cells,
        partials=partials,
        partial_carries=partial_carries,
        sum_carries=sum_carries,
        result_cells=result_cells,
        a_comma_boundary=_comma_boundary(width=width, digits_len=len(a_str), decimals=a_dec),
        b_comma_boundary=_comma_boundary(width=width, digits_len=len(b_str), decimals=b_dec),
        r_comma_boundary=_comma_boundary(width=width, digits_len=len(product_str), decimals=total_dec),
    )


class MultiplicationCanvas(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._layout: Optional[MultiplicationLayout] = None
        self._exercise_mode = False
        self._show_correction = False
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(QSize(680, 360))

        self.font_big = QFont("DejaVu Sans Mono", 28)
        self.font_small = QFont("DejaVu Sans Mono", 16)

        self.small_gap = 4
        self.block_gap = 10

    def set_layout(self, layout: Optional[MultiplicationLayout]) -> None:
        self._layout = layout
        hint = self.sizeHint()
        self.setMinimumSize(
            max(680, hint.width()),
            max(360, hint.height()),
        )
        self.updateGeometry()
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
        if self._layout is None:
            return QSize(680, 360)
        fm_big = QFontMetrics(self.font_big)
        fm_small = QFontMetrics(self.font_small)
        partial_count = len(self._layout.partials)
        width = 120 + self._layout.width * (
            max(fm_big.horizontalAdvance("8"), fm_small.horizontalAdvance("8")) + 12
        )
        if partial_count <= 1:
            height = 190 + partial_count * (fm_small.height() + self.small_gap)
        else:
            height = 210 + partial_count * (
                fm_small.height() + self.small_gap + fm_big.height() + 10
            )
        return QSize(max(680, width), max(360, height))

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), self.palette().base())

        if self._layout is None:
            p.setFont(QFont("DejaVu Sans", 13))
            p.setPen(self.palette().text().color())
            p.drawText(self.rect(), Qt.AlignCenter, "Saisir une multiplication (ex. 493 x 37 ou 12,5 x 3,4), puis Entrée.")
            return

        lay = self._layout
        width = lay.width
        num_partials = len(lay.partials)

        fm_big = QFontMetrics(self.font_big)
        fm_small = QFontMetrics(self.font_small)

        cell_w = max(fm_big.horizontalAdvance("8"), fm_small.horizontalAdvance("8")) + 12
        cell_h = fm_big.height() + 10
        small_h = fm_small.height()

        top_margin = 18
        left_margin = 24

        sign_zone_w = max(fm_big.horizontalAdvance("×"), fm_big.horizontalAdvance("+")) + 16
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

        def draw_sign(sign: str, y_baseline: int) -> None:
            p.setFont(self.font_big)
            rect = (x0, y_baseline - fm_big.ascent(), sign_zone_w, fm_big.height())
            p.drawText(*rect, Qt.AlignHCenter | Qt.AlignVCenter, sign)

        def draw_shift_dots(cells: List[Cell], shift: int, y_baseline: int) -> None:
            p.save()
            p.setPen(Qt.NoPen)
            p.setBrush(self.palette().text().color())
            radius = max(2.0, cell_w * 0.065)
            for col in shift_dot_columns(width, shift):
                if cells[col] is not None:
                    continue
                center = QPointF(
                    x_digits + col * cell_w + cell_w / 2.0,
                    y_baseline + 1.0,
                )
                p.drawEllipse(center, radius, radius)
            p.restore()

        def draw_comma(boundary: Optional[int], y_baseline: int, font: QFont) -> None:
            """Place la virgule entre les colonnes de chiffres."""
            if boundary is None:
                return
            p.setFont(font)
            fm = QFontMetrics(font)

            x_boundary = x_digits + boundary * cell_w

            # Rapprocher la virgule du chiffre à gauche.
            comma_w = max(10, cell_w // 2)
            rect = (
                int(x_boundary - comma_w * 0.65),
                int(y_baseline - fm.ascent()),
                int(comma_w),
                int(fm.height()),
            )
            p.drawText(*rect, Qt.AlignHCenter | Qt.AlignVCenter, ",")

        # Superposer les retenues des différents produits partiels.
        y = top_margin

        if num_partials > 0:
            for line_idx in range(num_partials):
                shift = (num_partials - 1) - line_idx
                carr = lay.partial_carries[shift]
                if any(v is not None for v in carr):
                    y_c = y + fm_small.ascent()
                    draw_cells_row(carr, y_c, self.font_small, expected=True)
                y += small_h + self.small_gap

        y += self.block_gap

        y_a = y + fm_big.ascent()
        draw_cells_row(lay.a_cells, y_a, self.font_big)
        draw_comma(lay.a_comma_boundary, y_a, self.font_big)
        y += cell_h

        y_b = y + fm_big.ascent()
        draw_sign("×", y_b)
        draw_cells_row(lay.b_cells, y_b, self.font_big)
        draw_comma(lay.b_comma_boundary, y_b, self.font_big)
        y += cell_h

        y_line1 = y + 8
        p.setPen(pen_line)
        p.drawLine(x0, y_line1, x_digits + width * cell_w, y_line1)
        p.setPen(self.palette().text().color())
        y = y_line1 + 10

        # Avec un seul chiffre au multiplicateur, le produit partiel est déjà le résultat.
        if num_partials == 1:
            y_r = y + fm_big.ascent()
            draw_cells_row(lay.result_cells, y_r, self.font_big, expected=True)
            draw_comma(lay.r_comma_boundary, y_r, self.font_big)
            return

        if num_partials >= 2 and any(v is not None for v in lay.sum_carries):
            y_sc = y + fm_small.ascent()
            draw_cells_row(lay.sum_carries, y_sc, self.font_small, expected=True)
            y += small_h + self.small_gap

        for idx, part in enumerate(lay.partials):
            y_p = y + fm_big.ascent()
            if num_partials >= 2 and idx == (num_partials - 1):
                draw_sign("+", y_p)
            draw_cells_row(part, y_p, self.font_big, expected=True)
            draw_shift_dots(part, idx, y_p)
            y += cell_h

        y_line2 = y + 6
        p.setPen(pen_line)
        p.drawLine(x0, y_line2, x_digits + width * cell_w, y_line2)
        p.setPen(self.palette().text().color())
        y = y_line2 + 10

        y_r = y + fm_big.ascent()
        draw_cells_row(lay.result_cells, y_r, self.font_big, expected=True)
        draw_comma(lay.r_comma_boundary, y_r, self.font_big)


class MultiplicationWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.canvas = MultiplicationCanvas()
        self.canvas.set_layout(None)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas, 1)

    def set_expression(self, expr: str) -> None:
        if not expr.strip():
            self.canvas.set_layout(None)
            return

        try:
            a_digits, a_dec, b_digits, b_dec = parse_multiplication(expr)
            self.canvas.set_layout(compute_french_multiplication(a_digits, a_dec, b_digits, b_dec))
        except Exception:
            self.canvas.set_layout(None)
            raise

    def set_exercise_mode(self, enabled: bool) -> None:
        self.canvas.set_exercise_mode(enabled)

    def set_correction_visible(self, visible: bool) -> None:
        self.canvas.set_correction_visible(visible)
