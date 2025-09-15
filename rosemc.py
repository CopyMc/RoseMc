# Creator And Developer : Copy

import sys, os, json, socket, struct, time
from datetime import datetime
from PyQt5 import QtCore, QtGui, QtWidgets

APP_NAME = "RoseMC"
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".rosemc_deluxe_cfg.json")
FONT_FILES = ["Minecraftia.ttf", "PressStart2P.ttf", "Minecraft.ttf"]  
VALID_USER = "Mctools"
VALID_PASS = "free"
HISTORY_LIMIT = 300


def load_config():
    try:
        if os.path.exists(CONFIG_FILE):
            return json.load(open(CONFIG_FILE, "r", encoding="utf-8"))
    except:
        pass
    return {"remember": False, "user": None, "password": None, "history": [], "theme": "dark"}

def save_config(cfg):
    try:
        json.dump(cfg, open(CONFIG_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    except Exception as e:
        print("save_config error:", e)


def write_varint(value: int) -> bytes:
    out = bytearray()
    v = value & 0xFFFFFFFF
    while True:
        temp = v & 0x7F
        v >>= 7
        if v != 0:
            out.append(temp | 0x80)
        else:
            out.append(temp)
            break
    return bytes(out)

def build_status_request(host: str, port: int, protocol_version: int = 754) -> bytes:
    payload = bytearray()
    payload += write_varint(0x00)  
    payload += write_varint(protocol_version)
    host_b = host.encode("utf-8")
    payload += write_varint(len(host_b))
    payload += host_b
    payload += struct.pack(">H", port)
    payload += write_varint(1)  
    packet = bytearray()
    packet += write_varint(len(payload))
    packet += payload

    req = bytearray()
    req += write_varint(0x00)
    packet += write_varint(len(req))
    packet += req
    return bytes(packet)

def read_varint_from_sock(sock: socket.socket, timeout=4.0) -> int:
    sock.settimeout(timeout)
    num_read = 0
    result = 0
    while True:
        b = sock.recv(1)
        if not b:
            raise EOFError("socket closed")
        val = b[0]
        result |= (val & 0x7F) << (7 * num_read)
        num_read += 1
        if num_read > 5:
            raise ValueError("VarInt too big")
        if (val & 0x80) == 0:
            break
    return result

def query_java(host: str, port: int, timeout: float = 5.0) -> dict:

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    start = time.time()
    s.connect((host, port))
    s.sendall(build_status_request(host, port))

    length = read_varint_from_sock(s, timeout)
    _packet_id = read_varint_from_sock(s, timeout)
    str_len = read_varint_from_sock(s, timeout)
    data = b''
    while len(data) < str_len:
        chunk = s.recv(str_len - len(data))
        if not chunk:
            raise EOFError("EOF reading JSON")
        data += chunk
    s.close()
    elapsed = int((time.time() - start) * 1000)
    text = data.decode("utf-8", errors="replace")
    out = {"success": True, "type": "java", "ping": elapsed, "raw": text}
    try:
        j = json.loads(text)
        desc = j.get("description")
        if isinstance(desc, str):
            motd = desc
        elif isinstance(desc, dict):
            motd = desc.get("text","")
            if not motd:
                extra = desc.get("extra", [])
                motd = "".join((e.get("text","") if isinstance(e,dict) else str(e)) for e in extra)
        else:
            motd = str(desc)
        out.update({
            "motd": motd,
            "version": j.get("version",{}).get("name",""),
            "protocol": j.get("version",{}).get("protocol", None),
            "players_online": j.get("players",{}).get("online", None),
            "players_max": j.get("players",{}).get("max", None),
            "sample": [p.get("name") for p in j.get("players",{}).get("sample",[]) if isinstance(p,dict)]
        })
    except Exception as e:
        out["parse_error"] = str(e)
    return out

def robust_query(addr_text: str, server_type: str, timeout: float, retries: int):
    """Parse addr_text (host[:port]) then query with retries."""
    if ":" in addr_text:
        host, port_s = addr_text.split(":",1)
        try:
            port = int(port_s)
        except:
            port = 25565
    else:
        host = addr_text
        port = 25565
    attempt = 0
    last_exc = None
    while attempt <= retries:
        try:

            return query_java(host, port, timeout)
        except Exception as e:
            last_exc = e
            attempt += 1
            time.sleep(0.4 * attempt)
    raise last_exc if last_exc else RuntimeError("Query failed")


class QueryThread(QtCore.QThread):
    finished = QtCore.pyqtSignal(dict)
    error = QtCore.pyqtSignal(str)
    progress = QtCore.pyqtSignal(int)

    def __init__(self, addr_text: str, server_type: str='auto', timeout: int=5, retries: int=1):
        super().__init__()
        self.addr_text = addr_text.strip()
        self.server_type = server_type
        self.timeout = timeout
        self.retries = retries

    def run(self):
        self.progress.emit(5)
        try:
            res = robust_query(self.addr_text, self.server_type, self.timeout, self.retries)

            if ":" in self.addr_text:
                host, port = self.addr_text.split(":",1)
            else:
                host = self.addr_text; port = 25565
            res["_host"] = f"{host}:{port}"
            self.progress.emit(100)
            self.finished.emit(res)
        except Exception as e:
            self.error.emit(str(e))


def load_embedded_font():

    for fname in FONT_FILES:
        if os.path.exists(fname):
            try:
                id_ = QtGui.QFontDatabase.addApplicationFont(fname)
                families = QtGui.QFontDatabase.applicationFontFamilies(id_)
                if families:
                    return families[0]
            except Exception:
                continue

    db = QtGui.QFontDatabase()
    for fam in ["Minecraftia", "Consolas", "Courier New", "Segoe UI", "Arial"]:
     if QtGui.QFont(fam).exactMatch():
        return fam

        if fam in db.families():
            return fam
    return db.defaultFamily()


class AboutDialog(QtWidgets.QMessageBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About " + APP_NAME)
        text = (f"<b>{APP_NAME}</b><br>"
                "Free edition — Minecraft-style server monitor<br>"
                "Features: Java status ping, history, auto-refresh, export.<br>"
                "Login demo: user <b>free</b> / pass <b>111</b>.")
        self.setText(text)
        self.setStandardButtons(QtWidgets.QMessageBox.Ok)

class HistoryManager(QtWidgets.QDialog):
    def __init__(self, history:list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Server List Manager")
        self.resize(480, 360)
        self.history = list(history)
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        self.listw = QtWidgets.QListWidget()
        self.listw.addItems(self.history)
        layout.addWidget(self.listw)
        row = QtWidgets.QHBoxLayout()
        self.add_btn = QtWidgets.QPushButton("Add")
        self.add_btn.clicked.connect(self.add_item)
        row.addWidget(self.add_btn)
        self.edit_btn = QtWidgets.QPushButton("Edit")
        self.edit_btn.clicked.connect(self.edit_item)
        row.addWidget(self.edit_btn)
        self.del_btn = QtWidgets.QPushButton("Delete")
        self.del_btn.clicked.connect(self.del_item)
        row.addWidget(self.del_btn)
        row.addStretch()
        self.ok_btn = QtWidgets.QPushButton("OK")
        self.ok_btn.clicked.connect(self.accept)
        row.addWidget(self.ok_btn)
        layout.addLayout(row)

    def add_item(self):
        text, ok = QtWidgets.QInputDialog.getText(self, "Add server", "host[:port]:")
        if ok and text:
            self.listw.insertItem(0, text)

    def edit_item(self):
        r = self.listw.currentRow()
        if r < 0: return
        it = self.listw.item(r)
        text, ok = QtWidgets.QInputDialog.getText(self, "Edit server", "host[:port]:", text=it.text())
        if ok and text:
            it.setText(text)

    def del_item(self):
        r = self.listw.currentRow()
        if r < 0: return
        self.listw.takeItem(r)

    def get_history(self):
        return [self.listw.item(i).text() for i in range(self.listw.count())]

class LoginDialog(QtWidgets.QDialog):
    def __init__(self, cfg, font_family):
        super().__init__()
        self.cfg = cfg
        self.font_family = font_family
        self.setWindowTitle("Login - " + APP_NAME)
        self.setModal(True)
        self.setFixedSize(520, 360)

        self.setWindowFlags(QtCore.Qt.Dialog | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self._build_ui()
        self._apply_style()
        self._add_shadow()
        self._animate()

    def _build_ui(self):
        main = QtWidgets.QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)

        bg = QtWidgets.QFrame()
        bg.setObjectName("bg")
        main.addWidget(bg)
        vbg = QtWidgets.QVBoxLayout(bg)
        vbg.setContentsMargins(0, 0, 0, 0)


        self.card = QtWidgets.QFrame()
        self.card.setObjectName("card")
        self.card.setFixedSize(420, 280)
        wrapper = QtWidgets.QHBoxLayout()
        wrapper.addStretch(1)
        wrapper.addWidget(self.card)
        wrapper.addStretch(1)
        vbg.addStretch(1)
        vbg.addLayout(wrapper)
        vbg.addStretch(1)

        layout = QtWidgets.QVBoxLayout(self.card)
        layout.setContentsMargins(28, 22, 28, 22)

        self.title_lbl = QtWidgets.QLabel("🌹 RoseMC Deluxe 🌹")
        self.title_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self.title_lbl.setFont(QtGui.QFont(self.font_family, 16, QtGui.QFont.Bold))
        layout.addWidget(self.title_lbl)

        self.subtitle = QtWidgets.QLabel("Login to continue")
        self.subtitle.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.subtitle)

        layout.addSpacing(12)

        self.user_edit = QtWidgets.QLineEdit()
        self.user_edit.setPlaceholderText("Username")
        self.user_edit.setFixedHeight(38)
        layout.addWidget(self.user_edit)

        self.pass_edit = QtWidgets.QLineEdit()
        self.pass_edit.setPlaceholderText("Password")
        self.pass_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self.pass_edit.setFixedHeight(38)
        layout.addWidget(self.pass_edit)

        self.remember_chk = QtWidgets.QCheckBox("Remember me")
        self.remember_chk.setChecked(bool(self.cfg.get("remember")))
        layout.addWidget(self.remember_chk)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        self.login_btn = QtWidgets.QPushButton("Login")
        self.login_btn.clicked.connect(self.on_login)
        btn_row.addWidget(self.login_btn)
        self.exit_btn = QtWidgets.QPushButton("Exit")
        self.exit_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.exit_btn)
        layout.addLayout(btn_row)


        if self.cfg.get("remember"):
            self.user_edit.setText(self.cfg.get("user", ""))
            self.pass_edit.setText(self.cfg.get("password", ""))

    def _apply_style(self):

        self.setStyleSheet(f"""
            QFrame#bg {{
                background: transparent; /اند سب*/
            }}
            QFrame#card {{
                background: rgba(20, 26, 18, 0.95);
                border-radius: 18px; /* curve */
                border: 2px solid rgba(80,150,100,0.2);
            }}
            QLabel {{
                color: #dfeee0;
                font-family: '{self.font_family}';
            }}
            QLineEdit {{
                background:#0a1610;
                color:#dfeee0;
                border:1px solid #2f5a3b;
                border-radius: 8px;
                padding-left:10px;
                font-family: '{self.font_family}';
            }}
            QCheckBox {{ 
                color:#bfe7c9;
                font-family: '{self.font_family}';
            }}
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                                            stop:0 #44c767, stop:1 #2f8f3f);
                color: #07120b;
                font-weight:bold;
                border-radius:10px;
                padding:8px 14px;
                font-family: '{self.font_family}';
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                                            stop:0 #5be884, stop:1 #3fb26a);
                color:#051006;
            }}
        """)


    def _add_shadow(self):

        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 0)
        shadow.setColor(QtGui.QColor(0, 0, 0, 180))
        self.card.setGraphicsEffect(shadow)

    def _animate(self):

        self.card.setWindowOpacity(0)
        anim = QtCore.QPropertyAnimation(self.card, b"windowOpacity")
        anim.setDuration(800)
        anim.setStartValue(0)
        anim.setEndValue(1)
        anim.setEasingCurve(QtCore.QEasingCurve.InOutQuad)
        anim.start(QtCore.QAbstractAnimation.DeleteWhenStopped)

    def on_login(self):
        u = self.user_edit.text().strip()
        p = self.pass_edit.text().strip()
        if u.lower() == VALID_USER and p == VALID_PASS:
            if self.remember_chk.isChecked():
                self.cfg["remember"] = True
                self.cfg["user"] = u
                self.cfg["password"] = p
            else:
                self.cfg["remember"] = False
                self.cfg["user"] = None
                self.cfg["password"] = None
            save_config(self.cfg)
            self.accept()
        else:
            QtWidgets.QMessageBox.critical(self, "Login failed", "Invalid credentials\n(use: free / 111)")


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, cfg, font_family):
        super().__init__()
        self.cfg = cfg
        self.font_family = font_family
        self.history = cfg.get("history", [])
        self.setWindowTitle(APP_NAME)
        self.resize(1100, 720)
        # frameless & translucent to remove white chrome
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.worker = None
        self.current_result = None
        self.prev_online = None
        self._build_ui()
        self._apply_style()
        self.auto_timer = QtCore.QTimer(self)
        self.auto_timer.timeout.connect(self._auto_refresh_tick)

    def _build_ui(self):
        central_bg = QtWidgets.QFrame()
        central_bg.setObjectName("central_bg")
        self.setCentralWidget(central_bg)
        main = QtWidgets.QVBoxLayout(central_bg)
        main.setContentsMargins(10,10,10,10)
        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel(f"{APP_NAME}  —  Deluxe")
        title.setFont(QtGui.QFont(self.font_family, 16, QtGui.QFont.Bold))
        header.addWidget(title)
        header.addStretch(1)
        self.about_btn = QtWidgets.QPushButton("About")
        self.about_btn.clicked.connect(self.on_about)
        header.addWidget(self.about_btn)
        self.theme_btn = QtWidgets.QPushButton("Theme")
        self.theme_btn.clicked.connect(self.on_toggle_theme)
        header.addWidget(self.theme_btn)
        self.close_btn = QtWidgets.QPushButton("Quit")
        self.close_btn.clicked.connect(QtWidgets.qApp.quit)
        header.addWidget(self.close_btn)
        main.addLayout(header)


        row = QtWidgets.QHBoxLayout()
        self.addr_combo = QtWidgets.QComboBox()
        self.addr_combo.setEditable(True)
        self.addr_combo.setFixedWidth(420)
        for it in self.history:
            self.addr_combo.addItem(it)
        self.addr_combo.setFont(QtGui.QFont(self.font_family, 11))
        row.addWidget(self.addr_combo)

        self.type_cb = QtWidgets.QComboBox()
        self.type_cb.addItems(["auto","java"])
        self.type_cb.setFixedWidth(120)
        row.addWidget(self.type_cb)

        self.timeout_spin = QtWidgets.QSpinBox(); self.timeout_spin.setRange(1,30); self.timeout_spin.setValue(6); self.timeout_spin.setSuffix(" s"); self.timeout_spin.setFixedWidth(90)
        row.addWidget(self.timeout_spin)
        self.retries_spin = QtWidgets.QSpinBox(); self.retries_spin.setRange(0,5); self.retries_spin.setValue(1); self.retries_spin.setSuffix(" r"); self.retries_spin.setFixedWidth(90)
        row.addWidget(self.retries_spin)

        self.check_btn = QtWidgets.QPushButton("Check")
        self.check_btn.clicked.connect(self.on_check)
        row.addWidget(self.check_btn)

        self.auto_chk = QtWidgets.QCheckBox("Auto Refresh")
        self.auto_chk.stateChanged.connect(self.on_auto_changed)
        row.addWidget(self.auto_chk)

        self.auto_interval = QtWidgets.QSpinBox(); self.auto_interval.setRange(5,3600); self.auto_interval.setValue(30); self.auto_interval.setSuffix(" s"); self.auto_interval.setFixedWidth(100)
        row.addWidget(self.auto_interval)

        main.addLayout(row)


        content = QtWidgets.QHBoxLayout()


        left_v = QtWidgets.QVBoxLayout()


        status_card = QtWidgets.QFrame()
        status_card.setObjectName("status_card")
        status_card.setFixedHeight(150)
        sc_l = QtWidgets.QHBoxLayout(status_card)
        sc_l.setContentsMargins(12,12,12,12)
        left_col = QtWidgets.QVBoxLayout()
        self.status_big = QtWidgets.QLabel("Ready")
        self.status_big.setFont(QtGui.QFont(self.font_family, 18, QtGui.QFont.Bold))
        left_col.addWidget(self.status_big)
        self.led = QtWidgets.QLabel(); self.led.setFixedSize(16,16); self._led('gray')
        left_col.addWidget(self.led)
        sc_l.addLayout(left_col,1)

        right_col = QtWidgets.QVBoxLayout()
        self.ping_label = QtWidgets.QLabel("Ping: -")
        self.version_label = QtWidgets.QLabel("Version: -")
        self.players_label = QtWidgets.QLabel("Players: - / -")
        for w in (self.ping_label, self.version_label, self.players_label):
            w.setFont(QtGui.QFont(self.font_family, 11))
            right_col.addWidget(w)
        sc_l.addLayout(right_col,1)
        left_v.addWidget(status_card)


        motd_card = QtWidgets.QFrame(); motd_card.setObjectName("card"); motd_card.setFixedHeight(120)
        motd_l = QtWidgets.QVBoxLayout(motd_card)
        motd_l.addWidget(QtWidgets.QLabel("MOTD / Raw:"))
        self.motd_text = QtWidgets.QTextEdit(); self.motd_text.setReadOnly(True); self.motd_text.setFixedHeight(84)
        motd_l.addWidget(self.motd_text)
        left_v.addWidget(motd_card)


        players_card = QtWidgets.QFrame(); players_card.setObjectName("card")
        players_l = QtWidgets.QVBoxLayout(players_card)
        players_l.addWidget(QtWidgets.QLabel("Player sample:"))
        self.player_list = QtWidgets.QListWidget()
        players_l.addWidget(self.player_list)
        left_v.addWidget(players_card)


        action_row = QtWidgets.QHBoxLayout()
        self.save_btn = QtWidgets.QPushButton("Save to list")
        self.save_btn.clicked.connect(self.save_current_to_history)
        action_row.addWidget(self.save_btn)
        self.export_json_btn = QtWidgets.QPushButton("Export JSON")
        self.export_json_btn.clicked.connect(self.export_json)
        action_row.addWidget(self.export_json_btn)
        self.export_txt_btn = QtWidgets.QPushButton("Export TXT")
        self.export_txt_btn.clicked.connect(self.export_txt)
        action_row.addWidget(self.export_txt_btn)
        self.copy_btn = QtWidgets.QPushButton("Copy")
        self.copy_btn.clicked.connect(self.copy_result)
        action_row.addWidget(self.copy_btn)
        left_v.addLayout(action_row)

        content.addLayout(left_v, 2)


        right_v = QtWidgets.QVBoxLayout()
        right_v.addWidget(QtWidgets.QLabel("Saved servers:"))
        self.history_list = QtWidgets.QListWidget()
        self.history_list.addItems(self.history)
        self.history_list.itemDoubleClicked.connect(self.on_history_activate)
        right_v.addWidget(self.history_list)

        hist_btns = QtWidgets.QHBoxLayout()
        self.manage_hist_btn = QtWidgets.QPushButton("Manage")
        self.manage_hist_btn.clicked.connect(self.open_history_manager)
        hist_btns.addWidget(self.manage_hist_btn)
        self.clear_hist_btn = QtWidgets.QPushButton("Clear All")
        self.clear_hist_btn.clicked.connect(self.clear_history)
        hist_btns.addWidget(self.clear_hist_btn)
        right_v.addLayout(hist_btns)

        right_v.addWidget(QtWidgets.QLabel("Log:"))
        self.log_text = QtWidgets.QTextEdit(); self.log_text.setReadOnly(True); self.log_text.setFixedHeight(220)
        right_v.addWidget(self.log_text)

        content.addLayout(right_v, 1)

        main.addLayout(content)


        footer = QtWidgets.QHBoxLayout()
        self.last_label = QtWidgets.QLabel("")
        footer.addWidget(self.last_label)
        footer.addStretch(1)
        main.addLayout(footer)

    def _apply_style(self):

        self.setStyleSheet(f"""
            QFrame#central_bg {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #07130a, stop:1 #0e2117); border-radius:12px; }}
            QFrame#status_card {{ background: rgba(26,30,20,0.95); border: 2px solid rgba(90,60,30,0.12); border-radius:10px; }}
            QFrame#card {{ background: rgba(18,22,14,0.94); border-radius:8px; border:1px solid rgba(80,60,30,0.08); }}
            QLabel {{ color: #dfeee0; font-family: '{self.font_family}'; }}
            QPushButton {{ background: #6aa84f; color: #07120b; border-radius:8px; padding:8px; font-weight:bold; font-family: '{self.font_family}'; }}
            QPushButton:hover {{ background: #8fd07a; color:#031b00; }}
            QLineEdit, QComboBox, QSpinBox {{ background:#081409; color:#dfeee0; border:1px solid #24441f; padding:6px; border-radius:6px; font-family: '{self.font_family}'; }}
            QListWidget, QTextEdit {{ background:#07120b; color:#dfeee0; border:1px solid #1f3720; font-family: '{self.font_family}'; }}
        """)

    def _led(self, color):
        colors = {'green':'#44d07c','red':'#e05b4d','yellow':'#f2c94c','gray':'#7b8a7b'}
        c = colors.get(color, '#7b8a7b')
        self.led.setStyleSheet(f"background:{c}; border-radius:8px; min-width:16px; min-height:16px;")

    def log(self, s):
        self.log_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] {s}")


    def on_check(self):
        addr = self.addr_combo.currentText().strip()
        if not addr:
            QtWidgets.QMessageBox.information(self, "Input", "Enter host or host:port")
            return

        timeout = int(self.timeout_spin.value())
        retries = int(self.retries_spin.value())
        stype = self.type_cb.currentText()
        self.log(f"Querying {addr} (timeout={timeout}s retries={retries})")
        self.status_big.setText("Querying...")
        self._led('yellow')
        self.player_list.clear()
        self.motd_text.clear()
        self.version_label.setText("Version: -")
        self.ping_label.setText("Ping: -")
        self.players_label.setText("Players: - / -")
        self.check_btn.setEnabled(False)
        self.worker = QueryThread(addr, stype, timeout, retries)
        self.worker.progress.connect(lambda v: self.status_big.setText(f"Querying... {v}%"))
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _on_finished(self, res):
        self.check_btn.setEnabled(True)
        self.current_result = res
        self._led('green')
        self.status_big.setText("Online")
        self.ping_label.setText(f"Ping: {res.get('ping','?')} ms")
        self.version_label.setText(f"Version: {res.get('version','-')}")
        po = res.get('players_online'); pm = res.get('players_max')
        self.players_label.setText(f"Players: {po if po is not None else '?'} / {pm if pm is not None else '?'}")
        self.motd_text.setPlainText(str(res.get('motd','')) + "\n\nRAW:\n" + str(res.get('raw',''))[:3000])
        sample = res.get('sample') or []
        self.player_list.clear()
        if sample:
            for s in sample:
                self.player_list.addItem(str(s))
        else:
            self.player_list.addItem("(no sample)")

        entry = res.get('_host')
        if entry and entry not in self.history:
            self.history.insert(0, entry)
            if len(self.history) > HISTORY_LIMIT:
                self.history = self.history[:HISTORY_LIMIT]
            self.history_list.insertItem(0, entry)
            self.addr_combo.insertItem(0, entry)
            self.cfg["history"] = self.history
            save_config(self.cfg)
        self.last_label.setText("Last: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        online_now = True
        if self.prev_online is None:
            self.prev_online = online_now
        else:
            if online_now != self.prev_online:

                QtWidgets.QMessageBox.information(self, APP_NAME, f"Server {res.get('_host')} changed status: Online")
            self.prev_online = online_now
        self.log(f"Success: {res.get('_host')} ping={res.get('ping')}ms")

    def _on_error(self, err):
        self.check_btn.setEnabled(True)
        self._led('red')
        self.status_big.setText("Offline / Error")
        self.motd_text.setPlainText("Error:\n" + str(err))
        self.log("Error: " + str(err))
        online_now = False
        if self.prev_online is None:
            self.prev_online = online_now
        else:
            if online_now != self.prev_online:
                QtWidgets.QMessageBox.information(self, APP_NAME, "Server changed status: Offline/Error")
            self.prev_online = online_now


    def save_current_to_history(self):
        addr = self.addr_combo.currentText().strip()
        if not addr: return
        if addr in self.history:
            QtWidgets.QMessageBox.information(self, "History", "Already saved")
            return
        self.history.insert(0, addr)
        self.history_list.insertItem(0, addr)
        self.addr_combo.insertItem(0, addr)
        self.cfg["history"] = self.history
        save_config(self.cfg)
        QtWidgets.QMessageBox.information(self, "History", "Saved")

    def on_history_activate(self, item):
        if not item: return
        self.addr_combo.setEditText(item.text())
        self.on_check()

    def open_history_manager(self):
        dlg = HistoryManager(self.history, parent=self)
        if dlg.exec_():
            self.history = dlg.get_history()
            self.history_list.clear()
            self.history_list.addItems(self.history)
            self.addr_combo.clear()
            self.addr_combo.addItems(self.history)
            self.cfg["history"] = self.history
            save_config(self.cfg)

    def clear_history(self):
        if QtWidgets.QMessageBox.question(self, "Clear history", "Clear all saved servers?") != QtWidgets.QMessageBox.Yes:
            return
        self.history = []
        self.history_list.clear()
        self.addr_combo.clear()
        self.cfg["history"] = []
        save_config(self.cfg)

    def del_hist_item(self):
        row = self.history_list.currentRow()
        if row < 0: return
        it = self.history_list.takeItem(row)
        if it:
            txt = it.text()
            try:
                self.history.remove(txt)
            except:
                pass
            self.cfg["history"] = self.history
            save_config(self.cfg)


    def export_json(self):
        if not self.current_result:
            QtWidgets.QMessageBox.information(self, "Export", "No result to export")
            return
        default = f"mc_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export JSON", default, "JSON files (*.json)")
        if not path: return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"checked_at": datetime.now().isoformat(), "server": self.current_result.get("_host"), "result": self.current_result}, f, ensure_ascii=False, indent=2)
            QtWidgets.QMessageBox.information(self, "Export", "Saved.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", str(e))

    def export_txt(self):
        if not self.current_result:
            QtWidgets.QMessageBox.information(self, "Export", "No result to export")
            return
        default = f"mc_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export TXT", default, "Text files (*.txt)")
        if not path: return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._format_result_text(self.current_result))
            QtWidgets.QMessageBox.information(self, "Export", "Saved.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", str(e))

    def _format_result_text(self, res):
        if not res: return ""
        lines = []
        lines.append(f"Server: {res.get('_host','')}")
        lines.append(f"Type: {res.get('type','')}")
        lines.append(f"Ping: {res.get('ping','?')} ms")
        lines.append(f"Version: {res.get('version','')}")
        lines.append(f"Players: {res.get('players_online','?')} / {res.get('players_max','?')}")
        lines.append("MOTD:")
        lines.append(str(res.get('motd','')))
        return "\n".join(lines)

    def copy_result(self):
        if not self.current_result:
            return
        QtWidgets.QApplication.clipboard().setText(json.dumps(self.current_result, ensure_ascii=False, indent=2))
        QtWidgets.QMessageBox.information(self, "Copied", "Result copied to clipboard")


    def on_auto_changed(self, state):
        if state == QtCore.Qt.Checked:
            interval = int(self.auto_interval.value()) * 1000
            self.auto_timer.start(interval)
            self.log("Auto-refresh enabled")
        else:
            self.auto_timer.stop()
            self.log("Auto-refresh disabled")

    def _auto_refresh_tick(self):
        addr = self.addr_combo.currentText().strip()
        if addr:
            self.on_check()

    def on_about(self):
        dlg = AboutDialog(self)
        dlg.exec_()

    def on_toggle_theme(self):

        current = self.cfg.get("theme","dark")
        new = "light" if current == "dark" else "dark"
        self.cfg["theme"] = new
        save_config(self.cfg)
        QtWidgets.QMessageBox.information(self, "Theme", "Theme toggled (restart may be required for full effect).")


def main():
    cfg = load_config()
    app = QtWidgets.QApplication(sys.argv)


    font_family = load_embedded_font()
    app.setFont(QtGui.QFont(font_family, 11))


    login = LoginDialog(cfg, font_family)
    if login.exec_() != QtWidgets.QDialog.Accepted:
        return

    w = MainWindow(cfg, font_family)
    w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()  