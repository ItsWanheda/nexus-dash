# 🌌 NEXUS // CORE DASHBOARD

> **A futuristic, cyberpunk-style system monitoring dashboard.**

Unlike typical static dashboards, **NEXUS** leverages a **Python Backend** to provide **real-time** hardware statistics (CPU, RAM, GPU, Network) and system control (Process Management, Terminal).

![Preview](src/img/Preview.png)

---

## ✨ Features

- 📊 **Real-Time Hardware Monitoring**: Live updates for CPU, RAM, GPU, and Network stats powered by `psutil`.
- 🛠️ **Process Manager**: View running processes and kill them directly from the UI.
- 💻 **Integrated Terminal**: Execute system commands securely via the backend API.
- 📱 **Responsive Cyberpunk UI**: Fully responsive design optimized for Desktop, Tablet, and Mobile.
- ⚡ **Hybrid Architecture**: Built with Vanilla JS/Frontend and FastAPI/Python Backend for maximum performance.
- 🚫 **No Frameworks**: Pure HTML, CSS, and JavaScript for the frontend—no bloat.

---

## 🛠️ Technologies

| Layer | Technologies |
| :--- | :--- |
| **Frontend** | HTML5, CSS3 (Custom Properties, Grid, Flexbox), Vanilla JavaScript (ES6+) |
| **Backend** | Python 3, FastAPI, Uvicorn, Psutil |
| **Design** | Cyberpunk Aesthetic |

---

## 📦 Installation & Setup

### Prerequisites

- **Python**: 3.8 or higher
- **Browser**: Modern web browser (Chrome, Edge, Firefox)

### 1. Clone the Repository

```bash
git clone https://github.com/ItsWanheda/nexus-dash.git
cd nexus-dash
```
### 2. Install Dependencies
```bash
pip install psutil fastapi uvicorn
```
or
```bash
pip install -r requirements.txt
```

### 3. Run the Backend
```bash
python server.py
```
"The server will run at http://127.0.0.1:8000"

### 4. Open the Frontend
*Open index.html in your web browser.*

---

## 📂 Project Structure
```text
nexus-dashboard/
├── src/
│   ├── static/
│   │   └── app.js          # Frontend Logic
│   └── style/
│       └── styles.css      # Frontend Styles
├── index.html              # Main HTML Entry
├── server.py               # Python Backend API
├── requirements.txt        # Python dependencies
├── README.md
├── LICENSE
├── CODE_OF_CONDUCT.md
├── CONTRIBUTING.md
└── CHANGELOG.md
```

---

## ⚠️ Security Warning
**🔴 CRITICAL: Local Use Only**
***This dashboard includes a Terminal feature that allows executing system commands.***
1. **Local Use Only:** This project is designed for local development and personal monitoring.
2. **Do Not Expose:** Do not host this dashboard on a public server without implementing strict authentication and command whitelisting.**

---

## 🤝 Contributing
* We welcome contributions! Please read our Contributing Guidelines for details on our code of conduct and the process for submitting pull requests.

---

## 📄 License
* This project is licensed under the MIT License - see the LICENSE file for details.

---

<p align="center">
Made with ❤️ for Cyberpunk Aesthetics
</p>
