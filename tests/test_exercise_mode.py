import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication

from main import (
    MainWindow,
    _render_widget_pixmap,
    _render_projector_pixmap,
    _try_grab_widget_png,
    _compose_training_pixmaps,
)


class ExerciseModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.resize(1100, 700)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        if self.window._projector is not None:
            self.window._projector.close()
        self.app.removeEventFilter(self.window)
        self.window.close()
        self.app.processEvents()

    def prepare_columns(self, expressions):
        self.window.mode_tabs.setCurrentIndex(1)
        self.window.training_count.setCurrentIndex(len(expressions) - 1)
        for edit, expression in zip(self.window.training_inputs, expressions):
            edit.setText(expression)
        self.assertTrue(self.window._show())
        self.app.processEvents()

    def test_equal_columns_keep_the_entire_tallest_image_in_any_position(self):
        short = QPixmap(80, 50)
        short.fill(Qt.red)
        tall = QPixmap(120, 900)
        tall.fill(Qt.blue)
        for images in ([short, tall], [short, short, tall], [tall, short, short]):
            result = _compose_training_pixmaps(images).toImage()
            self.assertEqual(result.height(), 964)
            self.assertEqual(result.width(), 64 + 120 * len(images) + 48 * (len(images) - 1))
            for index, px in enumerate(images):
                self.assertEqual(result.pixelColor(32 + index * 168 + 60, 32 + px.height() - 1), px.toImage().pixelColor(0, 0))

    def test_mixed_columns_and_projector_share_complete_render_and_correction(self):
        self.prepare_columns(["2 + 3", "493 * 37", "12345678 / 7"])
        widgets = self.window._training_widgets
        self.assertEqual(len(widgets), 3)
        self.assertIs(self.window.stack.currentWidget(), self.window.training_preview)
        images = [_render_widget_pixmap(widget, scale=2.0) for widget in widgets]
        self.assertGreater(images[2].height(), images[0].height())
        hidden = self.window.training_preview._pixmap.toImage()
        self.assertEqual(hidden.height(), max(px.height() for px in images) + 64)
        self.window._set_correction_visible(True)
        revealed = self.window.training_preview._pixmap.toImage()
        self.assertNotEqual(hidden, revealed)
        self.assertEqual(hidden.size(), revealed.size())
        self.window._show_projector()
        self.app.processEvents()
        self.assertTrue(self.window._correction_visible)
        self.assertEqual(self.window._projector.canvas._pixmap.toImage(), revealed)
        self.window._set_correction_visible(False)
        self.assertEqual(self.window._projector.canvas._pixmap.toImage(), hidden)

    def test_same_operation_columns_are_independent_and_invalid_input_keeps_display(self):
        self.prepare_columns(["12 + 4", "123 + 456"])
        first, second = self.window._training_widgets
        self.assertIsNot(first, second)
        self.assertNotEqual(first.canvas._layout, second.canvas._layout)
        before = self.window.training_preview._pixmap.toImage()
        self.window.training_inputs[1].setText("12 / 0")
        with patch("main.QMessageBox.warning") as warning:
            self.assertFalse(self.window._show())
            warning.assert_called_once()
        self.assertEqual(self.window.training_preview._pixmap.toImage(), before)
        self.window.training_count.setCurrentIndex(0)
        self.assertTrue(self.window._show())
        self.assertIs(self.window.stack.currentWidget(), self.window.pages["Addition"])
        self.window.mode_tabs.setCurrentIndex(0)
        self.assertFalse(self.window.training_bar.isVisible())

    def test_training_tab_hides_pdf_and_resets_correction(self):
        self.window.mode_tabs.setCurrentIndex(1)

        self.assertFalse(self.window.document_bar.isVisible())
        self.assertTrue(self.window.correction_btn.isVisible())
        self.assertFalse(self.window._correction_visible)

        self.window._set_correction_visible(True)
        self.assertTrue(self.window._correction_visible)

        self.window.mode_tabs.setCurrentIndex(0)
        self.assertTrue(self.window.document_bar.isVisible())
        self.assertFalse(self.window.correction_btn.isVisible())

        self.window.mode_tabs.setCurrentIndex(1)
        self.assertFalse(self.window._correction_visible)

    def test_all_operation_canvases_receive_correction_state(self):
        self.window.mode_tabs.setCurrentIndex(1)
        self.window._set_correction_visible(True)

        for widget in self.window.widgets.values():
            canvas = getattr(widget, "canvas", getattr(widget, "_renderer", None))
            self.assertIsNotNone(canvas)
            self.assertTrue(canvas._exercise_mode)
            self.assertTrue(canvas._show_correction)

        self.window._set_correction_visible(False)
        for widget in self.window.widgets.values():
            canvas = getattr(widget, "canvas", getattr(widget, "_renderer", None))
            self.assertFalse(canvas._show_correction)

    def test_expression_selects_the_operation_page_automatically(self):
        cases = {
            "12 + 4": "Addition",
            "12 - 4": "Soustraction",
            "12 * 4": "Multiplication",
            "12 / 4": "Division",
        }
        for expression, operation in cases.items():
            with self.subTest(expression=expression):
                self.window.expr_edit.setText(expression)
                self.app.processEvents()
                self.assertEqual(self.window._current_operation, operation)
                self.assertIs(
                    self.window.stack.currentWidget(),
                    self.window.pages[operation],
                )

    def test_projector_uses_an_adaptive_high_resolution_render(self):
        self.window.expr_edit.setText("2 + 3")
        self.assertTrue(self.window._show())
        self.app.processEvents()

        widget = self.window.widgets["Addition"]
        normal = _render_widget_pixmap(widget)
        projected = _render_projector_pixmap(widget)

        self.assertGreater(projected.width(), normal.width())
        self.assertGreater(projected.height(), normal.height())
        self.assertGreaterEqual(max(projected.width(), projected.height()), 1600)

        export_image = QImage.fromData(_try_grab_widget_png(widget))
        self.assertFalse(export_image.isNull())
        self.assertGreaterEqual(max(export_image.width(), export_image.height()), 800)


if __name__ == "__main__":
    unittest.main()
