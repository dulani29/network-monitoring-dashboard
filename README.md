# Network Monitoring Dashboard

A web-based network monitoring application built with **Python, Flask, SQLite, and Vanilla JavaScript**.

The application monitors network devices, checks connectivity, measures ping response time and packet loss, and displays network health through an interactive dashboard.

## Features

- **Device Management** – Add, edit, and delete devices using IP addresses or hostnames.
- **Network Monitoring** – Monitor multiple devices using parallel ICMP ping checks.
- **Status Detection** – Identify devices as Online, Degraded, or Offline.
- **Network Dashboard** – View device status, average latency, packet loss, and network health.
- **Incident Tracking** – Record outages, recovery times, and downtime.
- **Network Scanner** – Discover active devices on an authorized local network.
- **Monitoring History** – View historical results and export records as CSV.
- **Auto Monitoring** – Automatically check devices at configurable intervals.

## Technologies Used

- Python
- Flask
- SQLite
- HTML5
- CSS3
- Vanilla JavaScript
- REST API
- ICMP / Ping
- Python ThreadPoolExecutor

## Project Architecture

The application follows a layered architecture to separate business logic, API handling, and database operations.

```text
network-monitor/
├── run.py
├── config.py
├── requirements.txt
├── app/
│   ├── models/
│   ├── repositories/
│   ├── services/
│   ├── controllers/
│   ├── templates/
│   ├── static/
│   └── database.py
├── tests/
└── data/
```

**Request Flow:**

Browser → Flask Controllers → Services → Repositories → SQLite

## Installation

**1. Clone the repository**

```bash
git clone https://github.com/dulani29/network-monitoring-dashboard.git
cd network-monitoring-dashboard
```

**2. Create and activate a virtual environment**

```bash
python3 -m venv venv
source venv/bin/activate
```

**3. Install dependencies**

```bash
pip install -r requirements.txt
```

**4. Run the application**

```bash
python run.py
```

**5. Open in your browser**

http://127.0.0.1:5050

## Run Tests

```bash
python -m unittest discover -s tests -t . -v
```

## Skills Demonstrated

- Network troubleshooting and connectivity monitoring
- IP addressing, ICMP, DNS, and latency analysis
- Python backend development
- REST API development
- Database management with SQLite
- Frontend development
- Layered software architecture
- Testing and debugging
