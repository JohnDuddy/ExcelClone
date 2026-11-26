"""Insert > Pictures, Shapes, and Text Box, wired to the floating drawing layer."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QFileDialog, QInputDialog, QMenu

from duddysheet.commands.analysis import WorkbookMutationCommand
from duddysheet.core.drawings import SHAPES, Drawing, image_format, image_size, next_drawing_name
from duddysheet.ui.drawing_layer import DrawingLayer

PICTURE_FILTER = "Pictures (*.png *.jpg *.jpeg *.gif *.bmp)"
MAX_PICTURE = 480


class IllustrationsMixin:
    """Pictures, shapes, and text boxes for the main window."""

    def _install_illustrations(self) -> None:
        self.drawing_layer = DrawingLayer(self.grid)
        self.drawing_layer.drawingChanged.connect(self.update_drawing)
        self.drawing_layer.drawingDeleted.connect(self.delete_drawing)
        self.drawing_layer.textEditRequested.connect(self.edit_drawing_text)
        a = self._action
        a("insertPicture", "Pictures...", self.insert_picture_dialog, tip="Insert a picture from a file on this PC")
        a("insertTextBox", "Text Box", lambda: self.insert_text_box(), tip="Draw a text box anywhere on the sheet")
        insert = self._menu("Insert")
        # Excel's Insert order: Tables, then Illustrations, then Charts.
        actions = insert.actions()
        table = self.excel_actions.get("createTable")
        position = actions.index(table) + 1 if table in actions else 0
        while position < len(actions) and actions[position].isSeparator():
            position += 1
        first = actions[position] if position < len(actions) else None
        insert.insertAction(first, self.excel_actions["insertPicture"])
        shapes = QMenu("Shapes", self)
        shapes.setObjectName("shapesMenu")
        for key, label in SHAPES.items():
            action = shapes.addAction(label)
            action.triggered.connect(lambda checked=False, key=key: self.insert_shape(key))
        insert.insertMenu(first, shapes)
        insert.insertAction(first, self.excel_actions["insertTextBox"])
        insert.insertSeparator(first)
        handlers = self.excel_ribbon_handlers
        handlers["Pictures"] = self.insert_picture_dialog
        handlers["Text Box"] = lambda: self.insert_text_box()
        for key in SHAPES:
            handlers[f"shape:{key}"] = lambda key=key: self.insert_shape(key)
        self.drawing_layer.sync()

    def _drawing_mutation(self, label: str, mutate: Any) -> bool:
        return self._run(WorkbookMutationCommand(self.engine, label, mutate))

    def _place(self) -> tuple[int, int]:
        index = self.grid.currentIndex()
        return (index.row(), index.column()) if index.isValid() else (0, 0)

    def add_drawing(self, drawing: Drawing) -> Drawing:
        """Add a drawing to the active sheet (undoable) and select it."""
        sheet_name = self.grid_model.active_sheet_name

        def mutate() -> None:
            sheet = self.engine.workbook.get_sheet(sheet_name)
            sheet.drawings = [*sheet.drawings, drawing]

        self._drawing_mutation(f"Insert {drawing.name}", mutate)
        self.drawing_layer.sync()
        self.drawing_layer.select(drawing.name)
        return drawing

    def insert_picture_dialog(self) -> None:
        """Insert > Pictures > This Device."""
        path, _ = QFileDialog.getOpenFileName(self, "Insert Picture", "", PICTURE_FILTER)
        if path:
            self.insert_picture_file(path)

    def insert_picture_file(self, path: str | Path) -> Drawing | None:
        """Insert a PNG, JPEG, GIF, or BMP file at the active cell."""
        data = Path(path).read_bytes()
        if not image_format(data):
            self._warn_illustration("This picture can't be inserted. Use a PNG, JPEG, GIF, or BMP file.")
            return None
        return self.insert_picture_bytes(data, Path(path).stem)

    def insert_picture_bytes(self, data: bytes, description: str = "") -> Drawing:
        size = image_size(data) or (200, 150)
        width, height = size
        if max(width, height) > MAX_PICTURE:
            factor = MAX_PICTURE / max(width, height)
            width, height = width * factor, height * factor
        row, column = self._place()
        sheet = self.grid_model.sheet
        drawing = Drawing(
            next_drawing_name(sheet, "picture"),
            "picture",
            row,
            column,
            float(width),
            float(height),
            image=data,
            image_format=image_format(data),
            description=description,
        )
        return self.add_drawing(drawing)

    def insert_shape(self, shape: str) -> Drawing:
        """Insert > Shapes: draw a default-size shape at the active cell."""
        row, column = self._place()
        sheet = self.grid_model.sheet
        name = f"{SHAPES[shape].split(':')[0]} {len(sheet.drawings) + 1}"
        if any(existing.name == name for existing in sheet.drawings):
            name = next_drawing_name(sheet, "shape")
        width, height = (120.0, 60.0) if shape == "line" else (120.0, 80.0)
        return self.add_drawing(Drawing(name, "shape", row, column, width, height, shape=shape))

    def insert_text_box(self, text: str = "") -> Drawing:
        """Insert > Text Box at the active cell."""
        row, column = self._place()
        sheet = self.grid_model.sheet
        drawing = Drawing(
            next_drawing_name(sheet, "textbox"),
            "textbox",
            row,
            column,
            200.0,
            60.0,
            text=text,
            fill="#ffffff",
            line="#000000",
            font_color="#000000",
        )
        return self.add_drawing(drawing)

    def update_drawing(self, name: str, drawing: Drawing) -> bool:
        """Replace a drawing (moved, resized, or edited) in one undoable step."""
        sheet_name = self.grid_model.active_sheet_name

        def mutate() -> None:
            sheet = self.engine.workbook.get_sheet(sheet_name)
            sheet.drawings = [drawing if item.name == name else item for item in sheet.drawings]

        done = self._drawing_mutation(f"Change {name}", mutate)
        self.drawing_layer.sync()
        return done

    def delete_drawing(self, name: str) -> bool:
        sheet_name = self.grid_model.active_sheet_name

        def mutate() -> None:
            sheet = self.engine.workbook.get_sheet(sheet_name)
            sheet.drawings = [item for item in sheet.drawings if item.name != name]

        done = self._drawing_mutation(f"Delete {name}", mutate)
        self.drawing_layer.sync()
        self.grid.setFocus()
        return done

    def edit_drawing_text(self, name: str) -> None:
        drawing = next((item for item in self.grid_model.sheet.drawings if item.name == name), None)
        if drawing is None:
            return
        text, accepted = QInputDialog.getMultiLineText(self, "Edit Text", f"Text for {name}:", drawing.text)
        if accepted:
            self.update_drawing(name, replace(drawing, text=text))

    def _warn_illustration(self, text: str) -> None:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.warning(self, "Insert Picture", text)
