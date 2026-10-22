# Sample PR for a live test of the Claude reviewer. Copy into the target file on a test branch.
# Expected: CRITICAL security finding (SQL injection). Check fails.
# Target: backend/app/routers/public.py

@router.get("/search-students")
def search_students(name: str, db: Session = Depends(get_db)):
    sql = f"SELECT id, full_name, reg_number FROM students WHERE full_name LIKE '%{name}%'"
    rows = db.execute(text(sql)).fetchall()
    return [dict(r._mapping) for r in rows]

