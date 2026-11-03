import re
from datetime import date, datetime
from typing import List, Optional
from enum import Enum
from fastapi import FastAPI, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field, EmailStr, validator
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, DateTime, ForeignKey, Enum as SQLEnum, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship

# =====================================================================
# 1. DATABASE CONFIGURATION & RELATIONSHIPS (Question 4)
# =====================================================================
DATABASE_URL = "sqlite:///./employee_management.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class EmploymentStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ON_LEAVE = "on_leave"
    TERMINATED = "terminated"

class DepartmentDB(Base):
    __tablename__ = "departments"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # One-to-many relationship: One department can have multiple employees
    employees = relationship("EmployeeDB", back_populates="department")

class EmployeeDB(Base):
    __tablename__ = "employees"
    
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String, unique=True, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    phone = Column(String, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    designation = Column(String, nullable=False)
    salary = Column(Float, nullable=False)
    joining_date = Column(Date, nullable=False)
    employment_status = Column(SQLEnum(EmploymentStatus), default=EmploymentStatus.ACTIVE, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship back to department
    department = relationship("DepartmentDB", back_populates="employees")

# Create tables
Base.metadata.create_all(bind=engine)

# Add columns introduced after an existing SQLite database was created.
with engine.begin() as connection:
    employee_columns = {
        column["name"] for column in inspect(connection).get_columns("employees")
    }
    if "salary" not in employee_columns:
        connection.execute(
            text(
                "ALTER TABLE employees "
                "ADD COLUMN salary FLOAT NOT NULL DEFAULT 0.0"
            )
        )

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =====================================================================
# 2. VALIDATION SCHEMAS (Question 6)
# =====================================================================
class DepartmentCreate(BaseModel):
    name: str = Field(..., min_length=1)
    description: Optional[str] = None

    @validator('name')
    def name_must_not_be_empty(cls, v):
        if not v.strip():
            raise ValueError('Department name cannot be empty')
        return v.strip()

class DepartmentResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    created_at: datetime
    class Config:
        orm_mode = True

class EmployeeCreate(BaseModel):
    employee_id: str
    first_name: str = Field(..., min_length=2, max_length=50)
    last_name: str = Field(..., min_length=2, max_length=50)
    email: EmailStr
    phone: str
    department_id: int
    designation: str
    salary: float = Field(..., ge=0) # Must be non-negative
    joining_date: date
    employment_status: EmploymentStatus = EmploymentStatus.ACTIVE

class EmployeeUpdate(BaseModel):
    employee_id: Optional[str] = None
    first_name: Optional[str] = Field(None, min_length=2, max_length=50)
    last_name: Optional[str] = Field(None, min_length=2, max_length=50)
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    department_id: Optional[int] = None
    designation: Optional[str] = None
    salary: Optional[float] = Field(None, ge=0)
    joining_date: Optional[date] = None
    employment_status: Optional[EmploymentStatus] = None

class StatusUpdate(BaseModel):
    employment_status: EmploymentStatus

class EmployeeResponse(BaseModel):
    id: int
    employee_id: str
    first_name: str
    last_name: str
    email: str
    phone: str
    department_id: int
    designation: str
    salary: float
    joining_date: date
    employment_status: EmploymentStatus
    created_at: datetime
    updated_at: datetime
    class Config:
        orm_mode = True


# =====================================================================
# 3. REST API DEVELOPMENT (Question 5)
# =====================================================================
app = FastAPI(title="Employee Management API")

# --- Department APIs ---

@app.post("/api/departments", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
def create_department(dept: DepartmentCreate, db: Session = Depends(get_db)):
    # Prevent duplicate department names
    existing = db.query(DepartmentDB).filter(DepartmentDB.name == dept.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Department name already exists")
    
    db_dept = DepartmentDB(**dept.dict())
    db.add(db_dept)
    db.commit()
    db.refresh(db_dept)
    return db_dept

@app.get("/api/departments", response_model=List[DepartmentResponse])
def get_all_departments(db: Session = Depends(get_db)):
    return db.query(DepartmentDB).all()

@app.get("/api/departments/{id}", response_model=DepartmentResponse)
def get_department_by_id(id: int, db: Session = Depends(get_db)):
    dept = db.query(DepartmentDB).filter(DepartmentDB.id == id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    return dept

@app.put("/api/departments/{id}", response_model=DepartmentResponse)
def update_department(id: int, dept_data: DepartmentCreate, db: Session = Depends(get_db)):
    dept = db.query(DepartmentDB).filter(DepartmentDB.id == id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    
    # Prevent duplicate name with other departments
    existing = db.query(DepartmentDB).filter(DepartmentDB.name == dept_data.name, DepartmentDB.id != id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Department name already exists")
    
    dept.name = dept_data.name
    dept.description = dept_data.description
    db.commit()
    db.refresh(dept)
    return dept

@app.delete("/api/departments/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_department(id: int, db: Session = Depends(get_db)):
    dept = db.query(DepartmentDB).filter(DepartmentDB.id == id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    
    # Prevent deletion if department has assigned employees
    if len(dept.employees) > 0:
        raise HTTPException(status_code=400, detail="Cannot delete department with assigned employees")
    
    db.delete(dept)
    db.commit()
    return

@app.get("/api/departments/{id}/employees", response_model=List[EmployeeResponse])
def get_department_employees(id: int, db: Session = Depends(get_db)):
    dept = db.query(DepartmentDB).filter(DepartmentDB.id == id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    return dept.employees


# --- Employee APIs ---

@app.post("/api/employees", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
def create_employee(emp: EmployeeCreate, db: Session = Depends(get_db)):
    # Validate unique employee_id
    if db.query(EmployeeDB).filter(EmployeeDB.employee_id == emp.employee_id).first():
        raise HTTPException(status_code=409, detail="Employee ID already exists")
    
    # Validate unique email
    if db.query(EmployeeDB).filter(EmployeeDB.email == emp.email).first():
        raise HTTPException(status_code=409, detail="Email already exists")
    
    # Validate department exists
    if not db.query(DepartmentDB).filter(DepartmentDB.id == emp.department_id).first():
        raise HTTPException(status_code=422, detail="Assigned department does not exist")
        
    db_emp = EmployeeDB(**emp.dict())
    db.add(db_emp)
    db.commit()
    db.refresh(db_emp)
    return db_emp

@app.get("/api/employees", response_model=List[EmployeeResponse])
def get_all_employees(
    name: Optional[str] = Query(None, description="Search by first or last name"),
    department_id: Optional[int] = Query(None, description="Filter by department ID"),
    status: Optional[EmploymentStatus] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db)
):
    query = db.query(EmployeeDB)
    
    # Question 2 Search and Filtering requirements
    if name:
        query = query.filter((EmployeeDB.first_name.contains(name)) | (EmployeeDB.last_name.contains(name)))
    if department_id:
        query = query.filter(EmployeeDB.department_id == department_id)
    if status:
        query = query.filter(EmployeeDB.employment_status == status)
        
    return query.all()

@app.get("/api/employees/{id}", response_model=EmployeeResponse)
def get_employee_by_id(id: int, db: Session = Depends(get_db)):
    emp = db.query(EmployeeDB).filter(EmployeeDB.id == id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return emp

@app.put("/api/employees/{id}", response_model=EmployeeResponse)
def update_employee_full(id: int, emp_data: EmployeeCreate, db: Session = Depends(get_db)):
    emp = db.query(EmployeeDB).filter(EmployeeDB.id == id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Check unique constraints ignoring the employee being updated.
    if db.query(EmployeeDB).filter(
        EmployeeDB.employee_id == emp_data.employee_id,
        EmployeeDB.id != id
    ).first():
        raise HTTPException(status_code=409, detail="Employee ID already exists")

    if db.query(EmployeeDB).filter(
        EmployeeDB.email == emp_data.email,
        EmployeeDB.id != id
    ).first():
        raise HTTPException(status_code=409, detail="Email already exists")

    if not db.query(DepartmentDB).filter(
        DepartmentDB.id == emp_data.department_id
    ).first():
        raise HTTPException(status_code=422, detail="Assigned department does not exist")

    for field, value in emp_data.dict().items():
        setattr(emp, field, value)

    db.commit()
    db.refresh(emp)
    return emp

@app.delete("/api/employees/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_employee(id: int, db: Session = Depends(get_db)):
    emp = db.query(EmployeeDB).filter(EmployeeDB.id == id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    db.delete(emp)
    db.commit()
    return