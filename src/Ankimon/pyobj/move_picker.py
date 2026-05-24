import json
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView, 
    QAbstractItemView, QStyledItemDelegate, QStyleOptionViewItem,
    QFrame
)
from PyQt6.QtCore import Qt, QSize, QRect
from PyQt6.QtGui import QIcon, QPainter, QColor, QFont, QLinearGradient

from ..functions.pokedex_functions import find_details_move
from ..functions.gui_functions import type_icon_path, move_category_path
from ..utils import format_move_name

class NumericTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other):
        try:
            t1 = self.text().replace('--', '0').replace('---', '0').replace('None', '0').strip()
            t2 = other.text().replace('--', '0').replace('---', '0').replace('None', '0').strip()
            if not t1: t1 = '0'
            if not t2: t2 = '0'
            return float(t1) < float(t2)
        except ValueError:
            return super().__lt__(other)

class SortableIconTableWidgetItem(QTableWidgetItem):
    """Custom item for sorting columns that only display icons, by using their tooltip text."""
    def __lt__(self, other):
        return self.toolTip().lower() < other.toolTip().lower()

class IconDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        option.widget.style().drawControl(option.widget.style().ControlElement.CE_ItemViewItem, option, painter)
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if icon:
            icon_size = option.decorationSize
            if icon_size.width() <= 0:
                icon_size = QSize(50, 30)
            rect = option.rect
            x = rect.x() + (rect.width() - icon_size.width()) // 2
            y = rect.y() + (rect.height() - icon_size.height()) // 2
            icon.paint(painter, QRect(x, y, icon_size.width(), icon_size.height()), Qt.AlignmentFlag.AlignCenter)

class MovePickerDialog(QDialog):
    def __init__(self, pokemon_name, all_moves, current_moves, parent=None, force_show_current=False):
        super().__init__(parent)
        self.setWindowTitle("Move Selection & Details")
        self.setMinimumSize(1000, 650)
        
        # Main dark theme with glassy effects
        self.setStyleSheet("""
            QDialog {
                background-color: #0f172a;
                color: #f8fafc;
            }
            QLabel#HeaderLabel {
                font-size: 26px;
                font-weight: 900;
                color: #60a5fa;
                letter-spacing: 0.5px;
                margin-bottom: 5px;
            }
            QLineEdit {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 8px 12px;
                color: #f1f5f9;
                font-size: 14px;
                selection-background-color: #3b82f6;
            }
            QLineEdit:focus {
                border-color: #60a5fa;
                background-color: #0f172a;
            }
            QTableWidget {
                background-color: #0f172a;
                alternate-background-color: #161e33;
                gridline-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                font-size: 14px;
                color: #e2e8f0;
            }
            QTableWidget::item {
                padding-left: 10px;
            }
            QTableWidget::item:selected {
                background-color: #1e40af;
                color: white;
            }
            QHeaderView::section {
                background-color: #1e293b;
                color: #94a3b8;
                font-weight: bold;
                font-size: 12px;
                padding: 10px;
                border: none;
                text-transform: uppercase;
            }
            QPushButton#ActionBtn {
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 14px;
            }
            QPushButton#LearnBtn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2563eb, stop:1 #1d4ed8);
                color: white;
                border: 1px solid #1e40af;
            }
            QPushButton#LearnBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3b82f6, stop:1 #2563eb);
            }
            QPushButton#LearnBtn:disabled {
                background: #334155;
                color: #94a3b8;
                border-color: #1e293b;
            }
            QPushButton#CancelBtn {
                background-color: transparent;
                color: #94a3b8;
                border: 1px solid #334155;
            }
            QPushButton#CancelBtn:hover {
                background-color: #1e293b;
                color: #f1f5f9;
            }
            QScrollBar:vertical {
                border: none;
                background: #0f172a;
                width: 10px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #334155;
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: #475569;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        header_label = QLabel(pokemon_name)
        header_label.setObjectName("HeaderLabel")
        layout.addWidget(header_label)
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search moves by name...")
        self.search_bar.setClearButtonEnabled(True)
        self.search_bar.textChanged.connect(self.filter_moves)
        layout.addWidget(self.search_bar)
        
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["Name", "Type", "Category", "Power", "Accuracy", "PP", "Details"])
        self.table.setIconSize(QSize(50, 30))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(50)
        self.table.setAlternatingRowColors(True)
        
        self.icon_delegate = IconDelegate()
        self.table.setItemDelegateForColumn(1, self.icon_delegate)
        self.table.setItemDelegateForColumn(2, self.icon_delegate)
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for i, width in [(1, 60), (2, 60), (3, 75), (4, 85), (5, 55)]:
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(i, width)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        
        self.table.setSortingEnabled(True)
        
        self.current_moves = current_moves
        self.all_moves = list(all_moves)
        
        # Only add current moves if explicitly requested (e.g. from clicking a move name)
        # or if they are already present in the learnable list.
        if force_show_current:
            for m in self.current_moves:
                if m not in self.all_moves:
                    self.all_moves.append(m)

        self.move_data_cache = {}
        for move_name in self.all_moves:
            self.move_data_cache[move_name] = find_details_move(move_name)
            
        layout.addWidget(self.table)
        
        self.buttons = QHBoxLayout()
        self.learn_btn = QPushButton("Learn Move")
        self.learn_btn.setObjectName("LearnBtn")
        self.learn_btn.setProperty("class", "ActionBtn")
        self.learn_btn.setEnabled(False)
        self.learn_btn.setFixedSize(140, 38)
        self.learn_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.learn_btn.clicked.connect(self.accept)
        
        self.cancel_btn = QPushButton("Close")
        self.cancel_btn.setObjectName("CancelBtn")
        self.cancel_btn.setFixedSize(100, 38)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.clicked.connect(self.reject)
        
        self.buttons.addStretch()
        self.buttons.addWidget(self.cancel_btn)
        self.buttons.addWidget(self.learn_btn)
        layout.addLayout(self.buttons)
        
        self.table.itemSelectionChanged.connect(self.update_btn_state)
        self.populate_moves()

    def update_btn_state(self):
        selected_move = self.get_selected_move()
        if not selected_move:
            self.learn_btn.setEnabled(False)
            self.learn_btn.setText("Select a Move")
            return
            
        is_known = selected_move in self.current_moves
        self.learn_btn.setEnabled(not is_known)
        
        if is_known:
            self.learn_btn.setText("Already Known")
            self.learn_btn.setToolTip("Pokémon already knows this move")
        else:
            self.learn_btn.setText("Learn Move")
            self.learn_btn.setToolTip("")

    def populate_moves(self, filter_text=""):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        filter_text = filter_text.lower()
        
        row_idx = 0
        for move_name in self.all_moves:
            if filter_text and filter_text not in move_name.lower():
                continue
                
            move = self.move_data_cache.get(move_name)
            if not move: continue
            
            self.table.insertRow(row_idx)
            
            is_known = move_name in self.current_moves
            name_text = format_move_name(move_name)
            
            # Name Item
            name_item = QTableWidgetItem(name_text)
            name_item.setData(Qt.ItemDataRole.UserRole, move_name)
            
            if is_known:
                name_item.setForeground(QColor("#4ade80"))
                name_item.setFont(QFont("", -1, QFont.Weight.Black))
                name_item.setText(f"{name_text}  ●")
            
            # Type Icon
            m_type = move.get("type", "Normal")
            type_item = SortableIconTableWidgetItem("")
            t_icon_path = type_icon_path(m_type.lower())
            if t_icon_path.exists():
                type_item.setIcon(QIcon(str(t_icon_path)))
            type_item.setToolTip(m_type)
            
            self.table.setItem(row_idx, 0, name_item)
            self.table.setItem(row_idx, 1, type_item)
            
            # Category Icon
            cat = move.get("category", "Status")
            cat_item = SortableIconTableWidgetItem("")
            c_icon_path = move_category_path(cat)
            if c_icon_path.exists():
                cat_item.setIcon(QIcon(str(c_icon_path)))
            cat_item.setToolTip(cat)
            self.table.setItem(row_idx, 2, cat_item)
            
            # BP
            bp = str(move.get("basePower", "0"))
            bp_item = NumericTableWidgetItem(bp if bp != "0" else "--")
            bp_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, 3, bp_item)
            
            # Accuracy
            acc = move.get("accuracy")
            acc_str = str(acc) if isinstance(acc, int) else "100"
            acc_item = NumericTableWidgetItem(acc_str if acc_str != "True" else "---")
            acc_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, 4, acc_item)
            
            # PP
            pp_item = NumericTableWidgetItem(str(move.get("pp", "5")))
            pp_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, 5, pp_item)
            
            # Description
            desc_item = QTableWidgetItem(move.get("shortDesc", ""))
            self.table.setItem(row_idx, 6, desc_item)
            
            if is_known:
                for col in range(self.table.columnCount()):
                    item = self.table.item(row_idx, col)
                    if item:
                        item.setBackground(QColor("#0f172a"))
            
            row_idx += 1
            
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)

    def filter_moves(self, text):
        self.populate_moves(text)

    def get_selected_move(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return None
        row = selected_rows[0].row()
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
