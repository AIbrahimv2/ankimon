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
from aqt.theme import theme_manager

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
        self.setMinimumWidth(600)
        self.setMinimumHeight(550)
        self.resize(620, 580)

        self._releases = []
        self._tags = []
        self._branches = []
        self._prs = []

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

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
        frame_layout.setContentsMargins(12, 8, 12, 8)

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

        # Quick update to latest release
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
        self.update_latest_btn.clicked.connect(self._on_latest_tag_update)
        self.update_latest_btn.setEnabled(False)
        latest_layout.addWidget(self.update_latest_btn)
        layout.addWidget(latest_group)

        # Pick a specific release
        specific_group = QGroupBox("Specific Release")
        specific_layout = QVBoxLayout(specific_group)
        specific_layout.setContentsMargins(12, 16, 12, 12)
        specific_layout.setSpacing(8)
        specific_layout.addWidget(QLabel("Choose a specific version to install:"))
        self.release_combo = QComboBox()
        self.release_combo.addItem("Loading releases...")
        self.release_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
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
        layout.setSpacing(16)
        layout.setContentsMargins(8, 12, 8, 8)

        info = QLabel("For developers and testers. Install code from branches, PRs, or tags.")
        info.setStyleSheet("color: gray; font-size: 11px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        # Latest main
        main_group = QGroupBox("Latest Main Branch")
        main_layout = QVBoxLayout(main_group)
        main_layout.setContentsMargins(12, 16, 12, 12)
        self.main_btn = QPushButton("Update to Latest Main")
        self.main_btn.setMinimumHeight(32)
        self.main_btn.clicked.connect(self._on_main_update)
        main_layout.addWidget(self.main_btn)
        layout.addWidget(main_group)

        # Pull Requests
        pr_group = QGroupBox("Open Pull Requests")
        pr_layout = QVBoxLayout(pr_group)
        pr_layout.setContentsMargins(12, 16, 12, 12)
        pr_layout.setSpacing(8)
        self.pr_combo = QComboBox()
        self.pr_combo.addItem("Loading PRs...")
        self.pr_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.pr_combo.setMinimumHeight(28)
        pr_layout.addWidget(self.pr_combo)
        self.pr_btn = QPushButton("Install PR")
        self.pr_btn.setMinimumHeight(32)
        self.pr_btn.clicked.connect(self._on_pr_update)
        self.pr_btn.setEnabled(False)
        pr_layout.addWidget(self.pr_btn)
        layout.addWidget(pr_group)

        # Branches
        branch_group = QGroupBox("Branches")
        branch_layout = QVBoxLayout(branch_group)
        branch_layout.setContentsMargins(12, 16, 12, 12)
        branch_layout.setSpacing(8)
        self.branch_combo = QComboBox()
        self.branch_combo.addItem("Loading branches...")
        self.branch_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.branch_combo.setMinimumHeight(28)
        branch_layout.addWidget(self.branch_combo)
        self.branch_btn = QPushButton("Install Branch")
        self.branch_btn.setMinimumHeight(32)
        self.branch_btn.clicked.connect(self._on_branch_update)
        self.branch_btn.setEnabled(False)
        branch_layout.addWidget(self.branch_btn)
        layout.addWidget(branch_group)

        # Tags
        tag_group = QGroupBox("Tags")
        tag_layout = QVBoxLayout(tag_group)
        tag_layout.setContentsMargins(12, 16, 12, 12)
        tag_layout.setSpacing(8)
        self.tag_combo = QComboBox()
        self.tag_combo.addItem("Loading tags...")
        self.tag_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.tag_combo.setMinimumHeight(28)
        tag_layout.addWidget(self.tag_combo)
        self.tag_btn = QPushButton("Install Tag")
        self.tag_btn.setMinimumHeight(32)
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
        # Latest release button
        if self._releases:
            latest = self._releases[0]["name"]
            if latest == addon_ver:
                self.latest_tag_label.setText(f"You're on the latest release: {latest}")
                self.latest_tag_label.setStyleSheet("font-weight: bold; font-size: 12px; color: green;")
                self.update_latest_btn.setText("Already Up to Date")
            else:
                self.latest_tag_label.setText(f"Latest: {latest}  (you have: {addon_ver})")
                self.latest_tag_label.setStyleSheet("font-weight: bold; font-size: 12px; color: orange;")
                self.update_latest_btn.setEnabled(True)
        else:
            self.latest_tag_label.setText("Could not check for updates.")
            self.latest_tag_label.setStyleSheet("font-weight: bold; font-size: 12px; color: red;")

        # Releases
        self.release_combo.clear()
        if self._releases:
            for r in self._releases:
                self.release_combo.addItem(r["name"], r)
            self.release_btn.setEnabled(True)
        else:
            self.release_combo.addItem("No releases found")

        # Tags
        self.tag_combo.clear()
        if self._tags:
            for t in self._tags:
                self.tag_combo.addItem(t["name"], t)
            self.tag_btn.setEnabled(True)
        else:
            self.tag_combo.addItem("No tags found")

        # Branches
        self.branch_combo.clear()
        if self._branches:
            for b in self._branches:
                self.branch_combo.addItem(b["name"], b)
            self.branch_btn.setEnabled(True)
        else:
            self.branch_combo.addItem("No branches found")

        # PRs
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
        for btn in [self.update_latest_btn, self.release_btn, self.main_btn, self.pr_btn, self.branch_btn, self.tag_btn]:
            btn.setEnabled(not busy)

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

    def _on_latest_tag_update(self):
        if not self._releases:
            return
        release = self._releases[0]
        self._run_update(
            lambda: _download_zip(release["zipball_url"]),
            f"latest release ({release['name']})",
        )

    def _on_release_update(self):
        data = self.release_combo.currentData()
        if not data:
            return
        self._run_update(lambda: _download_zip(data["zipball_url"]), f"release {data['name']}")

    def _on_main_update(self):
        self._run_update(lambda: _download_branch_zip("main"), "latest main")

    def _on_pr_update(self):
        data = self.pr_combo.currentData()
        if not data:
            return
        self._run_update(lambda: _download_pr_zip(data["head_sha"]), f"PR #{data['number']} ({data['title']})")

    def _on_branch_update(self):
        data = self.branch_combo.currentData()
        if not data:
            return
        self._run_update(lambda: _download_branch_zip(data["name"]), f"branch {data['name']}")

    def _on_tag_update(self):
        data = self.tag_combo.currentData()
        if not data:
            return
        self._run_update(lambda: _download_zip(data["zipball_url"]), f"tag {data['name']}")
