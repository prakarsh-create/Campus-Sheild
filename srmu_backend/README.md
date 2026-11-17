# SRMU Campus Recover Backend

A FastAPI-based backend for managing lost-and-found reports on a university campus. The service supports user registration/login, report creation, item claims, admin review workflows, image uploads, and AI-assisted matching of similar lost/found items.

## Project Overview

SRMU Campus Recover helps students and campus staff quickly report missing or found items and verify ownership through a secure, structured claim process. The backend is designed for a campus environment where:

- students can submit lost/found reports
- security/admin staff can review claims
- sensitive ownership details remain hidden from the public
- similar reports can be surfaced through metadata and image-based matching

## Key Features

- JWT-based authentication and authorization
- Role-based access for students and admins
- Lost/found item submission with optional image upload
- Public item feed with filters and search
- Private ownership secret identifiers visible only to the reporter or admin
- Claim workflow with proof answer verification
- Admin dashboard for reviewing and approving/rejecting claims
- Image matching using a pretrained CNN embedding model
- SQLite database for local deployment and quick setup
- Swagger/OpenAPI docs for endpoint testing via /docs

## Tech Stack

- Python 3.10+
- FastAPI
- SQLAlchemy
- SQLite
- JWT (PyJWT)
- Python-Multipart
- Pillow
- PyTorch + TorchVision
- Uvicorn
- unittest / FastAPI TestClient

## Project Structure

```text
srmu_backend/
├─ app/
│  ├─ __init__.py
│  ├─ auth.py
│  ├─ database.py
│  ├─ image_features.py
│  ├─ main.py
│  ├─ matching.py
│  ├─ models.py
│  └─ schemas.py
├─ tests/
│  ├─ test_core_flow.py
│  └─ test_matching.py
├─ uploads/
├─ requirements.txt
├─ requirements-dev.txt
├─ srmu_recover.db
├─ README.md
└─ .gitignore (if present in your environment)
```

## Database Design

The application uses SQLite by default through the configuration in `app/database.py`.

Main entities:

- User
  - id
  - name
  - email
  - student_id
  - password_hash
  - role (`student` or `admin`)
  - created_at

- Item
  - id
  - type (`lost` or `found`)
  - title
  - category (`gadgets`, `id_cards`, `keys_bags`, `other`)
  - description
  - location
  - event_time
  - reward
  - secret_identifier
  - image_path
  - image_embedding
  - status (`open` or `claimed`)
  - reporter_id
  - created_at

- Claim
  - id
  - item_id
  - claimer_id
  - proof_answer
  - status (`pending`, `approved`, `rejected`)
  - admin_note
  - created_at

## Installation

1. Clone the repository and move into the project folder.
2. Create a virtual environment:

```bash
python -m venv venv
```

3. Activate the environment:

- Windows PowerShell:

```powershell
venv\Scripts\Activate.ps1
```

- Linux/macOS:

```bash
source venv/bin/activate
```

4. Install dependencies:

```bash
pip install -r requirements.txt
```

If you want the development tools used in tests:

```bash
pip install -r requirements-dev.txt
```

## Environment Variables

The backend expects the following environment variables for proper runtime behavior.

```bash
export SECRET_KEY="your-long-random-secret-key"
export ADMIN_EMAILS="security@srmu.ac.in,proctor@srmu.ac.in"
```

On Windows PowerShell:

```powershell
$env:SECRET_KEY="your-long-random-secret-key"
$env:ADMIN_EMAILS="security@srmu.ac.in,proctor@srmu.ac.in"
```

Notes:

- `SECRET_KEY` is required for JWT signing.
- `ADMIN_EMAILS` is a comma-separated list of emails that should receive admin privileges automatically on registration.
- If these values are not set, the app falls back to a development default, which should not be used in production.

## Running the Application

From the project folder:

```bash
uvicorn app.main:app --reload
```

Then open:

- API: http://127.0.0.1:8000
- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

## Authentication

The API uses a bearer token flow.

### Register

```bash
curl -X POST http://127.0.0.1:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Alice Student",
    "email": "alice@srmu.ac.in",
    "password": "securepass123",
    "student_id": "2024CS101"
  }'
```

### Login

The app expects form data with the field name `username` containing the email and `password` containing the password.

```bash
curl -X POST "http://127.0.0.1:8000/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=alice@srmu.ac.in&password=securepass123"
```

### Example returned payload

```json
{
  "access_token": "<jwt-token>",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "name": "Alice Student",
    "email": "alice@srmu.ac.in",
    "student_id": "2024CS101",
    "role": "student"
  }
}
```

Use the token in the `Authorization` header:

```http
Authorization: Bearer <access_token>
```

## Core API Endpoints

| Method | Endpoint | Access | Purpose |
|---|---|---|---|
| POST | /auth/register | Public | Create a new user account |
| POST | /auth/login | Public | Authenticate and get a JWT token |
| GET | /auth/me | Authenticated user | Fetch current user profile |
| POST | /items | Authenticated user | Create a lost/found item |
| GET | /items | Public / optional auth | List feed with filters and search |
| GET | /items/mine | Authenticated user | Fetch all items reported by the current user |
| GET | /items/{item_id} | Public / optional auth | View one item |
| GET | /items/{item_id}/matches | Authenticated owner/admin | Detect likely matching reports |
| DELETE | /items/{item_id} | Owner/admin | Delete an item |
| POST | /items/{item_id}/claim | Authenticated user | Submit a claim on an item |
| GET | /claims/mine | Authenticated user | View my claim history |
| GET | /admin/claims | Admin only | View pending/approved/rejected claims |
| POST | /admin/claims/{claim_id}/review | Admin only | Approve or reject a claim |
| GET | /stats | Public | Return summary counters for homepage |

## Item Submission Workflow

1. A user registers and logs in.
2. The user posts a lost or found item via `POST /items`.
3. The request may include:
   - type: `lost` or `found`
   - title
   - category
   - location
   - event_time
   - description
   - secret_identifier
   - reward
   - optional image file
4. The backend saves the item, stores the image if provided, and creates an embedding for image matching.
5. The item appears in the public feed after creation.

## Claim & Resolution Workflow

1. Another user finds a matching item in the public list and submits a claim using `POST /items/{item_id}/claim`.
2. The claimant provides a `proof_answer`, such as a secret detail that only the true owner would know.
3. The admin reviews claims at `/admin/claims`.
4. The backend reveals `secret_identifier` to the admin to verify the match.
5. If the claim is approved, the item status becomes `claimed` and all other pending claims for the same item are rejected.

## Image Matching Capabilities

The project contains a visual matching layer for similar lost/found reports.

- uploaded images are converted into normalized embeddings using a pretrained ResNet18 model
- if weights are not cached yet, they are downloaded automatically on first use
- image similarity is combined with metadata similarity logic
- matching can surface visually similar items even when text descriptors differ

Important note:

This is an assistive detection mechanism, not a guarantee of identity. All matches should still be reviewed by the campus staff or security desk before final resolution.

## CORS and Frontend Deployment

The app uses a permissive localhost regex in `app/main.py` to allow browser-based frontend testing during local development.

```python
allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?"
```

For production or staging deployment, update the allowed origins to include your frontend domain or deployment URL.

## Static Files

Uploaded images are stored in the `uploads/` directory and served via static files under:

```text
/uploads/<filename>
```

This allows the frontend to display item images directly from the API.

## Testing

Run the project tests with:

```bash
python -m unittest discover -s tests -v
```

The test suite covers the key flow:

- user registration and login
- item creation
- claim creation
- admin review
- ownership protection
- item deletion permissions
- match retrieval and access control

## Running in Development

Example:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY="dev-secret-key"
export ADMIN_EMAILS="security@srmu.ac.in"
uvicorn app.main:app --reload
```

## Production Considerations

Before deploying to production, review and update the following:

- `SECRET_KEY` should be a strong environment-specific secret
- `ADMIN_EMAILS` should be configured for trusted staff accounts
- CORS origins should be restricted to your frontend domain
- Use a non-SQLite database for larger deployments if needed
- Ensure upload storage and permissions are configured appropriately
- Consider adding backup, monitoring, and logging for production operations

## License

This project is intended for internal or academic campus deployment and is provided as-is for educational and operational use. Add a proper license file if you plan to distribute it publicly.

## Summary

SRMU Campus Recover is a campus lost-and-found management system built with FastAPI. It combines secure authentication, secure verification workflows, item reporting, claim review and AI-assisted image matching into a single backend service that can power a student-facing frontend or admin dashboard.
