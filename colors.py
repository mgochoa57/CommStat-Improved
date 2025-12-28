# Copyright (c) 2025 Manuel Ochoa
# This file is part of CommStat-Improved.
# Licensed under the GNU General Public License v3.0.
# AI Assistance: Claude (Anthropic), ChatGPT (OpenAI)

"""
Color Customization Dialog for CommStat-Improved
Allows users to customize all application colors.
"""

import os
from configparser import ConfigParser
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget,
    QLabel, QLineEdit, QPushButton, QGroupBox, QGridLayout,
    QMessageBox, QColorDialog, QScrollArea, QFrame
)


# Default colors
DEFAULT_COLORS = {
    'program_background': '#A52A2A',
    'program_foreground': '#FFFFFF',
    'title_bar_background': '#F07800',
    'title_bar_foreground': '#FFFFFF',
    'marquee_background': '#242424',
    'marquee_foreground_green': '#00FF00',
    'marquee_foreground_yellow': '#FFFF00',
    'marquee_foreground_red': '#FF00FF',
    'time_background': '#282864',
    'time_foreground': '#88CCFF',
    'condition_green': '#108010',
    'condition_yellow': '#FFFF77',
    'condition_red': '#BB0000',
    'condition_gray': '#808080',
    'data_background': '#EEEEEE',
    'data_foreground': '#000000',
    'feed_background': '#000000',
    'feed_foreground': '#FFFFFF',
}


class ColorInput(QLineEdit):
    """A text input that shows a color value and launches color picker on click."""

    colorChanged = QtCore.pyqtSignal(str)

    def __init__(self, color: str = "#FFFFFF", parent=None):
        super().__init__(parent)
        self._color = color
        self.setText(color.upper())
        self.setReadOnly(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(28)
        self.setFixedWidth(100)

    @property
    def color(self) -> str:
        return self._color

    @color.setter
    def color(self, value: str):
        self._color = value
        self.setText(value.upper())
        self.colorChanged.emit(value)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            color = QColorDialog.getColor(QtGui.QColor(self._color), self, "Select Color")
            if color.isValid():
                self.color = color.name()
        super().mousePressEvent(event)


class SampleBox(QFrame):
    """A sample box showing background and foreground color combination."""

    def __init__(self, text: str = "Sample", show_text: bool = True, parent=None):
        super().__init__(parent)
        self.setFixedSize(140, 28)
        self.setFrameStyle(QFrame.Box | QFrame.Plain)
        self._show_text = show_text
        self._label = QLabel(text if show_text else "", self)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setGeometry(0, 0, 140, 28)
        font = QtGui.QFont()
        font.setFamily("Arial")
        font.setPointSize(11)
        font.setBold(True)
        self._label.setFont(font)
        self._bg_color = "#FFFFFF"
        self._fg_color = "#000000"
        self._update_style()

    def set_colors(self, bg_color: str, fg_color: str):
        self._bg_color = bg_color
        self._fg_color = fg_color
        self._update_style()

    def set_background(self, color: str):
        self._bg_color = color
        self._update_style()

    def set_foreground(self, color: str):
        self._fg_color = color
        self._update_style()

    def _update_style(self):
        self.setStyleSheet(f"background-color: {self._bg_color};")
        self._label.setStyleSheet(f"color: {self._fg_color}; background-color: transparent;")


class ColorsDialog(QDialog):
    """Color customization dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CommStat-Improved Colors")
        self.setFixedSize(450, 650)
        self.setWindowFlags(
            Qt.Window |
            Qt.CustomizeWindowHint |
            Qt.WindowTitleHint |
            Qt.WindowCloseButtonHint |
            Qt.WindowStaysOnTopHint
        )

        # Set window icon
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap("radiation-32.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.setWindowIcon(icon)

        # Set font size to match main program
        font = QtGui.QFont()
        font.setFamily("Arial")
        font.setPointSize(10)
        self.setFont(font)

        # Store color inputs and sample boxes
        self.color_inputs = {}
        self.sample_boxes = {}

        # Setup UI
        self._setup_ui()

        # Load current colors
        self._load_colors()

    def _setup_ui(self):
        """Setup the main UI layout."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(12)

        # Program colors
        scroll_layout.addWidget(self._create_simple_group(
            "Program", "program_background", "program_foreground", "Text"
        ))

        # Table Headers
        scroll_layout.addWidget(self._create_simple_group(
            "Table Headers", "title_bar_background", "title_bar_foreground", "Header"
        ))

        # Marquee (special - multiple foreground colors)
        scroll_layout.addWidget(self._create_marquee_group())

        # Time Banner
        scroll_layout.addWidget(self._create_simple_group(
            "Time Banner", "time_background", "time_foreground", "Time"
        ))

        # Status Conditions (no background, just colors)
        scroll_layout.addWidget(self._create_conditions_group())

        # Data Tables
        scroll_layout.addWidget(self._create_simple_group(
            "Data Tables", "data_background", "data_foreground", "Data"
        ))

        # Live Feed
        scroll_layout.addWidget(self._create_simple_group(
            "Live Feed", "feed_background", "feed_foreground", "Feed"
        ))

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        # Button row
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.reset_btn = QPushButton("Reset to Defaults")
        self.reset_btn.clicked.connect(self._reset_colors)
        button_layout.addWidget(self.reset_btn)

        self.save_btn = QPushButton("Save Colors")
        self.save_btn.clicked.connect(self._save_colors)
        button_layout.addWidget(self.save_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

    def _create_simple_group(self, title: str, bg_key: str, fg_key: str, sample_text: str) -> QGroupBox:
        """Create a group with background, foreground, and sample box."""
        group = QGroupBox(title)
        grid = QGridLayout(group)
        grid.setSpacing(8)
        grid.setContentsMargins(10, 15, 10, 10)

        # Background row
        grid.addWidget(QLabel("Background:"), 0, 0)
        bg_input = ColorInput(DEFAULT_COLORS.get(bg_key, "#FFFFFF"))
        self.color_inputs[bg_key] = bg_input
        grid.addWidget(bg_input, 0, 1)

        # Foreground row with sample
        grid.addWidget(QLabel("Foreground:"), 1, 0)
        fg_input = ColorInput(DEFAULT_COLORS.get(fg_key, "#000000"))
        self.color_inputs[fg_key] = fg_input
        grid.addWidget(fg_input, 1, 1)

        sample = SampleBox("View Results")
        self.sample_boxes[f"{bg_key}_{fg_key}"] = sample
        grid.addWidget(sample, 1, 2)

        # Connect signals to update sample
        bg_input.colorChanged.connect(lambda c: sample.set_background(c))
        fg_input.colorChanged.connect(lambda c: sample.set_foreground(c))

        return group

    def _create_marquee_group(self) -> QGroupBox:
        """Create the Marquee group with multiple foreground colors."""
        group = QGroupBox("Marquee Banner")
        grid = QGridLayout(group)
        grid.setSpacing(8)
        grid.setContentsMargins(10, 15, 10, 10)

        # Background row (no sample)
        grid.addWidget(QLabel("Background:"), 0, 0)
        bg_input = ColorInput(DEFAULT_COLORS.get('marquee_background', "#242424"))
        self.color_inputs['marquee_background'] = bg_input
        grid.addWidget(bg_input, 0, 1)

        # Yellow row with sample
        grid.addWidget(QLabel("Yellow Text:"), 1, 0)
        yellow_input = ColorInput(DEFAULT_COLORS.get('marquee_foreground_yellow', "#FFFF00"))
        self.color_inputs['marquee_foreground_yellow'] = yellow_input
        grid.addWidget(yellow_input, 1, 1)

        yellow_sample = SampleBox("View Results")
        self.sample_boxes['marquee_yellow'] = yellow_sample
        grid.addWidget(yellow_sample, 1, 2)

        # Green row with sample
        grid.addWidget(QLabel("Green Text:"), 2, 0)
        green_input = ColorInput(DEFAULT_COLORS.get('marquee_foreground_green', "#00FF00"))
        self.color_inputs['marquee_foreground_green'] = green_input
        grid.addWidget(green_input, 2, 1)

        green_sample = SampleBox("View Results")
        self.sample_boxes['marquee_green'] = green_sample
        grid.addWidget(green_sample, 2, 2)

        # Red row with sample
        grid.addWidget(QLabel("Red Text:"), 3, 0)
        red_input = ColorInput(DEFAULT_COLORS.get('marquee_foreground_red', "#FF00FF"))
        self.color_inputs['marquee_foreground_red'] = red_input
        grid.addWidget(red_input, 3, 1)

        red_sample = SampleBox("View Results")
        self.sample_boxes['marquee_red'] = red_sample
        grid.addWidget(red_sample, 3, 2)

        # Connect signals
        def update_marquee_samples():
            bg = bg_input.color
            yellow_sample.set_colors(bg, yellow_input.color)
            green_sample.set_colors(bg, green_input.color)
            red_sample.set_colors(bg, red_input.color)

        bg_input.colorChanged.connect(lambda: update_marquee_samples())
        yellow_input.colorChanged.connect(lambda c: yellow_sample.set_foreground(c))
        green_input.colorChanged.connect(lambda c: green_sample.set_foreground(c))
        red_input.colorChanged.connect(lambda c: red_sample.set_foreground(c))

        return group

    def _create_conditions_group(self) -> QGroupBox:
        """Create the Status Conditions group (colors only, no background)."""
        group = QGroupBox("Status Conditions")
        grid = QGridLayout(group)
        grid.setSpacing(8)
        grid.setContentsMargins(10, 15, 10, 10)

        conditions = [
            ('condition_green', 'Green:'),
            ('condition_yellow', 'Yellow:'),
            ('condition_red', 'Red:'),
            ('condition_gray', 'Gray:'),
        ]

        for row, (key, label) in enumerate(conditions):
            grid.addWidget(QLabel(label), row, 0)
            color_input = ColorInput(DEFAULT_COLORS.get(key, "#808080"))
            self.color_inputs[key] = color_input
            grid.addWidget(color_input, row, 1)

            # Sample box showing the condition color as background (no text)
            sample = SampleBox("", show_text=False)
            self.sample_boxes[key] = sample
            grid.addWidget(sample, row, 2)

            # For conditions, the color IS the background with white text
            color_input.colorChanged.connect(
                lambda c, s=sample: s.set_colors(c, "#FFFFFF")
            )

        return group

    def _load_colors(self):
        """Load colors from config.ini."""
        if not os.path.exists("config.ini"):
            self._apply_defaults()
            return

        config = ConfigParser()
        config.read("config.ini")

        if "COLORS" in config:
            colors = config["COLORS"]
            for key, input_widget in self.color_inputs.items():
                color = colors.get(key, DEFAULT_COLORS.get(key, "#FFFFFF"))
                if not color.startswith("#"):
                    color = "#" + color
                input_widget.color = color
        else:
            self._apply_defaults()

        # Update all samples
        self._update_all_samples()

    def _apply_defaults(self):
        """Apply default colors."""
        for key, input_widget in self.color_inputs.items():
            input_widget.color = DEFAULT_COLORS.get(key, "#FFFFFF")
        self._update_all_samples()

    def _update_all_samples(self):
        """Update all sample boxes with current colors."""
        # Simple groups
        for bg_key, fg_key, sample_key in [
            ('program_background', 'program_foreground', 'program_background_program_foreground'),
            ('title_bar_background', 'title_bar_foreground', 'title_bar_background_title_bar_foreground'),
            ('time_background', 'time_foreground', 'time_background_time_foreground'),
            ('data_background', 'data_foreground', 'data_background_data_foreground'),
            ('feed_background', 'feed_foreground', 'feed_background_feed_foreground'),
        ]:
            if sample_key in self.sample_boxes:
                self.sample_boxes[sample_key].set_colors(
                    self.color_inputs[bg_key].color,
                    self.color_inputs[fg_key].color
                )

        # Marquee samples
        marquee_bg = self.color_inputs['marquee_background'].color
        if 'marquee_yellow' in self.sample_boxes:
            self.sample_boxes['marquee_yellow'].set_colors(
                marquee_bg, self.color_inputs['marquee_foreground_yellow'].color
            )
        if 'marquee_green' in self.sample_boxes:
            self.sample_boxes['marquee_green'].set_colors(
                marquee_bg, self.color_inputs['marquee_foreground_green'].color
            )
        if 'marquee_red' in self.sample_boxes:
            self.sample_boxes['marquee_red'].set_colors(
                marquee_bg, self.color_inputs['marquee_foreground_red'].color
            )

        # Condition samples (color as background, white text)
        for key in ['condition_green', 'condition_yellow', 'condition_red', 'condition_gray']:
            if key in self.sample_boxes:
                self.sample_boxes[key].set_colors(
                    self.color_inputs[key].color, "#FFFFFF"
                )

    def _save_colors(self):
        """Save colors to config.ini."""
        config = ConfigParser()
        if os.path.exists("config.ini"):
            config.read("config.ini")

        colors_dict = {}
        for key, input_widget in self.color_inputs.items():
            colors_dict[key] = input_widget.color

        config["COLORS"] = colors_dict

        with open("config.ini", "w") as f:
            config.write(f)

        self.accept()

    def _reset_colors(self):
        """Reset all colors to defaults."""
        reply = QMessageBox.question(
            self, "Reset Colors",
            "Reset all colors to their default values?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._apply_defaults()


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    dialog = ColorsDialog()
    dialog.show()
    sys.exit(app.exec_())
