<<<<<<< HEAD
# SRMU Campus Recover

This workspace contains the backend for the SRMU Campus Recover lost-and-found system.

## Project Details

- Project type: FastAPI backend for campus item recovery
- Main functionality: report lost/found items, manage claims, review admin actions, and match similar items by metadata and image similarity
- Auth model: JWT-based authentication with student/admin roles
- Database: SQLite by default
- Image support: upload and serve item images from the `uploads/` directory
- API docs: available via FastAPI Swagger at `/docs`

## Included Project Folder

The actual application code is inside:

- `srmu_backend/`

The detailed project documentation, environment setup, API endpoints, and usage instructions are available in that folder's README file.

## Quick Start

```bash
cd srmu_backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY="your-long-random-secret-key"
export ADMIN_EMAILS="security@srmu.ac.in"
uvicorn app.main:app --reload
```

For Windows PowerShell:

```powershell
cd srmu_backend
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:SECRET_KEY="your-long-random-secret-key"
$env:ADMIN_EMAILS="security@srmu.ac.in"
uvicorn app.main:app --reload
```

## Notes

- The API is intended for campus lost-and-found workflows.
- Sensitive claim verification details are hidden from the public and exposed only to allowed users/admins.
- Image matching is assistive and should still be reviewed by staff before final resolution.
=======
# Campus-Sheild
>>>>>>> 7872777044efa14909a479fa64157b27b9a2f22b
