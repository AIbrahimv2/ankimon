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
    QFrame,
    QSizePolicy,
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
        self.setWindowTitle("Update Ankimon")
        self.setMinimumWidth(580)
        self.setMinimumHeight(400)
        self.resize(600, 420)

        self._releases = []
        self._tags = []
        self._branches = []
        self._prs = []

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(16, 16, 16, 16)

        header = self._build_header()
        layout.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_releases_tab(), "Releases")
        self.tabs.addTab(self._build_dev_tab(), "Developer Mode")
        layout.addWidget(self.tabs)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.status_label)

        self._load_data()

    def _build_header(self):
        frame = QFrame()
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(0, 0, 0, 4)
        frame_layout.setSpacing(2)

        title = QLabel("Ankimon Updater")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        frame_layout.addWidget(title)

        ver = QLabel(f"Installed version: {addon_ver}")
        ver.setStyleSheet("font-size: 12px; color: gray;")
        frame_layout.addWidget(ver)

        return frame

    def _build_releases_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(16)
        layout.setContentsMargins(8, 12, 8, 8)

        # Quick update
        latest_group = QGroupBox("Quick Update")
        latest_layout = QVBoxLayout(latest_group)
        latest_layout.setContentsMargins(12, 16, 12, 12)
        latest_layout.setSpacing(10)
        desc = QLabel("Get the latest experimental release with one click.")
        desc.setWordWrap(True)
        latest_layout.addWidget(desc)
        self.latest_tag_label = QLabel("Checking for latest version...")
        self.latest_tag_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        latest_layout.addWidget(self.latest_tag_label)
        self.update_latest_btn = QPushButton("Update to Latest Release")
        self.update_latest_btn.setMinimumHeight(40)
        self.update_latest_btn.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.update_latest_btn.clicked.connect(self._on_latest_release_update)
        self.update_latest_btn.setEnabled(False)
        latest_layout.addWidget(self.update_latest_btn)
        layout.addWidget(latest_group)

        # Specific release
        specific_group = QGroupBox("Specific Release")
        specific_layout = QVBoxLayout(specific_group)
        specific_layout.setContentsMargins(12, 16, 12, 12)
        specific_layout.setSpacing(8)
        specific_layout.addWidget(QLabel("Choose a specific version to install:"))
        self.release_combo = QComboBox()
        self.release_combo.addItem("Loading releases...")
        self.release_combo.setMinimumHeight(28)
        specific_layout.addWidget(self.release_combo)
        self.release_btn = QPushButton("Install Selected Release")
        self.release_btn.setMinimumHeight(32)
        self.release_btn.clicked.connect(self._on_release_update)
        self.release_btn.setEnabled(False)
        specific_layout.addWidget(self.release_btn)
        layout.addWidget(specific_group)

        layout.addStretch()
        return widget

    def _build_dev_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(14)
        layout.setContentsMargins(8, 12, 8, 8)

        info = QLabel("For developers and testers. Install code from any source.")
        info.setStyleSheet("color: gray; font-size: 11px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        group = QGroupBox("Install from")
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(12, 16, 12, 12)
        group_layout.setSpacing(10)

        # Source type selector
        source_label = QLabel("Source:")
        source_label.setStyleSheet("font-weight: bold;")
        group_layout.addWidget(source_label)

        self.source_combo = QComboBox()
        self.source_combo.addItem("Latest Main Branch", "main")
        self.source_combo.addItem("Open Pull Request", "pr")
        self.source_combo.addItem("Branch", "branch")
        self.source_combo.addItem("Tag", "tag")
        self.source_combo.setMinimumHeight(28)
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        group_layout.addWidget(self.source_combo)

        # Target selector (hidden for "main")
        self.target_label = QLabel("Select:")
        self.target_label.setStyleSheet("font-weight: bold;")
        self.target_label.setVisible(False)
        group_layout.addWidget(self.target_label)

        self.target_combo = QComboBox()
        self.target_combo.setMinimumHeight(28)
        self.target_combo.setVisible(False)
        group_layout.addWidget(self.target_combo)

        # Install button
        self.dev_install_btn = QPushButton("Install")
        self.dev_install_btn.setMinimumHeight(36)
        self.dev_install_btn.setStyleSheet("font-weight: bold;")
        self.dev_install_btn.clicked.connect(self._on_dev_install)
        group_layout.addWidget(self.dev_install_btn)

        layout.addWidget(group)
        layout.addStretch()
        return widget

    def _on_source_changed(self, index):
        source = self.source_combo.currentData()
        if source == "main":
            self.target_label.setVisible(False)
            self.target_combo.setVisible(False)
        else:
            self.target_label.setVisible(True)
            self.target_combo.setVisible(True)
            self._populate_target(source)

    def _populate_target(self, source):
        self.target_combo.clear()
        if source == "pr":
            self.target_label.setText("Pull Request:")
            if self._prs:
                for pr in self._prs:
                    self.target_combo.addItem(f"#{pr['number']} — {pr['title']}", pr)
            else:
                self.target_combo.addItem("No open PRs")
        elif source == "branch":
            self.target_label.setText("Branch:")
            if self._branches:
                for b in self._branches:
                    self.target_combo.addItem(b["name"], b)
            else:
                self.target_combo.addItem("No branches found")
        elif source == "tag":
            self.target_label.setText("Tag:")
            if self._tags:
                for t in self._tags:
                    self.target_combo.addItem(t["name"], t)
            else:
                self.target_combo.addItem("No tags found")

    def _load_data(self):
        def bg(_col):
            return (fetch_releases(), fetch_tags(), fetch_branches(), fetch_open_prs())

        def on_done(result):
            self._releases, self._tags, self._branches, self._prs = result
            self._populate_ui()

        QueryOp(parent=self, op=bg, success=on_done).without_collection().run_in_background()

    def _populate_ui(self):
        # Latest release
        if self._releases:
            latest = self._releases[0]["name"]
            if latest == addon_ver:
                self.latest_tag_label.setText(f"You're on the latest release: {latest}")
                self.latest_tag_label.setStyleSheet("font-weight: bold; font-size: 13px; color: green;")
                self.update_latest_btn.setText("Already Up to Date")
            else:
                self.latest_tag_label.setText(f"Latest: {latest}  (you have: {addon_ver})")
                self.latest_tag_label.setStyleSheet("font-weight: bold; font-size: 13px; color: orange;")
                self.update_latest_btn.setEnabled(True)
        else:
            self.latest_tag_label.setText("Could not check for updates.")
            self.latest_tag_label.setStyleSheet("font-weight: bold; font-size: 13px; color: red;")

        # Releases combo
        self.release_combo.clear()
        if self._releases:
            for r in self._releases:
                self.release_combo.addItem(r["name"], r)
            self.release_btn.setEnabled(True)
        else:
            self.release_combo.addItem("No releases found")

        # Refresh dev target if visible
        source = self.source_combo.currentData()
        if source and source != "main":
            self._populate_target(source)

    def _set_busy(self, busy: bool):
        self.progress_bar.setVisible(busy)
        self.progress_bar.setValue(0)
        self.update_latest_btn.setEnabled(not busy)
        self.release_btn.setEnabled(not busy)
        self.dev_install_btn.setEnabled(not busy)

    def _run_update(self, download_fn, label: str):
        confirm = QMessageBox.question(
            self, "Confirm Update",
            f"Update Ankimon to {label}?\n\nYour Pokemon data, settings, and sprites will be preserved.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self._set_busy(True)
        self.status_label.setText(f"Downloading {label}...")

        def bg(_col):
            zip_data = download_fn()
            if not zip_data:
                return False, "Download failed. Check your internet connection.", []
            messages = []
            success, msg = apply_update(zip_data, status_cb=lambda m: messages.append(m))
            return success, msg, messages

        def on_done(result):
            self._set_busy(False)
            success, msg, messages = result
            self.status_label.setText(messages[-1] if messages else msg)
            self.progress_bar.setValue(100 if success else 0)
            if success:
                QMessageBox.information(
                    self, "Update Complete",
                    f"{msg}\n\nPlease restart Anki for changes to take effect.",
                )
            else:
                QMessageBox.warning(self, "Update Failed", msg)

        QueryOp(parent=self, op=bg, success=on_done).without_collection().run_in_background()

    def _on_latest_release_update(self):
        if not self._releases:
            return
        release = self._releases[0]
        self._run_update(lambda: _download_zip(release["zipball_url"]), f"latest release ({release['name']})")

    def _on_release_update(self):
        data = self.release_combo.currentData()
        if not data:
            return
        self._run_update(lambda: _download_zip(data["zipball_url"]), f"release {data['name']}")

    def _on_dev_install(self):
        source = self.source_combo.currentData()
        if source == "main":
            self._run_update(lambda: _download_branch_zip("main"), "latest main")
        elif source == "pr":
            data = self.target_combo.currentData()
            if data:
                self._run_update(lambda: _download_pr_zip(data["head_sha"]), f"PR #{data['number']} ({data['title']})")
        elif source == "branch":
            data = self.target_combo.currentData()
            if data:
                self._run_update(lambda: _download_branch_zip(data["name"]), f"branch {data['name']}")
        elif source == "tag":
            data = self.target_combo.currentData()
            if data:
                self._run_update(lambda: _download_zip(data["zipball_url"]), f"tag {data['name']}")
