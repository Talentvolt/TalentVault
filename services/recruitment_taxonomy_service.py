import re
import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from django.db.models import Q
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Stopwords & generic modifier tokens that must not dominate relevance
GENERIC_ROLE_MODIFIERS = {
    'senior', 'junior', 'lead', 'manager', 'associate', 'director', 'intern', 'staff',
    'principal', 'vp', 'head', 'executive', 'assistant', 'officer', 'specialist',
    'trainee', 'consultant', 'coordinator', 'analyst', 'engineer', 'developer',
    'technician', 'expert', 'representative', 'supervisor', 'agent', 'administrator'
}

# Multi-Domain Base Seed Taxonomy for dynamic DB initialization
SEED_TAXONOMY_DOMAINS = [
    # 1. SALES & BUSINESS DEVELOPMENT
    {
        "domain": "Sales",
        "roles": [
            {
                "name": "Sales Manager",
                "canonical": "Sales Manager",
                "department": "Sales",
                "industry": "Multi-Industry",
                "seniority": "MANAGER",
                "aliases": ["Sales Mgr", "Sales Lead", "Manager Sales", "Sales Head"],
                "related_roles": [
                    ("Area Sales Manager", "SENIORITY_VARIANT", 0.95),
                    ("Regional Sales Manager", "SENIORITY_VARIANT", 0.93),
                    ("Territory Sales Manager", "SENIORITY_VARIANT", 0.92),
                    ("Zonal Sales Manager", "SENIORITY_VARIANT", 0.90),
                    ("Channel Sales Manager", "RELATED_ROLE", 0.92),
                    ("Corporate Sales Manager", "RELATED_ROLE", 0.90),
                    ("Enterprise Sales Manager", "RELATED_ROLE", 0.90),
                    ("B2B Sales Manager", "RELATED_ROLE", 0.92),
                    ("B2C Sales Manager", "RELATED_ROLE", 0.88),
                    ("Inside Sales Manager", "RELATED_ROLE", 0.86),
                    ("Business Development Manager", "FUNCTIONAL_EQUIVALENT", 0.90),
                    ("Key Account Manager", "ADJACENT_ROLE", 0.85),
                    ("Relationship Manager", "ADJACENT_ROLE", 0.80),
                    ("Sales Executive", "CHILD_ROLE", 0.78),
                    ("Area Sales Executive", "CHILD_ROLE", 0.76),
                ],
                "skills": [
                    ("Sales", "PRIMARY_SKILL", 0.98),
                    ("B2B Sales", "PRIMARY_SKILL", 0.95),
                    ("B2C Sales", "SECONDARY_SKILL", 0.88),
                    ("Channel Sales", "PRIMARY_SKILL", 0.92),
                    ("Lead Generation", "PRIMARY_SKILL", 0.90),
                    ("CRM", "TOOL", 0.92),
                    ("Salesforce", "TOOL", 0.88),
                    ("Client Relationship Management", "PRIMARY_SKILL", 0.90),
                    ("Negotiation", "PRIMARY_SKILL", 0.92),
                    ("Business Development", "PRIMARY_SKILL", 0.90),
                    ("Team Management", "SECONDARY_SKILL", 0.88),
                    ("Direct Sales", "SECONDARY_SKILL", 0.85),
                    ("Territory Management", "DOMAIN_SKILL", 0.88),
                    ("Key Account Management", "DOMAIN_SKILL", 0.86),
                    ("Cold Calling", "SUPPORTING_SKILL", 0.80),
                ]
            },
            {
                "name": "Area Sales Manager",
                "canonical": "Area Sales Manager",
                "department": "Sales",
                "industry": "Multi-Industry",
                "seniority": "MANAGER",
                "aliases": ["ASM", "Area Sales Mgr", "Area Manager Sales"],
                "related_roles": [
                    ("Sales Manager", "PARENT_ROLE", 0.95),
                    ("Regional Sales Manager", "PARENT_ROLE", 0.90),
                    ("Territory Sales Manager", "RELATED_ROLE", 0.92),
                    ("Area Sales Executive", "CHILD_ROLE", 0.85),
                    ("Channel Sales Manager", "RELATED_ROLE", 0.88),
                    ("Business Development Manager", "FUNCTIONAL_EQUIVALENT", 0.85),
                ],
                "skills": [
                    ("Area Sales", "PRIMARY_SKILL", 0.98),
                    ("Channel Sales", "PRIMARY_SKILL", 0.95),
                    ("Distributor Management", "PRIMARY_SKILL", 0.95),
                    ("Dealer Network", "PRIMARY_SKILL", 0.92),
                    ("Sales Management", "PRIMARY_SKILL", 0.92),
                    ("Territory Sales", "PRIMARY_SKILL", 0.90),
                    ("CRM", "TOOL", 0.88),
                    ("Team Handling", "SECONDARY_SKILL", 0.85),
                ]
            },
            {
                "name": "Sales Executive",
                "canonical": "Sales Executive",
                "department": "Sales",
                "industry": "Multi-Industry",
                "seniority": "JUNIOR",
                "aliases": ["Sales Exec", "Sales Officer", "Field Sales Executive", "Business Development Executive", "BDE"],
                "related_roles": [
                    ("Area Sales Executive", "SENIORITY_VARIANT", 0.92),
                    ("Sales Officer", "FUNCTIONAL_EQUIVALENT", 0.95),
                    ("Business Development Executive", "FUNCTIONAL_EQUIVALENT", 0.92),
                    ("Sales Manager", "PARENT_ROLE", 0.80),
                    ("Inside Sales Executive", "RELATED_ROLE", 0.88),
                ],
                "skills": [
                    ("Sales", "PRIMARY_SKILL", 0.95),
                    ("Lead Generation", "PRIMARY_SKILL", 0.92),
                    ("Cold Calling", "PRIMARY_SKILL", 0.90),
                    ("Customer Relationship", "PRIMARY_SKILL", 0.88),
                    ("Client Acquisition", "PRIMARY_SKILL", 0.85),
                    ("Field Sales", "DOMAIN_SKILL", 0.85),
                    ("CRM", "TOOL", 0.80),
                ]
            },
            {
                "name": "Business Development Manager",
                "canonical": "Business Development Manager",
                "department": "Sales",
                "industry": "Multi-Industry",
                "seniority": "MANAGER",
                "aliases": ["BDM", "BD Manager", "Manager Business Development"],
                "related_roles": [
                    ("Sales Manager", "FUNCTIONAL_EQUIVALENT", 0.92),
                    ("Key Account Manager", "RELATED_ROLE", 0.88),
                    ("Corporate Sales Manager", "RELATED_ROLE", 0.88),
                    ("Business Development Executive", "CHILD_ROLE", 0.82),
                ],
                "skills": [
                    ("Business Development", "PRIMARY_SKILL", 0.98),
                    ("B2B Sales", "PRIMARY_SKILL", 0.95),
                    ("Client Acquisition", "PRIMARY_SKILL", 0.92),
                    ("Market Research", "SECONDARY_SKILL", 0.85),
                    ("Strategic Partnerships", "PRIMARY_SKILL", 0.88),
                    ("Negotiation", "PRIMARY_SKILL", 0.90),
                    ("Lead Generation", "PRIMARY_SKILL", 0.90),
                    ("CRM", "TOOL", 0.85),
                ]
            },
        ]
    },

    # 2. IT & SOFTWARE DEVELOPMENT
    {
        "domain": "IT",
        "roles": [
            {
                "name": "Full Stack Developer",
                "canonical": "Full Stack Developer",
                "department": "Engineering",
                "industry": "Information Technology",
                "seniority": "MID",
                "aliases": ["Full Stack Engineer", "Fullstack Developer", "Full-Stack Dev", "Fullstack Software Engineer"],
                "related_roles": [
                    ("Frontend Developer", "RELATED_ROLE", 0.88),
                    ("Backend Developer", "RELATED_ROLE", 0.88),
                    ("Software Engineer", "PARENT_ROLE", 0.90),
                    ("Senior Full Stack Developer", "SENIORITY_VARIANT", 0.95),
                    ("Lead Full Stack Engineer", "SENIORITY_VARIANT", 0.90),
                    ("Web Developer", "RELATED_ROLE", 0.80),
                ],
                "skills": [
                    ("JavaScript", "PRIMARY_SKILL", 0.95),
                    ("TypeScript", "PRIMARY_SKILL", 0.90),
                    ("React.js", "PRIMARY_SKILL", 0.92),
                    ("Node.js", "PRIMARY_SKILL", 0.92),
                    ("Python", "SECONDARY_SKILL", 0.85),
                    ("Django", "SECONDARY_SKILL", 0.85),
                    ("HTML5", "SUPPORTING_SKILL", 0.88),
                    ("CSS3", "SUPPORTING_SKILL", 0.88),
                    ("SQL", "PRIMARY_SKILL", 0.90),
                    ("PostgreSQL", "TOOL", 0.88),
                    ("MongoDB", "TOOL", 0.86),
                    ("REST API", "PRIMARY_SKILL", 0.92),
                    ("Git", "TOOL", 0.88),
                    ("Docker", "TOOL", 0.82),
                    ("AWS", "TOOL", 0.80),
                ]
            },
            {
                "name": "Python Developer",
                "canonical": "Python Developer",
                "department": "Engineering",
                "industry": "Information Technology",
                "seniority": "MID",
                "aliases": ["Python Engineer", "Python Backend Developer", "Python Programmer", "Django Developer"],
                "related_roles": [
                    ("Backend Developer", "RELATED_ROLE", 0.90),
                    ("Django Developer", "SENIORITY_VARIANT", 0.95),
                    ("Flask Developer", "SENIORITY_VARIANT", 0.92),
                    ("Data Engineer", "ADJACENT_ROLE", 0.80),
                    ("Full Stack Developer", "RELATED_ROLE", 0.85),
                    ("Senior Python Developer", "SENIORITY_VARIANT", 0.95),
                ],
                "skills": [
                    ("Python", "PRIMARY_SKILL", 0.99),
                    ("Django", "PRIMARY_SKILL", 0.95),
                    ("FastAPI", "PRIMARY_SKILL", 0.92),
                    ("Flask", "PRIMARY_SKILL", 0.90),
                    ("REST API", "PRIMARY_SKILL", 0.92),
                    ("PostgreSQL", "TOOL", 0.90),
                    ("SQL", "PRIMARY_SKILL", 0.90),
                    ("Celery", "TOOL", 0.85),
                    ("Redis", "TOOL", 0.85),
                    ("Docker", "TOOL", 0.85),
                    ("Pandas", "SECONDARY_SKILL", 0.80),
                    ("NumPy", "SECONDARY_SKILL", 0.80),
                    ("Git", "TOOL", 0.85),
                ]
            },
            {
                "name": "Java Developer",
                "canonical": "Java Developer",
                "department": "Engineering",
                "industry": "Information Technology",
                "seniority": "MID",
                "aliases": ["Java Engineer", "Java Backend Developer", "Core Java Developer", "Spring Boot Developer"],
                "related_roles": [
                    ("Backend Developer", "RELATED_ROLE", 0.90),
                    ("Spring Boot Developer", "SENIORITY_VARIANT", 0.95),
                    ("Senior Java Developer", "SENIORITY_VARIANT", 0.95),
                    ("Software Engineer", "PARENT_ROLE", 0.88),
                ],
                "skills": [
                    ("Java", "PRIMARY_SKILL", 0.99),
                    ("Spring Boot", "PRIMARY_SKILL", 0.96),
                    ("Hibernate", "PRIMARY_SKILL", 0.90),
                    ("Microservices", "PRIMARY_SKILL", 0.92),
                    ("REST API", "PRIMARY_SKILL", 0.90),
                    ("SQL", "PRIMARY_SKILL", 0.90),
                    ("MySQL", "TOOL", 0.88),
                    ("Maven", "TOOL", 0.85),
                    ("Kafka", "TOOL", 0.82),
                    ("Docker", "TOOL", 0.82),
                ]
            },
            {
                "name": "Data Analyst",
                "canonical": "Data Analyst",
                "department": "Analytics",
                "industry": "Information Technology",
                "seniority": "MID",
                "aliases": ["Business Data Analyst", "Junior Data Analyst", "Senior Data Analyst", "BI Analyst"],
                "related_roles": [
                    ("Business Analyst", "RELATED_ROLE", 0.85),
                    ("Data Scientist", "ADJACENT_ROLE", 0.85),
                    ("BI Developer", "FUNCTIONAL_EQUIVALENT", 0.88),
                ],
                "skills": [
                    ("SQL", "PRIMARY_SKILL", 0.98),
                    ("Python", "PRIMARY_SKILL", 0.90),
                    ("Power BI", "TOOL", 0.95),
                    ("Tableau", "TOOL", 0.92),
                    ("Excel", "PRIMARY_SKILL", 0.95),
                    ("Data Visualization", "PRIMARY_SKILL", 0.92),
                    ("Statistical Analysis", "PRIMARY_SKILL", 0.88),
                    ("Pandas", "TOOL", 0.88),
                ]
            },
        ]
    },

    # 3. HR & RECRUITMENT
    {
        "domain": "Human Resources",
        "roles": [
            {
                "name": "HR Manager",
                "canonical": "HR Manager",
                "department": "Human Resources",
                "industry": "Multi-Industry",
                "seniority": "MANAGER",
                "aliases": ["Human Resources Manager", "HR Lead", "Head of HR", "HRBP"],
                "related_roles": [
                    ("HR Generalist", "RELATED_ROLE", 0.90),
                    ("Recruiter", "RELATED_ROLE", 0.85),
                    ("Talent Acquisition Manager", "FUNCTIONAL_EQUIVALENT", 0.92),
                    ("HRBP", "FUNCTIONAL_EQUIVALENT", 0.90),
                    ("Senior HR Manager", "SENIORITY_VARIANT", 0.95),
                ],
                "skills": [
                    ("Human Resources", "PRIMARY_SKILL", 0.98),
                    ("Talent Acquisition", "PRIMARY_SKILL", 0.92),
                    ("Employee Relations", "PRIMARY_SKILL", 0.95),
                    ("Performance Management", "PRIMARY_SKILL", 0.90),
                    ("HR Policies", "PRIMARY_SKILL", 0.90),
                    ("Payroll Management", "SECONDARY_SKILL", 0.85),
                    ("Statutory Compliance", "PRIMARY_SKILL", 0.88),
                    ("Onboarding", "PRIMARY_SKILL", 0.88),
                    ("HRIS", "TOOL", 0.85),
                ]
            },
            {
                "name": "Recruiter",
                "canonical": "Recruiter",
                "department": "Human Resources",
                "industry": "Multi-Industry",
                "seniority": "MID",
                "aliases": ["Talent Acquisition Specialist", "Technical Recruiter", "HR Recruiter", "IT Recruiter", "Staffing Specialist"],
                "related_roles": [
                    ("Talent Acquisition Specialist", "FUNCTIONAL_EQUIVALENT", 0.96),
                    ("Technical Recruiter", "SENIORITY_VARIANT", 0.92),
                    ("Senior Recruiter", "SENIORITY_VARIANT", 0.95),
                    ("HR Executive", "RELATED_ROLE", 0.85),
                    ("HR Manager", "PARENT_ROLE", 0.82),
                ],
                "skills": [
                    ("Recruitment", "PRIMARY_SKILL", 0.98),
                    ("Sourcing", "PRIMARY_SKILL", 0.96),
                    ("Screening", "PRIMARY_SKILL", 0.95),
                    ("Interviewing", "PRIMARY_SKILL", 0.92),
                    ("Portal Sourcing (Naukri/LinkedIn)", "TOOL", 0.94),
                    ("Salary Negotiation", "PRIMARY_SKILL", 0.88),
                    ("Headhunting", "PRIMARY_SKILL", 0.88),
                    ("Applicant Tracking System (ATS)", "TOOL", 0.90),
                ]
            },
        ]
    },

    # 4. FINANCE & ACCOUNTING
    {
        "domain": "Finance",
        "roles": [
            {
                "name": "Accountant",
                "canonical": "Accountant",
                "department": "Finance",
                "industry": "Multi-Industry",
                "seniority": "MID",
                "aliases": ["Senior Accountant", "General Accountant", "Accounts Executive", "Staff Accountant", "Bookkeeper"],
                "related_roles": [
                    ("Accounts Executive", "FUNCTIONAL_EQUIVALENT", 0.95),
                    ("Senior Accountant", "SENIORITY_VARIANT", 0.95),
                    ("Finance Manager", "PARENT_ROLE", 0.85),
                    ("Chartered Accountant", "ADJACENT_ROLE", 0.88),
                    ("Tax Consultant", "RELATED_ROLE", 0.82),
                ],
                "skills": [
                    ("Accounting", "PRIMARY_SKILL", 0.99),
                    ("Bookkeeping", "PRIMARY_SKILL", 0.95),
                    ("GST", "PRIMARY_SKILL", 0.95),
                    ("TDS", "PRIMARY_SKILL", 0.92),
                    ("Tally ERP", "TOOL", 0.95),
                    ("Tally Prime", "TOOL", 0.94),
                    ("Excel", "TOOL", 0.95),
                    ("Bank Reconciliation", "PRIMARY_SKILL", 0.92),
                    ("Accounts Payable", "PRIMARY_SKILL", 0.90),
                    ("Accounts Receivable", "PRIMARY_SKILL", 0.90),
                    ("Financial Reporting", "PRIMARY_SKILL", 0.88),
                    ("Taxation", "PRIMARY_SKILL", 0.88),
                ]
            },
            {
                "name": "Finance Manager",
                "canonical": "Finance Manager",
                "department": "Finance",
                "industry": "Multi-Industry",
                "seniority": "MANAGER",
                "aliases": ["Manager Finance", "Head of Finance", "Financial Controller"],
                "related_roles": [
                    ("Accountant", "CHILD_ROLE", 0.85),
                    ("Financial Analyst", "RELATED_ROLE", 0.88),
                    ("Senior Finance Manager", "SENIORITY_VARIANT", 0.95),
                    ("Chartered Accountant", "ADJACENT_ROLE", 0.90),
                ],
                "skills": [
                    ("Financial Management", "PRIMARY_SKILL", 0.98),
                    ("Financial Planning & Analysis (FP&A)", "PRIMARY_SKILL", 0.95),
                    ("Budgeting & Forecasting", "PRIMARY_SKILL", 0.95),
                    ("Auditing", "PRIMARY_SKILL", 0.90),
                    ("Statutory Compliance", "PRIMARY_SKILL", 0.90),
                    ("Working Capital Management", "PRIMARY_SKILL", 0.88),
                    ("SAP FICO", "TOOL", 0.85),
                ]
            },
        ]
    },

    # 5. PHARMA & HEALTHCARE
    {
        "domain": "Healthcare",
        "roles": [
            {
                "name": "Medical Representative",
                "canonical": "Medical Representative",
                "department": "Sales",
                "industry": "Pharmaceutical",
                "seniority": "JUNIOR",
                "aliases": ["MR", "Pharma Rep", "Pharma Sales Representative", "Pharma Sales Executive", "Territory Business Executive (Pharma)", "Medical Sales Representative"],
                "related_roles": [
                    ("Area Business Manager (Pharma)", "PARENT_ROLE", 0.92),
                    ("Regional Sales Manager (Pharma)", "PARENT_ROLE", 0.88),
                    ("Pharma Sales Executive", "FUNCTIONAL_EQUIVALENT", 0.95),
                    ("Pharmacist", "RELATED_ROLE", 0.75),
                ],
                "skills": [
                    ("Pharma Sales", "PRIMARY_SKILL", 0.98),
                    ("Doctor Promotion", "PRIMARY_SKILL", 0.95),
                    ("Chemist Detailing", "PRIMARY_SKILL", 0.95),
                    ("Product Launch", "PRIMARY_SKILL", 0.88),
                    ("RCPA (Retail Chemist Prescription Audit)", "PRIMARY_SKILL", 0.92),
                    ("Territory Coverage", "PRIMARY_SKILL", 0.90),
                    ("Pharmaceutical Products", "DOMAIN_SKILL", 0.92),
                    ("Hospital Detailing", "PRIMARY_SKILL", 0.85),
                ]
            },
            {
                "name": "Pharmacist",
                "canonical": "Pharmacist",
                "department": "Pharmacy",
                "industry": "Healthcare",
                "seniority": "MID",
                "aliases": ["Hospital Pharmacist", "Retail Pharmacist", "Clinical Pharmacist", "Chemist"],
                "related_roles": [
                    ("Clinical Pharmacist", "SENIORITY_VARIANT", 0.95),
                    ("Pharmacy Manager", "PARENT_ROLE", 0.90),
                    ("Medical Representative", "RELATED_ROLE", 0.75),
                    ("Drug Safety Associate", "ADJACENT_ROLE", 0.80),
                ],
                "skills": [
                    ("Pharmacy Operations", "PRIMARY_SKILL", 0.98),
                    ("Prescription Dispensing", "PRIMARY_SKILL", 0.96),
                    ("Drug Interaction Knowledge", "PRIMARY_SKILL", 0.92),
                    ("Inventory Management", "PRIMARY_SKILL", 0.90),
                    ("Pharmacology", "PRIMARY_SKILL", 0.92),
                    ("B.Pharm / D.Pharm", "DOMAIN_SKILL", 0.95),
                    ("Patient Counseling", "SECONDARY_SKILL", 0.85),
                ]
            },
            {
                "name": "Staff Nurse",
                "canonical": "Nurse",
                "department": "Nursing",
                "industry": "Healthcare",
                "seniority": "MID",
                "aliases": ["Nurse", "Registered Nurse", "ICU Nurse", "Ward Nurse", "GNM Nurse", "BSc Nurse"],
                "related_roles": [
                    ("Nursing Supervisor", "PARENT_ROLE", 0.92),
                    ("ICU Nurse", "SENIORITY_VARIANT", 0.95),
                    ("OT Nurse", "SENIORITY_VARIANT", 0.92),
                ],
                "skills": [
                    ("Patient Care", "PRIMARY_SKILL", 0.98),
                    ("Medication Administration", "PRIMARY_SKILL", 0.95),
                    ("Vital Signs Monitoring", "PRIMARY_SKILL", 0.92),
                    ("ICU / Emergency Care", "DOMAIN_SKILL", 0.90),
                    ("Infection Control", "PRIMARY_SKILL", 0.88),
                    ("CPR / BLS", "CERTIFICATION", 0.90),
                ]
            },
        ]
    },

    # 6. AUTOMOBILE & MECHANICAL ENGINEERING
    {
        "domain": "Automobile",
        "roles": [
            {
                "name": "Vehicle Inspector",
                "canonical": "Vehicle Inspector",
                "department": "Inspection & Valuation",
                "industry": "Automotive",
                "seniority": "MID",
                "aliases": ["Car Inspector", "Automobile Inspector", "Automotive Inspector", "Vehicle Inspection Officer", "Car Inspection Executive", "Auto Inspection Engineer", "Motor Vehicle Inspector", "Vehicle Inspection Executive", "Car Inspection", "Vehicle Evaluator", "Used Car Evaluator"],
                "related_roles": [
                    ("Automobile Technician", "RELATED_ROLE", 0.88),
                    ("Service Advisor", "RELATED_ROLE", 0.85),
                    ("Workshop Supervisor", "PARENT_ROLE", 0.90),
                ],
                "skills": [
                    ("Vehicle Inspection", "PRIMARY_SKILL", 0.98),
                    ("Used Car Evaluation", "PRIMARY_SKILL", 0.96),
                    ("Vehicle Diagnostics", "PRIMARY_SKILL", 0.95),
                    ("Chassis & Engine Inspection", "PRIMARY_SKILL", 0.95),
                    ("OBD Scanning", "TOOL", 0.92),
                    ("Automobile Maintenance", "PRIMARY_SKILL", 0.90),
                ]
            },
            {
                "name": "Automobile Technician",
                "canonical": "Automobile Technician",
                "department": "Service",
                "industry": "Automotive",
                "seniority": "MID",
                "aliases": ["Auto Mechanic", "Vehicle Technician", "Service Technician", "Car Mechanic"],
                "related_roles": [
                    ("Service Advisor", "ADJACENT_ROLE", 0.88),
                    ("Workshop Supervisor", "PARENT_ROLE", 0.90),
                    ("Mechanical Engineer", "RELATED_ROLE", 0.78),
                    ("Diagnostic Technician", "SENIORITY_VARIANT", 0.92),
                ],
                "skills": [
                    ("Vehicle Diagnostics", "PRIMARY_SKILL", 0.98),
                    ("Engine Repair", "PRIMARY_SKILL", 0.95),
                    ("Brake & Suspension", "PRIMARY_SKILL", 0.92),
                    ("Automobile Maintenance", "PRIMARY_SKILL", 0.95),
                    ("OBD Scanning", "TOOL", 0.90),
                    ("Electrical Troubleshooting", "PRIMARY_SKILL", 0.88),
                    ("Wheel Alignment", "PRIMARY_SKILL", 0.85),
                ]
            },
            {
                "name": "Service Advisor",
                "canonical": "Service Advisor",
                "department": "Customer Service",
                "industry": "Automotive",
                "seniority": "MID",
                "aliases": ["Automobile Service Advisor", "Customer Service Advisor (Automotive)", "Workshop Advisor"],
                "related_roles": [
                    ("Automobile Technician", "ADJACENT_ROLE", 0.88),
                    ("Workshop Manager", "PARENT_ROLE", 0.90),
                    ("Floor Supervisor", "RELATED_ROLE", 0.85),
                ],
                "skills": [
                    ("Job Card Creation", "PRIMARY_SKILL", 0.95),
                    ("Customer Handling", "PRIMARY_SKILL", 0.95),
                    ("Vehicle Estimation", "PRIMARY_SKILL", 0.92),
                    ("Automobile Knowledge", "PRIMARY_SKILL", 0.90),
                    ("Service Sales", "SECONDARY_SKILL", 0.88),
                ]
            },
            {
                "name": "Mechanical Engineer",
                "canonical": "Mechanical Engineer",
                "department": "Engineering",
                "industry": "Manufacturing",
                "seniority": "MID",
                "aliases": ["Production Engineer", "Maintenance Engineer", "Design Engineer (Mechanical)"],
                "related_roles": [
                    ("Production Engineer", "RELATED_ROLE", 0.90),
                    ("Quality Engineer", "RELATED_ROLE", 0.88),
                    ("AutoCAD Designer", "RELATED_ROLE", 0.85),
                ],
                "skills": [
                    ("AutoCAD", "TOOL", 0.95),
                    ("SolidWorks", "TOOL", 0.92),
                    ("Manufacturing Processes", "PRIMARY_SKILL", 0.92),
                    ("Quality Control", "PRIMARY_SKILL", 0.88),
                    ("Preventive Maintenance", "PRIMARY_SKILL", 0.88),
                    ("P&ID", "SECONDARY_SKILL", 0.82),
                ]
            },
            {
                "name": "Civil Engineer",
                "canonical": "Civil Engineer",
                "department": "Engineering",
                "industry": "Construction",
                "seniority": "MID",
                "aliases": ["Site Engineer", "Civil Site Engineer", "Project Engineer (Civil)", "Structural Engineer"],
                "related_roles": [
                    ("Site Engineer", "FUNCTIONAL_EQUIVALENT", 0.95),
                    ("Structural Engineer", "SENIORITY_VARIANT", 0.92),
                    ("Billing Engineer", "RELATED_ROLE", 0.88),
                    ("Project Manager (Civil)", "PARENT_ROLE", 0.90),
                ],
                "skills": [
                    ("Site Supervision", "PRIMARY_SKILL", 0.98),
                    ("AutoCAD Civil", "TOOL", 0.95),
                    ("Quantity Estimation & Costing", "PRIMARY_SKILL", 0.92),
                    ("Concrete Technology", "PRIMARY_SKILL", 0.90),
                    ("Quality Assurance (Construction)", "PRIMARY_SKILL", 0.88),
                    ("Billing & Measurement", "PRIMARY_SKILL", 0.90),
                ]
            },
            {
                "name": "Electrical Engineer",
                "canonical": "Electrical Engineer",
                "department": "Engineering",
                "industry": "Engineering",
                "seniority": "MID",
                "aliases": ["Electrician", "Electrical Maintenance Engineer", "Power Engineer"],
                "related_roles": [
                    ("Electrician", "CHILD_ROLE", 0.85),
                    ("Maintenance Engineer", "RELATED_ROLE", 0.88),
                    ("Electronics Engineer", "ADJACENT_ROLE", 0.82),
                ],
                "skills": [
                    ("Electrical Maintenance", "PRIMARY_SKILL", 0.95),
                    ("PLC / SCADA", "TOOL", 0.90),
                    ("Switchgear & Transformers", "PRIMARY_SKILL", 0.92),
                    ("Circuit Design", "PRIMARY_SKILL", 0.88),
                    ("Single Line Diagram (SLD)", "PRIMARY_SKILL", 0.88),
                ]
            },
        ]
    },

    # 7. OPERATIONS, LOGISTICS & BPO
    {
        "domain": "Operations",
        "roles": [
            {
                "name": "Operations Manager",
                "canonical": "Operations Manager",
                "department": "Operations",
                "industry": "Multi-Industry",
                "seniority": "MANAGER",
                "aliases": ["Head of Operations", "Operations Lead", "Branch Operations Manager"],
                "related_roles": [
                    ("Supply Chain Manager", "RELATED_ROLE", 0.88),
                    ("Logistics Manager", "RELATED_ROLE", 0.88),
                    ("Branch Manager", "ADJACENT_ROLE", 0.85),
                ],
                "skills": [
                    ("Operations Management", "PRIMARY_SKILL", 0.98),
                    ("Process Optimization", "PRIMARY_SKILL", 0.92),
                    ("Team Leadership", "PRIMARY_SKILL", 0.92),
                    ("KPI Management", "PRIMARY_SKILL", 0.90),
                    ("Vendor Management", "PRIMARY_SKILL", 0.88),
                    ("SLA Adherence", "PRIMARY_SKILL", 0.88),
                ]
            },
            {
                "name": "Customer Support Executive",
                "canonical": "Customer Support Executive",
                "department": "Customer Support",
                "industry": "BPO / ITES",
                "seniority": "JUNIOR",
                "aliases": ["BPO Executive", "Customer Care Executive", "Telecaller", "Technical Support Representative", "Helpdesk Associate"],
                "related_roles": [
                    ("BPO Executive", "FUNCTIONAL_EQUIVALENT", 0.95),
                    ("Technical Support Specialist", "SENIORITY_VARIANT", 0.90),
                    ("Team Leader - BPO", "PARENT_ROLE", 0.85),
                ],
                "skills": [
                    ("Customer Service", "PRIMARY_SKILL", 0.98),
                    ("Voice / Non-Voice Support", "PRIMARY_SKILL", 0.95),
                    ("Inbound / Outbound Calling", "PRIMARY_SKILL", 0.92),
                    ("CRM / Ticketing (Zendesk/Freshdesk)", "TOOL", 0.90),
                    ("Communication Skills", "PRIMARY_SKILL", 0.95),
                    ("Complaint Resolution", "PRIMARY_SKILL", 0.90),
                ]
            },
        ]
    }
]


class RecruitmentTaxonomyService:
    """
    Universal Centralized Taxonomy & Semantic Matching Engine.
    Operates dynamically for ANY job title, skill, designation, domain, industry or keyword.
    """

    _IS_SEEDED = False

    @classmethod
    def ensure_taxonomy_seeded(cls):
        """
        Fast idempotent auto-seeder to populate base multi-domain taxonomy if DB is empty.
        """
        from apps.candidates.models import (
            TaxonomySkill, TaxonomyDesignation, RoleRelation, RoleSkillRelation
        )

        try:
            if TaxonomyDesignation.objects.filter(is_active=True).exists():
                return
        except Exception:
            return

        # Seed the multi-domain base entities
        for domain_data in SEED_TAXONOMY_DOMAINS:
            domain_name = domain_data["domain"]
            for r_data in domain_data.get("roles", []):
                role_obj, _ = TaxonomyDesignation.objects.get_or_create(
                    canonical_name=r_data["canonical"],
                    defaults={
                        "name": r_data["name"],
                        "normalized_name": r_data["canonical"].strip().lower(),
                        "department": r_data.get("department", ""),
                        "industry": r_data.get("industry", domain_name),
                        "seniority": r_data.get("seniority", "MID"),
                        "aliases": r_data.get("aliases", []),
                        "is_active": True,
                    }
                )

                # Connect Skills
                for sk_name, rel_type, weight in r_data.get("skills", []):
                    cat = "TOOL" if rel_type == "TOOL" else "TECHNICAL"
                    sk_obj, _ = TaxonomySkill.objects.get_or_create(
                        canonical_name=sk_name,
                        defaults={
                            "name": sk_name,
                            "normalized_name": sk_name.strip().lower(),
                            "category": cat,
                            "domain": domain_name,
                            "aliases": [],
                            "is_active": True
                        }
                    )
                    RoleSkillRelation.objects.get_or_create(
                        role=role_obj,
                        skill=sk_obj,
                        relation_type=rel_type,
                        defaults={"weight": weight}
                    )

        # Connect Role Relations (second pass after all roles are created)
        for domain_data in SEED_TAXONOMY_DOMAINS:
            for r_data in domain_data.get("roles", []):
                source_role = TaxonomyDesignation.objects.filter(canonical_name=r_data["canonical"]).first()
                if not source_role:
                    continue
                for target_name, rel_type, weight in r_data.get("related_roles", []):
                    target_role = TaxonomyDesignation.objects.filter(canonical_name=target_name).first()
                    if not target_role:
                        target_role, _ = TaxonomyDesignation.objects.get_or_create(
                            canonical_name=target_name,
                            defaults={
                                "name": target_name,
                                "normalized_name": target_name.strip().lower(),
                                "department": source_role.department,
                                "industry": source_role.industry,
                                "seniority": "MID",
                                "aliases": [],
                                "is_active": True
                            }
                        )
                    RoleRelation.objects.get_or_create(
                        source_role=source_role,
                        target_role=target_role,
                        relation_type=rel_type,
                        defaults={"weight": weight, "is_bidirectional": True}
                    )

        cls._IS_SEEDED = True

    @classmethod
    def normalize_term(cls, term: str) -> str:
        """
        Cleans and standardizes raw user/resume strings (removes punctuation, excess spaces).
        """
        if not term:
            return ""
        cleaned = re.sub(r'[\s_/\-]+', ' ', term.strip())
        cleaned = re.sub(r'[^\w\s\.\+\#]', '', cleaned)
        return cleaned.strip()

    @classmethod
    def find_canonical_designation(cls, query: str) -> Optional[Any]:
        """
        Looks up canonical TaxonomyDesignation by exact name, normalized name, or alias.
        """
        cls.ensure_taxonomy_seeded()
        if not query or not query.strip():
            return None

        from apps.candidates.models import TaxonomyDesignation

        q_clean = cls.normalize_term(query)
        q_lower = q_clean.lower()

        # 1. Exact canonical or normalized lookup
        exact = TaxonomyDesignation.objects.filter(
            Q(canonical_name__iexact=q_clean) | Q(normalized_name=q_lower),
            is_active=True
        ).first()
        if exact:
            return exact

        # 2. Alias lookup in JSONField
        for des in TaxonomyDesignation.objects.filter(is_active=True):
            if des.aliases:
                for a in des.aliases:
                    if a.strip().lower() == q_lower:
                        return des

        # 3. Substring / Prefix match
        sub = TaxonomyDesignation.objects.filter(
            Q(normalized_name__icontains=q_lower) | Q(canonical_name__icontains=q_clean),
            is_active=True
        ).first()
        return sub

    @classmethod
    def get_autocomplete_suggestions(cls, query: str, field_type: str = 'all', limit: int = 8) -> List[Dict[str, Any]]:
        """
        Ultra-fast autocomplete from universal taxonomy + candidate DB for typeahead.
        """
        cls.ensure_taxonomy_seeded()
        if not query or len(query.strip()) < 1:
            return []

        from apps.candidates.models import TaxonomyDesignation, TaxonomySkill

        q_clean = cls.normalize_term(query)
        q_lower = q_clean.lower()
        results: List[Dict[str, Any]] = []
        seen: Set[str] = set()

        # Search Designations
        if field_type in ['all', 'title', 'designation', 'role']:
            des_qs = TaxonomyDesignation.objects.filter(
                Q(normalized_name__icontains=q_lower) | Q(canonical_name__icontains=q_clean),
                is_active=True
            ).order_by('canonical_name')[:limit * 2]

            for des in des_qs:
                name = des.canonical_name
                if name in seen:
                    continue
                seen.add(name)
                rank = 1 if name.lower() == q_lower else (2 if name.lower().startswith(q_lower) else 3)
                results.append({
                    "value": name,
                    "title": name,
                    "subtitle": f"{des.department or des.industry or 'Role'} ({des.get_seniority_display()})",
                    "type": "designation",
                    "avatar": "D",
                    "rank": rank
                })

        # Search Skills
        if field_type in ['all', 'skill', 'skills', 'tool']:
            sk_qs = TaxonomySkill.objects.filter(
                Q(normalized_name__icontains=q_lower) | Q(canonical_name__icontains=q_clean),
                is_active=True
            ).order_by('canonical_name')[:limit * 2]

            for sk in sk_qs:
                name = sk.canonical_name
                if name in seen:
                    continue
                seen.add(name)
                rank = 1 if name.lower() == q_lower else (2 if name.lower().startswith(q_lower) else 3)
                results.append({
                    "value": name,
                    "title": name,
                    "subtitle": f"{sk.get_category_display()} • {sk.domain or 'General'}",
                    "type": "skill",
                    "avatar": "S",
                    "rank": rank
                })

        results.sort(key=lambda x: (x["rank"], len(x["value"]), x["value"]))
        return results[:limit]

    @classmethod
    def get_smart_suggestions(cls, query: str, active_tags: List[str] = None, limit: int = 12) -> Dict[str, Any]:
        """
        AI & Graph-Driven Suggested Keywords Engine.
        Returns relevant designations, seniority variants, aliases, related roles, skills,
        and domain terms with confidence scores.
        """
        cls.ensure_taxonomy_seeded()
        query = (query or "").strip()
        active_tags = [t.strip() for t in (active_tags or []) if t.strip()]

        raw_key = f"{query.lower()}_{'_'.join(sorted(active_tags)).lower()}"
        safe_suffix = re.sub(r'[^a-zA-Z0-9_]', '_', raw_key)[:100]
        cache_key = f"tv_smart_sug_{safe_suffix}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        from apps.candidates.models import (
            TaxonomyDesignation, TaxonomySkill, RoleRelation, RoleSkillRelation, CandidateTag
        )

        all_input_terms = []
        if query:
            all_input_terms.append(query)
        all_input_terms.extend(active_tags)

        suggestions_map: Dict[str, Dict[str, Any]] = {}
        matched_canonical_roles: List[Any] = []
        matched_skills: List[Any] = []

        # Find matching entities for all input terms
        for term in all_input_terms:
            t_clean = cls.normalize_term(term)
            t_lower = t_clean.lower()

            des = cls.find_canonical_designation(term)
            if des:
                matched_canonical_roles.append(des)

            sk = TaxonomySkill.objects.filter(
                Q(canonical_name__iexact=t_clean) | Q(normalized_name=t_lower),
                is_active=True
            ).first()
            if sk:
                matched_skills.append(sk)

        # 1. Graph Traversal from Matched Roles
        for des in matched_canonical_roles:
            # Outgoing & Incoming Role Relations
            out_relations = RoleRelation.objects.filter(source_role=des).select_related('target_role')
            for rel in out_relations:
                target = rel.target_role
                if target.canonical_name.lower() != des.canonical_name.lower():
                    suggestions_map[target.canonical_name] = {
                        "label": target.canonical_name,
                        "type": "designation",
                        "category": rel.get_relation_type_display(),
                        "relevance": round(float(rel.weight), 2),
                        "domain": target.industry or des.industry or "General"
                    }

            in_relations = RoleRelation.objects.filter(target_role=des, is_bidirectional=True).select_related('source_role')
            for rel in in_relations:
                source = rel.source_role
                if source.canonical_name.lower() != des.canonical_name.lower():
                    if source.canonical_name not in suggestions_map or suggestions_map[source.canonical_name]["relevance"] < float(rel.weight):
                        suggestions_map[source.canonical_name] = {
                            "label": source.canonical_name,
                            "type": "designation",
                            "category": rel.get_relation_type_display(),
                            "relevance": round(float(rel.weight), 2),
                            "domain": source.industry or des.industry or "General"
                        }

            # Associated Core & Secondary Skills
            skill_relations = RoleSkillRelation.objects.filter(role=des).select_related('skill')
            for sr in skill_relations:
                sk = sr.skill
                suggestions_map[sk.canonical_name] = {
                    "label": sk.canonical_name,
                    "type": "skill",
                    "category": sr.get_relation_type_display(),
                    "relevance": round(float(sr.weight), 2),
                    "domain": sk.domain or des.industry or "General"
                }

        # 2. Graph Traversal from Matched Skills
        for sk in matched_skills:
            role_relations = RoleSkillRelation.objects.filter(skill=sk).select_related('role')
            for rr in role_relations:
                r = rr.role
                if r.canonical_name not in suggestions_map:
                    suggestions_map[r.canonical_name] = {
                        "label": r.canonical_name,
                        "type": "designation",
                        "category": "Associated Role",
                        "relevance": round(float(rr.weight) * 0.9, 2),
                        "domain": r.industry or sk.domain or "General"
                    }

        # 3. Candidate Database Co-Occurrence Mining
        if query:
            q_clean = cls.normalize_term(query).lower()
            matching_candidate_tags = CandidateTag.objects.filter(
                Q(normalized_name__icontains=q_clean) | Q(canonical_name__icontains=q_clean)
            ).values_list('profile_id', flat=True)[:100]

            if matching_candidate_tags:
                co_occurring = CandidateTag.objects.filter(
                    profile_id__in=matching_candidate_tags
                ).exclude(
                    normalized_name=q_clean
                ).values_list('canonical_name', 'tag_type').distinct()[:20]

                for name, tag_type in co_occurring:
                    if name and name not in suggestions_map and len(name) > 2:
                        type_str = "designation" if "DESIGNATION" in tag_type else "skill"
                        suggestions_map[name] = {
                            "label": name,
                            "type": type_str,
                            "category": "Candidate Match",
                            "relevance": 0.78,
                            "domain": "Inferred"
                        }

        # 4. Unknown Query Fallback Discovery (No hardcoded roles)
        if not suggestions_map and query:
            suggestions_map = cls._discover_unknown_query_suggestions(query)

        # Remove items already present in active_tags or query
        existing_set = {cls.normalize_term(t).lower() for t in all_input_terms}
        cleaned_suggestions = [
            item for name, item in suggestions_map.items()
            if cls.normalize_term(name).lower() not in existing_set
        ]

        # Sort by relevance desc
        cleaned_suggestions.sort(key=lambda x: (-x["relevance"], x["label"]))

        response_payload = {
            "query": query,
            "canonical": matched_canonical_roles[0].canonical_name if matched_canonical_roles else query,
            "suggestions": cleaned_suggestions[:limit]
        }

        # Cache for 10 minutes
        cache.set(cache_key, response_payload, timeout=600)
        return response_payload

    @classmethod
    def _discover_unknown_query_suggestions(cls, query: str) -> Dict[str, Dict[str, Any]]:
        """
        Dynamically handles novel / unknown job titles or skills gracefully.
        Analyzes constituent words, finds candidate DB matches, and infers reasonable related terms.
        """
        suggestions: Dict[str, Dict[str, Any]] = {}
        words = [w.strip() for w in re.findall(r'\w+', query.lower()) if len(w) > 2]
        meaningful_words = [w for w in words if w not in GENERIC_ROLE_MODIFIERS]

        from apps.candidates.models import CandidateTag, TaxonomyDesignation, TaxonomySkill

        if not meaningful_words:
            return suggestions

        # Search across CandidateTags
        q_filter = Q()
        for w in meaningful_words:
            q_filter |= Q(normalized_name__icontains=w)

        found_tags = CandidateTag.objects.filter(q_filter).values_list('canonical_name', 'tag_type').distinct()[:10]
        for name, t_type in found_tags:
            if name and name.lower() != query.lower():
                type_str = "designation" if "DESIGNATION" in t_type else "skill"
                suggestions[name] = {
                    "label": name,
                    "type": type_str,
                    "category": "Discovered Match",
                    "relevance": 0.75,
                    "domain": "Dynamic"
                }

        # Search Taxonomy for partial tokens
        for w in meaningful_words:
            matched_des = TaxonomyDesignation.objects.filter(normalized_name__icontains=w, is_active=True)[:3]
            for d in matched_des:
                if d.canonical_name.lower() != query.lower():
                    suggestions[d.canonical_name] = {
                        "label": d.canonical_name,
                        "type": "designation",
                        "category": "Related Role",
                        "relevance": 0.70,
                        "domain": d.industry or "General"
                    }

        # If still empty, generate dynamic constituent keyword suggestions from terms
        if not suggestions:
            for w in meaningful_words:
                suggestions[w.title()] = {
                    "label": w.title(),
                    "type": "skill",
                    "category": "Discovered Keyword",
                    "relevance": 0.65,
                    "domain": "Dynamic"
                }
            if len(meaningful_words) >= 2:
                phrase = " ".join(w.title() for w in meaningful_words)
                if phrase.lower() != query.lower():
                    suggestions[phrase] = {
                        "label": phrase,
                        "type": "skill",
                        "category": "Domain Term",
                        "relevance": 0.70,
                        "domain": "Dynamic"
                    }

        return suggestions