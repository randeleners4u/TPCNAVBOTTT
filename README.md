# TPC NavBot: Intelligent Campus Navigation & Knowledge-Base RAG Assistant

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://tpcnavbottt-86x6mfwrmyvliw3xgpg2qp.streamlit.app/)

> **IS Professional Elective #4 — Generative AI Capstone Project**  
> **Institution**: Talibon Polytechnic College (TPC), San Isidro, Talibon, Bohol  
> **Live Deployed Web Application**: [https://tpcnavbottt-86x6mfwrmyvliw3xgpg2qp.streamlit.app/](https://tpcnavbottt-86x6mfwrmyvliw3xgpg2qp.streamlit.app/)  
> **GitHub Repository**: [https://github.com/randeleners4u/TPCNAVBOTTT](https://github.com/randeleners4u/TPCNAVBOTTT)  

---

## 🌐 Quick Access: Live Application
You can interact with **TPC NavBot** directly online without installing anything:
👉 **[Open TPC NavBot on Streamlit Community Cloud](https://tpcnavbottt-86x6mfwrmyvliw3xgpg2qp.streamlit.app/)**

Supported Languages:
- **Bisaya / Boholano** (e.g., *"Asa dapit ang opisina sa BSIS?"*)
- **English** (e.g., *"Where is the Registrar Office?"*)
- **Tagalog** (e.g., *"Saan po magbabayad ng tuition?"*)

---

## 🗂️ Project Contents & Documentation
The full application source code, datasets, evaluation reports, and containerization files are located in the [`TPC Navbot/`](TPC%20Navbot/) directory:

- **Web Application Entrypoint**: [`TPC Navbot/app.py`](TPC%20Navbot/app.py)
- **Documentation & Capstone Audit**: [`TPC Navbot/docs/`](TPC%20Navbot/docs/)
  - [`00_requirements_audit.md`](TPC%20Navbot/docs/00_requirements_audit.md): Requirements and verification compliance matrix
  - [`07_deployment_and_containerization.md`](TPC%20Navbot/docs/07_deployment_and_containerization.md): Deployment configuration & Streamlit Cloud evidence
  - [`07_final_technical_report.md`](TPC%20Navbot/docs/07_final_technical_report.md): Consolidated Capstone Report
  - [`08_presentation_defense_guide.md`](TPC%20Navbot/docs/08_presentation_defense_guide.md): Presentation & Defense Guide
- **Campus Knowledge Base**: [`TPC Navbot/data/raw/`](TPC%20Navbot/data/raw/) (School-confirmed & campus records)
- **Automated Tests**: [`TPC Navbot/tests/run_tests.py`](TPC%20Navbot/tests/run_tests.py)

---

## 🚀 Running Locally
```powershell
cd "TPC Navbot"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-full.txt
python run_app.py
```
