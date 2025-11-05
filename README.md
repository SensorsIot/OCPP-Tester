# ⚡ OCPP 1.6-J Wallbox Tester

A comprehensive testing tool for OCPP 1.6-J compliant electric vehicle charge points (wallboxes).

## 📋 Overview

This Python-based test server provides a complete suite of OCPP 1.6-J protocol tests with real-time monitoring and control through a web interface.

## ✨ Features

- **🔌 OCPP 1.6-J Protocol Support**: Full implementation of Open Charge Point Protocol 1.6-JSON
- **🖥️ Web UI**: Real-time monitoring, test execution, and results visualization
- **🚗 EV Simulator Integration**: Automated testing with simulated EV states
- **🧪 Comprehensive Test Suite**: 30+ tests covering all aspects of OCPP functionality
- **🎨 Visual Feedback**: Color-coded test results (green/red/yellow/orange/grey) for instant status recognition

## 🚀 Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
python3 main.py
```

Access the web interface at `http://localhost:5000`

## ⚙️ Configuration

Environment variables (see `app/core.py` for defaults):
- `OCPP_HOST` / `OCPP_PORT`: WebSocket server binding (default: 0.0.0.0:8887)
- `HTTP_HOST` / `HTTP_PORT`: Web UI server binding (default: 0.0.0.0:5000)
- `EV_SIMULATOR_BASE_URL`: EV simulator service URL
- `EV_SIMULATOR_CHARGE_POINT_ID`: Charge point ID for simulator

## 📊 Test Categories

### 📡 A. Core Communication & Status (6 tests)
Basic connectivity, configuration, and status monitoring

### 🎫 B. Authorization & Transaction Management (8 tests)
Transaction control, RFID authorization, and local authorization lists

### 🔋 C. Smart Charging Profile (4 tests)
Charging profile management and composite schedule handling

### 🔧 X. System Control
Wallbox reboot and server management

## 🏗️ Architecture

```
main.py                     # Entry point & WebSocket routing
├── app/
│   ├── core.py            # Global state & configuration
│   ├── ocpp_handler.py    # WebSocket connection management
│   ├── ocpp_test_steps.py # Test implementations
│   ├── messages.py        # OCPP message payloads
│   ├── web_ui_server.py   # Flask REST API
│   └── templates/
│       └── index.html     # Web UI
```

## 🎯 Test Result States

- 🟢 **Green**: Test passed
- 🔴 **Red**: Test failed
- 🟡 **Yellow**: Test skipped
- 🟠 **Orange**: Test partially completed
- ⚫ **Grey**: Feature not supported by wallbox

## 📚 Documentation

- 📄 `WallboxTester-FSD.md`: Functional Specification Document with complete test catalog
- 🤖 `CLAUDE.md`: Development guidelines for AI-assisted coding

## 📦 Requirements

- 🐍 Python 3.11+
- websockets
- flask
- requests
- aiohttp

## 📄 License

See repository license file.
