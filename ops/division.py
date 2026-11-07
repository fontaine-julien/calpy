"""Division en potence avec détail des soustractions et des chiffres rabattus."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, QSize, QRectF
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget, QVBoxLayout

from ops.exercise import draw_answer_box


Cell = Optional[int]  # None représente une case vide.


_DECIMAL_RE = re.compile(r"^\d+(?:[.,]\d+)?$")


@dataclass(frozen=True)
class DecimalOperand:
    digits: str
    decimals: int
    display: str

    @property
    def scaled_value(self) -> int:
        return int(self.digits)


def _parse_decimal_operand(token: str) -> DecimalOperand:
    value = token.strip()
    if not _DECIMAL_RE.fullmatch(value):
        raise ValueError("Nombre invalide.")

    canonical = value.replace(".", ",")
    if "," in canonical:
        integer, fractional = canonical.split(",", 1)
    else:
        integer, fractional = canonical, ""

    # Les zéros décimaux comptent dans le déplacement de la virgule.
    normalized_integer = integer.lstrip("0") or "0"
    digits = normalized_integer + fractional
    return DecimalOperand(
        digits=digits,
        decimals=len(fractional),
        display=normalized_integer + (("," + fractional) if fractional else ""),
    )


def parse_division(expr: str) -> Tuple[DecimalOperand, DecimalOperand]:
    s = expr.strip()
    number = r"\d+(?:[.,]\d+)?"
    m = re.fullmatch(
        rf"({number})\s*(?:÷|/|:|div)\s*({number})",
        s,
        flags=re.IGNORECASE,
    )
    if not m:
        raise ValueError("Expression invalide. Exemple : 2048 ÷ 8 ou 12,43 ÷ 4,56")

    dividend = _parse_decimal_operand(m.group(1))
    divisor = _parse_decimal_operand(m.group(2))
    if divisor.scaled_value == 0:
        raise ValueError("Division par zéro interdite.")
    return dividend, divisor


def _format_scaled_integer(value: int, decimals: int) -> str:
    if decimals <= 0:
        return str(value)
    digits = str(value).zfill(decimals + 1)
    return f"{digits[:-decimals]},{digits[-decimals:]}"


def _multiply_by_power_of_ten(operand: DecimalOperand, exponent: int) -> Tuple[str, int]:
    """Retourne (affichage, décimales restantes) après multiplication par 10**exponent."""
    remaining_decimals = max(0, operand.decimals - exponent)
    value = operand.scaled_value * (10 ** max(0, exponent - operand.decimals))
    return _format_scaled_integer(value, remaining_decimals), remaining_decimals


def _trailing_zero_count(value: int) -> int:
    if value == 0:
        return 100
    return len(str(value)) - len(str(value).rstrip("0"))


def cells_from_str(s: str, width: int, end_col: int) -> List[Cell]:
    """Aligne les chiffres à droite sur la colonne indiquée."""
    out: List[Cell] = [None] * width
    j = end_col
    for ch in reversed(s):
        if j < 0:
            break
        out[j] = int(ch)
        j -= 1
    return out


def first_non_empty(cells: List[Cell]) -> int:
    for i, v in enumerate(cells):
        if v is not None:
            return i
    return len(cells)


@dataclass(frozen=True)
class BorrowMarkers:
    add1_left_cols: List[bool]  # Petit 1 à gauche du chiffre qui reçoit une dizaine.
    sub1_below_cols: List[bool]  # Petit 1 sous la colonne qui prête.


def compute_borrow_markers(minuend: int, subtrahend: int, width: int, end_col: int) -> BorrowMarkers:
    """Repère les emprunts, y compris en cascade à travers les zéros."""
    a = [int(c) for c in str(minuend)]
    b = [int(c) for c in str(subtrahend)]
    n = len(a)
    b = [0] * (n - len(b)) + b

    add1 = [False] * width
    sub1 = [False] * width

    work = a[:]
    base_col = end_col - (n - 1)

    def mark_borrow(from_local: int, to_local: int) -> None:
        col_to = base_col + to_local
        col_from = base_col + from_local
        if 0 <= col_to < width:
            add1[col_to] = True
        if 0 <= col_from < width:
            sub1[col_from] = True

    for i in range(n - 1, -1, -1):
        if work[i] < b[i]:
            if i == 0:
                continue

            j = i - 1
            while j >= 0 and work[j] == 0:
                j -= 1
            if j < 0:
                continue

            work[j] -= 1
            for k in range(j + 1, i):
                mark_borrow(from_local=k - 1, to_local=k)
                work[k] = 9

            mark_borrow(from_local=i - 1, to_local=i)
            work[i] += 10
            work[i - 1] -= 1

    return BorrowMarkers(add1_left_cols=add1, sub1_below_cols=sub1)


@dataclass(frozen=True)
class DivisionStep:
    end_col: int
    cur_from_dividend: bool
    cur_len: int
    sub_cells: List[Cell]
    rem_cells: List[Cell]
    borrow: BorrowMarkers
    bring_col: Optional[int]
    bring_digit: Optional[int]


@dataclass(frozen=True)
class DivisionLayout:
    width: int
    dividend_cells: List[Cell]
    dividend_comma_boundary: Optional[int]
    divisor_str: str
    quotient_str: str
    steps: List[DivisionStep]
    remainder: int
    original_dividend_str: str
    original_divisor_str: str
    transform_label: Optional[str]


def compute_french_division(
    dividend: int | str,
    divisor: int,
    *,
    original_dividend: Optional[str] = None,
    original_divisor: Optional[str] = None,
    transform_label: Optional[str] = None,
) -> DivisionLayout:
    """Calcule la potence sans flottants, même si le dividende garde une virgule."""
    dvd_display = str(dividend).replace(".", ",")
    if "," in dvd_display:
        dvd_integer, dvd_fractional = dvd_display.split(",", 1)
    else:
        dvd_integer, dvd_fractional = dvd_display, ""

    dvd_str = dvd_integer + dvd_fractional
    decimal_digits = len(dvd_fractional)
    integer_digit_count = len(dvd_integer)
    width = len(dvd_str)

    dividend_cells: List[Cell] = [int(ch) for ch in dvd_str]
    quotient_chars: List[str] = []

    steps: List[DivisionStep] = []

    current = 0
    quotient_started = False
    step_index = 0

    for i, ch in enumerate(dvd_str):
        if decimal_digits and i == integer_digit_count:
            if not quotient_started:
                quotient_chars.append("0")
                quotient_started = True
            quotient_chars.append(",")

        digit = int(ch)
        current = current * 10 + digit

        if not quotient_started and current < divisor:
            continue

        quotient_started = True
        qdigit = current // divisor
        quotient_chars.append(str(qdigit))

        sub = qdigit * divisor
        rem = current - sub

        cur_str = str(current)
        cur_len = len(cur_str)

        sub_str = str(sub).rjust(cur_len, "0")
        rem_str = str(rem).rjust(cur_len, "0")

        sub_cells = cells_from_str(sub_str, width, end_col=i)
        rem_cells = cells_from_str(rem_str, width, end_col=i)

        borrow = compute_borrow_markers(current, sub, width, end_col=i)

        bring_col = i + 1 if (i + 1) < width else None
        bring_digit = int(dvd_str[bring_col]) if bring_col is not None else None

        steps.append(
            DivisionStep(
                end_col=i,
                cur_from_dividend=(step_index == 0),
                cur_len=cur_len,
                sub_cells=sub_cells,
                rem_cells=rem_cells,
                borrow=borrow,
                bring_col=bring_col,
                bring_digit=bring_digit,
            )
        )

        current = rem
        step_index += 1

    remainder = current
    quotient_str = "".join(quotient_chars) if quotient_chars else "0"

    return DivisionLayout(
        width=width,
        dividend_cells=dividend_cells,
        dividend_comma_boundary=integer_digit_count if decimal_digits else None,
        divisor_str=str(divisor),
        quotient_str=quotient_str,
        steps=steps,
        remainder=remainder,
        original_dividend_str=original_dividend or dvd_display,
        original_divisor_str=original_divisor or str(divisor),
        transform_label=transform_label,
    )


def prepare_division(expr: str) -> DivisionLayout:
    """Prépare un diviseur entier en conservant le quotient."""
    dividend, divisor = parse_division(expr)
    transform_label: Optional[str] = None

    if divisor.decimals > 0:
        # Décaler les deux virgules juste assez pour rendre le diviseur entier.
        exponent = divisor.decimals
        working_dividend, _ = _multiply_by_power_of_ten(dividend, exponent)
        working_divisor_text, _ = _multiply_by_power_of_ten(divisor, exponent)
        working_divisor = int(working_divisor_text)
        transform_label = f"× {10 ** exponent}"
    elif dividend.decimals == 0:
        working_dividend_value = dividend.scaled_value
        working_divisor = divisor.scaled_value
        common_zeros = min(
            _trailing_zero_count(working_dividend_value),
            _trailing_zero_count(working_divisor),
        )
        if common_zeros > 0:
            factor = 10 ** common_zeros
            working_dividend_value //= factor
            working_divisor //= factor
            transform_label = f"÷ {factor}"
        working_dividend = str(working_dividend_value)
    else:
        working_dividend = dividend.display
        working_divisor = divisor.scaled_value

    return compute_french_division(
        working_dividend,
        working_divisor,
        original_dividend=dividend.display,
        original_divisor=divisor.display,
        transform_label=transform_label,
    )


class DivisionCanvas(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._layout: Optional[DivisionLayout] = None
        self._exercise_mode = False
        self._show_correction = False
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(QSize(620, 400))

        self.font_big = QFont("DejaVu Sans Mono", 28)
        self.font_small = QFont("DejaVu Sans Mono", 16)
        self.font_transform = QFont("DejaVu Sans Mono", 18)

        self.step_gap = 14

    def set_layout(self, layout: Optional[DivisionLayout]) -> None:
        self._layout = layout
        hint = self.sizeHint()
        self.setMinimumSize(
            max(620, hint.width()),
            max(400, hint.height()),
        )
        self.updateGeometry()
        self.update()

    def set_exercise_mode(self, enabled: bool) -> None:
        self._exercise_mode = enabled
        if not enabled:
            self._show_correction = False
        hint = self.sizeHint()
        self.setMinimumSize(max(620, hint.width()), max(400, hint.height()))
        self.updateGeometry()
        self.update()

    def set_correction_visible(self, visible: bool) -> None:
        self._show_correction = self._exercise_mode and visible
        self.update()

    def sizeHint(self) -> QSize:
        if self._layout is None:
            return QSize(820, 460)
        fm = QFontMetrics(self.font_big)
        cell_h = fm.height() + 10
        transform_h = 92 if self._layout.transform_label else 0
        height = transform_h + 150 + len(self._layout.steps) * (
            (2 * cell_h) + 26 + self.step_gap
        )
        width = 180 + self._layout.width * (fm.horizontalAdvance("8") + 12)
        if self._exercise_mode:
            cell_w = fm.horizontalAdvance("8") + 12
            potence_content = max(
                len(self._layout.divisor_str.replace(",", "")) * cell_w,
                len(self._layout.quotient_str.replace(",", "")) * cell_w,
            )
        else:
            potence_content = max(
                fm.horizontalAdvance(self._layout.divisor_str),
                fm.horizontalAdvance(self._layout.quotient_str),
            )
        width += potence_content
        return QSize(max(820, width), max(460, height))

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), self.palette().base())

        if self._layout is None:
            p.setFont(QFont("DejaVu Sans", 13))
            p.setPen(self.palette().text().color())
            p.drawText(self.rect(), Qt.AlignCenter, "Saisir une division (ex. 2048 ÷ 8), puis Entrée.")
            return

        lay = self._layout
        width = lay.width

        fm_big = QFontMetrics(self.font_big)
        fm_small = QFontMetrics(self.font_small)
        fm_transform = QFontMetrics(self.font_transform)

        cell_w = max(fm_big.horizontalAdvance("8"), fm_small.horizontalAdvance("8")) + 12
        cell_h = fm_big.height() + 10

        top_margin = 18
        transform_h = 92 if lay.transform_label else 0
        left_margin = 24

        bar_gap = 18
        if self._exercise_mode:
            def expected_text_width(text: str) -> int:
                return sum((cell_w // 2) if ch == "," else cell_w for ch in text)

            potence_w = max(
                expected_text_width(lay.divisor_str),
                expected_text_width(lay.quotient_str),
            ) + 40
        else:
            potence_w = max(
                fm_big.horizontalAdvance(lay.divisor_str),
                fm_big.horizontalAdvance(lay.quotient_str),
            ) + 60

        total_w = width * cell_w + bar_gap + potence_w
        x0 = max(left_margin, (self.width() - total_w) // 2)

        x_digits = x0
        x_bar = x_digits + width * cell_w + (bar_gap // 2)
        x_pot = x_bar + (bar_gap // 2)

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

        def draw_single_digit(
            col: int,
            digit: int,
            y_baseline: int,
            font: QFont,
            expected: bool = False,
        ) -> None:
            p.setFont(font)
            fm = QFontMetrics(font)
            xc = x_digits + col * cell_w
            rect = (xc, y_baseline - fm.ascent(), cell_w, fm.height())
            if expected and self._exercise_mode:
                draw_answer_box(p, rect, str(digit), self._show_correction, font)
            else:
                p.drawText(*rect, Qt.AlignHCenter | Qt.AlignVCenter, str(digit))

        def draw_potence_value(text: str, y_baseline: int, expected: bool) -> None:
            p.setFont(self.font_big)
            if not (expected and self._exercise_mode):
                rect = (x_pot + 10, y_baseline - fm_big.ascent(), potence_w - 20, fm_big.height())
                p.drawText(*rect, Qt.AlignLeft | Qt.AlignVCenter, text)
                return

            cursor = x_pot + 10
            for ch in text:
                if ch == ",":
                    comma_rect = (
                        cursor - (cell_w // 5),
                        y_baseline - fm_big.ascent(),
                        cell_w // 2,
                        fm_big.height(),
                    )
                    p.drawText(*comma_rect, Qt.AlignHCenter | Qt.AlignVCenter, ",")
                    cursor += cell_w // 2
                    continue
                rect = (cursor, y_baseline - fm_big.ascent(), cell_w, fm_big.height())
                draw_answer_box(p, rect, ch, self._show_correction, self.font_big)
                cursor += cell_w

        def draw_comma(boundary: Optional[int], y_baseline: int) -> None:
            if boundary is None:
                return
            p.setFont(self.font_big)
            x_boundary = x_digits + boundary * cell_w
            comma_w = max(10, cell_w // 2)
            rect = (
                int(x_boundary - comma_w * 0.65),
                int(y_baseline - fm_big.ascent()),
                int(comma_w),
                int(fm_big.height()),
            )
            p.drawText(*rect, Qt.AlignHCenter | Qt.AlignVCenter, ",")

        def draw_minus_sign(y_baseline: int) -> None:
            p.setFont(self.font_big)
            rect = (x_digits - 40, y_baseline - fm_big.ascent(), 32, fm_big.height())
            p.drawText(*rect, Qt.AlignHCenter | Qt.AlignVCenter, "−")

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

        y_div = top_margin + transform_h + fm_big.ascent()

        if lay.transform_label:
            dividend_center = x_digits + (width * cell_w) / 2
            divisor_width = (
                expected_text_width(lay.divisor_str)
                if self._exercise_mode
                else fm_big.horizontalAdvance(lay.divisor_str)
            )
            divisor_center = x_pot + 10 + divisor_width / 2
            badge_y = float(top_margin)
            original_y = badge_y + 38

            accent = QColor(35, 91, 145)
            badge_fill = QColor(226, 240, 252)
            badge_pen = QPen(accent)
            badge_pen.setWidth(2)

            def draw_transform(center_x: float, original: str) -> None:
                badge_w = max(58, fm_small.horizontalAdvance(lay.transform_label or "") + 22)
                badge = QRectF(center_x - badge_w / 2, badge_y, badge_w, 30)
                p.setPen(badge_pen)
                correction_hidden = self._exercise_mode and not self._show_correction
                p.setBrush(Qt.NoBrush if correction_hidden else badge_fill)
                p.drawEllipse(badge)

                p.setPen(accent)
                p.setFont(self.font_small)
                if not correction_hidden:
                    p.drawText(badge, Qt.AlignCenter, lay.transform_label or "")

                p.setBrush(Qt.NoBrush)
                p.setPen(self.palette().text().color())
                p.setFont(self.font_transform)
                original_rect = QRectF(
                    center_x - max(90, fm_transform.horizontalAdvance(original) + 16) / 2,
                    original_y,
                    max(90, fm_transform.horizontalAdvance(original) + 16),
                    fm_transform.height(),
                )
                p.drawText(original_rect, Qt.AlignHCenter | Qt.AlignVCenter, original)

                arrow_top = original_rect.bottom() + 2
                arrow_bottom = y_div - fm_big.ascent() - 7
                p.setPen(badge_pen)
                p.drawLine(int(center_x), int(arrow_top), int(center_x), int(arrow_bottom))
                p.drawLine(int(center_x), int(arrow_bottom), int(center_x - 5), int(arrow_bottom - 7))
                p.drawLine(int(center_x), int(arrow_bottom), int(center_x + 5), int(arrow_bottom - 7))

            draw_transform(dividend_center, lay.original_dividend_str)
            draw_transform(divisor_center, lay.original_divisor_str)
            p.setBrush(Qt.NoBrush)
            p.setPen(self.palette().text().color())

        transformed_operand = lay.transform_label is not None
        draw_cells_row(
            lay.dividend_cells,
            y_div,
            self.font_big,
            expected=transformed_operand,
        )
        draw_comma(lay.dividend_comma_boundary, y_div)

        draw_potence_value(lay.divisor_str, y_div, expected=transformed_operand)

        y_hline = y_div + 10
        p.setPen(pen_line)
        p.drawLine(x_bar, y_hline, x_pot + potence_w - 10, y_hline)

        y_q = y_div + cell_h
        p.setPen(self.palette().text().color())
        draw_potence_value(lay.quotient_str, y_q, expected=True)

        y_cursor = y_div + cell_h - 2

        last_minuend_baseline = y_div

        for idx, st in enumerate(lay.steps):
            # Les emprunts se placent sur le dividende, puis sur la ligne du reste précédent.
            y_minuend_baseline = y_div if st.cur_from_dividend else last_minuend_baseline

            draw_borrow_add1_left(st.borrow.add1_left_cols, y_minuend_baseline)

            y_sub = y_cursor + fm_big.ascent()
            draw_minus_sign(y_sub)
            draw_cells_row(st.sub_cells, y_sub, self.font_big, expected=True)

            draw_borrow_sub1_below(st.borrow.sub1_below_cols, y_sub)

            y_cursor += cell_h

            left_chunk = first_non_empty(st.sub_cells)
            right_chunk = st.end_col
            x1 = x_digits + left_chunk * cell_w - 10
            x2 = x_digits + (right_chunk + 1) * cell_w
            y_line = y_cursor + 6

            p.setPen(pen_line)
            p.drawLine(x1, y_line, x2, y_line)
            p.setPen(self.palette().text().color())
            y_cursor = y_line + 10

            y_rem = y_cursor + fm_big.ascent()
            draw_cells_row(st.rem_cells, y_rem, self.font_big, expected=True)

            if st.bring_col is not None and st.bring_digit is not None and idx < len(lay.steps) - 1:
                draw_single_digit(
                    st.bring_col,
                    st.bring_digit,
                    y_rem,
                    self.font_big,
                    expected=True,
                )

                x_arrow = x_digits + st.bring_col * cell_w + cell_w // 2
                y_start = y_div + 10
                y_end = y_rem - fm_big.ascent() + 6
                p.setPen(pen_line)
                p.drawLine(x_arrow, y_start, x_arrow, y_end)
                p.drawLine(x_arrow, y_end, x_arrow - 6, y_end - 8)
                p.drawLine(x_arrow, y_end, x_arrow + 6, y_end - 8)
                p.setPen(self.palette().text().color())

            last_minuend_baseline = y_rem

            y_cursor += cell_h + self.step_gap

        # Ajuster la potence à la hauteur du calcul pour éviter de réduire l’image à l’export.
        p.setPen(pen_line)
        vertical_end = max(y_q + 10, y_cursor - self.step_gap)
        p.drawLine(
            x_bar,
            y_div - fm_big.ascent(),
            x_bar,
            min(self.height() - 16, vertical_end),
        )


class DivisionWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.canvas = DivisionCanvas()
        self.canvas.set_layout(None)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas, 1)

    def set_expression(self, expr: str) -> None:
        if not expr.strip():
            self.canvas.set_layout(None)
            return
        try:
            self.canvas.set_layout(prepare_division(expr))
        except Exception:
            self.canvas.set_layout(None)
            raise

    def set_exercise_mode(self, enabled: bool) -> None:
        self.canvas.set_exercise_mode(enabled)

    def set_correction_visible(self, visible: bool) -> None:
        self.canvas.set_correction_visible(visible)
