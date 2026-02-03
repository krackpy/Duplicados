DEPLOY (rápido)

Opción recomendada: Streamlit Community Cloud (gratis para probar)
1) Subí estos archivos a un repo (GitHub/GitLab):
   - app_streamlit.py
   - detector_core.py
   - requirements.txt
2) En Streamlit Cloud: New app -> elegís el repo -> Main file: app_streamlit.py

Otras opciones: Render / Railway / Azure App Service.

Seguridad (sugerida si se sube a internet):
- Agregar login simple (password) o SSO (Azure AD) si es corporativo.
- Evitar guardar archivos: procesar en memoria y borrar temporales.

Nota: esta versión usa pandas para mostrar tablas limpias en pantalla.
