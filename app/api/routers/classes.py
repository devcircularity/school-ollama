# app/api/routers/classes.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from typing import Dict, Any, List, Optional
from uuid import UUID
import logging

from app.core.db import get_db
from app.api.deps.tenancy import require_school
from app.models.class_model import Class
from app.models.student import Student
from app.schemas.class_schema import (
    ClassCreate, 
    ClassOut, 
    ClassList, 
    ClassDetail,
    ClassUpdate
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/", response_model=ClassOut, status_code=status.HTTP_201_CREATED)
async def create_class(
    class_data: ClassCreate,
    ctx: Dict[str, Any] = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Create a new class"""
    user = ctx["user"]
    school_id = ctx["school_id"]
    
    # Check if class name is unique within the school for the academic year (CASE-INSENSITIVE)
    existing_class = db.execute(
        select(Class).where(
            Class.school_id == UUID(school_id),
            func.lower(Class.name) == func.lower(class_data.name),
            Class.academic_year == class_data.academic_year
        )
    ).scalar_one_or_none()
    
    if existing_class:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Class '{class_data.name}' already exists for academic year {class_data.academic_year}"
        )
    
    # Create class
    new_class = Class(
        school_id=UUID(school_id),
        name=class_data.name,
        level=class_data.level,
        academic_year=class_data.academic_year,
        stream=class_data.stream
    )
    
    # ADD THESE MISSING LINES:
    try:
        db.add(new_class)
        db.commit()
        db.refresh(new_class)
        logger.info(f"Class created: {new_class.name} by {user.email}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating class: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating class"
        )
    
    # Return the created class with student count (0 for new class)
    return ClassOut(
        id=new_class.id,
        name=new_class.name,
        level=new_class.level,
        academic_year=new_class.academic_year,
        stream=new_class.stream,
        student_count=0,
        created_at=new_class.created_at
    )
    

@router.get("/", response_model=ClassList)
async def get_classes(
    ctx: Dict[str, Any] = Depends(require_school),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    academic_year: Optional[int] = Query(None),
    level: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
):
    """Get classes with filtering and pagination"""
    school_id = ctx["school_id"]
    
    # Base query with student count
    query = (
        select(Class, func.count(Student.id).label("student_count"))
        .outerjoin(Student, Class.id == Student.class_id)
        .where(Class.school_id == UUID(school_id))
        .group_by(Class.id)
    )
    
    # Apply filters
    if academic_year:
        query = query.where(Class.academic_year == academic_year)
    
    if level:
        # Case-insensitive level filter
        query = query.where(func.lower(Class.level).like(func.lower(f"%{level}%")))
    
    if search:
        # Case-insensitive search across name and level
        search_term = f"%{search}%"
        query = query.where(
            func.lower(Class.name).like(func.lower(search_term)) |
            func.lower(Class.level).like(func.lower(search_term))
        )
    
    # Order by level and name (case-insensitive)
    query = query.order_by(func.lower(Class.level), func.lower(Class.name))
    
    # Get total count for pagination
    count_query = (
        select(func.count(Class.id))
        .where(Class.school_id == UUID(school_id))
    )
    
    # Apply same filters to count query
    if academic_year:
        count_query = count_query.where(Class.academic_year == academic_year)
    
    if level:
        count_query = count_query.where(func.lower(Class.level).like(func.lower(f"%{level}%")))
    
    if search:
        search_term = f"%{search}%"
        count_query = count_query.where(
            func.lower(Class.name).like(func.lower(search_term)) |
            func.lower(Class.level).like(func.lower(search_term))
        )
    
    total = db.execute(count_query).scalar() or 0
    
    # Apply pagination
    offset = (page - 1) * limit
    results = db.execute(query.offset(offset).limit(limit)).all()
    
    # Format results
    classes = []
    for class_obj, student_count in results:
        classes.append(ClassOut(
            id=class_obj.id,
            name=class_obj.name,
            level=class_obj.level,
            academic_year=class_obj.academic_year,
            stream=class_obj.stream,
            student_count=student_count or 0,
            created_at=class_obj.created_at
        ))
    
    has_next = total > page * limit
    
    return ClassList(
        classes=classes,
        total=total,
        page=page,
        limit=limit,
        has_next=has_next
    )

@router.get("/{class_id}", response_model=ClassDetail)
async def get_class(
    class_id: str,
    ctx: Dict[str, Any] = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Get class details with student list"""
    school_id = ctx["school_id"]
    
    try:
        class_uuid = UUID(class_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid class ID format"
        )
    
    # Get class
    class_obj = db.execute(
        select(Class).where(
            Class.id == class_uuid,
            Class.school_id == UUID(school_id)
        )
    ).scalar_one_or_none()
    
    if not class_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Class not found"
        )
    
    # Get students in this class
    students = db.execute(
        select(Student).where(
            Student.class_id == class_uuid,
            Student.status == "ACTIVE"
        ).order_by(Student.first_name, Student.last_name)
    ).scalars().all()
    
    # Format student list
    student_list = []
    for student in students:
        student_list.append({
            "id": str(student.id),
            "admission_no": student.admission_no,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "full_name": f"{student.first_name} {student.last_name}".strip(),
            "gender": student.gender,
            "status": student.status
        })
    
    return ClassDetail(
        id=class_obj.id,
        name=class_obj.name,
        level=class_obj.level,
        academic_year=class_obj.academic_year,
        stream=class_obj.stream,
        student_count=len(student_list),
        students=student_list,
        created_at=class_obj.created_at,
        updated_at=class_obj.updated_at
    )

@router.put("/{class_id}", response_model=ClassOut)
async def update_class(
    class_id: str,
    class_data: ClassUpdate,
    ctx: Dict[str, Any] = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Update class information"""
    user = ctx["user"]
    school_id = ctx["school_id"]
    
    try:
        class_uuid = UUID(class_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid class ID format"
        )
    
    class_obj = db.execute(
        select(Class).where(
            Class.id == class_uuid,
            Class.school_id == UUID(school_id)
        )
    ).scalar_one_or_none()
    
    if not class_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Class not found"
        )
    
    # Check if name is unique (if being changed)
    if (class_data.name and 
        class_data.name != class_obj.name):
        
        academic_year = class_data.academic_year or class_obj.academic_year
        existing_class = db.execute(
            select(Class).where(
                Class.school_id == UUID(school_id),
                Class.name == class_data.name,
                Class.academic_year == academic_year,
                Class.id != class_uuid
            )
        ).scalar_one_or_none()
        
        if existing_class:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Class '{class_data.name}' already exists for academic year {academic_year}"
            )
    
    # Update fields that were provided
    update_data = class_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(class_obj, field, value)
    
    try:
        db.commit()
        db.refresh(class_obj)
        logger.info(f"Class updated: {class_obj.name} by {user.email}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating class: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating class"
        )
    
    # Get student count for response
    student_count = db.execute(
        select(func.count(Student.id)).where(
            Student.class_id == class_uuid,
            Student.status == "ACTIVE"
        )
    ).scalar() or 0
    
    return ClassOut(
        id=class_obj.id,
        name=class_obj.name,
        level=class_obj.level,
        academic_year=class_obj.academic_year,
        stream=class_obj.stream,
        student_count=student_count,
        created_at=class_obj.created_at
    )

@router.delete("/{class_id}")
async def delete_class(
    class_id: str,
    ctx: Dict[str, Any] = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Delete a class (only if no students are enrolled)"""
    user = ctx["user"]
    school_id = ctx["school_id"]
    
    try:
        class_uuid = UUID(class_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid class ID format"
        )
    
    class_obj = db.execute(
        select(Class).where(
            Class.id == class_uuid,
            Class.school_id == UUID(school_id)
        )
    ).scalar_one_or_none()
    
    if not class_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Class not found"
        )
    
    # Check if class has students
    student_count = db.execute(
        select(func.count(Student.id)).where(
            Student.class_id == class_uuid,
            Student.status == "ACTIVE"
        )
    ).scalar() or 0
    
    if student_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete class with {student_count} enrolled students. Please transfer students first."
        )
    
    try:
        db.delete(class_obj)
        db.commit()
        logger.info(f"Class deleted: {class_obj.name} by {user.email}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting class: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting class"
        )
    
    return {"message": "Class deleted successfully"}