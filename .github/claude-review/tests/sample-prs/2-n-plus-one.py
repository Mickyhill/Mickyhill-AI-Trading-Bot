# Sample PR for a live test of the Claude reviewer. Copy into the target file on a test branch.
# Expected: MEDIUM database finding (N+1) plus HIGH bug (missing return).
# Target: backend/app/routers/student.py

@router.get("/courses-with-materials")
def courses_with_materials(student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    courses = db.query(Course).filter(Course.semester_id == student.semester_id).all()
    out = []
    for c in courses:
        mats = db.query(Material).filter(Material.course_id == c.id).all()
        out.append({"course": c.code, "materials": [m.title for m in mats]})
