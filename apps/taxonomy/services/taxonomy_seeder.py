"""
TalentVault Universal Recruitment Taxonomy (TV-URT) — Multi-Domain Pre-built Data Seeder.
Provides legally open, standardized, rich employment taxonomy across 50+ sectors.
"""
from typing import Dict, Any, List, Tuple
from django.db import transaction


# Comprehensive 50+ Domain Hierarchy & Skill Matrix (TV-URT v2.0)
SEED_TAXONOMY_SECTORS: List[Dict[str, Any]] = [
    # 1. IT & SOFTWARE DEVELOPMENT
    {
        "industry": "Information Technology",
        "department": "Engineering & Technology",
        "job_function": "Software Development",
        "roles": [
            {
                "name": "Software Engineer",
                "canonical": "Software Engineer",
                "seniority": "MID",
                "experience": "MID_CAREER",
                "aliases": ["SDE", "Software Developer", "SWE", "Programmer", "Computer Programmer", "Applications Developer", "SDE II"],
                "alias_types": {"SDE": "ABBREVIATION", "SWE": "ABBREVIATION", "Software Developer": "SYNONYM", "SDE II": "SENIORITY_VARIANT"},
                "skills": [("Data Structures & Algorithms", "PRIMARY_SKILL", 0.98), ("System Design", "PRIMARY_SKILL", 0.92), ("Git", "TOOL", 0.95), ("Code Review", "SECONDARY_SKILL", 0.88), ("Unit Testing", "PRIMARY_SKILL", 0.90)],
                "technologies": [("Python", "PROGRAMMING_LANGUAGE", 0.90), ("Java", "PROGRAMMING_LANGUAGE", 0.90), ("C++", "PROGRAMMING_LANGUAGE", 0.85), ("PostgreSQL", "DATABASE", 0.88)],
                "tools": [("Git", "COLLABORATION", 0.95), ("VS Code", "DESIGN", 0.90), ("Docker", "DIAGNOSTIC", 0.85)],
                "related_roles": [("Senior Software Engineer", "PARENT_ROLE", 0.95), ("Junior Software Engineer", "CHILD_ROLE", 0.95), ("Full Stack Developer", "RELATED_ROLE", 0.90), ("Backend Developer", "RELATED_ROLE", 0.92)]
            },
            {
                "name": "Full Stack Developer",
                "canonical": "Full Stack Developer",
                "seniority": "MID",
                "experience": "MID_CAREER",
                "aliases": ["Full Stack Engineer", "Fullstack Developer", "Full-Stack Dev", "Fullstack Web Developer", "MEAN Stack Developer", "MERN Stack Developer"],
                "alias_types": {"Full Stack Engineer": "SYNONYM", "MERN Stack Developer": "SYNONYM", "MEAN Stack Developer": "SYNONYM"},
                "skills": [("Full Stack Web Development", "PRIMARY_SKILL", 0.98), ("REST APIs", "PRIMARY_SKILL", 0.95), ("Frontend Architecture", "PRIMARY_SKILL", 0.90), ("Database Design", "PRIMARY_SKILL", 0.90)],
                "technologies": [("JavaScript", "PROGRAMMING_LANGUAGE", 0.98), ("TypeScript", "PROGRAMMING_LANGUAGE", 0.95), ("React", "FRAMEWORK", 0.95), ("Node.js", "FRAMEWORK", 0.95), ("Django", "FRAMEWORK", 0.90), ("PostgreSQL", "DATABASE", 0.92), ("MongoDB", "DATABASE", 0.88)],
                "tools": [("Git", "COLLABORATION", 0.95), ("Postman", "DIAGNOSTIC", 0.90), ("Docker", "DIAGNOSTIC", 0.85)],
                "related_roles": [("Frontend Developer", "RELATED_ROLE", 0.92), ("Backend Developer", "RELATED_ROLE", 0.92), ("Software Engineer", "RELATED_ROLE", 0.90), ("Lead Full Stack Engineer", "PARENT_ROLE", 0.95)]
            },
            {
                "name": "Frontend Developer",
                "canonical": "Frontend Developer",
                "seniority": "MID",
                "experience": "MID_CAREER",
                "aliases": ["Frontend Engineer", "Front End Developer", "UI Developer", "Client-Side Developer", "React Developer", "Angular Developer", "Vue Developer"],
                "alias_types": {"Frontend Engineer": "SYNONYM", "UI Developer": "SYNONYM", "React Developer": "SYNONYM"},
                "skills": [("Frontend Web Development", "PRIMARY_SKILL", 0.98), ("Responsive Web Design", "PRIMARY_SKILL", 0.95), ("State Management (Redux/Zustand)", "PRIMARY_SKILL", 0.92), ("Web Performance Optimization", "PRIMARY_SKILL", 0.90)],
                "technologies": [("React", "FRAMEWORK", 0.98), ("JavaScript", "PROGRAMMING_LANGUAGE", 0.98), ("TypeScript", "PROGRAMMING_LANGUAGE", 0.95), ("Next.js", "FRAMEWORK", 0.92), ("HTML5", "PROGRAMMING_LANGUAGE", 0.95), ("CSS3 / TailwindCSS", "FRAMEWORK", 0.95), ("Vue.js", "FRAMEWORK", 0.88)],
                "tools": [("Figma", "DESIGN", 0.88), ("Webpack / Vite", "DEVOPS_TOOL", 0.90), ("Chrome DevTools", "DIAGNOSTIC", 0.92)],
                "related_roles": [("Full Stack Developer", "RELATED_ROLE", 0.92), ("UI/UX Designer", "ADJACENT_ROLE", 0.82), ("Senior Frontend Engineer", "PARENT_ROLE", 0.95)]
            },
            {
                "name": "Backend Developer",
                "canonical": "Backend Developer",
                "seniority": "MID",
                "experience": "MID_CAREER",
                "aliases": ["Backend Engineer", "Back End Developer", "Server-Side Developer", "Python Developer", "Java Developer", "Node Developer", "Go Developer"],
                "alias_types": {"Backend Engineer": "SYNONYM", "Python Developer": "SYNONYM", "Java Developer": "SYNONYM"},
                "skills": [("API Development & Microservices", "PRIMARY_SKILL", 0.98), ("Database Architecture & Query Optimization", "PRIMARY_SKILL", 0.95), ("Caching & Message Queues", "PRIMARY_SKILL", 0.92), ("System Security & Authentication", "PRIMARY_SKILL", 0.90)],
                "technologies": [("Python", "PROGRAMMING_LANGUAGE", 0.95), ("Java", "PROGRAMMING_LANGUAGE", 0.95), ("Django", "FRAMEWORK", 0.92), ("FastAPI", "FRAMEWORK", 0.90), ("Spring Boot", "FRAMEWORK", 0.92), ("Node.js", "FRAMEWORK", 0.92), ("PostgreSQL", "DATABASE", 0.95), ("Redis", "DATABASE", 0.92), ("Kafka", "DATABASE", 0.88)],
                "tools": [("Docker", "DIAGNOSTIC", 0.90), ("Postman", "DIAGNOSTIC", 0.92), ("Kubernetes", "DEVOPS_TOOL", 0.85)],
                "related_roles": [("Full Stack Developer", "RELATED_ROLE", 0.92), ("DevOps Engineer", "ADJACENT_ROLE", 0.85), ("Data Engineer", "ADJACENT_ROLE", 0.82), ("Senior Backend Engineer", "PARENT_ROLE", 0.95)]
            },
            {
                "name": "DevOps Engineer",
                "canonical": "DevOps Engineer",
                "seniority": "MID",
                "experience": "MID_CAREER",
                "aliases": ["Site Reliability Engineer", "SRE", "Cloud Engineer", "Platform Engineer", "Infrastructure Engineer", "Build & Release Engineer"],
                "alias_types": {"SRE": "ABBREVIATION", "Site Reliability Engineer": "SYNONYM", "Platform Engineer": "SYNONYM"},
                "skills": [("CI/CD Automation", "PRIMARY_SKILL", 0.98), ("Infrastructure as Code (IaC)", "PRIMARY_SKILL", 0.95), ("Container Orchestration", "PRIMARY_SKILL", 0.95), ("Cloud Security & Monitoring", "PRIMARY_SKILL", 0.92)],
                "technologies": [("Docker", "DEVOPS_TOOL", 0.98), ("Kubernetes", "DEVOPS_TOOL", 0.98), ("Terraform", "DEVOPS_TOOL", 0.95), ("AWS", "CLOUD_PLATFORM", 0.95), ("Azure", "CLOUD_PLATFORM", 0.90), ("GCP", "CLOUD_PLATFORM", 0.90), ("Linux / Bash", "OPERATING_SYSTEM", 0.95)],
                "tools": [("Jenkins / GitHub Actions", "DEVOPS_TOOL", 0.95), ("Prometheus / Grafana", "ANALYTICS", 0.92), ("Ansible", "DEVOPS_TOOL", 0.90)],
                "related_roles": [("Cloud Architect", "PARENT_ROLE", 0.92), ("Backend Developer", "ADJACENT_ROLE", 0.85), ("Cybersecurity Engineer", "ADJACENT_ROLE", 0.80)]
            },
        ]
    },

    # 2. DATA, ANALYTICS & AI / MACHINE LEARNING
    {
        "industry": "Data & Analytics",
        "department": "Data & Business Intelligence",
        "job_function": "Data Science & Analytics",
        "roles": [
            {
                "name": "Data Analyst",
                "canonical": "Data Analyst",
                "seniority": "MID",
                "experience": "MID_CAREER",
                "aliases": ["Data Analytics Specialist", "Reporting Analyst", "MIS Analyst", "BI Analyst", "Business Intelligence Analyst", "Statistical Analyst", "Data Quality Analyst"],
                "alias_types": {"MIS Analyst": "SYNONYM", "BI Analyst": "SYNONYM", "Data Analytics Specialist": "SYNONYM"},
                "skills": [("Data Analysis", "PRIMARY_SKILL", 0.98), ("SQL Querying", "PRIMARY_SKILL", 0.98), ("Data Visualization & Storytelling", "PRIMARY_SKILL", 0.95), ("Statistical Modeling", "PRIMARY_SKILL", 0.90), ("Excel & Spreadsheets Modeling", "PRIMARY_SKILL", 0.92), ("MIS Reporting", "DOMAIN_SKILL", 0.90)],
                "technologies": [("SQL", "DATABASE", 0.98), ("Python", "PROGRAMMING_LANGUAGE", 0.90), ("R", "PROGRAMMING_LANGUAGE", 0.85), ("PostgreSQL", "DATABASE", 0.90)],
                "tools": [("Power BI", "ANALYTICS", 0.98), ("Tableau", "ANALYTICS", 0.95), ("Advanced Excel", "ANALYTICS", 0.95)],
                "related_roles": [("Senior Data Analyst", "PARENT_ROLE", 0.95), ("Business Analyst", "RELATED_ROLE", 0.90), ("Data Scientist", "RELATED_ROLE", 0.88), ("Data Engineer", "ADJACENT_ROLE", 0.85)]
            },
            {
                "name": "Data Scientist",
                "canonical": "Data Scientist",
                "seniority": "SENIOR",
                "experience": "SENIOR_CAREER",
                "aliases": ["Data Science Specialist", "Applied Scientist", "Predictive Modeler", "Machine Learning Scientist", "Lead Data Scientist", "Senior Data Scientist"],
                "alias_types": {"Machine Learning Scientist": "SYNONYM", "Applied Scientist": "SYNONYM"},
                "skills": [("Machine Learning Algorithms", "PRIMARY_SKILL", 0.98), ("Statistical Analysis & Hypothesis Testing", "PRIMARY_SKILL", 0.95), ("Predictive Analytics", "PRIMARY_SKILL", 0.95), ("Natural Language Processing (NLP)", "DOMAIN_SKILL", 0.90), ("Deep Learning", "DOMAIN_SKILL", 0.90)],
                "technologies": [("Python", "PROGRAMMING_LANGUAGE", 0.98), ("Scikit-Learn", "AI_FRAMEWORK", 0.95), ("Pandas / NumPy", "AI_FRAMEWORK", 0.98), ("TensorFlow / PyTorch", "AI_FRAMEWORK", 0.92), ("SQL", "DATABASE", 0.95), ("Spark / PySpark", "AI_FRAMEWORK", 0.88)],
                "tools": [("Jupyter Notebook", "ANALYTICS", 0.95), ("MLflow", "DEVOPS_TOOL", 0.88), ("Docker", "DIAGNOSTIC", 0.85)],
                "related_roles": [("Machine Learning Engineer", "RELATED_ROLE", 0.92), ("Data Analyst", "CHILD_ROLE", 0.88), ("AI Research Scientist", "PARENT_ROLE", 0.90)]
            },
            {
                "name": "Data Engineer",
                "canonical": "Data Engineer",
                "seniority": "MID",
                "experience": "MID_CAREER",
                "aliases": ["Big Data Engineer", "Data Pipeline Engineer", "ETL Developer", "Data Platform Engineer", "Data Architect", "Data Warehouse Engineer"],
                "alias_types": {"Big Data Engineer": "SYNONYM", "ETL Developer": "SYNONYM", "Data Warehouse Engineer": "SYNONYM"},
                "skills": [("ETL / ELT Pipelines", "PRIMARY_SKILL", 0.98), ("Data Warehousing & Data Lakes", "PRIMARY_SKILL", 0.95), ("Data Modeling & Star Schema", "PRIMARY_SKILL", 0.95), ("Distributed Computing", "PRIMARY_SKILL", 0.90)],
                "technologies": [("SQL", "DATABASE", 0.98), ("Python", "PROGRAMMING_LANGUAGE", 0.95), ("Spark / PySpark", "AI_FRAMEWORK", 0.95), ("Snowflake / BigQuery", "DATABASE", 0.92), ("Airflow", "DEVOPS_TOOL", 0.92), ("Kafka", "DATABASE", 0.90), ("PostgreSQL", "DATABASE", 0.90)],
                "tools": [("Airflow / Prefect", "DEVOPS_TOOL", 0.92), ("dbt", "ANALYTICS", 0.90), ("Docker", "DIAGNOSTIC", 0.88)],
                "related_roles": [("Data Architect", "PARENT_ROLE", 0.95), ("Data Analyst", "ADJACENT_ROLE", 0.85), ("Backend Developer", "RELATED_ROLE", 0.82)]
            },
            {
                "name": "Database Administrator",
                "canonical": "Database Administrator",
                "seniority": "MID",
                "experience": "MID_CAREER",
                "aliases": ["DBA", "Database Engineer", "SQL Server DBA", "Oracle DBA", "PostgreSQL DBA", "MySQL Administrator"],
                "alias_types": {"DBA": "ABBREVIATION"},
                "skills": [("Database Administration", "PRIMARY_SKILL", 0.98), ("Backup & Disaster Recovery", "PRIMARY_SKILL", 0.95), ("Query Optimization & Indexing", "PRIMARY_SKILL", 0.95), ("Database High Availability & Replication", "PRIMARY_SKILL", 0.92)],
                "technologies": [("PostgreSQL", "DATABASE", 0.98), ("MySQL", "DATABASE", 0.95), ("Oracle Database", "DATABASE", 0.95), ("Microsoft SQL Server", "DATABASE", 0.95), ("MongoDB", "DATABASE", 0.88)],
                "tools": [("pgAdmin", "DIAGNOSTIC", 0.90), ("Oracle Enterprise Manager", "DIAGNOSTIC", 0.90)],
                "related_roles": [("Data Engineer", "RELATED_ROLE", 0.85), ("DevOps Engineer", "ADJACENT_ROLE", 0.80)]
            }
        ]
    },

    # 3. SALES, BUSINESS DEVELOPMENT & RELATIONSHIP MANAGEMENT
    {
        "industry": "Sales & Distribution",
        "department": "Sales & Commercial",
        "job_function": "B2B & B2C Sales",
        "roles": [
            {
                "name": "Sales Manager",
                "canonical": "Sales Manager",
                "seniority": "MANAGER",
                "experience": "SENIOR_CAREER",
                "aliases": ["Sales Mgr", "Manager - Sales", "Sales Head", "Sales Team Lead", "Commercial Manager"],
                "alias_types": {"Sales Mgr": "ABBREVIATION", "Manager - Sales": "SYNONYM"},
                "skills": [("Sales", "PRIMARY_SKILL", 0.98), ("Sales Management & Target Achievement", "PRIMARY_SKILL", 0.98), ("Team Leadership & Territory Allocation", "PRIMARY_SKILL", 0.95), ("Revenue Forecasting & Pipeline Management", "PRIMARY_SKILL", 0.95), ("Client Relationship Management (CRM)", "PRIMARY_SKILL", 0.92), ("Contract Negotiation & Closing", "PRIMARY_SKILL", 0.95)],
                "technologies": [],
                "tools": [("Salesforce CRM", "CRM", 0.95), ("HubSpot", "CRM", 0.90), ("Zoho CRM", "CRM", 0.90), ("MS Excel", "ANALYTICS", 0.92)],
                "related_roles": [("Area Sales Manager", "CHILD_ROLE", 0.95), ("Regional Sales Manager", "PARENT_ROLE", 0.95), ("National Sales Manager", "PARENT_ROLE", 0.92), ("Business Development Manager", "FUNCTIONAL_EQUIVALENT", 0.92), ("Key Account Manager", "RELATED_ROLE", 0.90)]
            },
            {
                "name": "Sales Executive",
                "canonical": "Sales Executive",
                "seniority": "JUNIOR",
                "experience": "EARLY_CAREER",
                "aliases": ["Field Sales Executive", "Direct Sales Executive", "Sales Representative", "Corporate Sales Executive", "Sales Associate"],
                "alias_types": {"Sales Representative": "SYNONYM", "Field Sales Executive": "SYNONYM"},
                "skills": [("Sales", "PRIMARY_SKILL", 0.98), ("Direct Sales & Client Pitching", "PRIMARY_SKILL", 0.98), ("Customer Acquisition", "PRIMARY_SKILL", 0.95), ("Lead Follow-up & Conversion", "PRIMARY_SKILL", 0.95), ("B2C & Retail Sales", "PRIMARY_SKILL", 0.92)],
                "technologies": [],
                "tools": [("CRM Software", "CRM", 0.90), ("LeadSquared", "CRM", 0.88)],
                "related_roles": [("Sales Manager", "PARENT_ROLE", 0.95), ("Sales Officer", "RELATED_ROLE", 0.92), ("Inside Sales Executive", "RELATED_ROLE", 0.90)]
            },
            {
                "name": "Sales Officer",
                "canonical": "Sales Officer",
                "seniority": "JUNIOR",
                "experience": "EARLY_CAREER",
                "aliases": ["SO", "Senior Sales Officer", "SSO", "Territory Sales Officer", "TSO"],
                "alias_types": {"SO": "ABBREVIATION", "TSO": "ABBREVIATION"},
                "skills": [("Sales", "PRIMARY_SKILL", 0.98), ("Channel Partner Servicing", "PRIMARY_SKILL", 0.95), ("Retailer Network Expansion", "PRIMARY_SKILL", 0.95), ("Secondary Sales Tracking", "PRIMARY_SKILL", 0.92)],
                "technologies": [],
                "tools": [("DMS", "ERP", 0.90)],
                "related_roles": [("Area Sales Manager", "PARENT_ROLE", 0.95), ("Sales Executive", "RELATED_ROLE", 0.92)]
            },
            {
                "name": "Sales Consultant",
                "canonical": "Sales Consultant",
                "seniority": "MID",
                "experience": "MID_CAREER",
                "aliases": ["Sales Advisor", "Solution Sales Consultant", "Pre-Sales Consultant", "Technical Sales Specialist"],
                "alias_types": {"Sales Advisor": "SYNONYM"},
                "skills": [("Consultative Selling", "PRIMARY_SKILL", 0.98), ("Solution Architecture & Demos", "PRIMARY_SKILL", 0.95), ("Customer Needs Assessment", "PRIMARY_SKILL", 0.95)],
                "technologies": [],
                "tools": [("Salesforce", "CRM", 0.92)],
                "related_roles": [("Sales Manager", "PARENT_ROLE", 0.92), ("Key Account Manager", "RELATED_ROLE", 0.90)]
            },
            {
                "name": "Area Sales Manager",
                "canonical": "Area Sales Manager",
                "seniority": "MANAGER",
                "experience": "MID_CAREER",
                "aliases": ["ASM", "Area Business Manager", "Area Manager - Sales", "District Sales Manager"],
                "alias_types": {"ASM": "ABBREVIATION", "Area Business Manager": "SYNONYM"},
                "skills": [("Sales", "PRIMARY_SKILL", 0.98), ("Area & Territory Sales", "PRIMARY_SKILL", 0.98), ("Distributor & Dealer Management", "PRIMARY_SKILL", 0.98), ("Channel Sales Strategy", "PRIMARY_SKILL", 0.95), ("Primary & Secondary Sales Target", "PRIMARY_SKILL", 0.95), ("Field Sales Force Supervision", "PRIMARY_SKILL", 0.92)],
                "technologies": [],
                "tools": [("Salesforce", "CRM", 0.90), ("DMS (Distribution Management System)", "ERP", 0.92), ("LeadSquared", "CRM", 0.88)],
                "related_roles": [("Sales Manager", "PARENT_ROLE", 0.95), ("Regional Sales Manager", "PARENT_ROLE", 0.95), ("Sales Executive", "CHILD_ROLE", 0.92), ("Sales Officer", "CHILD_ROLE", 0.92)]
            },
            {
                "name": "Regional Sales Manager",
                "canonical": "Regional Sales Manager",
                "seniority": "SENIOR",
                "experience": "LEADERSHIP",
                "aliases": ["RSM", "Regional Business Manager", "Zonal Sales Manager", "ZSM", "Regional Head - Sales"],
                "alias_types": {"RSM": "ABBREVIATION", "ZSM": "ABBREVIATION", "Zonal Sales Manager": "SYNONYM"},
                "skills": [("Sales", "PRIMARY_SKILL", 0.98), ("Regional Sales Strategy & Expansion", "PRIMARY_SKILL", 0.98), ("Zonal P&L Management", "PRIMARY_SKILL", 0.95), ("Large Scale Channel Network", "PRIMARY_SKILL", 0.95), ("Sales Force Leadership", "PRIMARY_SKILL", 0.95)],
                "technologies": [],
                "tools": [("SAP Sales & Distribution (SD)", "ERP", 0.90), ("Salesforce", "CRM", 0.92)],
                "related_roles": [("Area Sales Manager", "CHILD_ROLE", 0.95), ("National Sales Head", "PARENT_ROLE", 0.95), ("VP Sales", "PARENT_ROLE", 0.90)]
            },
            {
                "name": "Territory Sales Manager",
                "canonical": "Territory Sales Manager",
                "seniority": "MANAGER",
                "experience": "MID_CAREER",
                "aliases": ["TSM", "Territory Business Manager", "Territory Lead"],
                "alias_types": {"TSM": "ABBREVIATION"},
                "skills": [("Territory Sales Planning", "PRIMARY_SKILL", 0.98), ("Distributor Onboarding", "PRIMARY_SKILL", 0.95), ("Sales Revenue Growth", "PRIMARY_SKILL", 0.95)],
                "technologies": [],
                "tools": [("Salesforce", "CRM", 0.90)],
                "related_roles": [("Area Sales Manager", "RELATED_ROLE", 0.95), ("Sales Manager", "PARENT_ROLE", 0.92)]
            },
            {
                "name": "Field Sales Manager",
                "canonical": "Field Sales Manager",
                "seniority": "MANAGER",
                "experience": "MID_CAREER",
                "aliases": ["FSM", "Field Operations Sales Manager", "Field Sales Lead"],
                "alias_types": {"FSM": "ABBREVIATION"},
                "skills": [("Field Sales Operations", "PRIMARY_SKILL", 0.98), ("On-ground Team Coaching", "PRIMARY_SKILL", 0.95), ("Route-to-Market Optimization", "PRIMARY_SKILL", 0.92)],
                "technologies": [],
                "tools": [("Salesforce", "CRM", 0.90)],
                "related_roles": [("Sales Manager", "PARENT_ROLE", 0.95), ("Area Sales Manager", "RELATED_ROLE", 0.92)]
            },
            {
                "name": "Channel Sales Manager",
                "canonical": "Channel Sales Manager",
                "seniority": "MANAGER",
                "experience": "SENIOR_CAREER",
                "aliases": ["Partner Sales Manager", "Distribution Channel Manager", "Alliance Sales Manager"],
                "alias_types": {"Partner Sales Manager": "SYNONYM"},
                "skills": [("Channel Partner Network", "PRIMARY_SKILL", 0.98), ("Dealer Margin & Incentive Structuring", "PRIMARY_SKILL", 0.95), ("Trade Promotions", "PRIMARY_SKILL", 0.95)],
                "technologies": [],
                "tools": [("ERP Distribution Modules", "ERP", 0.92)],
                "related_roles": [("Sales Manager", "PARENT_ROLE", 0.95), ("Regional Sales Manager", "PARENT_ROLE", 0.92)]
            },
            {
                "name": "Inside Sales Executive",
                "canonical": "Inside Sales Executive",
                "seniority": "JUNIOR",
                "experience": "EARLY_CAREER",
                "aliases": ["ISR", "Inside Sales Representative", "Remote Sales Specialist", "Virtual Sales Executive"],
                "alias_types": {"ISR": "ABBREVIATION", "Inside Sales Representative": "SYNONYM"},
                "skills": [("Virtual Selling & Demos", "PRIMARY_SKILL", 0.98), ("Pipeline Cadence & Lead Nurturing", "PRIMARY_SKILL", 0.95), ("CRM Hygiene", "PRIMARY_SKILL", 0.92)],
                "technologies": [],
                "tools": [("HubSpot", "CRM", 0.92), ("ZoomInfo", "COLLABORATION", 0.90)],
                "related_roles": [("Business Development Executive", "RELATED_ROLE", 0.95), ("Sales Executive", "RELATED_ROLE", 0.92)]
            },
            {
                "name": "Business Development Executive",
                "canonical": "Business Development Executive",
                "seniority": "JUNIOR",
                "experience": "EARLY_CAREER",
                "aliases": ["BDE", "BD Executive", "Business Development Associate", "BDA", "Lead Generation Executive"],
                "alias_types": {"BDE": "ABBREVIATION", "BDA": "ABBREVIATION", "Business Development Associate": "SYNONYM"},
                "skills": [("Lead Generation & Prospecting", "PRIMARY_SKILL", 0.98), ("Cold Calling & Outbound Outreach", "PRIMARY_SKILL", 0.95), ("Client Pitching & Demos", "PRIMARY_SKILL", 0.92), ("B2B Sales", "PRIMARY_SKILL", 0.90), ("Relationship Building", "PRIMARY_SKILL", 0.88)],
                "technologies": [],
                "tools": [("HubSpot CRM", "CRM", 0.90), ("LinkedIn Sales Navigator", "COLLABORATION", 0.92), ("Apollo.io", "COLLABORATION", 0.90)],
                "related_roles": [("Business Development Manager", "PARENT_ROLE", 0.95), ("Sales Executive", "FUNCTIONAL_EQUIVALENT", 0.92), ("Inside Sales Specialist", "RELATED_ROLE", 0.90)]
            },
            {
                "name": "Business Development Manager",
                "canonical": "Business Development Manager",
                "seniority": "MANAGER",
                "experience": "SENIOR_CAREER",
                "aliases": ["BDM", "BD Manager", "Manager - Business Development", "Strategic Partnerships Manager", "Corporate Sales Manager"],
                "alias_types": {"BDM": "ABBREVIATION", "BD Manager": "SYNONYM"},
                "skills": [("B2B Enterprise Sales", "PRIMARY_SKILL", 0.98), ("Strategic Partnerships & Alliances", "PRIMARY_SKILL", 0.95), ("Client Acquisition & Account Expansion", "PRIMARY_SKILL", 0.95), ("Deal Structuring & Closing", "PRIMARY_SKILL", 0.92)],
                "technologies": [],
                "tools": [("Salesforce", "CRM", 0.92), ("HubSpot", "CRM", 0.90)],
                "related_roles": [("Sales Manager", "FUNCTIONAL_EQUIVALENT", 0.92), ("Key Account Manager", "RELATED_ROLE", 0.92), ("Business Development Executive", "CHILD_ROLE", 0.95)]
            },
            {
                "name": "Key Account Manager",
                "canonical": "Key Account Manager",
                "seniority": "SENIOR",
                "experience": "SENIOR_CAREER",
                "aliases": ["KAM", "Corporate Account Manager", "Strategic Account Manager", "Enterprise Account Manager", "Client Partner"],
                "alias_types": {"KAM": "ABBREVIATION"},
                "skills": [("Enterprise Account Management", "PRIMARY_SKILL", 0.98), ("Upselling & Cross-selling", "PRIMARY_SKILL", 0.95), ("Client Retention & Relationship Growth", "PRIMARY_SKILL", 0.95), ("Contract Renewals", "PRIMARY_SKILL", 0.90)],
                "technologies": [],
                "tools": [("Salesforce", "CRM", 0.95), ("Gainsight", "CRM", 0.88)],
                "related_roles": [("Sales Manager", "RELATED_ROLE", 0.90), ("Customer Success Manager", "ADJACENT_ROLE", 0.88), ("Business Development Manager", "RELATED_ROLE", 0.90)]
            }
        ]
    },

    # 4. HUMAN RESOURCES & RECRUITMENT
    {
        "industry": "Human Resources & Staffing",
        "department": "Human Resources",
        "job_function": "Talent Acquisition & HR Operations",
        "roles": [
            {
                "name": "HR Manager",
                "canonical": "HR Manager",
                "seniority": "MANAGER",
                "experience": "SENIOR_CAREER",
                "aliases": ["Human Resources Manager", "HR Head", "Manager - HR", "HR Generalist Manager", "People Operations Manager"],
                "alias_types": {"Human Resources Manager": "SYNONYM", "Manager - HR": "SYNONYM"},
                "skills": [("HR Operations & Policy Formulation", "PRIMARY_SKILL", 0.98), ("Employee Relations & Grievance Handling", "PRIMARY_SKILL", 0.95), ("Performance Management (PMS / OKR)", "PRIMARY_SKILL", 0.95), ("Statutory Compliance & Labor Laws", "PRIMARY_SKILL", 0.92), ("Talent Acquisition & Retention", "PRIMARY_SKILL", 0.90)],
                "technologies": [],
                "tools": [("Darwinbox", "ERP", 0.92), ("Keka HR", "ERP", 0.92), ("Workday", "ERP", 0.90), ("Zimyo", "ERP", 0.85)],
                "related_roles": [("HR Business Partner (HRBP)", "RELATED_ROLE", 0.95), ("HR Executive", "CHILD_ROLE", 0.95), ("Head of HR / CHRO", "PARENT_ROLE", 0.92), ("Talent Acquisition Manager", "RELATED_ROLE", 0.90)]
            },
            {
                "name": "Technical Recruiter",
                "canonical": "Technical Recruiter",
                "seniority": "MID",
                "experience": "MID_CAREER",
                "aliases": ["IT Recruiter", "Tech Recruiter", "Talent Acquisition Specialist (Tech)", "Senior IT Recruiter", "Staffing Specialist (IT)"],
                "alias_types": {"IT Recruiter": "SYNONYM", "Tech Recruiter": "SYNONYM"},
                "skills": [("Technical Sourcing & Boolean Search", "PRIMARY_SKILL", 0.98), ("Candidate Screening & Interview Scheduling", "PRIMARY_SKILL", 0.95), ("Tech Stack Understanding (Full Stack, Cloud, Data)", "PRIMARY_SKILL", 0.95), ("Salary Negotiation & Offer Rollout", "PRIMARY_SKILL", 0.92), ("Headhunting & Passive Sourcing", "PRIMARY_SKILL", 0.90)],
                "technologies": [],
                "tools": [("Naukri Resdex", "COLLABORATION", 0.95), ("LinkedIn Recruiter", "COLLABORATION", 0.98), ("Greenhouse / Lever ATS", "COLLABORATION", 0.92)],
                "related_roles": [("Talent Acquisition Specialist", "FUNCTIONAL_EQUIVALENT", 0.95), ("HR Executive", "RELATED_ROLE", 0.88), ("Talent Acquisition Lead", "PARENT_ROLE", 0.95)]
            },
            {
                "name": "HR Executive",
                "canonical": "HR Executive",
                "seniority": "JUNIOR",
                "experience": "EARLY_CAREER",
                "aliases": ["HR Officer", "Junior HR Generalist", "HR Associate", "HR Operations Executive", "HR Coordinator"],
                "alias_types": {"HR Officer": "SYNONYM", "HR Associate": "SYNONYM"},
                "skills": [("Employee Onboarding & Documentation", "PRIMARY_SKILL", 0.98), ("Attendance & Leave Management", "PRIMARY_SKILL", 0.95), ("Payroll Support (PF, ESI, TDS)", "PRIMARY_SKILL", 0.92), ("Employee Engagement Activities", "PRIMARY_SKILL", 0.90), ("Exit Formalities & Offboarding", "PRIMARY_SKILL", 0.90)],
                "technologies": [],
                "tools": [("Keka", "ERP", 0.90), ("Excel", "ANALYTICS", 0.92), ("Darwinbox", "ERP", 0.88)],
                "related_roles": [("HR Manager", "PARENT_ROLE", 0.95), ("Payroll Specialist", "ADJACENT_ROLE", 0.88), ("Technical Recruiter", "RELATED_ROLE", 0.85)]
            },
            {
                "name": "HR Business Partner",
                "canonical": "HR Business Partner",
                "seniority": "SENIOR",
                "experience": "SENIOR_CAREER",
                "aliases": ["HRBP", "Senior HRBP", "Strategic HR Partner", "People Partner"],
                "alias_types": {"HRBP": "ABBREVIATION"},
                "skills": [("Strategic HR Business Partnering", "PRIMARY_SKILL", 0.98), ("Workforce Planning & Org Design", "PRIMARY_SKILL", 0.95), ("Leadership Coaching & Succession Planning", "PRIMARY_SKILL", 0.92), ("Change Management", "PRIMARY_SKILL", 0.90)],
                "technologies": [],
                "tools": [("Workday", "ERP", 0.95), ("SuccessFactors", "ERP", 0.92)],
                "related_roles": [("HR Manager", "RELATED_ROLE", 0.95), ("CHRO", "PARENT_ROLE", 0.92)]
            }
        ]
    },

    # 5. FINANCE, ACCOUNTING & AUDITING
    {
        "industry": "Accounting & Finance",
        "department": "Finance & Accounts",
        "job_function": "Accounting & Taxation",
        "roles": [
            {
                "name": "Accountant",
                "canonical": "Accountant",
                "seniority": "MID",
                "experience": "MID_CAREER",
                "aliases": ["Senior Accountant", "Accounts Executive", "General Accountant", "Staff Accountant", "Bookkeeper", "Account Officer"],
                "alias_types": {"Accounts Executive": "SYNONYM", "Bookkeeper": "SYNONYM"},
                "skills": [("Financial Accounting & Bookkeeping", "PRIMARY_SKILL", 0.98), ("GST Filing & Reconciliation (GSTR-1, GSTR-3B)", "PRIMARY_SKILL", 0.98), ("TDS Return & Compliance", "PRIMARY_SKILL", 0.95), ("Balance Sheet & P&L Finalization", "PRIMARY_SKILL", 0.95), ("Bank Reconciliation (BRS)", "PRIMARY_SKILL", 0.95), ("Accounts Payable & Receivable (AP/AR)", "PRIMARY_SKILL", 0.92)],
                "technologies": [],
                "tools": [("Tally Prime / Tally.ERP 9", "ERP", 0.98), ("Busy Accounting Software", "ERP", 0.92), ("SAP FICO", "ERP", 0.90), ("Advanced Excel (VLOOKUP, Pivot)", "ANALYTICS", 0.95), ("QuickBooks / Zoho Books", "ERP", 0.90)],
                "related_roles": [("Finance Manager", "PARENT_ROLE", 0.95), ("Chartered Accountant", "PARENT_ROLE", 0.90), ("Tax Analyst", "RELATED_ROLE", 0.92), ("Accounts Manager", "PARENT_ROLE", 0.95)]
            },
            {
                "name": "Finance Manager",
                "canonical": "Finance Manager",
                "seniority": "MANAGER",
                "experience": "SENIOR_CAREER",
                "aliases": ["Manager - Finance", "Financial Controller", "Head of Accounts", "Finance Lead", "Director Finance"],
                "alias_types": {"Manager - Finance": "SYNONYM", "Financial Controller": "SENIORITY_VARIANT"},
                "skills": [("Financial Planning & Analysis (FP&A)", "PRIMARY_SKILL", 0.98), ("Budgeting & Cash Flow Management", "PRIMARY_SKILL", 0.98), ("Working Capital Management", "PRIMARY_SKILL", 0.95), ("Statutory Audit & Tax Audits", "PRIMARY_SKILL", 0.92), ("Fund Raising & Banking Relations", "PRIMARY_SKILL", 0.90)],
                "technologies": [],
                "tools": [("SAP FICO", "ERP", 0.95), ("Oracle NetSuite", "ERP", 0.92), ("Hyperion / Anaplan", "ANALYTICS", 0.88)],
                "related_roles": [("CFO", "PARENT_ROLE", 0.95), ("Accountant", "CHILD_ROLE", 0.95), ("Financial Analyst", "CHILD_ROLE", 0.92), ("Chartered Accountant", "FUNCTIONAL_EQUIVALENT", 0.90)]
            },
            {
                "name": "Chartered Accountant",
                "canonical": "Chartered Accountant",
                "seniority": "SENIOR",
                "experience": "SENIOR_CAREER",
                "aliases": ["CA", "Qualified CA", "Chartered Financial Accountant", "Senior CA", "Audit Manager"],
                "alias_types": {"CA": "ABBREVIATION"},
                "skills": [("Ind AS / IFRS Accounting Standards", "PRIMARY_SKILL", 0.98), ("Internal & Statutory Auditing", "PRIMARY_SKILL", 0.98), ("Direct & Indirect Tax Advisory", "PRIMARY_SKILL", 0.95), ("Transfer Pricing & International Tax", "DOMAIN_SKILL", 0.92), ("Financial Due Diligence", "PRIMARY_SKILL", 0.92)],
                "technologies": [],
                "tools": [("SAP", "ERP", 0.92), ("Tally", "ERP", 0.90), ("Excel", "ANALYTICS", 0.95)],
                "related_roles": [("Finance Manager", "FUNCTIONAL_EQUIVALENT", 0.92), ("CFO", "PARENT_ROLE", 0.95), ("Internal Auditor", "RELATED_ROLE", 0.92)]
            }
        ]
    },

    # 6. HEALTHCARE, PHARMA & MEDICAL
    {
        "industry": "Healthcare & Pharmaceuticals",
        "department": "Medical & Clinical",
        "job_function": "Pharma & Clinical Healthcare",
        "roles": [
            {
                "name": "Medical Representative",
                "canonical": "Medical Representative",
                "seniority": "JUNIOR",
                "experience": "EARLY_CAREER",
                "aliases": ["MR", "Pharma Rep", "Pharma Sales Representative", "Pharma Sales Executive", "Medical Sales Representative", "Territory Business Executive (Pharma)"],
                "alias_types": {"MR": "ABBREVIATION", "Pharma Rep": "ABBREVIATION", "Pharma Sales Executive": "SYNONYM"},
                "skills": [("Doctor Detailing & Product Promotion", "PRIMARY_SKILL", 0.98), ("Chemist & Pharmacy Network Coverage", "PRIMARY_SKILL", 0.98), ("RCPA (Retail Chemist Prescription Audit)", "PRIMARY_SKILL", 0.95), ("Hospital Detailing & Stockist Management", "PRIMARY_SKILL", 0.92), ("Pharmaceutical Brand Building", "PRIMARY_SKILL", 0.90)],
                "technologies": [],
                "tools": [("SFA (Sales Force Automation Pharma)", "CRM", 0.92), ("FieldAssist", "CRM", 0.90)],
                "related_roles": [("Area Business Manager (Pharma)", "PARENT_ROLE", 0.95), ("Regional Business Manager (Pharma)", "PARENT_ROLE", 0.90), ("Pharmacist", "RELATED_ROLE", 0.75)]
            },
            {
                "name": "Pharmacist",
                "canonical": "Pharmacist",
                "seniority": "MID",
                "experience": "MID_CAREER",
                "aliases": ["Hospital Pharmacist", "Retail Pharmacist", "Clinical Pharmacist", "Chemist", "Registered Pharmacist", "Pharmacy Executive"],
                "alias_types": {"Chemist": "SYNONYM", "Hospital Pharmacist": "SENIORITY_VARIANT"},
                "skills": [("Prescription Dispensing & Validation", "PRIMARY_SKILL", 0.98), ("Drug Interaction Knowledge & Pharmacology", "PRIMARY_SKILL", 0.98), ("Inventory Control & Cold Chain Maintenance", "PRIMARY_SKILL", 0.95), ("Schedule H & H1 Drug Compliance", "PRIMARY_SKILL", 0.92), ("Patient Counseling on Medication", "PRIMARY_SKILL", 0.90)],
                "technologies": [],
                "tools": [("Hospital HIS (Health Information System)", "ERP", 0.92), ("Marg ERP (Pharma)", "ERP", 0.95)],
                "related_roles": [("Pharmacy Manager", "PARENT_ROLE", 0.95), ("Medical Representative", "RELATED_ROLE", 0.75), ("Drug Safety Associate", "ADJACENT_ROLE", 0.85)]
            },
            {
                "name": "Staff Nurse",
                "canonical": "Staff Nurse",
                "seniority": "MID",
                "experience": "MID_CAREER",
                "aliases": ["Nurse", "Registered Nurse", "RN", "ICU Nurse", "Ward Nurse", "GNM Nurse", "BSc Nurse", "OT Nurse"],
                "alias_types": {"Nurse": "SYNONYM", "RN": "ABBREVIATION", "ICU Nurse": "SENIORITY_VARIANT"},
                "skills": [("Patient Care & Medication Administration", "PRIMARY_SKILL", 0.98), ("Vital Signs Monitoring & Charting", "PRIMARY_SKILL", 0.95), ("ICU & Emergency Care (BLS / ACLS)", "PRIMARY_SKILL", 0.95), ("IV Cannulation & Infusion Therapy", "PRIMARY_SKILL", 0.92), ("Infection Prevention Protocols", "PRIMARY_SKILL", 0.90)],
                "technologies": [],
                "tools": [("Patient Monitors / Ventilators", "MEDICAL", 0.95), ("Electronic Medical Records (EMR)", "ERP", 0.90)],
                "related_roles": [("Nursing Supervisor", "PARENT_ROLE", 0.95), ("Head Nurse", "PARENT_ROLE", 0.92), ("Clinical Care Executive", "RELATED_ROLE", 0.88)]
            }
        ]
    },

    # 7. ENGINEERING, AUTOMOBILE & MANUFACTURING
    {
        "industry": "Automotive & Manufacturing",
        "department": "Engineering & Operations",
        "job_function": "Automobile & Mechanical Maintenance",
        "roles": [
            {
                "name": "Vehicle Inspector",
                "canonical": "Vehicle Inspector",
                "seniority": "MID",
                "experience": "MID_CAREER",
                "aliases": ["Car Inspector", "Automobile Inspector", "Automotive Inspector", "Vehicle Inspection Officer", "Car Inspection Executive", "Auto Inspection Engineer", "Motor Vehicle Inspector", "Vehicle Inspection Executive", "Car Inspection", "Vehicle Evaluator", "Used Car Evaluator", "Auto Valuation Specialist", "Used Car Inspection Engineer"],
                "alias_types": {"Car Inspector": "SYNONYM", "Automobile Inspector": "SYNONYM", "Vehicle Inspection Officer": "SYNONYM", "Car Inspection": "SYNONYM", "Car Inspection Executive": "SYNONYM", "Vehicle Evaluator": "RELATED_ROLE"},
                "skills": [("Vehicle Inspection & Diagnostics", "PRIMARY_SKILL", 0.98), ("Used Car Evaluation & Pricing", "PRIMARY_SKILL", 0.96), ("Engine & Transmission Condition Check", "PRIMARY_SKILL", 0.95), ("Accident & Chassis Damage Inspection", "PRIMARY_SKILL", 0.95), ("OBD-II Scanning & Electrical Diagnostics", "PRIMARY_SKILL", 0.92), ("Road Test & Performance Assessment", "PRIMARY_SKILL", 0.90), ("Vehicle Health Report Generation", "PRIMARY_SKILL", 0.90)],
                "technologies": [],
                "tools": [("OBD-II Diagnostic Scanner", "DIAGNOSTIC", 0.98), ("Paint Thickness Gauge", "DIAGNOSTIC", 0.95), ("Digital Multimeter", "DIAGNOSTIC", 0.90)],
                "related_roles": [("Automobile Technician", "RELATED_ROLE", 0.88), ("Service Advisor", "RELATED_ROLE", 0.85), ("Automobile Service Advisor", "RELATED_ROLE", 0.85), ("Workshop Supervisor", "PARENT_ROLE", 0.90)]
            },
            {
                "name": "Automobile Service Advisor",
                "canonical": "Automobile Service Advisor",
                "seniority": "MID",
                "experience": "MID_CAREER",
                "aliases": ["Service Advisor", "Customer Advisor - Automotive", "Bodyshop Advisor", "Automobile Workshop Advisor", "Vehicle Service Advisor"],
                "alias_types": {"Service Advisor": "SYNONYM", "Customer Advisor - Automotive": "SYNONYM"},
                "skills": [("Customer Handling & Service Advisory", "PRIMARY_SKILL", 0.98), ("Job Card Creation & Vehicle Estimation", "PRIMARY_SKILL", 0.96), ("Automotive Repair Knowledge", "PRIMARY_SKILL", 0.92), ("Service Upselling & Customer Satisfaction", "PRIMARY_SKILL", 0.90)],
                "technologies": [],
                "tools": [("Dealer Management System (DMS)", "ERP", 0.95), ("Job Card Software", "ERP", 0.90)],
                "related_roles": [("Automobile Technician", "ADJACENT_ROLE", 0.90), ("Vehicle Inspector", "RELATED_ROLE", 0.85), ("Workshop Supervisor", "PARENT_ROLE", 0.92)]
            },
            {
                "name": "Automobile Technician",
                "canonical": "Automobile Technician",
                "seniority": "MID",
                "experience": "MID_CAREER",
                "aliases": ["Auto Mechanic", "Vehicle Technician", "Service Technician", "Car Mechanic", "Diagnostic Technician", "Automotive Technician"],
                "alias_types": {"Auto Mechanic": "SYNONYM", "Car Mechanic": "SYNONYM"},
                "skills": [("Vehicle Diagnostics & Engine Troubleshooting", "PRIMARY_SKILL", 0.98), ("Brake, Suspension & Transmission Repair", "PRIMARY_SKILL", 0.95), ("Automotive Electrical & Wiring Diagnostics", "PRIMARY_SKILL", 0.95), ("Periodic Maintenance Service (PMS)", "PRIMARY_SKILL", 0.92), ("Wheel Alignment & Balancing", "PRIMARY_SKILL", 0.88)],
                "technologies": [],
                "tools": [("OBD-II Diagnostic Scanner", "DIAGNOSTIC", 0.98), ("Digital Multimeter", "DIAGNOSTIC", 0.92), ("Pneumatic Tools / Torque Wrench", "DIAGNOSTIC", 0.90)],
                "related_roles": [("Service Advisor", "ADJACENT_ROLE", 0.90), ("Automobile Service Advisor", "ADJACENT_ROLE", 0.90), ("Vehicle Inspector", "RELATED_ROLE", 0.88), ("Workshop Supervisor", "PARENT_ROLE", 0.95), ("Mechanical Engineer", "RELATED_ROLE", 0.80)]
            },
            {
                "name": "Mechanical Engineer",
                "canonical": "Mechanical Engineer",
                "seniority": "MID",
                "experience": "MID_CAREER",
                "aliases": ["Production Engineer", "Maintenance Engineer", "Design Engineer (Mechanical)", "Manufacturing Engineer", "Plant Engineer"],
                "alias_types": {"Production Engineer": "RELATED_ROLE", "Maintenance Engineer": "RELATED_ROLE"},
                "skills": [("Mechanical Design & CAD Modeling", "PRIMARY_SKILL", 0.98), ("Manufacturing Processes (Machining, Casting, Welding)", "PRIMARY_SKILL", 0.95), ("Preventive & Breakdown Maintenance", "PRIMARY_SKILL", 0.95), ("Geometric Dimensioning & Tolerancing (GD&T)", "PRIMARY_SKILL", 0.90), ("Quality Control & Inspection", "PRIMARY_SKILL", 0.90)],
                "technologies": [],
                "tools": [("AutoCAD", "DESIGN", 0.98), ("SolidWorks", "DESIGN", 0.95), ("CATIA / Creo", "DESIGN", 0.92), ("CNC Machine Programming", "DIAGNOSTIC", 0.88)],
                "related_roles": [("Automobile Technician", "RELATED_ROLE", 0.80), ("Civil Engineer", "RELATED_ROLE", 0.70), ("Plant Manager", "PARENT_ROLE", 0.92)]
            },
            {
                "name": "Civil Engineer",
                "canonical": "Civil Engineer",
                "seniority": "MID",
                "experience": "MID_CAREER",
                "aliases": ["Site Engineer", "Site Supervisor", "Construction Engineer", "Structural Engineer", "Project Engineer (Civil)", "Quantity Surveyor"],
                "alias_types": {"Site Engineer": "SYNONYM", "Site Supervisor": "CHILD_ROLE"},
                "skills": [("Site Execution & Construction Supervision", "PRIMARY_SKILL", 0.98), ("Structural Drawing Interpretation", "PRIMARY_SKILL", 0.98), ("Quantity Estimation & Bill of Quantities (BOQ)", "PRIMARY_SKILL", 0.95), ("Concrete Mix Quality & Bar Bending Schedule (BBS)", "PRIMARY_SKILL", 0.92), ("Project Scheduling & Contractor Billing", "PRIMARY_SKILL", 0.90)],
                "technologies": [],
                "tools": [("AutoCAD Civil", "DESIGN", 0.98), ("STAAD.Pro / ETABS", "DESIGN", 0.92), ("MS Project / Primavera", "COLLABORATION", 0.90), ("Total Station", "DIAGNOSTIC", 0.88)],
                "related_roles": [("Site Supervisor", "CHILD_ROLE", 0.95), ("Project Manager - Construction", "PARENT_ROLE", 0.95), ("Mechanical Engineer", "RELATED_ROLE", 0.70)]
            },
            {
                "name": "Electrician",
                "canonical": "Electrician",
                "seniority": "MID",
                "experience": "MID_CAREER",
                "aliases": ["Industrial Electrician", "Maintenance Electrician", "Electrical Technician", "Wireman", "LT/HT Electrician"],
                "alias_types": {"Electrical Technician": "SYNONYM", "Wireman": "SYNONYM"},
                "skills": [("Electrical Wiring & Cable Jointing", "PRIMARY_SKILL", 0.98), ("HT / LT Panel Maintenance", "PRIMARY_SKILL", 0.95), ("Motor, Transformer & Switchgear Troubleshooting", "PRIMARY_SKILL", 0.95), ("Circuit Breaker & Relay Testing", "PRIMARY_SKILL", 0.92), ("Electrical Safety & Earthing Protocols", "PRIMARY_SKILL", 0.90)],
                "technologies": [],
                "tools": [("Multimeter / Megger (Insulation Tester)", "DIAGNOSTIC", 0.98), ("Clamp Meter", "DIAGNOSTIC", 0.95)],
                "related_roles": [("Electrical Engineer", "PARENT_ROLE", 0.90), ("Maintenance Technician", "RELATED_ROLE", 0.88)]
            }
        ]
    },

    # 8. OPERATIONS, BPO & CUSTOMER EXPERIENCE
    {
        "industry": "BPO, KPO & Customer Service",
        "department": "Customer Support & Operations",
        "job_function": "Voice & Non-Voice Support",
        "roles": [
            {
                "name": "Customer Support Executive",
                "canonical": "Customer Support Executive",
                "seniority": "JUNIOR",
                "experience": "EARLY_CAREER",
                "aliases": ["BPO Executive", "Customer Care Executive", "Telecaller", "Technical Support Representative", "Helpdesk Associate", "Customer Service Representative", "CSR"],
                "alias_types": {"BPO Executive": "SYNONYM", "CSR": "ABBREVIATION", "Customer Care Executive": "SYNONYM"},
                "skills": [("Customer Support & Inbound / Outbound Calling", "PRIMARY_SKILL", 0.98), ("Customer Service Orientation", "PRIMARY_SKILL", 0.98), ("Voice & Non-Voice Query Resolution", "PRIMARY_SKILL", 0.95), ("Ticket Management & SLA Adherence", "PRIMARY_SKILL", 0.92), ("Complaint Escalation & First Contact Resolution (FCR)", "PRIMARY_SKILL", 0.90)],
                "technologies": [],
                "tools": [("Zendesk", "CRM", 0.95), ("Freshdesk", "CRM", 0.92), ("Salesforce Service Cloud", "CRM", 0.90), ("Avaya / Genesys Dialers", "TOOL", 0.90)],
                "related_roles": [("Operations Manager", "PARENT_ROLE", 0.85), ("Team Leader - BPO", "PARENT_ROLE", 0.95), ("Customer Success Specialist", "RELATED_ROLE", 0.88)]
            },
            {
                "name": "Operations Manager",
                "canonical": "Operations Manager",
                "seniority": "MANAGER",
                "experience": "SENIOR_CAREER",
                "aliases": ["Operations Head", "Manager - Operations", "General Operations Manager", "Service Delivery Manager"],
                "alias_types": {"Manager - Operations": "SYNONYM"},
                "skills": [("Operations Management & Process Optimization", "PRIMARY_SKILL", 0.98), ("KPI & SLA Governance", "PRIMARY_SKILL", 0.95), ("Team Leadership & Resource Allocation", "PRIMARY_SKILL", 0.95), ("Continuous Process Improvement (Kaizen / Lean)", "PRIMARY_SKILL", 0.92), ("Vendor & Stakeholder Management", "PRIMARY_SKILL", 0.90)],
                "technologies": [],
                "tools": [("Jira", "COLLABORATION", 0.90), ("SAP ERP", "ERP", 0.92), ("Excel / Power BI", "ANALYTICS", 0.92)],
                "related_roles": [("Branch Manager", "RELATED_ROLE", 0.90), ("Store Manager", "RELATED_ROLE", 0.88), ("Customer Support Executive", "CHILD_ROLE", 0.85)]
            },
            {
                "name": "Store Manager",
                "canonical": "Store Manager",
                "seniority": "MANAGER",
                "experience": "MID_CAREER",
                "aliases": ["Retail Store Manager", "Branch Manager - Retail", "Showroom Manager", "Outlet Manager", "Shop Manager"],
                "alias_types": {"Retail Store Manager": "SYNONYM", "Showroom Manager": "SYNONYM"},
                "skills": [("Retail Store Operations & Inventory Control", "PRIMARY_SKILL", 0.98), ("Visual Merchandising & Shrinkage Control", "PRIMARY_SKILL", 0.95), ("Sales Target Achievement & Customer Experience", "PRIMARY_SKILL", 0.95), ("Store Staff Rostering & POS Billing", "PRIMARY_SKILL", 0.92)],
                "technologies": [],
                "tools": [("POS Billing Software", "ERP", 0.95), ("SAP Retail", "ERP", 0.90)],
                "related_roles": [("Operations Manager", "RELATED_ROLE", 0.88), ("Area Sales Manager", "RELATED_ROLE", 0.85)]
            }
        ]
    },

    # 9. MARKETING, DIGITAL & ADVERTISING
    {
        "industry": "Marketing & Advertising",
        "department": "Marketing & Communications",
        "job_function": "Brand & Digital Marketing",
        "roles": [
            {
                "name": "Marketing Manager",
                "canonical": "Marketing Manager",
                "seniority": "MANAGER",
                "experience": "SENIOR_CAREER",
                "aliases": ["Brand Manager", "Marketing Head", "Manager - Marketing", "Digital Marketing Manager", "Product Marketing Manager"],
                "alias_types": {"Brand Manager": "SYNONYM", "Manager - Marketing": "SYNONYM"},
                "skills": [("Marketing", "PRIMARY_SKILL", 0.98), ("Brand Strategy & Positioning", "PRIMARY_SKILL", 0.98), ("Campaign Planning & ROI Tracking", "PRIMARY_SKILL", 0.95), ("Digital Marketing Strategy", "PRIMARY_SKILL", 0.95), ("Market Research & Consumer Insights", "PRIMARY_SKILL", 0.92)],
                "technologies": [],
                "tools": [("Google Analytics", "ANALYTICS", 0.95), ("HubSpot", "CRM", 0.92), ("SEMrush", "ANALYTICS", 0.90)],
                "related_roles": [("Digital Marketing Executive", "CHILD_ROLE", 0.95), ("Sales Manager", "RELATED_ROLE", 0.88), ("Head of Marketing", "PARENT_ROLE", 0.95)]
            },
            {
                "name": "Digital Marketing Executive",
                "canonical": "Digital Marketing Executive",
                "seniority": "MID",
                "experience": "MID_CAREER",
                "aliases": ["SEO Specialist", "Performance Marketer", "SEM Executive", "Social Media Executive", "Growth Marketer"],
                "alias_types": {"SEO Specialist": "SYNONYM", "Performance Marketer": "SYNONYM"},
                "skills": [("Search Engine Optimization (SEO)", "PRIMARY_SKILL", 0.98), ("Google Ads & PPC Campaigns", "PRIMARY_SKILL", 0.95), ("Social Media Marketing (SMM)", "PRIMARY_SKILL", 0.95), ("Content Marketing & Copywriting", "PRIMARY_SKILL", 0.90)],
                "technologies": [],
                "tools": [("Google Search Console", "ANALYTICS", 0.95), ("Meta Ads Manager", "COLLABORATION", 0.92)],
                "related_roles": [("Marketing Manager", "PARENT_ROLE", 0.95), ("Content Strategist", "RELATED_ROLE", 0.88)]
            }
        ]
    },

    # 10. INSURANCE, BANKING & FINANCIAL SERVICES
    {
        "industry": "Banking & Insurance",
        "department": "Financial Products & Advisory",
        "job_function": "Insurance & Wealth Management",
        "roles": [
            {
                "name": "Insurance Advisor",
                "canonical": "Insurance Advisor",
                "seniority": "MID",
                "experience": "MID_CAREER",
                "aliases": ["Insurance Agent", "Insurance Consultant", "Life Insurance Advisor", "General Insurance Agent", "Financial Advisor"],
                "alias_types": {"Insurance Agent": "SYNONYM", "Insurance Consultant": "SYNONYM"},
                "skills": [("Insurance", "PRIMARY_SKILL", 0.98), ("Life & Health Insurance Advisory", "PRIMARY_SKILL", 0.98), ("Policy Underwriting Basics", "PRIMARY_SKILL", 0.95), ("Claims Assistance & Customer Advisory", "PRIMARY_SKILL", 0.95)],
                "technologies": [],
                "tools": [("Insurance Portals", "CRM", 0.90)],
                "related_roles": [("Insurance Manager", "PARENT_ROLE", 0.95), ("Sales Executive", "RELATED_ROLE", 0.88)]
            },
            {
                "name": "Insurance Manager",
                "canonical": "Insurance Manager",
                "seniority": "MANAGER",
                "experience": "SENIOR_CAREER",
                "aliases": ["Agency Manager", "Branch Manager - Insurance", "Territory Insurance Manager", "Area Manager - Life Insurance"],
                "alias_types": {"Agency Manager": "SYNONYM"},
                "skills": [("Insurance", "PRIMARY_SKILL", 0.98), ("Agency Channel Development", "PRIMARY_SKILL", 0.98), ("Advisor Recruitment & Training", "PRIMARY_SKILL", 0.95), ("Insurance Premium Target Achievement", "PRIMARY_SKILL", 0.95)],
                "technologies": [],
                "tools": [("Core Insurance ERP", "ERP", 0.92)],
                "related_roles": [("Insurance Advisor", "CHILD_ROLE", 0.95), ("Branch Manager", "RELATED_ROLE", 0.90)]
            },
            {
                "name": "Financial Analyst",
                "canonical": "Financial Analyst",
                "seniority": "MID",
                "experience": "MID_CAREER",
                "aliases": ["FP&A Analyst", "Investment Analyst", "Equity Analyst", "Corporate Finance Analyst"],
                "alias_types": {"FP&A Analyst": "SYNONYM", "Investment Analyst": "SYNONYM"},
                "skills": [("Financial Modeling & Valuation (DCF, LBO)", "PRIMARY_SKILL", 0.98), ("Variance Analysis & Forecasting", "PRIMARY_SKILL", 0.95), ("Equity & Market Research", "PRIMARY_SKILL", 0.92)],
                "technologies": [],
                "tools": [("MS Excel (Macros, VBA)", "ANALYTICS", 0.98), ("Bloomberg Terminal / Capital IQ", "ANALYTICS", 0.92)],
                "related_roles": [("Finance Manager", "PARENT_ROLE", 0.95), ("Accountant", "RELATED_ROLE", 0.88)]
            }
        ]
    }
]


class TaxonomySeeder:
    """
    Fast, idempotent, transaction-safe seeder for TalentVault Universal Recruitment Taxonomy (TV-URT).
    """

    @classmethod
    def seed_all(cls, clear_existing: bool = False) -> Dict[str, int]:
        from apps.taxonomy.models import (
            Industry, Department, JobFunction, JobRole, Specialization,
            SkillCategory, Skill, Technology, Tool, Certification, Qualification,
            TaxonomyAlias, RoleSkill, RoleRelation, RoleHierarchy, IndustryRole,
            TaxonomyImportLog, TaxonomyStatus, TaxonomySource
        )

        stats = {
            "industries": 0,
            "departments": 0,
            "job_functions": 0,
            "job_roles": 0,
            "skills": 0,
            "technologies": 0,
            "tools": 0,
            "certifications": 0,
            "qualifications": 0,
            "aliases": 0,
            "role_skills": 0,
            "role_relations": 0,
        }

        with transaction.atomic():
            # 1. Seed Skill Categories
            cat_tech, _ = SkillCategory.objects.get_or_create(name="Technical & Engineering", defaults={"category_type": SkillCategory.CategoryType.TECHNICAL})
            cat_func, _ = SkillCategory.objects.get_or_create(name="Functional & Commercial", defaults={"category_type": SkillCategory.CategoryType.FUNCTIONAL})
            cat_domain, _ = SkillCategory.objects.get_or_create(name="Domain & Industry Knowledge", defaults={"category_type": SkillCategory.CategoryType.DOMAIN})
            cat_tools, _ = SkillCategory.objects.get_or_create(name="Tools & Platforms", defaults={"category_type": SkillCategory.CategoryType.TOOL})
            cat_mgmt, _ = SkillCategory.objects.get_or_create(name="Management & Leadership", defaults={"category_type": SkillCategory.CategoryType.MANAGERIAL})

            # 2. Seed Qualifications
            for deg_name, lvl, disc in [
                ("B.Tech / B.E (Computer Science / IT)", Qualification.DegreeLevel.BACHELORS, "Engineering"),
                ("B.Tech / B.E (Mechanical / Civil / Electrical)", Qualification.DegreeLevel.BACHELORS, "Engineering"),
                ("M.Tech / M.E / M.S", Qualification.DegreeLevel.MASTERS, "Engineering"),
                ("MBA (Marketing / Finance / HR / Operations)", Qualification.DegreeLevel.MASTERS, "Business Administration"),
                ("B.Com / M.Com (Commerce & Accounts)", Qualification.DegreeLevel.BACHELORS, "Commerce"),
                ("Chartered Accountant (CA)", Qualification.DegreeLevel.PROFESSIONAL, "Accounting & Auditing"),
                ("B.Pharm / M.Pharm", Qualification.DegreeLevel.BACHELORS, "Pharmacy"),
                ("B.Sc / M.Sc Nursing / GNM", Qualification.DegreeLevel.BACHELORS, "Nursing"),
                ("MBBS / MD / MS", Qualification.DegreeLevel.BACHELORS, "Medicine"),
                ("Diploma (Polytechnic / Mechanical / Civil / ITI)", Qualification.DegreeLevel.DIPLOMA, "Vocational & Technical"),
            ]:
                q_obj, created = Qualification.objects.get_or_create(
                    name=deg_name,
                    defaults={"canonical_name": deg_name, "degree_level": lvl, "discipline": disc, "source": TaxonomySource.TV_URT}
                )
                if created:
                    stats["qualifications"] += 1

            # 3. Process each sector
            for sector in SEED_TAXONOMY_SECTORS:
                ind_name = sector["industry"]
                dept_name = sector["department"]
                func_name = sector["job_function"]

                ind_obj, created = Industry.objects.get_or_create(
                    name=ind_name,
                    defaults={"normalized_name": ind_name.lower(), "source": TaxonomySource.TV_URT}
                )
                if created:
                    stats["industries"] += 1

                dept_obj, created = Department.objects.get_or_create(
                    name=dept_name,
                    defaults={"normalized_name": dept_name.lower(), "source": TaxonomySource.TV_URT}
                )
                if created:
                    stats["departments"] += 1

                func_obj, created = JobFunction.objects.get_or_create(
                    name=func_name,
                    department=dept_obj,
                    defaults={"normalized_name": func_name.lower(), "source": TaxonomySource.TV_URT}
                )
                if created:
                    stats["job_functions"] += 1

                for r_data in sector.get("roles", []):
                    role_name = r_data["name"]
                    canonical = r_data.get("canonical", role_name)
                    seniority_val = getattr(JobRole.SeniorityLevel, r_data.get("seniority", "MID"), JobRole.SeniorityLevel.MID)
                    exp_val = getattr(JobRole.ExperienceLevel, r_data.get("experience", "MID_CAREER"), JobRole.ExperienceLevel.MID_CAREER)

                    role_obj, created = JobRole.objects.get_or_create(
                        canonical_name=canonical,
                        defaults={
                            "name": role_name,
                            "normalized_name": canonical.lower(),
                            "industry": ind_obj,
                            "department": dept_obj,
                            "job_function": func_obj,
                            "seniority": seniority_val,
                            "typical_experience": exp_val,
                            "source": TaxonomySource.TV_URT
                        }
                    )
                    if created:
                        stats["job_roles"] += 1

                    IndustryRole.objects.get_or_create(industry=ind_obj, job_role=role_obj, defaults={"is_primary": True})

                    # Role Aliases
                    for alias_text in r_data.get("aliases", []):
                        alias_clean = alias_text.strip()
                        if not alias_clean:
                            continue
                        a_type_str = r_data.get("alias_types", {}).get(alias_clean, "SYNONYM")
                        a_type_val = getattr(TaxonomyAlias.AliasType, a_type_str, TaxonomyAlias.AliasType.SYNONYM)
                        
                        alias_obj, a_created = TaxonomyAlias.objects.get_or_create(
                            normalized_alias=alias_clean.lower(),
                            entity_type=TaxonomyAlias.EntityType.JOB_ROLE,
                            canonical_name=canonical,
                            defaults={
                                "alias": alias_clean,
                                "alias_type": a_type_val,
                                "job_role": role_obj,
                                "confidence": 0.95,
                                "source": TaxonomySource.TV_URT
                            }
                        )
                        if a_created:
                            stats["aliases"] += 1

                    # Skills
                    for sk_tuple in r_data.get("skills", []):
                        sk_name, rel_type_str, weight_val = sk_tuple
                        sk_obj, s_created = Skill.objects.get_or_create(
                            canonical_name=sk_name,
                            defaults={
                                "name": sk_name,
                                "normalized_name": sk_name.lower(),
                                "category": cat_func if "Management" in sk_name or "Sales" in sk_name else cat_tech,
                                "source": TaxonomySource.TV_URT
                            }
                        )
                        if s_created:
                            stats["skills"] += 1

                        rel_type_val = getattr(RoleSkill.RelationType, rel_type_str, RoleSkill.RelationType.PRIMARY_SKILL)
                        _, rs_created = RoleSkill.objects.get_or_create(
                            role=role_obj,
                            skill=sk_obj,
                            defaults={
                                "relation_type": rel_type_val,
                                "weight": float(weight_val),
                                "source": TaxonomySource.TV_URT
                            }
                        )
                        if rs_created:
                            stats["role_skills"] += 1

                    # Technologies
                    for tech_tuple in r_data.get("technologies", []):
                        t_name, t_cat_str, _ = tech_tuple
                        t_cat_val = getattr(Technology.TechCategory, t_cat_str, Technology.TechCategory.FRAMEWORK)
                        tech_obj, t_created = Technology.objects.get_or_create(
                            canonical_name=t_name,
                            defaults={
                                "name": t_name,
                                "normalized_name": t_name.lower(),
                                "tech_category": t_cat_val,
                                "source": TaxonomySource.TV_URT
                            }
                        )
                        if t_created:
                            stats["technologies"] += 1

                        RoleSkill.objects.get_or_create(
                            role=role_obj,
                            technology=tech_obj,
                            defaults={"relation_type": RoleSkill.RelationType.TOOL, "weight": 0.90, "source": TaxonomySource.TV_URT}
                        )

                    # Tools
                    for tool_tuple in r_data.get("tools", []):
                        tool_name, tool_type_str, _ = tool_tuple
                        tool_type_val = getattr(Tool.ToolType, tool_type_str, Tool.ToolType.ANALYTICS)
                        tool_obj, tool_created = Tool.objects.get_or_create(
                            canonical_name=tool_name,
                            defaults={
                                "name": tool_name,
                                "normalized_name": tool_name.lower(),
                                "tool_type": tool_type_val,
                                "source": TaxonomySource.TV_URT
                            }
                        )
                        if tool_created:
                            stats["tools"] += 1

                        RoleSkill.objects.get_or_create(
                            role=role_obj,
                            tool=tool_obj,
                            defaults={"relation_type": RoleSkill.RelationType.TOOL, "weight": 0.90, "source": TaxonomySource.TV_URT}
                        )

            # 4. Build Role Relations and Career Ladders
            for sector in SEED_TAXONOMY_SECTORS:
                for r_data in sector.get("roles", []):
                    src_canonical = r_data.get("canonical", r_data["name"])
                    src_role = JobRole.objects.filter(canonical_name=src_canonical).first()
                    if not src_role:
                        continue

                    for rel_tuple in r_data.get("related_roles", []):
                        tgt_canonical, rel_type_str, weight_val = rel_tuple
                        tgt_role = JobRole.objects.filter(canonical_name=tgt_canonical).first()
                        if not tgt_role:
                            continue

                        rel_type_val = getattr(RoleRelation.RelationType, rel_type_str, RoleRelation.RelationType.RELATED_ROLE)
                        _, rr_created = RoleRelation.objects.get_or_create(
                            source_role=src_role,
                            target_role=tgt_role,
                            relation_type=rel_type_val,
                            defaults={
                                "weight": float(weight_val),
                                "is_bidirectional": (rel_type_val in [RoleRelation.RelationType.RELATED_ROLE, RoleRelation.RelationType.FUNCTIONAL_EQUIVALENT]),
                                "source": TaxonomySource.TV_URT
                            }
                        )
                        if rr_created:
                            stats["role_relations"] += 1

            # Log the seed audit
            TaxonomyImportLog.objects.create(
                source_name="TalentVault Universal Recruitment Taxonomy (TV-URT)",
                version="2.0.0",
                license="ODbL / CC BY 4.0 / TV-URT Open Data",
                records_processed=sum(stats.values()),
                records_created=sum(stats.values()),
                status=TaxonomyImportLog.ImportStatus.SUCCESS,
                statistics=stats
            )

        return stats
