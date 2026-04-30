# =========================
# Config
# =========================
PYTHON=python3
VENV=venv
PIP=$(VENV)/bin/pip
PY=$(VENV)/bin/python

APP=app.py
DIST=dist
BUILD=build

$(VENV)/bin/activate:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip

# =========================
# Setup ambiente virtuale
# =========================
venv:
	$(VENV)/bin/activate

# =========================
# Install dipendenze
# =========================
install: venv
	$(PIP) install -r requirements.txt

# =========================
# Run app (dev)
# =========================
run:
	$(PY) $(APP)

# =========================
# Run con debug Qt
# =========================
run-debug:
	QT_QPA_PLATFORM=xcb $(PY) $(APP)

# =========================
# Build Linux (PyInstaller)
# =========================
build:
	$(PIP) install pyinstaller
	$(VENV)/bin/pyinstaller \
		--noconfirm \
		--onefile \
		--windowed \
		--add-data "ui:ui" \
		$(APP)

# =========================
# Clean build artifacts
# =========================
clean:
	rm -rf $(BUILD) $(DIST) *.spec

# =========================
# Full rebuild
# =========================
rebuild: clean build