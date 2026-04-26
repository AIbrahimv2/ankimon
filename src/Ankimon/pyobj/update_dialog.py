from aqt import mw
from aqt.operations import QueryOp
from aqt.qt import (
    Qt,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QProgressBar,
    QTabWidget,
    QWidget,
    QMessageBox,
    QGroupBox,
)

from .update_manager import (
    fetch_releases,
    fetch_tags,
    fetch_branches,
    fetch_open_prs,
    apply_update,
    _download_zip,
    _download_branch_zip,
    _download_pr_zip,
)
from ..resources import addon_ver


class UpdateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent or mw)
        self.setWindowTitle("Ankimon Updater")
        self.setMinimumWidth(500)
        self.setMinimumHeight(350)

        self._zip_data = None
        self._releases = []
        self._tags = []
        self._branches = []
        self._prs = []

        layout = QVBoxLayout(self)

        version_label = QLabel(f"Current version: {addon_ver}")
        version_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(version_label)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_releases_tab(), "Releases")
        self.tabs.addTab(self._build_dev_tab(), "Developer")
        layout.addWidget(self.tabs)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self._load_data()

    def _build_releases_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        release_group = QGroupBox("Update to a release")
        release_layout = QVBoxLayout(release_group)
        self.release_combo = QComboBox()
        self.release_combo.addItem("Loading...")
        release_layout.addWidget(self.release_combo)
        self.release_btn = QPushButton("Update to Release")
        self.release_btn.clicked.connect(self._on_release_update)
        self.release_btn.setEnabled(False)
        release_layout.addWidget(self.release_btn)
        layout.addWidget(release_group)

        main_group = QGroupBox("Update to latest main")
        main_layout = QVBoxLayout(main_group)
        main_layout.addWidget(QLabel("Download the latest code from the main branch."))
        self.main_btn = QPushButton("Update to Latest Main")
        self.main_btn.clicked.connect(self._on_main_update)
        main_layout.addWidget(self.main_btn)
        layout.addWidget(main_group)

        layout.addStretch()
        return widget

    def _build_dev_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        pr_group = QGroupBox("Checkout a Pull Request")
        pr_layout = QVBoxLayout(pr_group)
        self.pr_combo = QComboBox()
        self.pr_combo.addItem("Loading...")
        pr_layout.addWidget(self.pr_combo)
        self.pr_btn = QPushButton("Install PR")
        self.pr_btn.clicked.connect(self._on_pr_update)
        self.pr_btn.setEnabled(False)
        pr_layout.addWidget(self.pr_btn)
        layout.addWidget(pr_group)

        branch_group = QGroupBox("Checkout a Branch")
        branch_layout = QVBoxLayout(branch_group)
        self.branch_combo = QComboBox()
        self.branch_combo.addItem("Loading...")
        branch_layout.addWidget(self.branch_combo)
        self.branch_btn = QPushButton("Install Branch")
        self.branch_btn.clicked.connect(self._on_branch_update)
        self.branch_btn.setEnabled(False)
        branch_layout.addWidget(self.branch_btn)
        layout.addWidget(branch_group)

        tag_group = QGroupBox("Checkout a Tag")
        tag_layout = QVBoxLayout(tag_group)
        self.tag_combo = QComboBox()
        self.tag_combo.addItem("Loading...")
        tag_layout.addWidget(self.tag_combo)
        self.tag_btn = QPushButton("Install Tag")
        self.tag_btn.clicked.connect(self._on_tag_update)
        self.tag_btn.setEnabled(False)
        tag_layout.addWidget(self.tag_btn)
        layout.addWidget(tag_group)

        layout.addStretch()
        return widget

    def _load_data(self):
        def bg(_col):
            return (fetch_releases(), fetch_tags(), fetch_branches(), fetch_open_prs())

        def on_done(result):
            self._releases, self._tags, self._branches, self._prs = result
            self._populate_combos()

        QueryOp(parent=self, op=bg, success=on_done).without_collection().run_in_background()

    def _populate_combos(self):
        self.release_combo.clear()
        if self._releases:
            for r in self._releases:
                self.release_combo.addItem(r["name"], r)
            self.release_btn.setEnabled(True)
        else:
            self.release_combo.addItem("No releases found")

        self.tag_combo.clear()
        if self._tags:
            for t in self._tags:
                self.tag_combo.addItem(t["name"], t)
            self.tag_btn.setEnabled(True)
        else:
            self.tag_combo.addItem("No tags found")

        self.branch_combo.clear()
        if self._branches:
            for b in self._branches:
                self.branch_combo.addItem(b["name"], b)
            self.branch_btn.setEnabled(True)
        else:
            self.branch_combo.addItem("No branches found")

        self.pr_combo.clear()
        if self._prs:
            for pr in self._prs:
                self.pr_combo.addItem(f"#{pr['number']} — {pr['title']}", pr)
            self.pr_btn.setEnabled(True)
        else:
            self.pr_combo.addItem("No open PRs")

    def _set_busy(self, busy: bool):
        self.progress_bar.setVisible(busy)
        self.progress_bar.setValue(0)
        self.release_btn.setEnabled(not busy)
        self.main_btn.setEnabled(not busy)
        self.pr_btn.setEnabled(not busy)
        self.branch_btn.setEnabled(not busy)
        self.tag_btn.setEnabled(not busy)

    def _on_progress(self, downloaded, total):
        pct = int((downloaded / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(pct)

    def _run_update(self, download_fn, label: str):
        self._set_busy(True)
        self.status_label.setText(f"Downloading {label}...")

        def bg(_col):
            zip_data = download_fn()
            if not zip_data:
                return False, "Download failed. Check your internet connection."
            messages = []
            success, msg = apply_update(zip_data, status_cb=lambda m: messages.append(m))
            return success, msg, messages

        def on_done(result):
            self._set_busy(False)
            success, msg, *extra = result
            messages = extra[0] if extra else []
            if messages:
                self.status_label.setText(messages[-1] if messages else msg)
            else:
                self.status_label.setText(msg)
            if success:
                QMessageBox.information(self, "Update Complete", f"{msg}\n\nPlease restart Anki for changes to take effect.")
            else:
                QMessageBox.warning(self, "Update Failed", msg)

        QueryOp(parent=self, op=bg, success=on_done).without_collection().run_in_background()

    def _on_release_update(self):
        data = self.release_combo.currentData()
        if not data:
            return
        self._run_update(
            lambda: _download_zip(data["zipball_url"]),
            f"release {data['name']}",
        )

    def _on_main_update(self):
        self._run_update(
            lambda: _download_branch_zip("main"),
            "latest main",
        )

    def _on_pr_update(self):
        data = self.pr_combo.currentData()
        if not data:
            return
        self._run_update(
            lambda: _download_pr_zip(data["head_sha"]),
            f"PR #{data['number']} ({data['title']})",
        )

    def _on_branch_update(self):
        data = self.branch_combo.currentData()
        if not data:
            return
        self._run_update(
            lambda: _download_branch_zip(data["name"]),
            f"branch {data['name']}",
        )

    def _on_tag_update(self):
        data = self.tag_combo.currentData()
        if not data:
            return
        self._run_update(
            lambda: _download_zip(data["zipball_url"]),
            f"tag {data['name']}",
        )
