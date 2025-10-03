# app/api/routers/fees.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from uuid import UUID
from decimal import Decimal

from app.core.db import get_db
from app.api.deps.tenancy import require_school
from app.models.fee import FeeStructure, FeeItem
from app.schemas.fee_schema import (
    FeeStructureCreate, FeeStructureOut, FeeStructureDetail,
    FeeItemCreate, FeeItemOut
)

router = APIRouter()

@router.post("/structures/", response_model=FeeStructureOut, status_code=status.HTTP_201_CREATED)
async def create_fee_structure(
    data: FeeStructureCreate,
    ctx: dict = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Create a new fee structure with uniqueness validation"""
    school_id = UUID(ctx["school_id"])
    
    # If is_default=True, unset other defaults for same term/year
    if data.is_default:
        for existing in db.execute(
            select(FeeStructure).where(
                FeeStructure.school_id == school_id,
                FeeStructure.term == data.term,
                FeeStructure.year == data.year,
                FeeStructure.is_default == True
            )
        ).scalars():
            existing.is_default = False
    
    structure = FeeStructure(
        school_id=school_id,
        **data.model_dump()
    )
    
    try:
        db.add(structure)
        db.commit()
        db.refresh(structure)
    except IntegrityError as e:
        db.rollback()
        if 'uix_fee_structure_unique' in str(e):
            raise HTTPException(
                status_code=400,
                detail=f"A fee structure named '{data.name}' already exists for Term {data.term} {data.year}, Level {data.level}. "
                       f"Please use a different name (e.g., 'Day Scholars', 'Boarding') or update the existing structure."
            )
        raise HTTPException(status_code=400, detail="Database constraint violation")
    
    return FeeStructureOut(
        **structure.__dict__,
        total_amount=Decimal('0.00'),
        item_count=0
    )

@router.get("/structures/", response_model=List[FeeStructureOut])
async def list_fee_structures(
    ctx: dict = Depends(require_school),
    db: Session = Depends(get_db),
    year: Optional[int] = None,
    term: Optional[int] = None,
    level: Optional[str] = None,
    hide_empty: bool = Query(False, description="Hide structures with 0 items")
):
    """List all fee structures with optional filters"""
    school_id = UUID(ctx["school_id"])
    
    query = select(FeeStructure).where(FeeStructure.school_id == school_id)
    
    if year:
        query = query.where(FeeStructure.year == year)
    if term:
        query = query.where(FeeStructure.term == term)
    if level:
        query = query.where(FeeStructure.level == level)
    
    structures = db.execute(query.order_by(FeeStructure.year.desc(), FeeStructure.term.desc())).scalars().all()
    
    result = []
    for s in structures:
        items = db.execute(
            select(FeeItem).where(FeeItem.fee_structure_id == s.id)
        ).scalars().all()
        
        total = sum(item.amount for item in items)
        item_count = len(items)
        
        if hide_empty and item_count == 0:
            continue
        
        result.append(FeeStructureOut(
            **s.__dict__, 
            total_amount=total,
            item_count=item_count
        ))
    
    return result

@router.get("/structures/search", response_model=List[FeeStructureOut])
async def search_fee_structures(
    ctx: dict = Depends(require_school),
    db: Session = Depends(get_db),
    query_text: str = Query(..., description="Search term for structure name"),
    year: Optional[int] = None,
    term: Optional[int] = None
):
    """Search fee structures by name with fuzzy matching"""
    school_id = UUID(ctx["school_id"])
    
    search_query = select(FeeStructure).where(
        FeeStructure.school_id == school_id,
        func.lower(FeeStructure.name).like(f"%{query_text.lower()}%")
    )
    
    if year:
        search_query = search_query.where(FeeStructure.year == year)
    if term:
        search_query = search_query.where(FeeStructure.term == term)
    
    structures = db.execute(
        search_query.order_by(FeeStructure.year.desc(), FeeStructure.term.desc())
    ).scalars().all()
    
    result = []
    for s in structures:
        items = db.execute(
            select(FeeItem).where(FeeItem.fee_structure_id == s.id)
        ).scalars().all()
        
        total = sum(item.amount for item in items)
        item_count = len(items)
        
        result.append(FeeStructureOut(
            **s.__dict__, 
            total_amount=total,
            item_count=item_count
        ))
    
    return result

@router.get("/structures/{structure_id}", response_model=FeeStructureDetail)
async def get_fee_structure(
    structure_id: UUID,
    ctx: dict = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Get detailed fee structure with items"""
    school_id = UUID(ctx["school_id"])
    
    structure = db.execute(
        select(FeeStructure).where(
            FeeStructure.id == structure_id,
            FeeStructure.school_id == school_id
        )
    ).scalar_one_or_none()
    
    if not structure:
        raise HTTPException(status_code=404, detail="Fee structure not found")
    
    items = db.execute(
        select(FeeItem).where(FeeItem.fee_structure_id == structure_id)
    ).scalars().all()
    
    total = sum(item.amount for item in items)
    
    return FeeStructureDetail(
        **structure.__dict__,
        total_amount=total,
        items=[FeeItemOut.model_validate(item) for item in items]
    )

@router.post("/structures/{structure_id}/items/", response_model=FeeItemOut)
async def add_fee_item(
    structure_id: UUID,
    data: FeeItemCreate,
    ctx: dict = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Add fee item to structure"""
    school_id = UUID(ctx["school_id"])
    
    structure = db.execute(
        select(FeeStructure).where(
            FeeStructure.id == structure_id,
            FeeStructure.school_id == school_id
        )
    ).scalar_one_or_none()
    
    if not structure:
        raise HTTPException(status_code=404, detail="Fee structure not found")
    
    if structure.is_published:
        raise HTTPException(status_code=400, detail="Cannot modify published structure")
    
    item = FeeItem(
        school_id=school_id,
        fee_structure_id=structure_id,
        **data.model_dump()
    )
    
    db.add(item)
    db.commit()
    db.refresh(item)
    
    return FeeItemOut.model_validate(item)

@router.put("/structures/{structure_id}", response_model=FeeStructureOut)
async def update_fee_structure(
    structure_id: UUID,
    is_default: Optional[bool] = None,
    is_published: Optional[bool] = None,
    ctx: dict = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Update fee structure settings"""
    school_id = UUID(ctx["school_id"])
    
    structure = db.execute(
        select(FeeStructure).where(
            FeeStructure.id == structure_id,
            FeeStructure.school_id == school_id
        )
    ).scalar_one_or_none()
    
    if not structure:
        raise HTTPException(status_code=404, detail="Fee structure not found")
    
    if is_default is not None and is_default:
        for existing in db.execute(
            select(FeeStructure).where(
                FeeStructure.school_id == school_id,
                FeeStructure.term == structure.term,
                FeeStructure.year == structure.year,
                FeeStructure.is_default == True,
                FeeStructure.id != structure_id
            )
        ).scalars():
            existing.is_default = False
        
        structure.is_default = True
    
    if is_published is not None:
        structure.is_published = is_published
    
    db.commit()
    db.refresh(structure)
    
    items = db.execute(
        select(FeeItem).where(FeeItem.fee_structure_id == structure_id)
    ).scalars().all()
    
    total = sum(item.amount for item in items)
    item_count = len(items)
    
    return FeeStructureOut(
        **structure.__dict__, 
        total_amount=total,
        item_count=item_count
    )

@router.delete("/structures/{structure_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fee_structure(
    structure_id: UUID,
    ctx: dict = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Delete fee structure if no invoices exist"""
    from app.models.payment import Invoice
    
    school_id = UUID(ctx["school_id"])
    
    structure = db.execute(
        select(FeeStructure).where(
            FeeStructure.id == structure_id,
            FeeStructure.school_id == school_id
        )
    ).scalar_one_or_none()
    
    if not structure:
        raise HTTPException(status_code=404, detail="Fee structure not found")
    
    invoice_count = db.execute(
        select(func.count(Invoice.id)).where(
            Invoice.school_id == school_id,
            Invoice.term == structure.term,
            Invoice.year == structure.year
        )
    ).scalar()
    
    if invoice_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete structure: {invoice_count} invoices exist for this term/year"
        )
    
    db.delete(structure)
    db.commit()

@router.put("/structures/{structure_id}/items/{item_id}", response_model=FeeItemOut)
async def update_fee_item(
    structure_id: UUID,
    item_id: UUID,
    data: FeeItemCreate,
    ctx: dict = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Update an existing fee item"""
    school_id = UUID(ctx["school_id"])
    
    structure = db.execute(
        select(FeeStructure).where(
            FeeStructure.id == structure_id,
            FeeStructure.school_id == school_id
        )
    ).scalar_one_or_none()
    
    if not structure:
        raise HTTPException(status_code=404, detail="Fee structure not found")
    
    if structure.is_published:
        raise HTTPException(status_code=400, detail="Cannot modify published structure")
    
    item = db.execute(
        select(FeeItem).where(
            FeeItem.id == item_id,
            FeeItem.fee_structure_id == structure_id,
            FeeItem.school_id == school_id
        )
    ).scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="Fee item not found")
    
    for field, value in data.model_dump().items():
        setattr(item, field, value)
    
    db.commit()
    db.refresh(item)
    
    return FeeItemOut.model_validate(item)

@router.get("/structures/{structure_id}/items/by-name/{item_name}", response_model=FeeItemOut)
async def get_fee_item_by_name(
    structure_id: UUID,
    item_name: str,
    ctx: dict = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Get fee item by name for update operations"""
    school_id = UUID(ctx["school_id"])
    
    item = db.execute(
        select(FeeItem).where(
            FeeItem.fee_structure_id == structure_id,
            FeeItem.school_id == school_id,
            func.lower(FeeItem.item_name) == item_name.lower()
        )
    ).scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="Fee item not found")
    
    return FeeItemOut.model_validate(item)

@router.delete("/structures/{structure_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fee_item(
    structure_id: UUID,
    item_id: UUID,
    ctx: dict = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Delete a specific fee item"""
    school_id = UUID(ctx["school_id"])
    
    structure = db.execute(
        select(FeeStructure).where(
            FeeStructure.id == structure_id,
            FeeStructure.school_id == school_id
        )
    ).scalar_one_or_none()
    
    if not structure:
        raise HTTPException(status_code=404, detail="Fee structure not found")
    
    if structure.is_published:
        raise HTTPException(status_code=400, detail="Cannot delete items from published structure")
    
    item = db.execute(
        select(FeeItem).where(
            FeeItem.id == item_id,
            FeeItem.fee_structure_id == structure_id,
            FeeItem.school_id == school_id
        )
    ).scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="Fee item not found")
    
    db.delete(item)
    db.commit()

@router.delete("/structures/{structure_id}/items", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_fee_items(
    structure_id: UUID,
    ctx: dict = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Delete all fee items from a structure"""
    school_id = UUID(ctx["school_id"])
    
    structure = db.execute(
        select(FeeStructure).where(
            FeeStructure.id == structure_id,
            FeeStructure.school_id == school_id
        )
    ).scalar_one_or_none()
    
    if not structure:
        raise HTTPException(status_code=404, detail="Fee structure not found")
    
    if structure.is_published:
        raise HTTPException(status_code=400, detail="Cannot delete items from published structure")
    
    items = db.execute(
        select(FeeItem).where(
            FeeItem.fee_structure_id == structure_id,
            FeeItem.school_id == school_id
        )
    ).scalars().all()
    
    for item in items:
        db.delete(item)
    
    db.commit()